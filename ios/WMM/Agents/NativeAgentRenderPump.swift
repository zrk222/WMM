import AVFoundation
import Foundation

/// Executes only an admitted, persisted native render intent. Models never supply
/// a local path, decoder proof or host completion action.
@MainActor
final class NativeAgentRenderPump {
    private let bridge: DomainBridge
    private let session: LocalIdentity.Session
    private let scene = NativeStudioRenderer()
    private let timeline = TimelineRenderer()
    private var stopped = false
    init(bridge: DomainBridge, session: LocalIdentity.Session) { self.bridge = bridge; self.session = session }
    func cancel() async { stopped = true; scene.cancel(); await timeline.cancel() }

    func complete(request: Data, response: Data, reviewed: Bool = false) async throws -> Data {
        guard !stopped,
              var output = try JSONSerialization.jsonObject(with: response) as? [String: Any] else { return response }
        let envelope: [String: Any]?
        let prepared: [String: Any]?
        if reviewed {
            envelope = output["envelope"] as? [String: Any]
            let receipt = output["result"] as? [String: Any]
            prepared = receipt?["outcome"] as? String == "SUCCEEDED" ? receipt?["data"] as? [String: Any] : nil
        } else {
            envelope = try JSONSerialization.jsonObject(with: request) as? [String: Any]
            prepared = output
        }
        guard let envelope, let appID = envelope["app_id"] as? String,
              let operation = envelope["operation"] as? String,
              ["ios.scene.start", "ios.timeline.queue"].contains(operation), let prepared,
              let job = prepared["job"] as? [String: Any], let jobID = job["job_id"] as? String,
              let packet = prepared["packet"] as? [String: Any], packet["app_id"] as? String == appID else { return response }
        do {
            let proof = operation == "ios.scene.start"
                ? try await renderScene(appID: appID, jobID: jobID, packet: packet)
                : try await renderTimeline(appID: appID, jobID: jobID, packet: packet)
            guard !stopped else { throw DomainBridge.Failure.closed }
            output["native_render"] = try JSONSerialization.jsonObject(with: proof)
        } catch {
            // Retain the saved intent identity. A finish may already have committed;
            // callers inspect it before any retry rather than inventing failure.
            output["native_render"] = ["job_id": jobID, "status": "RECONCILE_REQUIRED"]
        }
        return try JSONSerialization.data(withJSONObject: output, options: [.sortedKeys])
    }

    private func renderScene(appID: String, jobID: String, packet: [String: Any]) async throws -> Data {
        let saved = try await bridge.studio(session: session, appID: appID, action: "inspect", body: ["job_id": jobID])
        if let job = try JSONSerialization.jsonObject(with: saved) as? [String: Any],
           let status = job["status"] as? String, ["SUCCEEDED", "CANCELLED"].contains(status) { return saved }
        let plan = try JSONDecoder().decode(NativeStudioPacket.self, from: JSONSerialization.data(withJSONObject: packet))
        try plan.validateBounds()
        let destination = try await bridge.studioDestination(jobID: jobID)
        func validate() async throws {
            guard !stopped else { throw DomainBridge.Failure.closed }
            _ = try await bridge.studio(session: session, appID: appID, action: "validate", body: ["job_id": jobID, "packet_hash": plan.packet_hash])
        }
        try await validate()
        if FileManager.default.fileExists(atPath: destination.path) {
            try await checkCadence(destination, expectedFrames: plan.frame_count)
            _ = try await bridge.finishStudio(session: session, appID: appID, jobID: jobID, packetHash: plan.packet_hash, output: destination)
        } else {
            _ = try await scene.render(plan, destination: destination, resolve: { source in
                try await self.bridge.studioSource(session: self.session, appID: appID, jobID: jobID,
                    packetHash: plan.packet_hash, mediaID: source.id, sha256: source.sha256)
            }, validate: validate, finish: { output in
                try await self.checkCadence(output, expectedFrames: plan.frame_count)
                _ = try await self.bridge.finishStudio(session: self.session, appID: appID, jobID: jobID, packetHash: plan.packet_hash, output: output)
            })
        }
        return try await bridge.studio(session: session, appID: appID, action: "inspect", body: ["job_id": jobID])
    }

    private func renderTimeline(appID: String, jobID: String, packet: [String: Any]) async throws -> Data {
        let saved = try await bridge.agentTimeline(session: session, appID: appID, action: "inspect", body: ["job_id": jobID])
        if let job = try JSONSerialization.jsonObject(with: saved) as? [String: Any],
           let status = job["status"] as? String, ["SUCCEEDED", "CANCELLED"].contains(status) { return saved }
        let prepared = try JSONDecoder().decode(DomainBridge.ProductionPacket.self, from: JSONSerialization.data(withJSONObject: packet))
        guard prepared.schema == "growth.ios-production-packet.v1", prepared.app_id == appID,
              prepared.status == "PREPARED_NOT_RENDERED", !prepared.execution_authority else { throw DomainBridge.Failure.invalidRequest }
        try prepared.plan.validateBounds()
        let destination = try await bridge.agentTimelineDestination(jobID: jobID)
        func validate() async throws {
            guard !stopped else { throw DomainBridge.Failure.closed }
            _ = try await bridge.agentTimeline(session: session, appID: appID, action: "validate", body: ["job_id": jobID, "packet_hash": prepared.packet_hash])
        }
        try await validate()
        if !FileManager.default.fileExists(atPath: destination.path) {
            _ = try await timeline.render(prepared.plan, destination: destination, resolve: { source in
                try await self.bridge.agentTimelineSource(session: self.session, appID: appID, jobID: jobID, packetHash: prepared.packet_hash, source: source)
            }, validateAuthority: validate)
        } else {
            var expectsAudio = false
            for clip in prepared.plan.clips where clip.audio == "RETAIN" {
                let source = try await bridge.agentTimelineSource(session: session, appID: appID,
                    jobID: jobID, packetHash: prepared.packet_hash, source: clip.source)
                if !(try await AVURLAsset(url: source).loadTracks(withMediaType: .audio)).isEmpty { expectsAudio = true }
            }
            try await MediaInspector.verify(destination, plan: prepared.plan,
                expectsAudio: expectsAudio)
        }
        try await checkCadence(destination, expectedFrames: prepared.plan.output_frame_count)
        _ = try await bridge.finishAgentTimeline(session: session, appID: appID, jobID: jobID, packetHash: prepared.packet_hash, output: destination)
        return try await bridge.agentTimeline(session: session, appID: appID, action: "inspect", body: ["job_id": jobID])
    }

    private func checkCadence(_ url: URL, expectedFrames: Int) async throws {
        let bytes = try await MediaInspector.inspectOriginal(url)
        guard let inspected = try JSONSerialization.jsonObject(with: bytes) as? [String: Any],
              let metadata = inspected["metadata"] as? [String: Any],
              let decoded = inspected["decoded"] as? [String: Any],
              let duration = metadata["duration_seconds"] as? Double,
              let rate = metadata["frame_rate"] as? Double,
              let frames = decoded["video_frames"] as? Int else { throw DomainBridge.Failure.invalidRequest }
        try Self.validateCadence(frames: frames, duration: duration, rate: rate, expectedFrames: expectedFrames)
    }

    static func validateCadence(frames: Int, duration: Double, rate: Double, expectedFrames: Int) throws {
        guard expectedFrames > 0, frames == expectedFrames, duration.isFinite, rate.isFinite,
              abs(duration - Double(expectedFrames) / 24.0) <= 1.0 / 24.0,
              abs(rate - 24.0) <= 0.05 else { throw DomainBridge.Failure.invalidRequest }
    }
}
