import SwiftUI
import UniformTypeIdentifiers

@MainActor
final class NativeOneSignalSetupModel: ObservableObject, Identifiable {
    let id = UUID()
    let appName: String
    private let execute: (String, Data) async throws -> Data
    @Published var status: [String: Any] = [:]
    @Published var effects: [[String: Any]] = []
    @Published var apps: [[String: Any]] = []
    @Published var proposal: [String: Any]?
    @Published var message = ""
    @Published var busy = false
    private var closed = false
    init(appName: String, execute: @escaping (String, Data) async throws -> Data) { self.appName = appName; self.execute = execute }
    var uncertain: [[String: Any]] { effects.filter { ["UNKNOWN", "RESERVED"].contains($0["status"] as? String ?? "") && $0["recovery"] as? String != "RECOVERED_READBACK_ONLY" } }
    private func call(_ action: String, _ body: [String: Any]) async throws -> Any {
        guard !closed else { throw DomainBridge.Failure.closed }
        let result = try await execute(action, JSONSerialization.data(withJSONObject: body))
        guard !closed else { throw DomainBridge.Failure.closed }
        return try JSONSerialization.jsonObject(with: result, options: [.fragmentsAllowed])
    }
    private func load() async throws {
        guard let s = try await call("status", [:]) as? [String: Any], let h = try await call("history", [:]) as? [String: Any] else { throw DomainBridge.Failure.closed }
        status = s; effects = h["effects"] as? [[String: Any]] ?? []; proposal = nil
    }
    func run(_ action: String, _ body: [String: Any], result: String = "Saved status refreshed.") async {
        guard !busy, !closed else { return }; busy = true; message = "Working…"
        defer { busy = false }
        do {
            if action == "execute" || action == "recovery-confirm" { proposal = nil }
            let value = try await call(action, body)
            if action == "read" { apps = value as? [[String: Any]] ?? []; message = apps.isEmpty ? "No apps returned. Check the key and app ID." : "Choose the exact app ID and organization."; return }
            if action == "prepare" || action == "recovery-prepare" { proposal = value as? [String: Any]; message = "Review this exact change before applying."; return }
            if action == "save-key" { apps = [] }
            try await load()
            if action == "execute", let data = value as? [String: Any], data["status"] as? String == "BLOCKED_NOT_SENT" { message = "No provider change was sent. Review a new proposal if needed." }
            else if action == "execute", let data = value as? [String: Any], data["status"] as? String != "SUCCEEDED" { message = "Outcome uncertain. Inspect OneSignal and reconcile the exact app; do not retry." }
            else { message = result }
        } catch {
            if action == "execute" || action == "recovery-confirm" { try? await load() }
            message = "The action could not be confirmed. Refresh saved history before trying again. \(error.localizedDescription)"
        }
    }
    func refresh() async { guard !busy, !closed else { return }; busy = true; defer { busy = false }; do { try await load(); message = "Saved status refreshed." } catch { message = "Unable to read setup. Check owner access and try again." } }
    func close() { closed = true; proposal = nil; apps = [] }
}

struct NativeOneSignalSetupView: View {
    @ObservedObject var model: NativeOneSignalSetupModel
    @Environment(\.dismiss) private var dismiss
    @State private var kind = "app"
    @State private var key = ""
    @State private var appID = ""
    @State private var appName = ""
    @State private var organization = ""
    @State private var apnsKey = ""
    @State private var team = ""
    @State private var bundle = ""
    @State private var environment = ""
    @State private var p8 = ""
    @State private var fcm = ""
    @State private var recoveryID = ""
    @State private var recoveryKind = "app"
    @State private var recoveryKey = ""
    @State private var importing = false
    @State private var importTarget = ""
    @State private var fileMessage = ""
    private var isOrg: Bool { model.status["key_kind"] as? String == "org" }
    private var version: Int { model.status["version"] as? Int ?? 0 }
    private let stateLabels = [
        "KEY_NOT_CONFIGURED": "Save your OneSignal key",
        "KEY_SAVED_UNBOUND": "Choose your OneSignal app",
        "APP_BOUND": "Your app is connected",
        "APNS_CONFIGURED_UNVERIFIED": "Apple push settings saved; verification needed",
        "FCM_CONFIGURED_UNVERIFIED": "Android push settings saved; verification needed"
    ]
    private func stateLabel(_ value: String) -> String {
        stateLabels[value] ?? value.replacingOccurrences(of: "_", with: " ").lowercased()
    }
    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text("For \(model.appName)").font(.headline)
                    Text("Connect your OneSignal app, then review any push settings before applying them. Keys stay in protected local storage.")
                }
                Section("What is verified") {
                    Text(stateLabel(model.status["state"] as? String ?? "Loading"))
                    ForEach(model.status["channel_states"] as? [String] ?? [], id: \.self) { Text(stateLabel($0)) }
                    Text("SDK build not yet verified")
                    Text("Device subscription not yet verified")
                    DisclosureGroup("Technical status") {
                        Text(model.status["state"] as? String ?? "Loading")
                        ForEach(model.status["channel_states"] as? [String] ?? [], id: \.self) { Text($0) }
                        Text("SDK_BUILD_NOT_VERIFIED")
                        Text("DEVICE_SUBSCRIPTION_NOT_VERIFIED")
                    }
                    Text("App ID: \(model.status["provider_app_id"] as? String ?? "Not bound")")
                    Text("Verify provider credentials, integrate and build the SDK, then verify a real device subscription.").font(.callout)
                    Button("Refresh status and history") { Task { await model.refresh() } }
                    DisclosureGroup("Setup history") {
                        if model.effects.isEmpty { Text("No setup effects recorded.") }
                        ForEach(model.effects.indices, id: \.self) { index in
                            let effect = model.effects[index]
                            Text("\(effect["action"] as? String ?? "") · \(effect["status"] as? String ?? "") · \(effect["id"] as? String ?? "")")
                            if effect["recovery"] as? String == "RECOVERED_READBACK_ONLY" { Text("Readback recovery recorded. Original outcome remains uncertain.") }
                        }
                    }
                }
                if !model.uncertain.isEmpty && model.proposal == nil {
                    Section("Recover uncertain action") {
                        Text("Do not retry. Inspect OneSignal, then confirm the exact app identity.")
                        ForEach(model.uncertain.indices, id: \.self) { index in
                            let effect = model.uncertain[index]
                            Text("Effect \(effect["id"] as? String ?? "")")
                            TextField("Exact OneSignal app ID", text: $recoveryID).textInputAutocapitalization(.never)
                            Picker("Readback key type", selection: $recoveryKind) { Text("App key").tag("app"); Text("Organization key").tag("org") }
                            SecureField("OneSignal readback key", text: $recoveryKey).textInputAutocapitalization(.never)
                            Button("Review recovery readback") { let value = recoveryKey; recoveryKey = ""; Task { await model.run("recovery-prepare", ["effect_id": effect["id"] as? String ?? "", "provider_app_id": recoveryID, "key_kind": recoveryKind, "key": value]) } }
                        }
                    }
                } else if let review = model.proposal, let packet = review["proposal"] as? [String: Any], let identity = packet["provider_identity"] as? [String: Any] {
                    Section("Review readback-only recovery") {
                        Text("Original effect: \(packet["effect_id"] as? String ?? "") · \(packet["effect_status"] as? String ?? "")")
                        Text("OneSignal app: \(identity["name"] as? String ?? "") · ID: \(identity["id"] as? String ?? "")")
                        Text("Organization: \(identity["organization_id"] as? String ?? "None")")
                        let old = packet["original"] as? [String: Any] ?? [:]
                        let current = packet["current"] as? [String: Any] ?? [:]
                        Text("App revision: \(old["app_version"] as? Int ?? 0) → \(current["app_version"] as? Int ?? 0); owner: \(old["role_version"] as? Int ?? 0) → \(current["role_version"] as? Int ?? 0); connection: \(old["connection_version"] as? Int ?? 0) → \(current["connection_version"] as? Int ?? 0)")
                        Text("Expires: \(packet["expires_at"] as? String ?? "")")
                        Text("This repeats only the exact app readback. The original change is not retried or asserted successful. Save and bind a current key afterward if needed.")
                        Button("Confirm readback recovery") { Task { await model.run("recovery-confirm", ["recovery_id": review["id"] as? String ?? "", "source_hash": review["source_hash"] as? String ?? "", "confirmed": true], result: "Readback recovery recorded. The original action remains uncertain; no mutation was retried.") } }
                        Button("Cancel recovery review") { Task { await model.refresh() } }
                    }
                } else if let review = model.proposal, let packet = review["proposal"] as? [String: Any], let details = packet["details"] as? [String: Any] {
                    Section("Review exact provider change") {
                        Text("Action: \(packet["action"] as? String ?? "")")
                        Text("WMM app: \(model.appName)")
                        Text("OneSignal app: \(details["name"] as? String ?? model.status["name"] as? String ?? "New app")")
                        Text("App ID: \(packet["provider_app_id"] as? String ?? "Assigned on creation")")
                        Text("Organization: \(details["organization_id"] as? String ?? packet["organization_id"] as? String ?? "Not specified")")
                        Text("Fields: \(details.keys.filter { !["name", "organization_id"].contains($0) }.sorted().map { "\($0): \(["apns_p8", "fcm_v1_service_account_json"].contains($0) ? "PROTECTED_VALUE_SELECTED" : (details[$0] as? String ?? ""))" }.joined(separator: ", "))")
                        Text("Effect: \(review["id"] as? String ?? "")")
                        Text("Expires: \(packet["expires_at"] as? String ?? "")")
                        Text("No notifications, deletion, organization transfer or paid upgrade. Verify SDK and device separately.")
                        Button("Confirm and apply this exact change") { Task { await model.run("execute", ["effect_id": review["id"] as? String ?? "", "source_hash": review["source_hash"] as? String ?? "", "confirmed": true]) } }
                        Button("Cancel review") { Task { await model.refresh() } }
                    }
                } else {
                    Section(model.status["protected_key"] as? Bool == true ? "Rotate protected key" : "Save a protected key") {
                        Picker("Key type", selection: $kind) { Text("App key").tag("app"); Text("Organization key").tag("org") }
                        SecureField("OneSignal key", text: $key).textInputAutocapitalization(.never)
                        Text("App keys read one exact app. Organization keys discover apps and allow reviewed setup. Rotation clears the binding.").font(.callout)
                        Button("Save protected key") { let value = key; key = ""; Task { await model.run("save-key", ["kind": kind, "key": value, "version": version]) } }
                    }
                    if model.status["protected_key"] as? Bool == true {
                        Section("Find your app") {
                            if !isOrg { TextField("Exact OneSignal app ID", text: $appID).textInputAutocapitalization(.never) }
                            Button("Read OneSignal apps") { Task { await model.run("read", ["selected_id": isOrg ? NSNull() : appID as Any]) } }
                            if model.apps.isEmpty { Text("No current app readback. Read the provider to see choices.") }
                            ForEach(model.apps.indices, id: \.self) { index in
                                let item = model.apps[index]
                                VStack(alignment: .leading) {
                                    Text((item["name"] as? String ?? "") + ((item["name"] as? String ?? "").localizedCaseInsensitiveCompare(model.appName) == .orderedSame ? " (name matches; verify IDs)" : ""))
                                    Text("App ID: \(item["id"] as? String ?? "") · Organization: \(item["organization_id"] as? String ?? "Not provided")").font(.caption)
                                    Button("Select this exact app") { Task { await model.run("bind", ["provider_app_id": item["id"] as? String ?? "", "expected_name": item["name"] as? String ?? "", "expected_org": item["organization_id"] ?? NSNull(), "version": version]) } }
                                }
                            }
                            Button("Check retired-key cleanup") { Task { await model.run("cleanup", [:], result: "Retired-key cleanup checked. Provider revocation was not performed.") } }
                        }
                    }
                    if isOrg {
                        Section("Create a OneSignal app") {
                            TextField("App name", text: $appName); TextField("Organization ID", text: $organization).textInputAutocapitalization(.never)
                            Button("Review app creation") { Task { await model.run("prepare", ["action": "create", "details": ["name": appName, "organization_id": organization], "request_key": UUID().uuidString.lowercased()]) } }
                        }
                        if model.status["provider_app_id"] as? String != nil {
                            Section("Optional push channels") {
                                TextField("APNs key ID", text: $apnsKey); TextField("Apple team ID", text: $team); TextField("App bundle ID", text: $bundle)
                                Picker("APNs environment", selection: $environment) { Text("Not selected").tag(""); Text("Production").tag("production"); Text("Development").tag("development") }
                                SecureField("APNs P8 private key", text: $p8); Button("Choose APNs P8 file") { importTarget = "p8"; importing = true }
                                SecureField("Firebase service account JSON", text: $fcm); Button("Choose Firebase JSON file") { importTarget = "fcm"; importing = true }
                                if !fileMessage.isEmpty { Text(fileMessage).font(.caption) }
                                Button("Review channel configuration") {
                                    var details: [String: String] = [:]
                                    for (k,v) in [("apns_key_id",apnsKey),("apns_team_id",team),("apns_bundle_id",bundle),("apns_env",environment),("apns_p8",p8),("fcm_v1_service_account_json",fcm)] where !v.isEmpty { details[k] = v }
                                    p8 = ""; fcm = ""
                                    Task { await model.run("prepare", ["action": "update", "details": details, "request_key": UUID().uuidString.lowercased()]) }
                                }
                            }
                        }
                    }
                }
                Section { if model.busy { ProgressView("Working…") }; Text(model.message).accessibilityIdentifier("onesignal-status") }
            }.disabled(model.busy).navigationTitle("OneSignal setup").toolbar { Button("Done") { model.close(); dismiss() } }
            .task { appName = model.appName; await model.refresh() }
            .onDisappear { key = ""; p8 = ""; fcm = ""; recoveryKey = ""; model.close() }
            .fileImporter(isPresented: $importing, allowedContentTypes: [.data]) { result in
                do {
                    let url = try result.get(); let access = url.startAccessingSecurityScopedResource()
                    defer { if access { url.stopAccessingSecurityScopedResource() } }
                    let attributes = try url.resourceValues(forKeys: [.fileSizeKey, .isRegularFileKey])
                    guard attributes.isRegularFile == true, let size = attributes.fileSize, size > 0, size <= 16384 else { throw DomainBridge.Failure.invalidRequest }
                    let data = try Data(contentsOf: url)
                    guard data.count <= 16384, let text = String(data: data, encoding: .utf8) else { throw DomainBridge.Failure.invalidRequest }
                    if importTarget == "p8" { p8 = text } else { fcm = text }
                    fileMessage = "File loaded privately for review."
                } catch { if importTarget == "p8" { p8 = "" } else { fcm = "" }; fileMessage = "Choose a UTF-8 file up to 16 KB." }
            }
        }.privacySensitive()
    }
}
