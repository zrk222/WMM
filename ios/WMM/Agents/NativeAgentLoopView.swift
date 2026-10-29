import Foundation
import SwiftUI

/// Model proposals, scoped tool effects and human checkpoints remain separate receipts.
@MainActor
final class NativeAgentLoopModel: ObservableObject, Identifiable {
    struct Prepared: Decodable {
        struct Proposal: Decodable { let provider: String; let model: String; let prompt: String; let native_turn: Int }
        let proposal: Proposal; let source_hash: String; let destination: String; let cost: String
    }
    struct History: Decodable {
        struct Item: Decodable, Identifiable { let id: String; let status: String; let turn: Int; let tool_dispatch: String }
        let items: [Item]
    }
    let id = UUID()
    let appID: String
    @Published private(set) var profiles: NativeInferenceModel.Profiles?
    @Published private(set) var grants: [NativeAgentGrant] = []
    @Published private(set) var history: [History.Item] = []
    @Published private(set) var prepared: Prepared?
    @Published private(set) var job: [String: Any]?
    @Published private(set) var toolReceipt: String?
    @Published private(set) var reviewID = ""
    @Published private(set) var busy = false
    @Published private(set) var activity = ""
    @Published private(set) var message: String?
    private var preparedRequest: [String: Any]?
    private var requestKey = UUID().uuidString.lowercased()
    private var closed = false
    private let execute: @MainActor (String, Data) async throws -> Data
    private let dispatch: @MainActor (String, Data) async throws -> Data
    private let review: @MainActor (String, String, Data) async throws -> Data
    private let teardown: @MainActor () async -> Void

    init(appID: String, execute: @escaping @MainActor (String, Data) async throws -> Data,
         dispatch: @escaping @MainActor (String, Data) async throws -> Data,
         review: @escaping @MainActor (String, String, Data) async throws -> Data,
         teardown: @escaping @MainActor () async -> Void) {
        self.appID = appID; self.execute = execute; self.dispatch = dispatch; self.review = review; self.teardown = teardown
    }
    static func bytes(_ value: [String: Any]) throws -> Data { try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]) }
    static func object(_ data: Data) throws -> [String: Any] {
        guard data.count <= 1_048_576, let value = try JSONSerialization.jsonObject(with: data) as? [String: Any] else { throw DomainBridge.Failure.invalidRequest }
        return value
    }
    static func display(_ value: [String: Any]) -> String {
        guard let bytes = try? JSONSerialization.data(withJSONObject: value, options: [.prettyPrinted, .sortedKeys]) else { return "Unavailable" }
        return String(decoding: bytes, as: UTF8.self)
    }
    var status: String { job?["status"] as? String ?? "No saved turn selected" }
    var jobID: String? { job?["id"] as? String }
    private var answer: [String: Any]? { (job?["result"] as? [String: Any])?["turn"] as? [String: Any] }
    var proposedEnvelope: [String: Any]? { answer?["kind"] as? String == "tool" ? answer?["envelope"] as? [String: Any] : nil }
    var canDispatch: Bool { status == "SUCCEEDED" && proposedEnvelope != nil && job?["tool_dispatch"] as? String == "NOT_RESERVED" }
    var canContinue: Bool { proposedEnvelope != nil && job?["tool_dispatch"] as? String == "RESERVED_RECONCILE_REQUIRED" }
    var finalSummary: String? { answer?["kind"] as? String == "final" ? answer?["summary"] as? String : nil }
    var savedJSON: String { job.map(Self.display) ?? "No saved turn" }
    private var savedRequest: [String: Any]? { (job?["data"] as? [String: Any])?["request"] as? [String: Any] }
    private func call(_ action: String, _ body: [String: Any] = [:]) async throws -> Data { try await execute(action, Self.bytes(body)) }
    private func load() async throws {
        profiles = try JSONDecoder().decode(NativeInferenceModel.Profiles.self, from: await call("profiles"))
        grants = try JSONDecoder().decode(NativeAgentAccessModel.Listing.self, from: await call("grants")).grants
        history = try JSONDecoder().decode(History.self, from: await call("history")).items
    }
    private func perform(_ label: String, _ work: () async throws -> Void) async {
        guard !busy, !closed else { return }; busy = true; activity = label; message = nil
        defer { busy = false; activity = "" }
        do { try await work() }
        catch { message = "The step was not confirmed. Read the saved turn and action receipts before retrying. A model request may have used provider allowance. Reserved actions are not automatically repeated." }
    }
    func refresh() async { await perform("Reading your profiles, grants and saved turns…") { try await load() } }
    func useAPIMode() async {
        guard let version = profiles?.routing.version else { return }
        await perform("Saving API access mode…") {
            _ = try await call("api_mode", ["version": version, "confirm_api_mode": true]); discard(); try await load()
        }
    }
    func prepare(task: String, focus: String, profile: String, grant: String, operations: Set<String>) async {
        await perform("Building the exact prompt from current app evidence…") {
            let request: [String: Any] = ["task": task, "focus": focus, "connection_id": profile, "grant_id": grant,
                "operations": operations.sorted(), "previous_turn_id": NSNull(), "feedback": NSNull()]
            try await preview(request)
            job = nil; toolReceipt = nil; reviewID = ""
        }
    }
    private func preview(_ request: [String: Any]) async throws {
        discard()
        let value = try JSONDecoder().decode(Prepared.self, from: await call("prepare", request))
        guard !closed else { throw DomainBridge.Failure.closed }
        prepared = value; preparedRequest = request; requestKey = UUID().uuidString.lowercased()
    }
    func approve() async {
        guard let approved = prepared, let request = preparedRequest else { return }
        await perform("Saving approval and sending this model turn once…") {
            job = try Self.object(await call("start", ["request": request, "source_hash": approved.source_hash,
                "request_key": requestKey, "confirm_transmission": true]))
            guard !closed else { throw DomainBridge.Failure.closed }
            discard()
            guard let identity = jobID else { throw DomainBridge.Failure.invalidRequest }
            activity = "Waiting for the selected model's response…"
            job = try Self.object(await call("run", ["id": identity]))
            guard !closed else { throw DomainBridge.Failure.closed }
            activity = "Reading the saved proposal and provider usage…"; try await load()
            message = "Model turn saved. A proposed action has not run. Inspect it before using the scoped tool controls."
        }
    }
    func open(_ identity: String) async {
        await perform("Reading the existing turn without replay…") {
            job = try Self.object(await call("read", ["id": identity])); discard(); toolReceipt = nil; reviewID = ""
        }
    }
    func runQueued() async {
        guard let identity = jobID, ["READY", "RUNNING"].contains(status) else { return }
        await perform("Reconciling the saved model request…") { job = try Self.object(await call("run", ["id": identity])); try await load() }
    }
    func cancelTurn() async {
        guard let identity = jobID else { return }
        await perform("Cancelling the saved model turn…") { job = try Self.object(await call("cancel", ["id": identity])); try await load() }
    }
    func runTool() async {
        guard canDispatch, let identity = jobID, let grantID = savedRequest?["grant_id"] as? String else { return }
        await perform("Reserving this action once and checking its current grant…") {
            let reserved = try Self.object(await call("reserve_tool", ["id": identity]))
            job = try Self.object(await call("read", ["id": identity]))
            guard !closed else { throw DomainBridge.Failure.closed }
            guard let envelope = reserved["envelope"] as? [String: Any], let operation = envelope["operation"] as? String,
                  let grant = grants.first(where: { $0.id == grantID }) else { throw DomainBridge.Failure.invalidRequest }
            let result: Data
            if grant.review_operations.contains(operation) {
                activity = "Saving the independent human checkpoint…"
                reviewID = "turn-" + identity
                result = try await review(grantID, "prepare", Self.bytes(["id": reviewID, "envelope": envelope]))
                message = "Human checkpoint saved as \(reviewID). Open Human review for the independent check, then inspect this exact checkpoint here. No business action has run."
            } else {
                activity = "Executing the selected scoped action…"
                result = try await dispatch(grantID, Self.bytes(envelope))
                message = "Scoped tool returned a receipt. Inspect its recorded status; provider proposals and prepared packets do not prove publication or app sales."
            }
            guard !closed else { throw DomainBridge.Failure.closed }
            toolReceipt = Self.display(try Self.object(result)); try await load()
        }
    }
    func prepareReservedReview() async {
        guard canContinue, let identity = jobID, let envelope = proposedEnvelope,
              let grantID = savedRequest?["grant_id"] as? String else { return }
        await perform("Creating or reading this reserved action's exact checkpoint…") {
            let checkpoint = "turn-" + identity
            let result = try await review(grantID, "prepare", Self.bytes(["id": checkpoint, "envelope": envelope]))
            guard !closed else { throw DomainBridge.Failure.closed }
            reviewID = checkpoint; toolReceipt = Self.display(try Self.object(result))
            message = "Checkpoint retained. Complete its independent check in Human review, then inspect this exact checkpoint. This does not repeat the business action."
        }
    }
    func inspectReview(_ identity: String, resume: Bool) async {
        guard let expected = proposedEnvelope, let grantID = savedRequest?["grant_id"] as? String else { return }
        await perform(resume ? "Completing the exact approved checkpoint…" : "Reading the saved human checkpoint…") {
            let inspected = try Self.object(await review(grantID, "inspect", Self.bytes(["id": identity, "app_id": appID])))
            guard let envelope = inspected["envelope"] as? [String: Any], try Self.bytes(envelope) == Self.bytes(expected) else { throw DomainBridge.Failure.invalidRequest }
            var result = inspected
            if resume {
                if inspected["result"] is [String: Any] {
                    result = try Self.object(await review(grantID, "recover", Self.bytes(["id": identity, "app_id": appID])))
                } else {
                    guard let checkpoint = inspected["checkpoint"] as? [String: Any], let revision = checkpoint["revision"] as? Int,
                          let hash = checkpoint["hash"] as? String else { throw DomainBridge.Failure.invalidRequest }
                    result = try Self.object(await review(grantID, "resume", Self.bytes(["id": identity, "app_id": appID, "revision": revision, "packet_hash": hash])))
                }
            }
            reviewID = identity; toolReceipt = Self.display(result)
        }
    }
    func prepareContinuation(note: String) async {
        guard canContinue, let identity = jobID, var request = savedRequest else { return }
        await perform("Preparing your reviewed feedback as a new transmission…") {
            // The backend labels this as caller-supplied feedback, never verified proof.
            request["previous_turn_id"] = identity
            request["feedback"] = ["owner_note": note, "receipt_available_locally": toolReceipt != nil]
            try await preview(request)
        }
    }
    func discard() { prepared = nil; preparedRequest = nil }
    func close() async { closed = true; discard(); await teardown() }
}

@MainActor
struct NativeAgentLoopView: View {
    @ObservedObject var model: NativeAgentLoopModel
    @Environment(\.dismiss) private var dismiss
    @State private var profile = ""
    @State private var grant = ""
    @State private var selected: Set<String> = ["workspace.read"]
    @State private var task = "campaign_plan"
    @State private var focus = ""
    @State private var transmission = false
    @State private var confirmTool = false
    @State private var confirmMode = false
    @State private var checkpoint = ""
    @State private var feedback = ""
    var body: some View {
        NavigationStack {
            List {
                Section {
                    Text("Give your agent an app-marketing job. Review the prompt, inspect its proposed action, then follow the saved tool receipt.")
                    Text("Each model turn uses your selected API allowance. This bounded workflow allows three turns and up to ten granted operations; every new transmission needs your confirmation. Human checkpoints remain in force.").font(.callout)
                }
                Section("Choose the job and access") {
                    Picker("API profile", selection: $profile) {
                        Text("Choose a configured profile").tag("")
                        ForEach(model.profiles?.profiles.filter { $0.status != "DISCONNECTED" } ?? []) { Text($0.data.label).tag($0.id) }
                    }
                    Picker("Agent grant", selection: $grant) {
                        Text("Choose an active scoped grant").tag("")
                        ForEach(model.grants.filter { $0.status == "ACTIVE" }) { Text($0.agent_id).tag($0.id) }
                    }
                    DisclosureGroup("Allowed operations · \(selected.count)/10") {
                        ForEach(model.grants.first(where: { $0.id == grant })?.operations ?? [], id: \.self) { name in
                            Toggle(name, isOn: Binding(get: { selected.contains(name) }, set: { enabled in
                                model.discard(); transmission = false
                                if enabled, selected.count < 10 { selected.insert(name) } else { selected.remove(name) }
                            }))
                        }
                    }
                    Picker("Task", selection: $task) {
                        Text("Plan campaign work").tag("campaign_plan")
                        Text("Draft original copy").tag("original_copy")
                        Text("Critique an experiment").tag("experiment_critique")
                    }
                    TextField("What should the agent accomplish for this app?", text: $focus, axis: .vertical)
                    Text("Set up API keys in Provider access and issue a scoped grant in Your agent access. Current API mode: \(model.profiles?.routing.data.mode ?? "Unknown").").font(.caption)
                    Button("Select API access mode") { confirmMode = true }
                    Button("Review the exact agent prompt") { transmission = false; Task { await model.prepare(task: task, focus: focus, profile: profile, grant: grant, operations: selected) } }
                        .disabled(profile.isEmpty || grant.isEmpty || selected.isEmpty || focus.isEmpty)
                }.disabled(model.busy)
                if let prepared = model.prepared {
                    Section("Review model transmission · turn \(prepared.proposal.native_turn)/3") {
                        Text("\(prepared.proposal.provider) · \(prepared.proposal.model)")
                        Text(prepared.destination).textSelection(.enabled)
                        Text(prepared.cost).font(.callout)
                        Text(prepared.proposal.prompt).textSelection(.enabled)
                        Text("Source hash: \(prepared.source_hash)").font(.caption).textSelection(.enabled)
                        Toggle("I approve this exact prompt, destination and API allowance use", isOn: $transmission)
                        Button("Send approved turn once") { transmission = false; Task { await model.approve() } }.disabled(!transmission || model.busy)
                    }
                }
                if model.job != nil {
                    Section("Saved turn · \(model.status)") {
                        if let identity = model.jobID { Text(identity).font(.caption).textSelection(.enabled) }
                        if let summary = model.finalSummary { Text(summary) }
                        if let envelope = model.proposedEnvelope {
                            Text(NativeAgentLoopModel.display(envelope)).textSelection(.enabled)
                            Button("Run this scoped action") { confirmTool = true }.disabled(!model.canDispatch || model.busy)
                            Text("An action is reserved once before dispatch. An interrupted reservation needs receipt inspection; it is not silently repeated.").font(.caption)
                        }
                        if ["READY", "RUNNING"].contains(model.status) {
                            Button("Reconcile saved model turn") { Task { await model.runQueued() } }.disabled(model.busy)
                            Button("Cancel model turn", role: .destructive) { Task { await model.cancelTurn() } }.disabled(model.busy)
                        }
                        if let receipt = model.toolReceipt { Text(receipt).textSelection(.enabled) }
                        DisclosureGroup("Saved turn details") { Text(model.savedJSON).font(.caption).textSelection(.enabled) }
                    }
                    if model.canContinue {
                        Section("Human checkpoint and next turn") {
                            Text("Saved checkpoint: \(model.reviewID.isEmpty ? "Inspect Human review for this app" : model.reviewID)").textSelection(.enabled)
                            Button("Create or recover required checkpoint") { Task { await model.prepareReservedReview() } }.disabled(model.busy)
                            TextField("Exact checkpoint ID to inspect", text: $checkpoint).textInputAutocapitalization(.never).autocorrectionDisabled()
                            Button("Inspect checkpoint") { Task { await model.inspectReview(checkpoint.isEmpty ? model.reviewID : checkpoint, resume: false) } }.disabled(model.busy)
                            Button("Complete or reconcile approved checkpoint") { Task { await model.inspectReview(checkpoint.isEmpty ? model.reviewID : checkpoint, resume: true) } }.disabled(model.busy)
                            TextField("Your factual feedback for the next model turn", text: $feedback, axis: .vertical)
                            Text("Feedback is your unverified account of the result. Review the full next prompt before sharing it; no receipt or private tool output is transmitted automatically.").font(.caption)
                            Button("Review next prompt with this feedback") { transmission = false; Task { await model.prepareContinuation(note: feedback) } }.disabled(model.busy || feedback.isEmpty)
                        }
                    }
                }
                Section("Saved turn history") {
                    if model.history.isEmpty { Text("No model turns saved for this app. Choose a tested API profile and a scoped grant to begin.") }
                    ForEach(model.history) { item in Button("Turn \(item.turn) · \(item.status) · \(item.tool_dispatch)") { Task { await model.open(item.id) } }.disabled(model.busy) }
                }
                if model.busy { Section { ProgressView(model.activity).accessibilityIdentifier("agent-loop-progress") } }
                if let message = model.message { Section("Step result") { Text(message).accessibilityIdentifier("agent-loop-message") } }
            }
            .navigationTitle("Agent work")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Done") { dismiss() }.disabled(model.busy) }
                ToolbarItem(placement: .primaryAction) { Button("Refresh") { Task { await model.refresh() } }.disabled(model.busy) }
            }
            .confirmationDialog("Execute this exact proposed action under its scoped grant?", isPresented: $confirmTool) {
                Button("Reserve and run scoped action") { Task { await model.runTool() } }
            } message: { Text("Required human checks still apply. Inspect the saved result before approving a later model transmission.") }
            .confirmationDialog("Select API mode and clear previous task routes?", isPresented: $confirmMode) {
                Button("Use API access mode") { Task { await model.useAPIMode() } }
            } message: { Text("Each model turn still needs its own reviewed prompt and confirmation.") }
            .onChange(of: profile) { _, _ in model.discard(); transmission = false }
            .onChange(of: grant) { _, value in
                selected = model.grants.first(where: { $0.id == value })?.operations.contains("workspace.read") == true ? ["workspace.read"] : []
                model.discard(); transmission = false
            }
            .onChange(of: task) { _, _ in model.discard(); transmission = false }
            .onChange(of: focus) { _, _ in model.discard(); transmission = false }
            .onChange(of: feedback) { _, _ in model.discard(); transmission = false }
            .task { await model.refresh() }
            .onDisappear { Task { await model.close() } }
            .interactiveDismissDisabled(model.busy)
        }.privacySensitive()
    }
}
