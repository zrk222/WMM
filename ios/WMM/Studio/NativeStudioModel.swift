import Foundation
import Combine

struct NativeStudioProject: Decodable, Identifiable {
    let project_id: String
    let revision: Int
    let manifest_version: Int
    let source_hash: String
    let scene: NativeStudioScene
    var id: String { project_id }
}

struct NativeStudioJob: Decodable, Identifiable {
    struct Result: Decodable { let artifact_id: String; let sha256: String; let frames: Int }
    let job_id: String
    let project_id: String
    let revision: Int
    let source_hash: String
    let packet_hash: String
    let status: String
    let result: Result?
    var id: String { job_id }
}

struct NativeCreativeBrief: Identifiable {
    let id: String
    let hash: String
    let objective: String
    let seconds: Int
}

@MainActor
final class NativeStudioModel: ObservableObject, Identifiable {
    typealias Execute = (String, [String: Any]) async throws -> Data
    typealias Render = (NativeStudioPacket, String) async throws -> URL
    let id = UUID()
    let appID: String
    let manifestVersion: Int
    let firstUse: NativeCreativeFirstUse
    private let execute: Execute
    private let render: Render
    private let openArtifact: (NativeStudioJob) async throws -> URL
    private let reconcile: (NativeStudioJob) async throws -> URL
    private let cancelRender: () async -> Void
    private let listOriginals: () async throws -> [NativeMediaItem]
    private let batchExecute: (String, [String: Any]) async throws -> Data
    private let runBatch: (Data, Data) async throws -> Data
    private let cancelBatchRender: () async -> Void
    private let batchArtifact: (String, Int) async throws -> URL
    @Published var projects: [NativeStudioProject] = []
    @Published var originals: [NativeMediaItem] = []
    @Published var selected: NativeStudioProject?
    @Published var jobs: [NativeStudioJob] = []
    @Published var draft = NativeStudioScene(title: "", shape: "PORTRAIT", scenes: [.init(text: "", seconds: 3)])
    @Published var output: URL?
    @Published var outputRevision: Int?
    private var outputJobID: String?
    @Published var message: String?
    @Published var activity = ""
    @Published var busy = false
    private var activeJob: String?
    private var cancelRequested = false
    private var activeBatch: String?
    private var reviewedBatch: [String: Any]?
    private var savedBatches: [[String: Any]] = []
    private var selectedBatchArtifact: (String, Int)?
    @Published var batchBriefs: [NativeCreativeBrief] = []
    @Published var batchBriefID = ""
    @Published var batchBothShapes = false
    @Published var batchReview: String?
    @Published var batchProgress: [String] = []
    @Published var batchOutput: URL?
    var hasUnsavedChanges: Bool { selected.map { $0.scene != draft } ?? true }

    init(appID: String, manifestVersion: Int, execute: @escaping Execute,
         render: @escaping Render, openArtifact: @escaping (NativeStudioJob) async throws -> URL,
         reconcile: @escaping (NativeStudioJob) async throws -> URL,
         cancelRender: @escaping () async -> Void,
         listOriginals: @escaping () async throws -> [NativeMediaItem],
         batchExecute: @escaping (String, [String: Any]) async throws -> Data,
         runBatch: @escaping (Data, Data) async throws -> Data,
         cancelBatchRender: @escaping () async -> Void,
         batchArtifact: @escaping (String, Int) async throws -> URL,
         uploadCreativeStill: @escaping (String, URL) async throws -> Data) {
        self.appID = appID; self.manifestVersion = manifestVersion
        self.firstUse = NativeCreativeFirstUse(appID: appID, manifestVersion: manifestVersion,
                                               execute: batchExecute, upload: uploadCreativeStill)
        self.execute = execute; self.render = render; self.openArtifact = openArtifact
        self.reconcile = reconcile; self.cancelRender = cancelRender; self.listOriginals = listOriginals
        self.batchExecute = batchExecute; self.runBatch = runBatch; self.cancelBatchRender = cancelBatchRender
        self.batchArtifact = batchArtifact
    }

    private func perform(_ activity: String, _ work: () async throws -> Void) async {
        guard !busy else { return }
        busy = true; self.activity = activity; message = nil
        defer { busy = false; self.activity = "" }
        do { try await work() }
        catch { message = "Studio could not complete this action. Reopen the current revision and check your session." }
    }

    func refresh() async {
        struct Listing: Decodable { let projects: [NativeStudioProject] }
        await perform("Loading saved scenes…") {
            projects = try JSONDecoder().decode(Listing.self, from: await execute("projects", [:])).projects
            originals = try await listOriginals()
            try await refreshBatches()
        }
    }

    private func refreshBatches() async throws {
        let bytes = try await batchExecute("workspace.read", [:])
        guard let workspace = try JSONSerialization.jsonObject(with: bytes) as? [String: Any],
              let briefs = workspace["briefs"] as? [[String: Any]] else { throw NativeStudioRenderer.Failure.invalidPacket }
        batchBriefs = briefs.compactMap { item in
            guard item["evidence_status"] as? String == "CURRENT", let id = item["id"] as? String,
                  let current = item["current"] as? [String: Any], let hash = current["hash"] as? String,
                  let data = current["data"] as? [String: Any], let definition = data["definition"] as? [String: Any],
                  definition["channel"] as? String == "SHORT_VIDEO", let objective = definition["objective"] as? String,
                  let seconds = definition["duration_seconds"] as? Int else { return nil }
            return NativeCreativeBrief(id: id, hash: hash, objective: objective, seconds: seconds)
        }
        if !batchBriefs.contains(where: { $0.id == batchBriefID }) { batchBriefID = batchBriefs.first?.id ?? "" }
        let listing = try await batchExecute("creative.batch.list", [:])
        guard let object = try JSONSerialization.jsonObject(with: listing) as? [String: Any],
              let items = object["items"] as? [[String: Any]] else { throw NativeStudioRenderer.Failure.invalidPacket }
        savedBatches = items.filter { ($0["plan"] as? [String: Any])?["runtime"] as? String == "IOS" }
        batchProgress = savedBatches.map { item in
            let state = item["state"] as? String ?? "UNKNOWN"
            let variants = item["variants"] as? [[String: Any]] ?? []
            return "\(state): " + variants.map { ($0["status"] as? String ?? "UNKNOWN") }.joined(separator: ", ") + " · not published"
        }
    }

    func prepareBatch() async {
        guard let brief = batchBriefs.first(where: { $0.id == batchBriefID }) else { return }
        await perform("Preparing your exact batch…") {
            let shapes = batchBothShapes ? ["PORTRAIT", "LANDSCAPE"] : ["PORTRAIT"]
            let variants = shapes.map { ["brief_id": brief.id, "brief_hash": brief.hash, "shape": $0] }
            let expiry = ISO8601DateFormatter().string(from: Date().addingTimeInterval(3600))
            let input: [String: Any] = ["variants": variants, "max_total_frames": brief.seconds * 24 * shapes.count,
                                        "runtime": "IOS", "expires": expiry]
            let bytes = try await batchExecute("creative.batch.plan", input)
            guard let result = try JSONSerialization.jsonObject(with: bytes) as? [String: Any],
                  let plan = result["plan"] as? [String: Any], let encoded = result["plan_json"] as? String, let hash = result["plan_hash"] as? String,
                  let rows = plan["variants"] as? [[String: Any]] else { throw NativeStudioRenderer.Failure.invalidPacket }
            let captions = rows.enumerated().map { index, row in
                let brief = row["brief"] as? [String: Any] ?? [:]
                let data = brief["data"] as? [String: Any] ?? [:]
                let content = data["content"] as? [String: Any] ?? [:]
                let screens = content["screens"] as? [[String: Any]] ?? []
                let source = data["source"] as? [String: Any] ?? [:]
                let stills = screens.map { "Still \($0["file_id"] as? String ?? "") · SHA-256 \($0["sha256"] as? String ?? "")" }.joined(separator: "\n")
                return "Variant \(index + 1) · \(row["shape"] as? String ?? "")\n" +
                    ((row["captions"] as? [String]) ?? []).joined(separator: "\n") +
                    "\nBrief \(row["brief_hash"] as? String ?? "") · source \(source["hash"] as? String ?? "")\n" + stills
            }.joined(separator: "\n\n")
            batchReview = "\(shapes.count) video(s), \(brief.seconds * 24 * shapes.count) frames, on this device. Expires in 1 hour. Each video is limited to 8 MiB.\n\n\(captions)\n\nReview captions and framing after rendering. Nothing is published."
            reviewedBatch = ["plan": encoded, "plan_hash": hash, "request_key": UUID().uuidString]
        }
    }

    func clearBatchReview() {
        reviewedBatch = nil
        batchReview = nil
    }

    func queueBatch() async {
        guard let body = reviewedBatch else { return }
        await perform("Rendering your reviewed batch on this device…") {
            cancelRequested = false
            let request = try JSONSerialization.data(withJSONObject: ["app_id": appID, "operation": "creative.batch.create", "input": body])
            let response = try await batchExecute("creative.batch.create", body)
            guard let object = try JSONSerialization.jsonObject(with: response) as? [String: Any],
                  let id = object["id"] as? String else { throw NativeStudioRenderer.Failure.invalidPacket }
            activeBatch = id
            defer { activeBatch = nil }
            if cancelRequested {
                _ = try await batchExecute("creative.batch.cancel", ["batch_id": id])
                throw NativeStudioRenderer.Failure.cancelled
            }
            _ = try await runBatch(request, response)
            reviewedBatch = nil; batchReview = nil
            try await refreshBatches()
            message = "Batch status updated. Review the local videos and any unresolved items before sharing."
        }
    }

    func resumeBatch(_ index: Int) async {
        guard savedBatches.indices.contains(index), savedBatches[index]["state"] as? String == "ACTIVE",
              let id = savedBatches[index]["id"] as? String else { return }
        await perform("Inspecting the interrupted batch on this device…") {
            cancelRequested = false; activeBatch = id
            defer { activeBatch = nil }
            let request = try JSONSerialization.data(withJSONObject: ["app_id": appID, "operation": "creative.batch.create", "input": [:]])
            let response = try JSONSerialization.data(withJSONObject: savedBatches[index])
            _ = try await runBatch(request, response)
            try await refreshBatches()
            message = "Interrupted batch inspected. Any unresolved attempt keeps its original identity and reservation."
        }
    }

    func completedVariants(_ index: Int) -> [Int] {
        guard savedBatches.indices.contains(index), let variants = savedBatches[index]["variants"] as? [[String: Any]] else { return [] }
        return variants.compactMap { $0["status"] as? String == "SUCCEEDED" ? $0["ordinal"] as? Int : nil }
    }

    func previewBatch(_ index: Int, ordinal: Int) async {
        guard savedBatches.indices.contains(index), let id = savedBatches[index]["id"] as? String,
              let variants = savedBatches[index]["variants"] as? [[String: Any]],
              variants.contains(where: { $0["status"] as? String == "SUCCEEDED" && $0["ordinal"] as? Int == ordinal }) else { return }
        batchOutput = nil; selectedBatchArtifact = nil
        await perform("Checking the saved video and its source…") {
            batchOutput = try await batchArtifact(id, ordinal)
            selectedBatchArtifact = (id, ordinal)
            message = "Local video decoded. Check captions, audio and framing before sharing."
        }
    }

    func prepareBatchShare() async -> URL? {
        guard !busy, let (id, ordinal) = selectedBatchArtifact else { return nil }
        batchOutput = nil
        await perform("Rechecking the saved video before sharing…") {
            batchOutput = try await batchArtifact(id, ordinal)
        }
        return batchOutput
    }

    private func read(_ projectID: String) async throws {
        struct Detail: Decodable { let project: NativeStudioProject; let jobs: [NativeStudioJob] }
        let value = try JSONDecoder().decode(Detail.self, from: await execute("read", ["project_id": projectID]))
        selected = value.project; draft = value.project.scene; jobs = value.jobs; output = nil; outputRevision = nil; outputJobID = nil
    }

    func open(_ project: NativeStudioProject) async {
        await perform("Opening saved scenes…") { try await read(project.project_id) }
    }

    func newProject() {
        guard !busy else { return }
        selected = nil; jobs = []; output = nil; outputRevision = nil; outputJobID = nil
        draft = NativeStudioScene(title: "", shape: "PORTRAIT", scenes: [.init(text: "", seconds: 3)])
    }

    func save() async {
        await perform("Saving a new scene revision…") {
            let projectID = selected?.project_id ?? "studio-" + UUID().uuidString.lowercased()
            let bytes = try JSONEncoder().encode(draft)
            let scene = try JSONSerialization.jsonObject(with: bytes)
            _ = try await execute("save", ["project_id": projectID, "base_revision": selected?.revision ?? 0,
                "manifest_version": manifestVersion, "request_key": UUID().uuidString, "scene": scene])
            try await read(projectID)
            message = "Scene revision saved. Render it locally to review the video."
        }
    }

    func export() async {
        guard let project = selected, !hasUnsavedChanges else { return }
        struct Start: Decodable { let job: NativeStudioJob; let packet: NativeStudioPacket }
        await perform("Rendering and decoding the saved scene revision…") {
            output = nil; outputRevision = nil; outputJobID = nil
            cancelRequested = false
            let request: [String: Any] = ["project_id": project.project_id, "revision": project.revision,
                "source_hash": project.source_hash, "request_key": UUID().uuidString]
            let started = try JSONDecoder().decode(Start.self, from: await execute("start", request))
            try started.packet.validateBounds()
            guard started.job.status == "PREPARED", started.packet.app_id == appID,
                  started.packet.project_id == project.project_id, started.packet.revision == project.revision,
                  started.packet.source_hash == project.source_hash, started.packet.packet_hash == started.job.packet_hash else {
                throw NativeStudioRenderer.Failure.invalidPacket
            }
            activeJob = started.job.job_id
            defer { activeJob = nil }
            if cancelRequested {
                _ = try await execute("cancel", ["job_id": started.job.job_id])
                throw NativeStudioRenderer.Failure.cancelled
            }
            let url = try await render(started.packet, started.job.job_id)
            let job = try JSONDecoder().decode(NativeStudioJob.self,
                from: await execute("inspect", ["job_id": started.job.job_id]))
            guard job.status == "SUCCEEDED", job.result != nil else { throw NativeStudioRenderer.Failure.unavailable }
            output = url
            outputRevision = job.revision
            outputJobID = job.job_id
            jobs.append(job)
            message = "Local video decoded and saved for this revision. Review it before sharing."
        }
    }

    func reopen(_ job: NativeStudioJob) async {
        guard job.status == "SUCCEEDED", selected?.project_id == job.project_id else { return }
        await perform("Checking saved video bytes and their source revision…") {
            let current = try JSONDecoder().decode(NativeStudioJob.self,
                from: await execute("artifact", ["job_id": job.job_id]))
            guard current.status == "SUCCEEDED", current.project_id == job.project_id,
                  current.revision == job.revision, current.packet_hash == job.packet_hash,
                  current.result?.artifact_id == job.result?.artifact_id,
                  current.result?.sha256 == job.result?.sha256, current.result != nil else {
                throw NativeStudioRenderer.Failure.invalidPacket
            }
            output = try await openArtifact(current)
            outputRevision = current.revision
            outputJobID = current.job_id
            message = "Opened the decoded video for revision \(current.revision)."
        }
    }

    func recover(_ job: NativeStudioJob) async {
        guard job.status == "PREPARED", selected?.project_id == job.project_id else { return }
        await perform("Inspecting the interrupted render before recovery…") {
            let current = try JSONDecoder().decode(NativeStudioJob.self,
                from: await execute("inspect", ["job_id": job.job_id]))
            guard current.project_id == job.project_id, current.revision == job.revision,
                  current.packet_hash == job.packet_hash else { throw NativeStudioRenderer.Failure.invalidPacket }
            let recovered: URL
            if current.status == "SUCCEEDED" {
                recovered = try await openArtifact(current)
            } else if current.status == "PREPARED" {
                recovered = try await reconcile(current)
            } else { throw NativeStudioRenderer.Failure.unavailable }
            let result = try JSONDecoder().decode(NativeStudioJob.self,
                from: await execute("inspect", ["job_id": job.job_id]))
            guard result.status == "SUCCEEDED", result.result != nil else { throw NativeStudioRenderer.Failure.unavailable }
            if let index = jobs.firstIndex(where: { $0.job_id == job.job_id }) { jobs[index] = result }
            output = recovered
            outputRevision = result.revision; outputJobID = result.job_id
            message = "Recovered the decoded video for revision \(result.revision)."
        }
    }

    func prepareShare() async -> URL? {
        guard !busy, !hasUnsavedChanges, let id = outputJobID,
              let job = jobs.first(where: { $0.job_id == id }) else { return nil }
        // Reopen uses fresh owner/source checks and re-decodes the saved bytes.
        output = nil
        await reopen(job)
        return output
    }

    func plan() async {
        guard let project = selected, !hasUnsavedChanges else { return }
        await perform("Checking the saved scene plan…") {
            let packet = try JSONDecoder().decode(NativeStudioPacket.self, from: await execute("plan", [
                "project_id": project.project_id, "revision": project.revision, "source_hash": project.source_hash]))
            try packet.validateBounds()
            guard packet.app_id == appID, packet.project_id == project.project_id, packet.revision == project.revision,
                  packet.source_hash == project.source_hash else { throw NativeStudioRenderer.Failure.invalidPacket }
            message = "Plan: \(packet.scene.scenes.count) scenes, \(packet.frame_count) frames at 24 fps. No video has been rendered yet."
        }
    }

    func cancel() async {
        cancelRequested = true
        await cancelRender()
        if let job = activeJob { _ = try? await execute("cancel", ["job_id": job]) }
        if let batch = activeBatch {
            _ = try? await batchExecute("creative.batch.cancel", ["batch_id": batch])
            await cancelBatchRender()
        }
    }
}
