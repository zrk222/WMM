import Foundation
import SwiftUI

@MainActor
final class NativeInferenceModel: ObservableObject, Identifiable {
    struct Profiles: Decodable {
        struct Routing: Decodable { struct Config: Decodable { let mode: String }; let version: Int; let data: Config }
        let profiles: [NativeProviderModel.Profile]; let routing: Routing
    }
    struct Prepared: Decodable {
        struct Envelope: Decodable {
            let task: String; let focus: String; let connection_id: String
            let provider: String; let model: String; let prompt: String; let max_output_tokens: Int
        }
        let proposal: Envelope; let source_hash: String; let cost: String; let destination: String
    }
    struct Job: Decodable {
        struct Result: Decodable {
            struct Draft: Decodable {
                struct Item: Decodable { let title: String; let detail: String; let source_ids: [String] }
                let summary: String; let items: [Item]; let unknowns: [String]
            }
            let status: String?; let draft: Draft?; let usage: [String: Int?]?
            let cost: String?; let quota: String?; let next_action: String?
        }
        let id: String; let status: String; let result: Result?
    }
    struct History: Decodable {
        struct Item: Decodable, Identifiable { let id: String; let status: String; let task: String; let created: String }
        let items: [Item]
    }
    let id = UUID()
    @Published private(set) var profiles: Profiles?
    @Published private(set) var prepared: Prepared?
    @Published private(set) var job: Job?
    @Published private(set) var history: [History.Item] = []
    @Published private(set) var busy = false
    @Published private(set) var activity = ""
    @Published private(set) var message: String?
    private var requestKey = UUID().uuidString.lowercased()
    private let execute: @MainActor (String, Data) async throws -> Data

    init(execute: @escaping @MainActor (String, Data) async throws -> Data) { self.execute = execute }

    private func call(_ action: String, _ body: [String: Any] = [:]) async throws -> Data {
        try await execute(action, JSONSerialization.data(withJSONObject: body))
    }

    private func load() async throws {
        profiles = try JSONDecoder().decode(Profiles.self, from: await call("profiles"))
        history = try JSONDecoder().decode(History.self, from: await call("history")).items
    }

    private func perform(_ label: String, _ work: () async throws -> Void) async {
        guard !busy else { return }; busy = true; activity = label; message = nil
        defer { busy = false; activity = "" }
        do { try await work() }
        catch { message = "The action was not confirmed. Refresh saved requests before retrying. A dispatched model request may have consumed provider allowance; it will not be automatically resent." }
    }

    func refresh() async { await perform("Reading app-owned API profiles and saved requests…") { try await load() } }

    func useAPIMode() async {
        guard let version = profiles?.routing.version else { return }
        await perform("Saving your confirmed API access mode…") {
            _ = try await call("mode", ["version": version, "confirm_api_mode": true])
            prepared = nil; try await load()
            message = "API mode selected and prior task routes cleared. You must still choose a profile and approve each exact request."
        }
    }

    func prepare(task: String, focus: String, profileID: String) async {
        await perform("Preparing the exact prompt from current app evidence…") {
            prepared = nil; job = nil
            prepared = try JSONDecoder().decode(Prepared.self, from: await call("prepare", ["task": task, "focus": focus, "connection_id": profileID]))
            requestKey = UUID().uuidString.lowercased()
        }
    }

    func approve() async {
        guard let approved = prepared else { return }
        await perform("Recording approval, sending one model request and checking the returned draft…") {
            let proposal = approved.proposal
            let queued = try JSONDecoder().decode(Job.self, from: await call("start", ["task": proposal.task,
                "focus": proposal.focus, "connection_id": proposal.connection_id, "source_hash": approved.source_hash,
                "request_key": requestKey, "confirm_transmission": true]))
            job = queued
            job = try JSONDecoder().decode(Job.self, from: await call("run", ["id": queued.id]))
            try await load()
            prepared = nil
            message = job?.status == "SUCCEEDED"
                ? "Draft saved. Review its cited sources and unknowns before using it. No campaign was published."
                : "Request needs inspection. Provider usage may have occurred; review the saved result before approving another call."
        }
    }

    func open(_ identity: String) async {
        await perform("Reading the saved inference request…") {
            job = try JSONDecoder().decode(Job.self, from: await call("read", ["id": identity]))
            prepared = nil
        }
    }

    func reconcile() async {
        guard let identity = job?.id else { return }
        await perform("Checking the existing request without automatic replay…") {
            job = try JSONDecoder().decode(Job.self, from: await call("run", ["id": identity]))
            try await load()
        }
    }

    func discardPreview() { if !busy { prepared = nil } }
}

@MainActor
struct NativeInferenceView: View {
    @ObservedObject var model: NativeInferenceModel
    @Environment(\.dismiss) private var dismiss
    @State private var task = "connection_test"
    @State private var focus = ""
    @State private var profileID = ""
    @State private var approved = false
    @State private var changeMode = false

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Text("Ask your selected API model to draft app-marketing work from reviewed app evidence. You inspect the complete prompt before anything is sent.")
                    Text("The provider may charge for the request. Model drafts are proposals, not verified results or campaign authority.").font(.callout)
                }
                Section("Choose this request") {
                    Picker("API profile", selection: $profileID) {
                        Text("Choose a saved profile").tag("")
                        ForEach(model.profiles?.profiles.filter { $0.status != "DISCONNECTED" } ?? []) { profile in
                            Text("\(profile.data.label) · \(profile.status)").tag(profile.id)
                        }
                    }
                    Picker("Task", selection: $task) {
                        Text("Test provider connection").tag("connection_test")
                        Text("Plan campaign work").tag("campaign_plan")
                        Text("Draft original copy").tag("original_copy")
                        Text("Critique an experiment").tag("experiment_critique")
                    }
                    TextField("Specific app-marketing focus", text: $focus, axis: .vertical)
                    Text("Test a configured profile first. Draft tasks also require API access mode; switching mode clears prior task routes.").font(.caption)
                    Text("Current access mode: \(model.profiles?.routing.data.mode ?? "Unknown")").font(.caption)
                    Button("Switch this app to API access mode") { changeMode = true }.disabled(model.busy)
                    Button("Review exact prompt") { approved = false; Task { await model.prepare(task: task, focus: focus, profileID: profileID) } }
                        .disabled(model.busy || profileID.isEmpty)
                }.disabled(model.busy)
                if let prepared = model.prepared {
                    Section("Review before transmission") {
                        Text("API endpoint: \(prepared.destination)").font(.callout).textSelection(.enabled)
                        Text("\(prepared.proposal.provider) · \(prepared.proposal.model)").font(.headline)
                        Text("Maximum output: \(prepared.proposal.max_output_tokens) tokens")
                        Text(prepared.cost).font(.callout)
                        Text(prepared.proposal.prompt).font(.body).textSelection(.enabled)
                        Text("Approved source hash: \(prepared.source_hash)").font(.caption).textSelection(.enabled)
                        Toggle("I approve sending this exact prompt to this API provider and using its allowance", isOn: $approved)
                        Button("Send approved request once") { Task { await model.approve(); approved = false } }
                            .disabled(model.busy || !approved)
                    }
                }
                if model.busy { Section { ProgressView(model.activity) } }
                if let message = model.message { Section("Action result") { Text(message) } }
                if let job = model.job {
                    Section("Saved request · \(job.status)") {
                        Text(job.id).font(.caption).textSelection(.enabled)
                        if let draft = job.result?.draft {
                            Text(draft.summary).font(.headline)
                            ForEach(Array(draft.items.enumerated()), id: \.offset) { row in
                                VStack(alignment: .leading, spacing: 6) {
                                    Text(row.element.title).font(.headline)
                                    Text(row.element.detail)
                                    Text("Sources: \(row.element.source_ids.joined(separator: ", "))").font(.caption)
                                }
                            }
                            ForEach(Array(draft.unknowns.enumerated()), id: \.offset) { row in Text("Unknown: \(row.element)") }
                        }
                        if let usage = job.result?.usage {
                            ForEach(usage.keys.sorted(), id: \.self) { key in
                                Text("\(key.replacingOccurrences(of: "_", with: " ")): \(usage[key].flatMap { $0 }.map(String.init) ?? "Unknown")").font(.caption)
                            }
                        }
                        Text("Cost: \(job.result?.cost ?? "Unknown") · allowance: \(job.result?.quota ?? "Unknown")").font(.caption)
                        if let next = job.result?.next_action { Text(next) }
                        if ["QUEUED", "RUNNING"].contains(job.status) {
                            Button("Run queued request or reconcile expired attempt") { Task { await model.reconcile() } }.disabled(model.busy)
                            Text("An expired running request becomes unknown; it is never resent automatically.").font(.caption)
                        }
                    }
                }
                Section("Previous approved requests") {
                    if model.history.isEmpty { Text("No native inference requests recorded for this owner yet.") }
                    ForEach(model.history) { item in
                        Button("\(item.task.replacingOccurrences(of: "_", with: " ")) · \(item.status)") { Task { await model.open(item.id) } }.disabled(model.busy)
                    }
                }
            }
            .navigationTitle("Agent drafting")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Done") { dismiss() }.disabled(model.busy) }
                ToolbarItem(placement: .primaryAction) { Button("Refresh") { Task { await model.refresh() } }.disabled(model.busy) }
            }
            .confirmationDialog("Switch to API mode and clear previous task routes?", isPresented: $changeMode) {
                Button("Use API access mode") { approved = false; Task { await model.useAPIMode() } }
            } message: { Text("No inference runs from this change. You still select a profile and review each exact request.") }
            .onChange(of: task) { _, _ in approved = false; model.discardPreview() }
            .onChange(of: focus) { _, _ in approved = false; model.discardPreview() }
            .onChange(of: profileID) { _, _ in approved = false; model.discardPreview() }
            .task { await model.refresh() }
            .interactiveDismissDisabled(model.busy)
        }.privacySensitive()
    }
}
