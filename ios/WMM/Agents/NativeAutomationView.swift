import Foundation
import SwiftUI

@MainActor
final class NativeAutomationModel: ObservableObject, Identifiable {
    struct Choice: Identifiable { let id: String; let name: String; let blockers: [String] }
    struct Policy: Decodable, Identifiable {
        struct Scope: Decodable { let operations: [String] }
        struct Usage: Decodable { let used: Int; let max_calls: Int; let expires: String }
        struct Execution: Decodable, Identifiable { let id: String; let operation: String; let status: String }
        let id: String; let version: Int; let status: String; let effective_status: String; let grant_id: String
        let repair: String?; let usage: Usage?; let executions: [Execution]
        let summary: Scope?
    }
    let id = UUID()
    let appID: String; let manifestVersion: Int; let currency: String
    @Published private(set) var choices: [Choice] = []
    @Published private(set) var profiles: [NativeProviderModel.Profile] = []
    @Published private(set) var policies: [Policy] = []
    @Published private(set) var busy = false
    @Published private(set) var message: String?
    @Published private(set) var summary = ""
    @Published private(set) var blockers: [String] = []
    @Published private(set) var ready = false
    @Published private(set) var activity = ""
    @Published private(set) var jobProgress: NativeJobProgress?
    @Published private(set) var pendingJob: String?
    private var preparationKey = UUID().uuidString.lowercased()
    private var preview: [String: Any]?
    private let runtime: ScopedAgentRuntime
    private let execute: @MainActor (String, Data) async throws -> Data

    init(appID: String, manifestVersion: Int, currency: String, runtime: ScopedAgentRuntime,
         execute: @escaping @MainActor (String, Data) async throws -> Data) {
        self.appID = appID; self.manifestVersion = manifestVersion; self.currency = currency
        self.runtime = runtime; self.execute = execute
    }
    private func call(_ action: String, _ body: [String: Any] = [:]) async throws -> Data {
        try await execute(action, JSONSerialization.data(withJSONObject: body))
    }
    private func load() async throws {
        let bytes = try await call("status")
        guard let object = try JSONSerialization.jsonObject(with: bytes) as? [String: Any],
              let rows = object["policies"] as? [[String: Any]],
              let catalog = object["catalog"] as? [String: Any],
              let workflows = catalog["workflows"] as? [String: [String: Any]] else { throw DomainBridge.Failure.invalidRequest }
        policies = try JSONDecoder().decode([Policy].self, from: JSONSerialization.data(withJSONObject: rows))
        let native = object["native_blockers"] as? [[String: String]] ?? []
        choices = workflows.keys.sorted().map { key in
            let row = workflows[key] ?? [:]
            let reasons = native.filter { $0["workflow"] == key }.compactMap { $0["reason"] }
            return Choice(id: key, name: row["name"] as? String ?? key,
                blockers: Array(Set((row["blockers"] as? [String] ?? []) + reasons)).sorted())
        }
        profiles = try JSONDecoder().decode(NativeProviderModel.Listing.self, from: await call("profiles")).profiles
            .filter { $0.status != "DISCONNECTED" }
    }
    func discardPreview() { preview = nil; summary = ""; blockers = []; ready = false }
    func refresh() async {
        guard !busy else { return }; busy = true; defer { busy = false }
        discardPreview(); message = nil
        do { try await load() }
        catch { message = "Standing approval could not be read. Unlock and refresh; existing scopes and receipts are retained." }
    }
    func prepare(agent: String, purpose: String, selected: Set<String>, profile: String, hours: Int, calls: Int, inflight: Int) async {
        guard !busy else { return }; busy = true; defer { busy = false }
        discardPreview(); message = nil
        do {
            let selection: [String: Any] = ["agent_id": agent, "manifest_version": manifestVersion,
                "workflows": selected.sorted(), "agent_connection_id": profile, "social_connection_ids": [String]()]
            let limits: [String: Any] = ["expires": ISO8601DateFormatter().string(from: Date().addingTimeInterval(Double(hours) * 3600)),
                "max_calls": calls, "max_inflight": inflight, "currency": currency, "spend_limit_minor": 0]
            let bytes = try await call("preview", ["selection": selection, "limits": limits, "purpose": purpose])
            guard let value = try JSONSerialization.jsonObject(with: bytes) as? [String: Any] else { throw DomainBridge.Failure.invalidRequest }
            preview = value
            let scoped = value["summary"] as? [String: Any] ?? [:]
            let inventory = scoped["inventory"] as? [String: Any] ?? [:]
            let workflowRows = inventory["workflows"] as? [[String: Any]] ?? []
            let nativeReasons = (value["blockers"] as? [[String: String]] ?? []).compactMap { $0["reason"] }
            blockers = Array(Set(nativeReasons + workflowRows.flatMap { $0["blockers"] as? [String] ?? [] })).sorted()
            ready = value["summary_hash"] is String && (inventory["scope_status"] as? String) == "READY_FOR_SCOPE_REVIEW" && blockers.isEmpty
            let display = scoped.isEmpty ? value : scoped
            summary = String(data: try JSONSerialization.data(withJSONObject: display, options: [.prettyPrinted, .sortedKeys]), encoding: .utf8) ?? ""
            message = ready ? "Your exact scope is ready to review. Nothing has been activated." : "This scope has setup or workflow gaps. Resolve the listed items before approval."
        } catch { message = "Scope preparation was not confirmed. Choose a connected profile, current workflows and a purpose, then refresh before trying again." }
    }
    func activate(confirmed: Bool) async {
        guard !busy, confirmed, ready, let preview,
              let proposal = preview["proposal"] as? [String: Any], let hash = preview["summary_hash"] as? String else { return }
        busy = true; defer { busy = false }; message = nil
        do {
            let bytes = try await call("activate", ["proposal": proposal, "summary_hash": hash, "confirm_scope": true])
            _ = try await runtime.retainIssuedGrant(bytes)
            discardPreview(); try await load()
            message = "Standing scope saved and its grant stored in device-only Keychain. This grants the listed local operations; it does not start an agent or prove a campaign ran."
        } catch {
            discardPreview(); try? await load()
            message = "Activation or protected token storage was not confirmed. Inspect saved scopes below; switch any unusable active scope OFF before creating another."
        }
    }
    func off(_ policy: Policy) async {
        guard !busy else { return }; busy = true; defer { busy = false }; discardPreview()
        do {
            _ = try await call("off", ["id": policy.id, "version": policy.version, "confirm_off": true])
            try await runtime.forgetCredential(grantID: policy.grant_id)
            try await load()
            message = "Standing approval is OFF. New admissions are denied; inspect existing receipts for already dispatched work."
        } catch { message = "OFF was not confirmed. Refresh the exact saved scope before trying again." }
    }
    func close() async { await runtime.cancel() }

    func preparePipeline(_ policy: Policy) async {
        guard !busy, policy.effective_status == "ACTIVE", policy.summary?.operations.contains("pipeline.prepare") == true else { return }
        busy = true; defer { busy = false; activity = "" }; message = nil
        do {
            if pendingJob == nil {
                activity = "Admitting preparation under your exact standing scope…"
                let envelope: [String: Any] = ["app_id": appID, "operation": "pipeline.prepare",
                    "input": ["action": "pipeline", "data": ["stage": 0], "request_key": preparationKey] as [String: Any]]
                let bytes = try await runtime.call(grantID: policy.grant_id,
                    request: JSONSerialization.data(withJSONObject: envelope))
                struct Queued: Decodable { let id: String }
                pendingJob = try JSONDecoder().decode(Queued.self, from: bytes).id
            }
            try await runPending()
        } catch {
            try? await loadProgress()
            message = "Preparation was not confirmed. Inspect saved work before retrying. Its request key and any admitted job are retained."
        }
    }
    private func loadProgress() async throws {
        jobProgress = try JSONDecoder().decode(NativeJobProgress.self, from: await call("monitor_jobs"))
    }
    private func runPending() async throws {
        guard let identity = pendingJob else { return }
        try await loadProgress()
        activity = "Checking the current scope and preparing twelve evidence stages…"
        struct Finished: Decodable { let status: String }
        let bytes = try await call("run_job", ["id": identity])
        let result = try JSONDecoder().decode(Finished.self, from: bytes)
        try await loadProgress(); try await load()
        if ["SUCCEEDED", "FAILED", "CANCELLED"].contains(result.status) {
            pendingJob = nil; preparationKey = UUID().uuidString.lowercased()
        }
        message = "Preparation returned \(result.status). Review its stage observations below. Prepared packets do not establish publication or measured app sales."
    }
    func resumePreparation() async {
        guard !busy, pendingJob != nil else { return }; busy = true; defer { busy = false; activity = "" }
        do { try await runPending() }
        catch { try? await loadProgress(); message = "Resume was denied or not confirmed. Inspect the job's scope, expiry and live lease before retrying." }
    }
    func refreshProgress() async {
        guard !busy else { return }; busy = true; defer { busy = false }
        do { try await loadProgress() }
        catch { message = "Progress could not be read. Unlock and refresh; the durable job remains saved." }
    }
}

@MainActor
struct NativeAutomationView: View {
    @ObservedObject var model: NativeAutomationModel
    @Environment(\.dismiss) private var dismiss
    @State private var agent = "personal-agent"
    @State private var purpose = ""
    @State private var profile = ""
    @State private var selected: Set<String> = []
    @State private var hours = 1
    @State private var calls = 100
    @State private var inflight = 1
    @State private var approved = false
    @State private var stopping: NativeAutomationModel.Policy?

    private var inputs: [String] { [agent, purpose, profile, String(hours), String(calls), String(inflight)] + selected.sorted() }
    private var scopeControls: some View {
        Section("Choose your agent's job") {
            TextField("Agent name", text: $agent).textInputAutocapitalization(.never).autocorrectionDisabled()
            TextField("What should this work achieve?", text: $purpose, axis: .vertical)
            Picker("Connected API profile", selection: $profile) {
                Text("Choose a protected profile").tag("")
                ForEach(model.profiles) { item in Text("\(item.data.label) · \(item.status)").tag(item.id) }
            }
            Text("Onboard and test the chosen profile through Provider access and Agent drafting first.").font(.callout)
            ForEach(model.choices) { choice in
                Toggle(choice.name, isOn: Binding(get: { selected.contains(choice.id) }, set: { value in
                    if value { selected.insert(choice.id) } else { selected.remove(choice.id) }
                }))
                if !choice.blockers.isEmpty { Text(choice.blockers.joined(separator: ", ").replacingOccurrences(of: "_", with: " ").lowercased()).font(.caption) }
            }
        }
    }
    private var limitsControls: some View {
        Section("Set the boundaries") {
            Stepper("Expires in \(hours) hours", value: $hours, in: 1...24)
            Stepper("Maximum \(calls) tool calls", value: $calls, in: 1...10000)
            Stepper("Maximum \(inflight) operations in flight", value: $inflight, in: 1...8)
            Text("Spending limit: 0 \(model.currency). Provider requests keep their separate approval and allowance checks.").font(.callout)
            Button("Review this exact scope") { approved = false; Task {
                await model.prepare(agent: agent, purpose: purpose, selected: selected, profile: profile,
                    hours: hours, calls: calls, inflight: inflight)
            }}.disabled(selected.isEmpty || profile.isEmpty || purpose.isEmpty || agent.isEmpty)
        }
    }
    @ViewBuilder private var approvalControls: some View {
        if !model.summary.isEmpty {
            Section("Review before switching ON") {
                Text("App: \(model.appID) · revision \(model.manifestVersion)")
                Text("Purpose: \(purpose)")
                Text("\(selected.count) workflows · \(hours) hours · \(calls) calls · \(inflight) in flight")
                ForEach(model.blockers, id: \.self) { Text($0.replacingOccurrences(of: "_", with: " ").lowercased()) }
                DisclosureGroup("Exact operations, credentials and stop rules") { Text(model.summary).font(.caption).textSelection(.enabled) }
                Toggle("I approve the exact displayed scope", isOn: $approved).disabled(!model.ready)
                Button("Switch this standing scope ON") { Task { await model.activate(confirmed: approved); approved = false } }
                    .disabled(!approved || !model.ready)
            }
        }
    }
    private var savedScopes: some View {
        Section("Saved scopes and receipts") {
            if model.policies.isEmpty { Text("No standing scope saved. Choose a limited job above to prepare your first scope.") }
            ForEach(model.policies) { policy in
                VStack(alignment: .leading, spacing: 8) {
                    Text(policy.effective_status).font(.headline)
                    Text("Scope \(policy.id) · revision \(policy.version)").font(.caption).textSelection(.enabled)
                    if let usage = policy.usage { Text("\(usage.used)/\(usage.max_calls) calls · expires \(usage.expires)").font(.callout) }
                    if let repair = policy.repair { Text(repair).font(.callout) }
                    if policy.summary?.operations.contains("pipeline.prepare") == true {
                        Button("Prepare twelve stages with this agent scope") { Task { await model.preparePipeline(policy) } }
                            .disabled(policy.effective_status != "ACTIVE" || model.pendingJob != nil)
                    }
                    ForEach(policy.executions) { item in Text("\(item.operation) · \(item.status) · receipt \(item.id)").font(.caption).textSelection(.enabled) }
                    Button("Switch this scope OFF", role: .destructive) { stopping = policy }.disabled(policy.status != "ACTIVE")
                }
            }
        }
    }
    var body: some View {
        NavigationStack {
            Form {
                Section { Text("Set the local work your agent may do without asking at every step. Review its exact permissions, expiry and limits, then switch the scope ON. You can switch it OFF here.")
                    Text("Standing approval grants authority. It does not start an agent or keep iOS running in the background. Execution and device acceptance remain under test.").font(.callout) }
                scopeControls
                limitsControls
                approvalControls
                if let message = model.message { Section("Current result") { Text(message) } }
                if let progress = model.jobProgress {
                    Section("Preparation progress") {
                        Text("Observed at \(progress.observed_at)").font(.caption)
                        ForEach(progress.runs) { run in
                            Text("\(run.status) · \(run.processed_stages) stages checked · \(run.blocked_stages) with gaps")
                            Text(run.activity).font(.callout)
                            DisclosureGroup("Stage observations") {
                                ForEach(Array(run.events.enumerated()), id: \.offset) { item in
                                    Text("\(item.element.observed_at) · \(item.element.message)").font(.caption)
                                }
                            }
                        }
                        Button("Refresh progress") { Task { await model.refreshProgress() } }
                        if model.pendingJob != nil { Button("Resume eligible preparation") { Task { await model.resumePreparation() } } }
                        Text("Reopen Work and recovery to inspect saved jobs after leaving this screen. A live lease cannot be restarted.").font(.caption)
                    }
                }
                savedScopes
            }.disabled(model.busy)
            .navigationTitle("Standing approval")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Done") { dismiss() }.disabled(model.busy) }
                ToolbarItem(placement: .primaryAction) { Button("Refresh") { approved = false; Task { await model.refresh() } }.disabled(model.busy) }
            }
            .overlay { if model.busy { ProgressView(model.activity.isEmpty ? "Checking current scope and protected access…" : model.activity).padding().background(.regularMaterial) } }
            .confirmationDialog("Switch this exact scope OFF?", isPresented: Binding(get: { stopping != nil }, set: { if !$0 { stopping = nil } })) {
                if let policy = stopping { Button("Switch OFF", role: .destructive) { Task { await model.off(policy) }; stopping = nil } }
            } message: { Text("New tool admissions stop. Existing effects and receipts remain available for inspection.") }
            .onChange(of: inputs) { _, _ in approved = false; model.discardPreview() }
            .task { await model.refresh() }
            .onDisappear { Task { await model.close() } }
            .interactiveDismissDisabled(model.busy)
        }.privacySensitive()
    }
}
