import Foundation

/// Serialized in-process owner transport. A handle identifies a database, not a role.
actor DomainBridge {
    enum Failure: Error { case closed, invalidRequest }
    private var handle: String?
    private let storeRoot: URL

    init(store: LocalStore, identity: LocalIdentity) throws {
        storeRoot = store.root.standardizedFileURL.resolvingSymlinksInPath()
        let authority = identity.authority
        let providerStorage = try ProviderAuthentication(database: store.database)
        handle = try EngineBootstrap.open(database: store.database, verifier: { nonce in
            authority.verify(nonce)
        }, vault: { request in providerStorage.invoke(request) })
    }

    func workspaces(session: LocalIdentity.Session) throws -> Data {
        guard let handle else { throw Failure.closed }
        return try EngineBootstrap.workspaces(handle: handle, session: session.nonce.uuidString)
    }

    /// Call only after explicit owner confirmation in the UI.
    func enroll(session: LocalIdentity.Session, appID: String) throws -> Data {
        guard let handle else { throw Failure.closed }
        return try EngineBootstrap.enroll(handle: handle, session: session.nonce.uuidString, appID: appID)
    }

    func call(session: LocalIdentity.Session, request: Data) throws -> Data {
        guard let handle else { throw Failure.closed }
        guard !request.isEmpty, request.count <= 1_048_576 else { throw Failure.invalidRequest }
        return try EngineBootstrap.ownerCall(handle: handle, session: session.nonce.uuidString, request: request)
    }

    /// Fixed first-app path. The request must include explicit owner confirmation.
    func createWorkspace(session: LocalIdentity.Session, request: Data) throws -> Data {
        guard let handle else { throw Failure.closed }
        guard !request.isEmpty, request.count <= 1_048_576 else { throw Failure.invalidRequest }
        return try EngineBootstrap.createWorkspace(handle: handle, session: session.nonce.uuidString, request: request)
    }

    func close() {
        if let handle { EngineBootstrap.close(handle) }
        handle = nil
    }

    func reviewLogout() {
        if let handle { EngineBootstrap.reviewLogout(handle: handle) }
    }

    func insights(session: LocalIdentity.Session, appID: String, action: String, request: Data) throws -> Data {
        guard let handle else { throw Failure.closed }
        guard !request.isEmpty, request.count <= 1_048_576 else { throw Failure.invalidRequest }
        return try EngineBootstrap.insights(handle: handle, session: session.nonce.uuidString,
            appID: appID, action: action, request: request)
    }

    func storeConnection(session: LocalIdentity.Session, appID: String, action: String, request: Data) throws -> Data {
        guard let handle else { throw Failure.closed }
        guard !request.isEmpty, request.count <= 1_048_576 else { throw Failure.invalidRequest }
        return try EngineBootstrap.storeConnection(handle: handle, session: session.nonce.uuidString,
            appID: appID, action: action, request: request)
    }

    func agentTimeline(session: LocalIdentity.Session, appID: String, action: String, body: [String: Any]) throws -> Data {
        guard let handle else { throw Failure.closed }
        let request = try JSONSerialization.data(withJSONObject: body)
        guard !request.isEmpty, request.count <= 1_048_576 else { throw Failure.invalidRequest }
        return try EngineBootstrap.agentTimeline(handle: handle, session: session.nonce.uuidString,
            appID: appID, action: action, request: request)
    }

    func agentTimelineDestination(jobID: String) throws -> URL {
        guard handle != nil, let id = UUID(uuidString: jobID) else { throw Failure.closed }
        let folder = storeRoot.appendingPathComponent("native-agent-timeline-exports", isDirectory: true)
        try LocalStore.createProtectedDirectory(folder)
        guard folder.standardizedFileURL.resolvingSymlinksInPath() == folder else { throw Failure.invalidRequest }
        return folder.appendingPathComponent(id.uuidString.lowercased() + ".mp4")
    }

    func agentTimelineSource(session: LocalIdentity.Session, appID: String, jobID: String, packetHash: String,
                             source: NativeRenderPlan.Source) throws -> URL {
        let bytes = try agentTimeline(session: session, appID: appID, action: "source", body: [
            "job_id": jobID, "packet_hash": packetHash, "kind": source.kind, "source_id": source.id, "sha256": source.sha256])
        struct Location: Decodable { let path: String }
        let location = try JSONDecoder().decode(Location.self, from: bytes)
        let url = URL(fileURLWithPath: location.path).standardizedFileURL.resolvingSymlinksInPath()
        guard url.path.hasPrefix(storeRoot.path + "/"),
              try url.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile == true else { throw Failure.invalidRequest }
        return url
    }

    func finishAgentTimeline(session: LocalIdentity.Session, appID: String, jobID: String,
                             packetHash: String, output: URL) async throws -> Data {
        guard let handle else { throw Failure.closed }
        let expected = storeRoot.appendingPathComponent("native-agent-timeline-exports", isDirectory: true)
        guard output.isFileURL, output.pathExtension == "mp4",
              output.deletingLastPathComponent().standardizedFileURL.resolvingSymlinksInPath() == expected,
              output.standardizedFileURL.resolvingSymlinksInPath() == output,
              let identity = UUID(uuidString: output.deletingPathExtension().lastPathComponent),
              UUID(uuidString: jobID) == identity else { throw Failure.invalidRequest }
        let bytes = try await MediaInspector.inspectOriginal(output)
        guard self.handle == handle,
              let inspected = try JSONSerialization.jsonObject(with: bytes) as? [String: Any],
              let metadata = inspected["metadata"] as? [String: Any],
              let decoded = inspected["decoded"] as? [String: Any],
              let sha = inspected["sha256"] as? String, let size = inspected["bytes"] as? Int,
              let frames = decoded["video_frames"] as? Int, let width = metadata["width"] as? Int,
              let height = metadata["height"] as? Int, let audio = metadata["audio"] as? Bool else { throw Failure.invalidRequest }
        let proof: [String: Any] = ["artifact_id": identity.uuidString.lowercased(), "sha256": sha, "bytes": size,
            "frames": frames, "width": width, "height": height, "audio": audio]
        return try EngineBootstrap.agentTimelineFinish(handle: handle, session: session.nonce.uuidString, appID: appID,
            request: JSONSerialization.data(withJSONObject: ["job_id": jobID, "packet_hash": packetHash]),
            inspection: JSONSerialization.data(withJSONObject: proof))
    }

    func humanReview(session: LocalIdentity.Session, appID: String, action: String, request: Data) throws -> Data {
        guard let handle else { throw Failure.closed }
        guard !request.isEmpty, request.count <= 1_048_576 else { throw Failure.invalidRequest }
        return try EngineBootstrap.humanReview(handle: handle, session: session.nonce.uuidString,
            appID: appID, action: action, request: request)
    }

    func agentReview(session: LocalIdentity.Session, credential: Data, action: String, request: Data) throws -> Data {
        guard let handle else { throw Failure.closed }
        guard let token = String(data: credential, encoding: .utf8), token.utf8.count == 48,
              !request.isEmpty, request.count <= 1_048_576 else { throw Failure.invalidRequest }
        return try EngineBootstrap.agentReview(handle: handle, session: session.nonce.uuidString,
            credential: token, action: action, request: request)
    }

    func evidenceForm(session: LocalIdentity.Session, appID: String) throws -> Data {
        guard let handle else { throw Failure.closed }
        return try EngineBootstrap.evidenceForm(handle: handle, session: session.nonce.uuidString, appID: appID)
    }

    func automation(session: LocalIdentity.Session, appID: String, action: String, request: Data) throws -> Data {
        guard let handle else { throw Failure.closed }
        guard ["preview", "activate", "status", "off"].contains(action), !request.isEmpty,
              request.count <= 1_048_576 else { throw Failure.invalidRequest }
        return try EngineBootstrap.automation(handle: handle, session: session.nonce.uuidString,
            appID: appID, action: action, request: request)
    }

    func studio(session: LocalIdentity.Session, appID: String, action: String, body: [String: Any]) throws -> Data {
        guard let handle else { throw Failure.closed }
        guard ["projects", "read", "save", "plan", "start", "inspect", "artifact", "cancel", "validate"].contains(action) else { throw Failure.invalidRequest }
        let bytes = try JSONSerialization.data(withJSONObject: body)
        guard bytes.count <= 1_048_576 else { throw Failure.invalidRequest }
        return try EngineBootstrap.studio(handle: handle, session: session.nonce.uuidString, appID: appID, action: action, request: bytes)
    }

    func studioDestination(jobID: String) throws -> URL {
        guard handle != nil else { throw Failure.closed }
        guard let identity = UUID(uuidString: jobID) else { throw Failure.invalidRequest }
        let folder = storeRoot.appendingPathComponent("native-studio-exports", isDirectory: true)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true,
            attributes: [.protectionKey: FileProtectionType.complete])
        guard folder.standardizedFileURL.resolvingSymlinksInPath().path == folder.path else { throw Failure.invalidRequest }
        return folder.appendingPathComponent(identity.uuidString.lowercased() + ".mp4")
    }

    func studioSource(session: LocalIdentity.Session, appID: String, jobID: String,
                      packetHash: String, mediaID: String, sha256: String) throws -> URL {
        guard let handle else { throw Failure.closed }
        let request = try JSONSerialization.data(withJSONObject: ["job_id": jobID,
            "packet_hash": packetHash, "media_id": mediaID, "sha256": sha256])
        let result = try EngineBootstrap.studioSource(handle: handle, session: session.nonce.uuidString,
            appID: appID, request: request)
        struct Location: Decodable { let path: String }
        let location = try JSONDecoder().decode(Location.self, from: result)
        let url = URL(fileURLWithPath: location.path).standardizedFileURL.resolvingSymlinksInPath()
        guard url.path.hasPrefix(storeRoot.path + "/"),
              try url.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile == true else {
            throw Failure.invalidRequest
        }
        return url
    }

    func studioArtifact(session: LocalIdentity.Session, appID: String, jobID: String) async throws -> URL {
        struct Artifact: Decodable {
            struct Proof: Decodable { let artifact_id: String; let sha256: String; let frames: Int }
            let result: Proof?
        }
        let bytes = try studio(session: session, appID: appID, action: "artifact", body: ["job_id": jobID])
        guard let proof = try JSONDecoder().decode(Artifact.self, from: bytes).result,
              let identity = UUID(uuidString: proof.artifact_id) else { throw Failure.invalidRequest }
        let folder = storeRoot.appendingPathComponent("native-studio-exports", isDirectory: true)
        let output = folder.appendingPathComponent(identity.uuidString.lowercased() + ".mp4")
        guard output.standardizedFileURL.resolvingSymlinksInPath() == output else { throw Failure.invalidRequest }
        let inspection = try await MediaInspector.inspectOriginal(output)
        guard let value = try JSONSerialization.jsonObject(with: inspection) as? [String: Any],
              let decoded = value["decoded"] as? [String: Any], value["sha256"] as? String == proof.sha256,
              decoded["video_frames"] as? Int == proof.frames else { throw Failure.invalidRequest }
        let current = try studio(session: session, appID: appID, action: "artifact", body: ["job_id": jobID])
        guard current == bytes else { throw Failure.invalidRequest }
        return output
    }

    func finishStudio(session: LocalIdentity.Session, appID: String, jobID: String, packetHash: String, output: URL) async throws -> Data {
        guard let handle else { throw Failure.closed }
        let expected = storeRoot.appendingPathComponent("native-studio-exports", isDirectory: true)
        guard output.isFileURL, output.pathExtension == "mp4",
              output.deletingLastPathComponent().standardizedFileURL.resolvingSymlinksInPath() == expected,
              output.standardizedFileURL.resolvingSymlinksInPath() == output,
              let identity = UUID(uuidString: output.deletingPathExtension().lastPathComponent),
              UUID(uuidString: jobID) == identity else { throw Failure.invalidRequest }
        let bytes = try await MediaInspector.inspectOriginal(output)
        guard self.handle == handle,
              let inspected = try JSONSerialization.jsonObject(with: bytes) as? [String: Any],
              let metadata = inspected["metadata"] as? [String: Any],
              let decoded = inspected["decoded"] as? [String: Any],
              let sha = inspected["sha256"] as? String, let size = inspected["bytes"] as? Int,
              let frames = decoded["video_frames"] as? Int,
              let width = metadata["width"] as? Int, let height = metadata["height"] as? Int,
              let audio = metadata["audio"] as? Bool else { throw Failure.invalidRequest }
        let proof: [String: Any] = ["artifact_id": identity.uuidString.lowercased(), "sha256": sha,
            "bytes": size, "frames": frames, "width": width, "height": height, "audio": audio]
        let request = try JSONSerialization.data(withJSONObject: ["job_id": jobID, "packet_hash": packetHash])
        return try EngineBootstrap.studioFinish(handle: handle, session: session.nonce.uuidString, appID: appID,
            request: request, inspection: JSONSerialization.data(withJSONObject: proof))
    }

    func snapshotExport(session: LocalIdentity.Session, appID: String) throws -> Data {
        guard let handle else { throw Failure.closed }
        return try EngineBootstrap.snapshotExport(handle: handle, session: session.nonce.uuidString, appID: appID)
    }

    func snapshotRestore(session: LocalIdentity.Session, appID: String, request: Data, confirmed: Bool) throws -> Data {
        guard let handle else { throw Failure.closed }
        guard confirmed, !request.isEmpty, request.count <= 33_554_432 else { throw Failure.invalidRequest }
        return try EngineBootstrap.snapshotRestore(handle: handle, session: session.nonce.uuidString,
            appID: appID, request: request, confirmed: confirmed)
    }

    func updateWorkspace(session: LocalIdentity.Session, appID: String, request: Data) throws -> Data {
        guard let handle else { throw Failure.closed }
        guard !request.isEmpty, request.count <= 1_048_576 else { throw Failure.invalidRequest }
        return try EngineBootstrap.updateWorkspace(handle: handle, session: session.nonce.uuidString,
            appID: appID, request: request)
    }

    func report(session: LocalIdentity.Session, appID: String) throws -> Data {
        guard let handle else { throw Failure.closed }
        return try EngineBootstrap.report(handle: handle, session: session.nonce.uuidString, appID: appID)
    }

    func uploadMedia(session: LocalIdentity.Session, appID: String, filename: String,
                     original: URL, manifestVersion: Int, requestKey: String) async throws -> Data {
        guard let handle else { throw Failure.closed }
        // Produce inspection here from actual bytes, never from an agent envelope.
        let inspection = try await MediaInspector.inspectOriginal(original)
        try Task.checkCancellation()
        let content = try MediaIntake.readBounded(original)
        let body = try JSONSerialization.data(withJSONObject: [
            "manifest_version": manifestVersion, "request_key": requestKey] as [String: Any])
        guard self.handle == handle else { throw Failure.closed }
        return try EngineBootstrap.uploadMedia(handle: handle, session: session.nonce.uuidString,
            appID: appID, filename: filename, content: content, request: body, inspection: inspection)
    }

    func mediaList(session: LocalIdentity.Session, appID: String) throws -> Data {
        guard let handle else { throw Failure.closed }
        return try EngineBootstrap.mediaList(handle: handle, session: session.nonce.uuidString, appID: appID)
    }

    func reviewMedia(session: LocalIdentity.Session, appID: String, mediaID: String, request: Data) throws -> Data {
        guard let handle else { throw Failure.closed }
        return try EngineBootstrap.reviewMedia(handle: handle, session: session.nonce.uuidString,
            appID: appID, mediaID: mediaID, request: request)
    }

    struct ProductionPacket: Decodable {
        let schema: String; let app_id: String; let manifest_version: Int
        let project_id: String; let revision: Int; let project_hash: String
        let packet_hash: String; let status: String; let execution_authority: Bool
        let plan: NativeRenderPlan

        fileprivate func request() -> [String: Any] {
            ["project_id": project_id, "revision": revision, "project_hash": project_hash,
             "packet_hash": packet_hash]
        }
    }

    func prepareProduction(session: LocalIdentity.Session, appID: String,
                           projectID: String, revision: Int, projectHash: String) throws -> ProductionPacket {
        let result = try production(session: session, appID: appID, action: "prepare", body: [
            "project_id": projectID, "revision": revision, "project_hash": projectHash])
        let packet = try JSONDecoder().decode(ProductionPacket.self, from: result)
        guard packet.schema == "growth.ios-production-packet.v1", packet.app_id == appID,
              packet.project_id == projectID, packet.revision == revision,
              packet.project_hash == projectHash, packet.status == "PREPARED_NOT_RENDERED",
              !packet.execution_authority else { throw Failure.invalidRequest }
        try packet.plan.validateBounds()
        return packet
    }

    func validateProduction(session: LocalIdentity.Session, packet: ProductionPacket) throws {
        _ = try production(session: session, appID: packet.app_id, action: "validate", body: packet.request())
    }

    func productionSource(session: LocalIdentity.Session, packet: ProductionPacket,
                          source: NativeRenderPlan.Source) throws -> URL {
        var body = packet.request()
        body["kind"] = source.kind; body["source_id"] = source.id; body["sha256"] = source.sha256
        let result = try production(session: session, appID: packet.app_id, action: "source", body: body)
        struct SourceLocation: Decodable { let path: String }
        let location = try JSONDecoder().decode(SourceLocation.self, from: result)
        let url = URL(fileURLWithPath: location.path).standardizedFileURL.resolvingSymlinksInPath()
        guard url.path.hasPrefix(storeRoot.path + "/"),
              try url.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile == true else {
            throw Failure.invalidRequest
        }
        return url
    }

    /// Authority and reuse rights are checked during resolution and after decoded output verification.
    /// A returned file is a local export, not a published campaign or shared production receipt.
    func renderProduction(session: LocalIdentity.Session, packet: ProductionPacket,
                          renderer: TimelineRenderer) async throws -> URL {
        try validateProduction(session: session, packet: packet)
        let directory = storeRoot.appendingPathComponent("native-exports", isDirectory: true)
        try LocalStore.createProtectedDirectory(directory)
        let destination = directory.appendingPathComponent(UUID().uuidString + ".mp4")
        return try await renderer.render(packet.plan, destination: destination, resolve: { source in
            try await self.productionSource(session: session, packet: packet, source: source)
        }, validateAuthority: {
            try await self.validateProduction(session: session, packet: packet)
        })
    }

    private func production(session: LocalIdentity.Session, appID: String,
                            action: String, body: [String: Any]) throws -> Data {
        guard let handle else { throw Failure.closed }
        return try EngineBootstrap.production(handle: handle, session: session.nonce.uuidString,
            appID: appID, action: action, request: JSONSerialization.data(withJSONObject: body))
    }

    deinit {
        if let handle { EngineBootstrap.close(handle) }
    }

    func agentAccess(session: LocalIdentity.Session, appID: String, action: String, request: Data) throws -> Data {
        guard let handle else { throw Failure.closed }
        guard ["list", "issue", "revoke"].contains(action), !request.isEmpty, request.count <= 1_048_576 else {
            throw Failure.invalidRequest
        }
        return try EngineBootstrap.agentAccess(handle: handle, session: session.nonce.uuidString,
            appID: appID, action: action, request: request)
    }

    func jobs(session: LocalIdentity.Session, appID: String, action: String, request: Data) throws -> Data {
        guard let handle else { throw Failure.closed }
        guard ["queue", "run", "monitor", "cancel"].contains(action), !request.isEmpty, request.count <= 1_048_576 else {
            throw Failure.invalidRequest
        }
        return try EngineBootstrap.jobs(handle: handle, session: session.nonce.uuidString,
            appID: appID, action: action, request: request)
    }

    func providers(session: LocalIdentity.Session, appID: String, action: String, request: Data) throws -> Data {
        guard let handle else { throw Failure.closed }
        guard ["view", "save", "disconnect", "cleanup"].contains(action), !request.isEmpty, request.count <= 1_048_576 else {
            throw Failure.invalidRequest
        }
        return try EngineBootstrap.providers(handle: handle, session: session.nonce.uuidString,
            appID: appID, action: action, request: request)
    }

    func inference(session: LocalIdentity.Session, appID: String, action: String, request: Data) throws -> Data {
        guard let handle else { throw Failure.closed }
        guard ["prepare", "start", "run", "read", "history", "mode"].contains(action),
              !request.isEmpty, request.count <= 1_048_576 else { throw Failure.invalidRequest }
        return try EngineBootstrap.inference(handle: handle, session: session.nonce.uuidString,
            appID: appID, action: action, request: request)
    }

    func agentCall(session: LocalIdentity.Session, credential: Data, request: Data) throws -> Data {
        guard let handle else { throw Failure.closed }
        guard credential.count == 48, let text = String(data: credential, encoding: .utf8),
              !request.isEmpty, request.count <= 1_048_576 else { throw Failure.invalidRequest }
        return try EngineBootstrap.agentCall(handle: handle, session: session.nonce.uuidString,
            credential: text, request: request)
    }

    func agentLoop(session: LocalIdentity.Session, appID: String, action: String, request: Data) throws -> Data {
        guard let handle else { throw Failure.closed }
        guard ["prepare", "start", "run", "read", "history", "cancel", "reserve_tool"].contains(action),
              !request.isEmpty, request.count <= 1_048_576 else { throw Failure.invalidRequest }
        return try EngineBootstrap.agentLoop(handle: handle, session: session.nonce.uuidString,
            appID: appID, action: action, request: request)
    }
}
