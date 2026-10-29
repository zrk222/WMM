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

@MainActor
final class NativeStudioModel: ObservableObject, Identifiable {
    typealias Execute = (String, [String: Any]) async throws -> Data
    typealias Render = (NativeStudioPacket, String) async throws -> URL
    let id = UUID()
    let appID: String
    let manifestVersion: Int
    private let execute: Execute
    private let render: Render
    private let openArtifact: (NativeStudioJob) async throws -> URL
    private let reconcile: (NativeStudioJob) async throws -> URL
    private let cancelRender: () async -> Void
    @Published var projects: [NativeStudioProject] = []
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
    var hasUnsavedChanges: Bool { selected.map { $0.scene != draft } ?? true }

    init(appID: String, manifestVersion: Int, execute: @escaping Execute,
         render: @escaping Render, openArtifact: @escaping (NativeStudioJob) async throws -> URL,
         reconcile: @escaping (NativeStudioJob) async throws -> URL,
         cancelRender: @escaping () async -> Void) {
        self.appID = appID; self.manifestVersion = manifestVersion
        self.execute = execute; self.render = render; self.openArtifact = openArtifact
        self.reconcile = reconcile; self.cancelRender = cancelRender
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
        }
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
    }
}
