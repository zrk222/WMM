import Foundation
import SwiftUI

struct NativeAgentGrant: Decodable, Identifiable {
    let id: String; let agent_id: String; let operations: [String]; let expires: String
    let max_calls: Int; let used: Int; let status: String; let version: Int
    let review_operations: [String]
}

@MainActor
final class NativeAgentAccessModel: ObservableObject, Identifiable {
    struct Operation: Decodable { let effect: String; let method: String }
    struct Listing: Decodable { let grants: [NativeAgentGrant]; let operations: [String: Operation] }
    let id = UUID()
    let appID: String
    let manifestVersion: Int
    @Published private(set) var grants: [NativeAgentGrant] = []
    @Published private(set) var operations: [String: Operation] = [:]
    @Published private(set) var busy = false
    @Published private(set) var message: String?
    private let execute: @MainActor (String, Data) async throws -> Data
    private let runtime: ScopedAgentRuntime

    init(appID: String, manifestVersion: Int, runtime: ScopedAgentRuntime,
         execute: @escaping @MainActor (String, Data) async throws -> Data) {
        self.appID = appID; self.manifestVersion = manifestVersion; self.runtime = runtime; self.execute = execute
    }

    private func load() async throws {
        let bytes = try await execute("list", Data("{}".utf8))
        let listing = try JSONDecoder().decode(Listing.self, from: bytes)
        grants = listing.grants; operations = listing.operations
    }

    func refresh() async {
        guard !busy else { return }; busy = true; message = nil; defer { busy = false }
        do { try await load() }
        catch { message = "Agent access could not be read. Unlock again if your session expired, then refresh." }
    }

    func issue(agentID: String, selected: Set<String>, reviewed: Set<String>, hours: Int,
               maxCalls: Int, confirmed: Bool) async {
        guard !busy, confirmed, !selected.isEmpty, (1...24).contains(hours), (1...10000).contains(maxCalls) else { return }
        busy = true; message = nil; defer { busy = false }
        do {
            let expires = ISO8601DateFormatter().string(from: Date().addingTimeInterval(Double(hours) * 3600))
            let body: [String: Any] = ["confirm_scope": true, "grant": ["agent_id": agentID,
                "manifest_version": manifestVersion, "operations": selected.sorted(),
                "review_operations": reviewed.intersection(selected).sorted(), "expires": expires, "max_calls": maxCalls]]
            let issued = try await execute("issue", JSONSerialization.data(withJSONObject: body))
            _ = try await runtime.retainIssuedGrant(issued)
            try await load()
            message = "Grant saved. Its token is stored in this app's device-only Keychain. The selected operations, review requirements, expiry and call limit apply to every request."
        } catch {
            message = "Issuance or Keychain storage was not confirmed. Refresh the grant list. If a grant exists without a retained token, revoke it before issuing another."
        }
    }

    func revoke(_ grant: NativeAgentGrant) async {
        guard !busy else { return }; busy = true; message = nil; defer { busy = false }
        do {
            let body = try JSONSerialization.data(withJSONObject: ["id": grant.id, "version": grant.version, "confirm_revoke": true] as [String: Any])
            _ = try await execute("revoke", body)
            try await runtime.forgetCredential(grantID: grant.id)
            try await load()
            message = "Grant revoked and its local credential removed. Future admissions are denied. Check in-flight work for its recorded result before retrying."
        } catch { message = "Revocation was not confirmed. Refresh this exact grant before retrying; do not assume in-flight work was cancelled." }
    }

    func verify(_ grant: NativeAgentGrant) async {
        guard !busy else { return }; busy = true; message = nil; defer { busy = false }
        do {
            let envelope = try JSONSerialization.data(withJSONObject: ["app_id": appID, "operation": "workspace.read", "input": [:]] as [String: Any])
            let bytes = try await runtime.call(grantID: grant.id, request: envelope)
            let snapshot = try JSONDecoder().decode(NativeWorkflowSnapshot.self, from: bytes)
            guard snapshot.app.id == appID else { throw DomainBridge.Failure.invalidRequest }
            try await load()
            message = "Local scoped access verified: read \(snapshot.stages.count) stages for this app. One grant call was consumed. This checks the tool transport; no AI provider or marketing campaign ran."
        } catch { message = "Scoped access was not verified. Check the stored token, workspace.read permission, quota, expiry and owner session. Refresh before retrying." }
    }

    func close() async { await runtime.cancel() }
}

@MainActor
struct NativeAgentAccessView: View {
    @ObservedObject var model: NativeAgentAccessModel
    @Environment(\.dismiss) private var dismiss
    @State private var agentID = "personal-agent"
    @State private var selected: Set<String> = ["workspace.read"]
    @State private var reviewed: Set<String> = []
    @State private var hours = 1
    @State private var maxCalls = 100
    @State private var confirmed = false
    @State private var revoking: NativeAgentGrant?

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text("Give your local agent a defined job and only the operations it needs. You control what it can do, which writes need review, how long access lasts and how many calls it can make.")
                    Text("Native agent execution is still under acceptance testing. Issuing a grant does not connect an AI provider, launch a campaign or publish anything.").font(.callout)
                }
                Section("Choose the access scope") {
                    TextField("Agent identifier", text: $agentID).textInputAutocapitalization(.never).autocorrectionDisabled()
                    DisclosureGroup("Choose operation permissions") {
                    ForEach(model.operations.keys.sorted(), id: \.self) { name in
                        Toggle(name, isOn: Binding(get: { selected.contains(name) }, set: { value in
                            confirmed = false
                            if value {
                                selected.insert(name)
                                if model.operations[name]?.method == "POST", model.operations[name]?.effect.hasPrefix("READ_") == false { reviewed.insert(name) }
                            } else { selected.remove(name); reviewed.remove(name) }
                        }))
                        if selected.contains(name), model.operations[name]?.method == "POST", model.operations[name]?.effect.hasPrefix("READ_") == false {
                            Toggle("Require human review for \(name)", isOn: Binding(get: { reviewed.contains(name) }, set: { value in
                                confirmed = false
                                if value { reviewed.insert(name) } else { reviewed.remove(name) }
                            }))
                            Text(model.operations[name]?.effect.replacingOccurrences(of: "_", with: " ").lowercased() ?? "").font(.caption)
                        }
                    }
                    }
                    Stepper("Expires in \(hours) hours", value: $hours, in: 1...24)
                    Stepper("Maximum \(maxCalls) calls", value: $maxCalls, in: 1...10000)
                }.disabled(model.busy)
                Section("Review your exact delegation") {
                    Text("App: \(model.appID) · revision \(model.manifestVersion)")
                    Text("Operations: \(selected.sorted().joined(separator: ", "))")
                    Text("Human review: \(reviewed.intersection(selected).sorted().joined(separator: ", "))")
                    Text("Lifetime: \(hours) hours · ceiling: \(maxCalls) calls")
                    Toggle("I approve this exact scope for my agent", isOn: $confirmed)
                    Button("Create scoped agent access") { Task {
                        await model.issue(agentID: agentID, selected: selected, reviewed: reviewed, hours: hours, maxCalls: maxCalls, confirmed: confirmed)
                        confirmed = false
                    }}.disabled(model.busy || !confirmed || selected.isEmpty || agentID.isEmpty)
                }
                Section("Saved grants") {
                    if model.grants.isEmpty { Text("No scoped grants saved for this app.") }
                    ForEach(model.grants) { grant in
                        VStack(alignment: .leading, spacing: 8) {
                            Text(grant.agent_id).font(.headline)
                            Text("\(grant.status) · \(grant.used)/\(grant.max_calls) calls · expires \(grant.expires)").font(.callout)
                            Text(grant.operations.joined(separator: ", ")).font(.caption)
                            Button("Verify local tool access") { Task { await model.verify(grant) } }
                                .disabled(model.busy || grant.status != "ACTIVE" || !grant.operations.contains("workspace.read"))
                            Button("Revoke grant", role: .destructive) { revoking = grant }.disabled(model.busy || grant.status != "ACTIVE")
                        }
                    }
                }
                if model.busy { Section { ProgressView("Checking and saving current agent authority…") } }
                if let message = model.message { Section("Action result") { Text(message) } }
            }
            .navigationTitle("Your agent access")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Done") { dismiss() }.disabled(model.busy) }
                ToolbarItem(placement: .primaryAction) { Button("Refresh") { Task { await model.refresh() } }.disabled(model.busy) }
            }
            .confirmationDialog("Revoke this exact saved grant?", isPresented: Binding(get: { revoking != nil }, set: { if !$0 { revoking = nil } })) {
                if let grant = revoking { Button("Revoke \(grant.agent_id)", role: .destructive) { Task { await model.revoke(grant) }; revoking = nil } }
            } message: { Text("New calls will be denied. Revocation does not erase existing results or prove that in-flight work stopped.") }
            .onChange(of: agentID) { _, _ in confirmed = false }
            .onChange(of: hours) { _, _ in confirmed = false }
            .onChange(of: maxCalls) { _, _ in confirmed = false }
            .task { await model.refresh() }
            .onDisappear { Task { await model.close() } }
            .interactiveDismissDisabled(model.busy)
        }.privacySensitive()
    }
}
