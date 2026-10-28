import Foundation
import SwiftUI

struct NativeJobProgress: Decodable {
    struct Run: Decodable, Identifiable {
        struct Event: Decodable {
            let code: String; let stage: Int?; let message: String; let observed_at: String
        }
        let id: String; let action: String; let status: String; let attempts: Int
        let processed_stages: Int; let blocked_stages: Int; let activity: String
        let events: [Event]
    }
    let app_id: String; let observed_at: String; let runs: [Run]
}

/// Foreground driver of the shared durable queue. No timer claims background service.
@MainActor
final class LocalScheduler: ObservableObject, Identifiable {
    let id = UUID()
    @Published private(set) var progress: NativeJobProgress?
    @Published private(set) var busy = false
    @Published private(set) var message: String?
    private let execute: @MainActor (String, Data) async throws -> Data
    private var requestKey = UUID().uuidString
    private var pendingID: String?

    init(execute: @escaping @MainActor (String, Data) async throws -> Data) { self.execute = execute }

    private func call(_ action: String, _ body: [String: Any] = [:]) async throws -> Data {
        try await execute(action, JSONSerialization.data(withJSONObject: body))
    }

    private func readProgress() async throws {
        progress = try JSONDecoder().decode(NativeJobProgress.self, from: await call("monitor"))
    }

    func refresh() async {
        guard !busy else { return }; busy = true; message = nil; defer { busy = false }
        do { try await readProgress() }
        catch { message = "Progress could not be read. Unlock again if needed; saved jobs and checkpoints remain local." }
    }

    func prepare() async {
        guard !busy else { return }; busy = true; message = nil; defer { busy = false }
        do {
            struct Queued: Decodable { let id: String }
            if pendingID == nil {
                let data = try await call("queue", ["stage": 0, "request_key": requestKey])
                pendingID = try JSONDecoder().decode(Queued.self, from: data).id
            }
            try await readProgress()
            struct Completed: Decodable { let status: String }
            var status = "UNKNOWN"
            if let pendingID {
                let bytes = try await call("run", ["id": pendingID])
                status = try JSONDecoder().decode(Completed.self, from: bytes).status
            }
            try await readProgress()
            pendingID = nil; requestKey = UUID().uuidString
            message = status == "SUCCEEDED"
                ? "Preparation finished. Open each stage's evidence gaps before taking downstream actions. Prepared packets do not mean a campaign ran."
                : "Preparation returned \(status). Inspect its saved job and stage events before starting new work."
        } catch {
            message = "Preparation was not confirmed. Refresh progress before retrying. The same request key is retained; a live lease will not be restarted."
        }
    }

    func resume(_ run: NativeJobProgress.Run) async {
        guard !busy else { return }; busy = true; message = nil; defer { busy = false }
        do {
            _ = try await call("run", ["id": run.id])
            try await readProgress()
            message = "Job state refreshed after the permitted resume. Inspect its saved status and stage events."
        } catch { message = "Resume was denied or not confirmed. A live lease, changed app or lost owner session requires inspection before retrying." }
    }

    func cancel(_ run: NativeJobProgress.Run) async {
        guard !busy else { return }; busy = true; message = nil; defer { busy = false }
        do {
            _ = try await call("cancel", ["id": run.id])
            try await readProgress()
            message = "Local preparation cancelled. Prior evidence and completed effects are retained."
        } catch { message = "Cancellation was not confirmed. Refresh the job's recorded state." }
    }
}
