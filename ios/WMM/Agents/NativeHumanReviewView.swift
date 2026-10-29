import SwiftUI

@MainActor
final class NativeHumanReviewModel: ObservableObject, Identifiable {
    struct Member: Decodable, Identifiable {
        let principal: String; let login: String; let role: String; let status: String; let version: Int
        var id: String { principal }
    }
    struct Request: Identifiable {
        let id: String; let revision: Int; let hash: String; let state: String; let operation: String
    }
    struct Source: Decodable, Identifiable { let id: String; let title: String; let kind: String }
    struct Evidence: Identifiable {
        let id: String; let hash: String; let status: String; let available: Bool; let detail: String
    }
    let id = UUID()
    @Published var reviewer = ""
    @Published var ownerIdentity = ""
    @Published var reviewerPrincipal = ""
    @Published var members: [Member] = []
    @Published var requests: [Request] = []
    @Published var sources: [Source] = []
    @Published var evidence: [Evidence] = []
    @Published var nextOffset: Int?
    @Published var selectedEvidence: Evidence?
    @Published var selected: Request?
    @Published var detail = ""
    @Published var busy = false
    @Published var message: String?
    private let execute: (String, Data) async throws -> Data
    private let teardown: () async -> Void
    private var closed = false
    init(execute: @escaping (String, Data) async throws -> Data, teardown: @escaping () async -> Void) {
        self.execute = execute; self.teardown = teardown
    }

    private func call(_ action: String, _ body: [String: Any] = [:]) async throws -> [String: Any] {
        guard !closed else { throw DomainBridge.Failure.closed }
        let data = try await execute(action, JSONSerialization.data(withJSONObject: body))
        guard !closed else { throw DomainBridge.Failure.closed }
        guard let result = try JSONSerialization.jsonObject(with: data) as? [String: Any] else { throw DomainBridge.Failure.invalidRequest }
        return result
    }
    private func perform(_ work: () async throws -> Void) async {
        guard !busy, !closed else { return }; busy = true; message = nil; defer { busy = false }
        do { try await work() }
        catch { selected = nil; detail = ""; message = "The action was not confirmed. Refresh the current request and reviewer access before trying again." }
    }
    func close() async {
        closed = true
        reviewer = ""; reviewerPrincipal = ""; ownerIdentity = ""
        selected = nil; selectedEvidence = nil; detail = ""; requests = []; evidence = []
        // Teardown never uses the busy-guarded action path. An in-flight login
        // must be followed by session removal even after its view disappears.
        await teardown()
    }
    private func load() async throws {
        let owner = try await call("owner_identity_status")
        ownerIdentity = owner["login"] as? String ?? ""
        let status = try await call("reviewer_status")
        reviewer = status["login"] as? String ?? ""
        reviewerPrincipal = status["principal"] as? String ?? ""
        let access = try await call("members_list")
        members = try JSONDecoder().decode([Member].self, from: JSONSerialization.data(withJSONObject: access["members"] ?? []))
        let records = try await call("review_sources")
        sources = try JSONDecoder().decode([Source].self, from: JSONSerialization.data(withJSONObject: records["items"] ?? []))
        let reviews = try await call("review_list")
        evidence = try (reviews["items"] as? [[String: Any]] ?? []).compactMap { row in
            guard let id = row["id"] as? String, let hash = row["hash"] as? String,
                  let status = row["status"] as? String else { return nil }
            let detail = String(data: try JSONSerialization.data(withJSONObject: row, options: [.prettyPrinted, .sortedKeys]), encoding: .utf8) ?? ""
            return Evidence(id: id, hash: hash, status: status, available: row["availability"] as? String == "CURRENT", detail: detail)
        }
        selectedEvidence = nil; nextOffset = nil
        requests = []; selected = nil; detail = ""
        if !reviewer.isEmpty {
            // A newly signed-in person may still need the owner's app role.
            if let listing = try? await call("agent_list") {
                nextOffset = listing["next_offset"] as? Int
                let rows = listing["items"] as? [[String: Any]] ?? []
                requests = rows.compactMap { row in
                    guard let id = row["id"] as? String else { return nil }
                    return Request(id: id, revision: row["revision"] as? Int ?? 0,
                        hash: row["checkpoint_hash"] as? String ?? "", state: row["state"] as? String ?? "UNKNOWN",
                        operation: row["operation"] as? String ?? "Agent request")
                }
            }
        }
    }
    func refresh() async { await perform { try await load() } }
    func loadMore() async {
        guard let offset = nextOffset else { return }
        await perform {
            let page = try await call("agent_list", ["offset": offset])
            let rows = page["items"] as? [[String: Any]] ?? []
            for row in rows {
                guard let id = row["id"] as? String else { continue }
                if !requests.contains(where: { $0.id == id }) {
                    requests.append(Request(id: id, revision: row["revision"] as? Int ?? 0,
                        hash: row["checkpoint_hash"] as? String ?? "", state: row["state"] as? String ?? "UNKNOWN",
                        operation: row["operation"] as? String ?? "Agent request"))
                }
            }
            nextOffset = page["next_offset"] as? Int
        }
    }
    func prepareEvidence(_ source: Source) async {
        await perform { _ = try await call("review_prepare", ["record_id": source.id]); try await load() }
    }
    func approveEvidence(_ item: Evidence) async {
        await perform {
            _ = try await call("review_approve", ["id": item.id, "hash": item.hash]); try await load()
            message = "The exact evidence packet has a recorded review. No campaign or external change was executed."
        }
    }
    func login(_ token: String) async {
        await perform { _ = try await call("reviewer_login", ["token": token]); try await load() }
    }
    func loginOwner(_ token: String) async {
        await perform { _ = try await call("owner_identity_login", ["token": token]); try await load() }
    }
    func logout() async {
        await perform {
            _ = try await call("reviewer_logout"); reviewer = ""; reviewerPrincipal = ""
            requests = []; selected = nil; detail = ""; message = "Reviewer signed out. Pending requests retain their recorded state."
        }
    }
    func assign(role: String, status: String) async {
        await perform {
            let version = members.first(where: { $0.principal == reviewerPrincipal })?.version
            _ = try await call("member_save", ["role": role, "status": status, "version": version.map { $0 as Any } ?? NSNull()])
            try await load(); message = "App access saved for the verified reviewer."
        }
    }
    func revoke(_ member: Member) async {
        await perform {
            _ = try await call("member_revoke", ["principal": member.principal, "version": member.version])
            try await load(); message = "Member access revoked. Previously approved requests must pass the current role checks before execution."
        }
    }
    func inspect(_ request: Request) async {
        await perform {
            let result = try await call("agent_inspect", ["id": request.id])
            guard let checkpoint = result["checkpoint"] as? [String: Any],
                  let revision = checkpoint["revision"] as? Int, let hash = checkpoint["hash"] as? String,
                  let state = checkpoint["state"] as? String else { throw DomainBridge.Failure.invalidRequest }
            selected = Request(id: request.id, revision: revision, hash: hash, state: state, operation: request.operation)
            detail = String(data: try JSONSerialization.data(withJSONObject: result, options: [.prettyPrinted, .sortedKeys]), encoding: .utf8) ?? ""
        }
    }
    func decide(_ request: Request, approve: Bool) async {
        await perform {
            var body: [String: Any] = ["id": request.id, "revision": request.revision]
            if approve { body["packet_hash"] = request.hash }
            _ = try await call(approve ? "agent_approve" : "agent_cancel", body)
            try await load()
            message = approve ? "This exact request is approved. The agent must resume it under its current grant; approval has not executed the action."
                : "Cancellation recorded. Inspect any work already running before assuming it stopped."
        }
    }
    func reconcile(_ request: Request, outcome: String, evidenceHash: String) async {
        await perform {
            _ = try await call("agent_reconcile", ["id": request.id, "revision": request.revision,
                "outcome": outcome, "evidence_hash": evidenceHash])
            try await load(); message = "The observed outcome was recorded with its evidence hash. This does not authorize replay."
        }
    }
}

@MainActor
struct NativeHumanReviewView: View {
    @ObservedObject var model: NativeHumanReviewModel
    @Environment(\.dismiss) private var dismiss
    @State private var token = ""
    @State private var approving = false
    @State private var cancelling = false
    @State private var changingRole = false
    @State private var ownerToken = ""
    @State private var revoking: NativeHumanReviewModel.Member?
    @State private var approvingEvidence = false
    @State private var reconciling = false
    @State private var outcome = "FAILED"
    @State private var evidenceHash = ""
    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text("Review your agent's exact proposal before it changes your app workspace.")
                    Text("A reviewer uses a different verified account, reads the saved input and approves its current revision. The owner controls who can review this app.").font(.callout)
                }
                Section("Owner account for independent review") {
                    if model.ownerIdentity.isEmpty {
                        SecureField("Owner GitHub token", text: $ownerToken).textInputAutocapitalization(.never).autocorrectionDisabled()
                        Text("Verify your own account first. Its public account identity is bound to this app; its token stays in memory. A reviewer must use a different account.").font(.caption)
                        Button("Verify owner account") {
                            let credential = ownerToken; ownerToken = ""
                            Task { await model.loginOwner(credential) }
                        }.disabled(ownerToken.isEmpty || model.busy)
                    } else { Text("Verified owner: \(model.ownerIdentity)") }
                }
                Section("Reviewer identity") {
                    if model.reviewer.isEmpty {
                        SecureField("Reviewer GitHub token", text: $token).textInputAutocapitalization(.never).autocorrectionDisabled()
                        Text("Use the reviewer's own personal access token. Repository permissions are unnecessary. It stays in memory for this unlocked session and is never included in reports.").font(.caption)
                        Button("Verify reviewer") {
                            let credential = token; token = ""
                            Task { await model.login(credential) }
                        }.disabled(token.isEmpty || model.busy || model.ownerIdentity.isEmpty)
                    } else {
                        Text("Signed in as \(model.reviewer)")
                        Text(model.reviewerPrincipal).font(.caption).textSelection(.enabled)
                        Button("Sign reviewer out") { Task { await model.logout() } }.disabled(model.busy)
                    }
                }
                    Section("Owner's app access controls") {
                        ForEach(model.members) { member in
                            Text("\(member.login) · \(member.role.lowercased()) · \(member.status.lowercased())").font(.callout)
                            if member.role != "OWNER", member.status == "ACTIVE" {
                                Button("Revoke \(member.login)", role: .destructive) { revoking = member }.disabled(model.busy)
                            }
                        }
                        if !model.reviewer.isEmpty {
                            Button("Give this reviewer checker access") { changingRole = true }.disabled(model.busy)
                        }
                    }
                Section("Agent proposals") {
                    Button("Refresh proposals") { Task { await model.refresh() } }.disabled(model.busy)
                    if model.requests.isEmpty {
                        Text("No proposals are available to this reviewer. Sign in and ask the owner for checker access, or have the agent prepare a request.")
                    }
                    ForEach(model.requests) { request in
                        Button { Task { await model.inspect(request) } } label: {
                            VStack(alignment: .leading) {
                                Text(request.operation)
                                Text("\(request.id) · \(request.state)").font(.caption)
                            }
                        }.disabled(model.busy)
                    }
                    if model.nextOffset != nil {
                        Button("Load more proposals") { Task { await model.loadMore() } }.disabled(model.busy)
                    }
                }
                Section("Prepare an evidence review") {
                    Text("Choose a saved store, distribution or experiment record. WMM freezes its current content for the reviewer.").font(.caption)
                    if model.sources.isEmpty { Text("Save an eligible record in Your evidence first.") }
                    ForEach(model.sources) { source in
                        Button("Prepare review: \(source.title)") { Task { await model.prepareEvidence(source) } }.disabled(model.busy)
                    }
                }
                Section("Evidence review history") {
                    if model.evidence.isEmpty { Text("No evidence review packets prepared yet.") }
                    ForEach(model.evidence) { item in
                        Button("\(item.id) · \(item.status)") { model.selectedEvidence = item }.disabled(model.busy)
                    }
                    if let item = model.selectedEvidence {
                        Text(item.detail).font(.caption.monospaced()).textSelection(.enabled)
                        Button("Approve this evidence packet") { approvingEvidence = true }
                            .disabled(model.busy || model.reviewer.isEmpty || !item.available || item.status != "WAITING_REVIEW")
                    }
                }
                if let request = model.selected {
                    Section("Exact saved request") {
                        Text("Revision \(request.revision) · \(request.state)")
                        Text(request.hash).font(.caption.monospaced()).textSelection(.enabled)
                        Text(model.detail).font(.caption.monospaced()).textSelection(.enabled)
                        Button("Approve this exact request") { approving = true }
                            .disabled(model.busy || request.state != "WAITING_REVIEW")
                        Button("Cancel this request", role: .destructive) { cancelling = true }.disabled(model.busy)
                        if ["UNKNOWN", "CANCEL_REQUESTED"].contains(request.state) {
                            Text("Inspect the actual effect, choose its known outcome and supply the SHA-256 of the supporting receipt. This records recovery without retrying the action.").font(.caption)
                            Picker("Observed outcome", selection: $outcome) {
                                Text("Succeeded").tag("SUCCEEDED"); Text("Failed").tag("FAILED")
                            }
                            TextField("Receipt SHA-256", text: $evidenceHash).textInputAutocapitalization(.never).autocorrectionDisabled()
                            Button("Record observed outcome") { reconciling = true }
                                .disabled(model.busy || evidenceHash.range(of: "^[a-f0-9]{64}$", options: .regularExpression) == nil)
                        }
                    }
                }
                if model.busy { Section { ProgressView("Checking current identity, app access and request…") } }
                if let message = model.message { Section("Result") { Text(message) } }
            }
            .navigationTitle("Human review")
            .toolbar { Button("Done") { token = ""; ownerToken = ""; dismiss() } }
            .task { await model.refresh() }
            .onDisappear { token = ""; ownerToken = ""; Task { await model.close() } }
            .confirmationDialog("Revoke this member's app access?", isPresented: Binding(get: { revoking != nil }, set: { if !$0 { revoking = nil } })) {
                if let member = revoking { Button("Revoke \(member.login)", role: .destructive) {
                    revoking = nil; Task { await model.revoke(member) }
                } }
            }
            .confirmationDialog("Give \(model.reviewer) checker access to this app?", isPresented: $changingRole) {
                Button("Grant checker access") { Task { await model.assign(role: "CHECKER", status: "ACTIVE") } }
            } message: { Text("This person can approve eligible requests for this app. Your owner role remains unchanged.") }
            .confirmationDialog("Approve the displayed revision and hash?", isPresented: $approving) {
                Button("Approve exact request") { if let request = model.selected { Task { await model.decide(request, approve: true) } } }
            } message: { Text("The agent can resume this saved input under its current grant. Changes to its source, role or approval invalidate admission.") }
            .confirmationDialog("Record cancellation for this request?", isPresented: $cancelling) {
                Button("Cancel request", role: .destructive) { if let request = model.selected { Task { await model.decide(request, approve: false) } } }
            }
            .confirmationDialog("Approve this exact evidence hash?", isPresented: $approvingEvidence) {
                Button("Record evidence review") { if let item = model.selectedEvidence { Task { await model.approveEvidence(item) } } }
            } message: { Text("WMM rechecks the saved source, your checker role and the owner's account binding before recording this review.") }
            .confirmationDialog("Record this known outcome and receipt hash?", isPresented: $reconciling) {
                Button("Record recovery evidence") { if let request = model.selected {
                    Task { await model.reconcile(request, outcome: outcome, evidenceHash: evidenceHash) }
                } }
            } message: { Text("Only record an outcome supported by the receipt you inspected. The action will not run again.") }
        }.privacySensitive()
    }
}
