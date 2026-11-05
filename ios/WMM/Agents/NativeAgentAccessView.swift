import Foundation
import SwiftUI

struct NativeAgentGrant: Decodable, Identifiable {
    let id: String; let agent_id: String; let operations: [String]; let expires: String
    let max_calls: Int; let used: Int; let status: String; let version: Int
    let review_operations: [String]
}

struct NativeHandoffJob: Decodable, Identifiable {
    let id: String; let action: String; let status: String
}

struct NativeHandoff: Decodable, Identifiable {
    struct Context: Decodable { struct Resources: Decodable { let unverified_field_count: Int }; let resources: Resources }
    let id: String; let recipient: String; let version: Int; let payload_hash: String
    let status: String; let effective_status: String; let job_id: String; let job_action: String; let job_status: String
    let request_key_hash: String; let created: String; let expires: String; let next_action: String
    let context_status: String; let context_changes: [String]
    let operations: [String]
    let context: Context
}

@MainActor
final class NativeAgentAccessModel: ObservableObject, Identifiable {
    struct Operation: Decodable { let effect: String; let method: String }
    struct Listing: Decodable { let grants: [NativeAgentGrant]; let operations: [String: Operation] }
    struct HandoffListing: Decodable { let handoffs: [NativeHandoff] }
    let id = UUID()
    let appID: String
    let manifestVersion: Int
    @Published private(set) var grants: [NativeAgentGrant] = []
    @Published private(set) var operations: [String: Operation] = [:]
    @Published private(set) var handoffs: [NativeHandoff] = []
    @Published private(set) var handoffJobs: [NativeHandoffJob] = []
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
        let handoffBytes = try await execute("handoff-list", Data("{}".utf8))
        handoffs = try JSONDecoder().decode(HandoffListing.self, from: handoffBytes).handoffs
    }

    func refresh() async {
        guard !busy else { return }; busy = true; message = nil; defer { busy = false }
        do { try await load() }
        catch { message = "Agent access could not be read. Unlock again if your session expired, then refresh." }
    }

    func issue(agentID: String, selected: Set<String>, reviewed: Set<String>, hours: Int,
               maxCalls: Int, confirmed: Bool, expiry: Date? = nil, extendedConsent: Bool = false) async {
        let target = expiry ?? Date().addingTimeInterval(Double(hours) * 3600)
        let extended = target.timeIntervalSinceNow > 24 * 3600
        guard !busy, confirmed, !selected.isEmpty, target > Date(), (!extended || extendedConsent), (1...10000).contains(maxCalls) else { return }
        busy = true; message = nil; defer { busy = false }
        do {
            let expires = ISO8601DateFormatter().string(from: target)
            var grant: [String: Any] = ["agent_id": agentID, "manifest_version": manifestVersion, "operations": selected.sorted(),
                "review_operations": reviewed.intersection(selected).sorted(), "expires": expires, "max_calls": maxCalls]
            if extended { grant["extended_expiry_consent"] = true }
            let body: [String: Any] = ["confirm_scope": true, "grant": grant]
            let issued = try await execute("issue", JSONSerialization.data(withJSONObject: body))
            _ = try await runtime.retainIssuedGrant(issued)
            try await load()
            message = "Grant saved. Its token is stored in this app's device-only Keychain. The selected operations, review requirements, expiry and call limit apply to every request."
        } catch {
            message = "Issuance or Keychain storage was not confirmed. Refresh the grant list. If a grant exists without a retained token, revoke it before issuing another."
        }
    }

    func expiryAction(_ action: String, _ body: Data) async throws -> Data { try await execute(action, body) }

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

    func loadHandoffJobs() async {
        guard !busy, let grant = grants.first(where: { $0.status == "ACTIVE" && $0.operations.contains("jobs.read") }) else {
            message = "A current grant with jobs.read is needed to inspect saved jobs."; return
        }
        busy = true; message = nil; defer { busy = false }
        do {
            let request = try JSONSerialization.data(withJSONObject: ["app_id": appID, "operation": "jobs.read", "input": [:]] as [String: Any])
            handoffJobs = try JSONDecoder().decode([NativeHandoffJob].self, from: await runtime.call(grantID: grant.id, request: request))
            try await load()
        } catch { message = "Saved jobs could not be read with this grant. Check its scope, quota and current owner session." }
    }

    func createHandoff(jobID: String, recipient: String, selected: Set<String>) async {
        guard !busy, !jobID.isEmpty, !recipient.isEmpty, !selected.isEmpty else { return }
        busy = true; message = nil; defer { busy = false }
        do {
            let expires = ISO8601DateFormatter().string(from: Date().addingTimeInterval(3600))
            let body = try JSONSerialization.data(withJSONObject: ["job_id": jobID, "recipient": recipient, "operations": selected.sorted(), "expires": expires] as [String: Any])
            _ = try await execute("handoff-create", body); try await load()
            message = "Handoff saved. No work was started and no authority was transferred."
        } catch { message = "Handoff was not saved. Refresh the app and check the job and selected operations." }
    }

    func resumeHandoff(_ handoff: NativeHandoff, grant: NativeAgentGrant) async {
        guard !busy else { return }; busy = true; message = nil; defer { busy = false }
        do {
            let request = try JSONSerialization.data(withJSONObject: ["app_id": appID, "operation": "handoff.resume", "resource_id": handoff.id,
                "input": ["version": handoff.version, "payload_hash": handoff.payload_hash]] as [String: Any])
            let bytes = try await runtime.call(grantID: grant.id, request: request)
            let value = try JSONSerialization.jsonObject(with: bytes) as? [String: Any]
            guard value?["resume"] as? String == "RESUME_ADMITTED", value?["job_id"] as? String == handoff.job_id else { throw DomainBridge.Failure.invalidRequest }
            try await load(); message = "Replacement admitted to the original job context. Inspect its current status before any separately authorized action."
        } catch { message = "Handoff admission was not confirmed. Refresh and inspect the existing job; do not start a replacement job blindly." }
    }

    func revokeHandoff(_ handoff: NativeHandoff) async {
        guard !busy else { return }; busy = true; message = nil; defer { busy = false }
        do {
            let body = try JSONSerialization.data(withJSONObject: ["id": handoff.id, "version": handoff.version])
            _ = try await execute("handoff-revoke", body); try await load()
            message = "Handoff revoked. Existing work and results remain available for inspection."
        } catch { message = "Revocation was not confirmed. Refresh this handoff before retrying." }
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
    @State private var expiry = Date().addingTimeInterval(24 * 3600)
    @State private var extendedConsent = false
    @State private var maxCalls = 100
    @State private var confirmed = false
    @State private var revoking: NativeAgentGrant?
    @State private var handoffJob = ""
    @State private var handoffRecipient = ""
    @State private var handoffOperations: Set<String> = ["jobs.read"]

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
                    DatePicker("Permission expires", selection: $expiry, in: Date()...)
                    if expiry.timeIntervalSinceNow > 24 * 3600 { Toggle("I consent to permission lasting beyond 24 hours", isOn: $extendedConsent) }
                    Stepper("Maximum \(maxCalls) calls", value: $maxCalls, in: 1...10000)
                }.disabled(model.busy)
                Section("Review your exact delegation") {
                    Text("App: \(model.appID) · revision \(model.manifestVersion)")
                    Text("Operations: \(selected.sorted().joined(separator: ", "))")
                    Text("Human review: \(reviewed.intersection(selected).sorted().joined(separator: ", "))")
                    Text("Permission expires: \(expiry.formatted()), ceiling: \(maxCalls) calls")
                    Toggle("I approve this exact scope for my agent", isOn: $confirmed)
                    Button("Create scoped agent access") { Task {
                        await model.issue(agentID: agentID, selected: selected, reviewed: reviewed, hours: 24, maxCalls: maxCalls, confirmed: confirmed, expiry: expiry, extendedConsent: extendedConsent)
                        confirmed = false
                    }}.disabled(model.busy || !confirmed || selected.isEmpty || agentID.isEmpty || (expiry.timeIntervalSinceNow > 24 * 3600 && !extendedConsent))
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
                            if grant.status == "ACTIVE" { NativeExpiryReview(kind: "AGENT_GRANT", authorityID: grant.id, execute: model.expiryAction, refresh: model.refresh) }
                            Button("Revoke grant", role: .destructive) { revoking = grant }.disabled(model.busy || grant.status != "ACTIVE")
                        }
                    }
                }
                Section("Task handoffs") {
                    Text("Keep the original job and its request digest. Handoffs do not start work or transfer authority. Native-only job records are not yet supported.")
                    Button("Load saved jobs") { Task { await model.loadHandoffJobs() } }.disabled(model.busy)
                    Picker("Job", selection: $handoffJob) {
                        Text("Choose a job").tag("")
                        ForEach(model.handoffJobs) { job in Text("\(job.action) · \(job.status)").tag(job.id) }
                    }
                    Picker("Replacement agent", selection: $handoffRecipient) {
                        Text("Choose an agent").tag("")
                        ForEach(Array(Set(model.grants.filter { $0.status == "ACTIVE" }.map(\.agent_id))).sorted(), id: \.self) { agent in Text(agent).tag(agent) }
                    }
                    DisclosureGroup("Continuation operations") {
                        ForEach(model.operations.keys.filter { !$0.hasPrefix("handoff.") }.sorted(), id: \.self) { name in
                            Toggle(name, isOn: Binding(get: { handoffOperations.contains(name) }, set: { enabled in
                                if enabled { handoffOperations.insert(name) } else { handoffOperations.remove(name) }
                            }))
                        }
                    }
                    Button("Save one-hour handoff") { Task { await model.createHandoff(jobID: handoffJob, recipient: handoffRecipient, selected: handoffOperations) } }
                        .disabled(model.busy || handoffJob.isEmpty || handoffRecipient.isEmpty || handoffOperations.isEmpty)
                    ForEach(model.handoffs) { handoff in
                        VStack(alignment: .leading, spacing: 6) {
                            Text("\(handoff.job_action) · \(handoff.job_status) · \(handoff.effective_status)").font(.headline)
                            Text("To \(handoff.recipient) · job \(handoff.job_id)")
                            Text("Request digest \(handoff.request_key_hash) · saved \(handoff.created) · expires \(handoff.expires)").font(.caption)
                            Text("Context \(handoff.context_status) \(handoff.context_changes.joined(separator: ", "))").font(.caption)
                            Text("Resource revisions cover allowlisted references; \(handoff.context.resources.unverified_field_count) identifier fields need separate checks.").font(.caption)
                            Text(handoff.next_action).font(.caption)
                            if let grant = model.grants.first(where: { $0.agent_id == handoff.recipient && $0.status == "ACTIVE" && $0.operations.contains("handoff.resume") }) {
                                Button("Admit replacement") { Task { await model.resumeHandoff(handoff, grant: grant) } }.disabled(model.busy || !["READY", "CLAIMED"].contains(handoff.effective_status))
                            }
                            Button("Revoke handoff", role: .destructive) { Task { await model.revokeHandoff(handoff) } }.disabled(model.busy || handoff.status == "REVOKED")
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
            .onChange(of: expiry) { _, _ in confirmed = false; extendedConsent = false }
            .onChange(of: extendedConsent) { _, _ in confirmed = false }
            .onChange(of: maxCalls) { _, _ in confirmed = false }
            .task { await model.refresh() }
            .onDisappear { Task { await model.close() } }
            .interactiveDismissDisabled(model.busy)
        }.privacySensitive()
    }
}

/// A changed date cannot submit the previously reviewed payload.
@MainActor
func confirmNativeExpiry(reviewedDate: Date?, selectedDate: Date, consent: Bool,
                         submit: @MainActor () async throws -> Void) async throws {
    guard consent, let reviewedDate, reviewedDate == selectedDate else { throw DomainBridge.Failure.invalidRequest }
    try await submit()
}

/// Owner-only expiry review retains the exact server preview and request key.
@MainActor
struct NativeExpiryReview: View {
    let kind: String
    let authorityID: String
    let execute: @MainActor (String, Data) async throws -> Data
    let refresh: @MainActor () async -> Void
    @State private var expiry = Date().addingTimeInterval(48 * 3600)
    @State private var preview: [String: Any]?
    @State private var reviewedDate: Date?
    @State private var previewHash = ""
    @State private var requestID = UUID().uuidString.lowercased()
    @State private var display = ""
    @State private var consent = false
    @State private var busy = false
    @State private var result = ""

    private func send(_ action: String, _ body: [String: Any]) async throws -> [String: Any] {
        let data = try await execute(action, JSONSerialization.data(withJSONObject: body))
        guard let value = try JSONSerialization.jsonObject(with: data) as? [String: Any] else { throw DomainBridge.Failure.invalidRequest }
        return value
    }
    private func describe(_ value: [String: Any]) throws -> String {
        String(data: try JSONSerialization.data(withJSONObject: value, options: [.prettyPrinted, .sortedKeys]), encoding: .utf8) ?? ""
    }
    var body: some View {
        DisclosureGroup("Extend permission or inspect receipts") {
            DatePicker("New permission expiry", selection: $expiry, in: Date()...)
            Text("Permission expiry and execution readiness are separate. Verification, credentials and existing work may expire earlier; usage and limits remain unchanged.").font(.caption)
            Button("Review extension") { Task {
                busy = true; defer { busy = false }
                do {
                    let selectedDate = expiry
                    let value = try await send("extension-preview", ["kind": kind, "id": authorityID, "expires": ISO8601DateFormatter().string(from: selectedDate)])
                    guard expiry == selectedDate else { throw DomainBridge.Failure.invalidRequest }
                    guard let reviewed = value["preview"] as? [String: Any], let hash = value["preview_hash"] as? String else { throw DomainBridge.Failure.invalidRequest }
                    preview = reviewed; reviewedDate = selectedDate; previewHash = hash; requestID = UUID().uuidString.lowercased(); consent = false
                    display = try describe(reviewed); result = "Review the exact authority, usage and dependent deadlines below."
                } catch { preview = nil; result = "Extension review failed. Refresh the active authority and check its expiry." }
            }}
            if preview != nil {
                Text(display).font(.caption).textSelection(.enabled)
                Toggle("I approve this exact expiry extension", isOn: $consent)
                Button("Confirm extension") { Task {
                    guard let reviewed = preview else { return }; busy = true; defer { busy = false }
                    do {
                        var value: [String: Any] = [:]
                        try await confirmNativeExpiry(reviewedDate: reviewedDate, selectedDate: expiry, consent: consent) {
                            value = try await send("extension-confirm", ["preview": reviewed, "preview_hash": previewHash, "request_id": requestID, "extended_expiry_consent": true])
                        }
                        display = try describe(value); preview = nil; reviewedDate = nil; consent = false
                        result = "Extension recorded. Existing credentials, usage and independent deadlines are unchanged."
                        await refresh()
                    } catch { result = "Extension was not confirmed. Retry this exact request or refresh and review again." }
                }}.disabled(!consent)
            }
            Button("Show expiry receipts") { Task {
                busy = true; defer { busy = false }
                do { display = try describe(try await send("extension-history", ["kind": kind, "id": authorityID])); result = "Expiry receipts" }
                catch { result = "Receipts could not be read. Unlock and refresh." }
            }}
            if !result.isEmpty { Text(result).font(.caption) }
            if preview == nil && !display.isEmpty { Text(display).font(.caption).textSelection(.enabled) }
        }.disabled(busy).onChange(of: expiry) { _, _ in preview = nil; reviewedDate = nil; consent = false; display = "" }
    }
}
