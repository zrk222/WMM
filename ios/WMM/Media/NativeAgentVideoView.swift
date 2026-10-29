import AVKit
import SwiftUI
import UIKit

@MainActor
final class NativeAgentVideoModel: ObservableObject, Identifiable {
    struct Job: Decodable, Identifiable {
        struct Proof: Decodable { let sha256: String; let frames: Int; let bytes: Int }
        let job_id: String; let project_id: String; let revision: Int; let status: String; let result: Proof?
        var id: String { job_id }
    }
    struct Listing: Decodable { let items: [Job] }
    let id = UUID()
    @Published private(set) var jobs: [Job] = []
    @Published private(set) var busy = false
    @Published private(set) var message: String?
    private var closed = false
    private let execute: @MainActor (String, Data) async throws -> Data
    private let artifact: @MainActor (String) async throws -> URL
    init(execute: @escaping @MainActor (String, Data) async throws -> Data,
         artifact: @escaping @MainActor (String) async throws -> URL) { self.execute = execute; self.artifact = artifact }
    func refresh() async {
        guard !closed, !busy else { return }; busy = true; message = nil; defer { busy = false }
        do {
            let bytes = try await execute("history", Data("{}".utf8))
            guard !closed else { return }
            jobs = try JSONDecoder().decode(Listing.self, from: bytes).items
        } catch { message = "Saved video attempts could not be read. Unlock and refresh; existing files and receipts are retained." }
    }
    func verifiedURL(_ job: Job) async -> URL? {
        guard !closed, !busy, job.status == "SUCCEEDED" else { return nil }
        busy = true; message = nil; defer { busy = false }
        do {
            let output = try await artifact(job.job_id)
            guard !closed else { return nil }
            message = "Current source rights and decoded video bytes match the saved result. Preview or share this local file."
            return output
        } catch {
            message = "This video could not be verified against its current source and saved result. Inspect source rights, project changes and missing files before rendering again."
            return nil
        }
    }
    func cancel(_ job: Job) async {
        guard !closed, !busy, job.status == "PREPARED" else { return }
        busy = true; message = nil
        do { _ = try await execute("cancel", JSONSerialization.data(withJSONObject: ["job_id": job.job_id])) }
        catch { message = "Cancellation was not confirmed. Refresh this exact attempt before retrying." }
        busy = false
        if message == nil { await refresh() }
    }
    func close() { closed = true; jobs = [] }
}

@MainActor
struct NativeAgentVideoView: View {
    @ObservedObject var model: NativeAgentVideoModel
    @Environment(\.dismiss) private var dismiss
    @State private var player: AVPlayer?
    @State private var sharing: AgentVideoShare?
    var body: some View {
        NavigationStack {
            List {
                Section {
                    Text("Your agent's completed timeline videos are ready for you to inspect here. Preview the actual file, then share the version you choose.")
                    Text("WMM checks the current app, project and source rights, then decodes and hashes the file before each preview or share. A completed render does not mean it was published. Scene videos are available in Native studio.").font(.callout)
                }
                if let player { Section("Video preview") { VideoPlayer(player: player).frame(minHeight: 240) } }
                Section("Saved timeline attempts") {
                    if model.jobs.isEmpty { Text("No agent timeline attempts are saved for this app. Use Agent work with an approved timeline project to produce a video.") }
                    ForEach(model.jobs) { job in
                        VStack(alignment: .leading, spacing: 8) {
                            Text("\(job.project_id) · revision \(job.revision)").font(.headline)
                            Text(job.status.replacingOccurrences(of: "_", with: " "))
                            Text(job.job_id).font(.caption).textSelection(.enabled)
                            if let proof = job.result {
                                Text("\(proof.frames) decoded frames · \(proof.bytes) bytes").font(.caption)
                                Text("SHA256: \(proof.sha256)").font(.caption).textSelection(.enabled)
                            }
                            if job.status == "SUCCEEDED" {
                                Button("Verify and preview video") { Task {
                                    player?.pause(); player = nil
                                    if let output = await model.verifiedURL(job) { player = AVPlayer(url: output) }
                                }}.disabled(model.busy)
                                Button("Verify and share video") { Task {
                                    if let output = await model.verifiedURL(job) { sharing = AgentVideoShare(url: output) }
                                }}.disabled(model.busy)
                            } else if job.status == "PREPARED" {
                                Text("Prepared intent; no completed output is recorded. Inspect Agent work before recovering the existing attempt.").font(.caption)
                                Button("Cancel this prepared attempt", role: .destructive) { Task { await model.cancel(job) } }.disabled(model.busy)
                            }
                        }
                    }
                }
                if model.busy { Section { ProgressView("Checking saved video and source evidence…") } }
                if let message = model.message { Section("Result") { Text(message) } }
            }
            .navigationTitle("Agent videos")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Done") { dismiss() }.disabled(model.busy) }
                ToolbarItem(placement: .primaryAction) { Button("Refresh") { Task { await model.refresh() } }.disabled(model.busy) }
            }
            .sheet(item: $sharing) { AgentVideoActivity(url: $0.url) }
            .task { await model.refresh() }
            .onDisappear { player?.pause(); player = nil; sharing = nil; model.close() }
            .interactiveDismissDisabled(model.busy)
        }.privacySensitive()
    }
}
private struct AgentVideoShare: Identifiable { let id = UUID(); let url: URL }
private struct AgentVideoActivity: UIViewControllerRepresentable {
    let url: URL
    func makeUIViewController(context: Context) -> UIActivityViewController { UIActivityViewController(activityItems: [url], applicationActivities: nil) }
    func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}
