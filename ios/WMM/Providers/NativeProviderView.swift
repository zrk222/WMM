import Foundation
import SwiftUI

@MainActor
final class NativeProviderModel: ObservableObject, Identifiable {
    struct BillingPolicy: Decodable { let account_id: String; let mode: String; let daily_request_limit: Int; let max_output_tokens: Int }
    struct Profile: Decodable, Identifiable {
        struct Config: Decodable { let provider: String; let label: String; let model: String; let endpoint: String; let protected_key: Bool; let billing_policy: BillingPolicy? }
        let id: String; let version: Int; let status: String; let data: Config
    }
    struct Listing: Decodable { let profiles: [Profile]; let cleanup_pending: Int; let native_inference: String }
    let id = UUID()
    @Published private(set) var listing: Listing?
    @Published private(set) var busy = false
    @Published private(set) var message: String?
    private let execute: @MainActor (String, Data) async throws -> Data

    init(execute: @escaping @MainActor (String, Data) async throws -> Data) { self.execute = execute }

    private func read() async throws {
        listing = try JSONDecoder().decode(Listing.self, from: await execute("view", Data("{}".utf8)))
    }

    func refresh() async {
        guard !busy else { return }; busy = true; message = nil; defer { busy = false }
        do { try await read() }
        catch { message = "Provider profiles could not be read. Unlock again if needed; protected credentials and saved records are retained." }
    }

    func save(provider: String, label: String, model: String, endpoint: String, key: String,
              allowCharges: Bool, confirmed: Bool, accountID: String = "", billingMode: String = "free",
              dailyLimit: Int = 10, outputLimit: Int = 1024) async -> Bool {
        guard !busy, confirmed else { return false }; busy = true; message = nil; defer { busy = false }
        do {
            var profile: [String: Any] = ["provider": provider, "label": label, "model": model,
                "endpoint": endpoint, "api_key": key, "allow_api_charges": allowCharges,
                "id": NSNull(), "version": NSNull()]
            if provider == "cloudflare_api" {
                profile["account_id"] = accountID; profile["billing_mode"] = billingMode
                profile["daily_request_limit"] = dailyLimit; profile["max_output_tokens"] = outputLimit
            }
            let bytes = try JSONSerialization.data(withJSONObject: ["confirm_storage": true, "profile": profile])
            _ = try await execute("save", bytes)
            try await read()
            message = "Profile saved with a device-only Keychain key. It is configured, untested. No inference was sent and no provider charge was made by this setup action."
            return true
        } catch {
            message = "Setup was not confirmed. Check the selected adapter, model, HTTPS endpoint and key format. Refresh saved profiles before repeating setup."
            return false
        }
    }

    func disconnect(_ profile: Profile) async {
        guard !busy else { return }; busy = true; message = nil; defer { busy = false }
        do {
            let bytes = try JSONSerialization.data(withJSONObject: ["id": profile.id, "version": profile.version, "confirm_disconnect": true] as [String: Any])
            _ = try await execute("disconnect", bytes)
            try await read()
            message = "Profile disconnected locally. Its retired key cleanup is recorded below. This does not revoke the key at the provider."
        } catch { message = "Disconnection was not confirmed. Refresh the current profile version before retrying." }
    }

    func cleanup() async {
        guard !busy else { return }; busy = true; message = nil; defer { busy = false }
        do { _ = try await execute("cleanup", Data("{}".utf8)); try await read(); message = "Retired-key cleanup checked. Active profile keys are retained." }
        catch { message = "Cleanup could not finish. Unlock and retry; pending references are retained without exposing keys." }
    }
}

@MainActor
struct NativeProviderView: View {
    @ObservedObject var model: NativeProviderModel
    @Environment(\.dismiss) private var dismiss
    @State private var provider = "openai_api"
    @State private var label = ""
    @State private var modelID = ""
    @State private var endpoint = ""
    @State private var key = ""
    @State private var charges = false
    @State private var accountID = ""
    @State private var billingMode = "free"
    @State private var dailyLimit = 10
    @State private var outputLimit = 1024
    @State private var confirmed = false
    @State private var disconnecting: NativeProviderModel.Profile?

    private var destination: String {
        provider == "cloudflare_api" ? "https://api.cloudflare.com/client/v4/accounts/\(accountID)/ai/v1" : provider == "openai_api" ? "https://api.openai.com/v1" : provider == "anthropic_api" ? "https://api.anthropic.com/v1" : endpoint
    }
    private var canSave: Bool {
        guard !model.busy, confirmed, !label.isEmpty, !modelID.isEmpty, !key.isEmpty else { return false }
        if provider != "cloudflare_api" { return charges }
        return (billingMode == "free" || charges) && accountID.count == 32 && (1...1000).contains(dailyLimit) && (64...2048).contains(outputLimit)
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text("Bring a provider API key for this app. The key stays in your device's protected Keychain. Saved profile metadata contains an opaque reference, not the key.")
                    Text("Save your API profile here, then open Agent drafting to review and approve an exact request. OAuth and native device acceptance remain unfinished. Desktop CLI subscriptions cannot run on iOS; an API key does not confer subscription access.").font(.callout)
                }
                Section("Add an API profile") {
                    Picker("Adapter", selection: $provider) {
                        Text("OpenAI API").tag("openai_api")
                        Text("Anthropic API").tag("anthropic_api")
                        Text("Compatible HTTPS API").tag("compatible_api")
                        Text("Cloudflare Workers AI").tag("cloudflare_api")
                    }
                    TextField("Profile name", text: $label)
                    TextField("Exact model identifier", text: $modelID).textInputAutocapitalization(.never).autocorrectionDisabled()
                    if provider == "compatible_api" {
                        TextField("Public HTTPS API base URL", text: $endpoint).keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                    }
                    if provider == "cloudflare_api" {
                        TextField("Cloudflare account ID (32 lowercase hex characters)", text: $accountID).textInputAutocapitalization(.never).autocorrectionDisabled()
                        Picker("Inference billing mode", selection: $billingMode) {
                            Text("Free allowance only").tag("free")
                            Text("Allow paid inference").tag("paid")
                        }
                        Text("Free-only requires a Workers Free account and an allowlisted model: @cf/meta/llama-3.2-3b-instruct or @cf/meta/llama-3.1-8b-instruct-fp8-fast. WMM cannot prevent charges on an already-paid account or from other clients.").font(.caption)
                        Link("Manage your Cloudflare account", destination: URL(string: "https://dash.cloudflare.com/")!)
                        TextField("Maximum output tokens (64–2048)", value: $outputLimit, format: .number).keyboardType(.numberPad)
                        TextField("Daily approval limit per WMM connection (1–1000, UTC)", value: $dailyLimit, format: .number).keyboardType(.numberPad)
                        Text("Every approval counts on its UTC approval day, including cancelled and uncertain work. This is not account-wide, a provider-usage ceiling, or a dollar cap.").font(.caption)
                    }
                    SecureField("API key", text: $key).textInputAutocapitalization(.never).autocorrectionDisabled()
                    Text("Destination: \(destination)").font(.caption)
                    if provider != "cloudflare_api" || billingMode == "paid" {
                        Toggle("I explicitly allow provider API charges for this route", isOn: $charges)
                    }
                    Text("Provider pricing and allowance remain unknown until checked with the provider. Saving this profile sends no inference request.").font(.caption)
                    Toggle("Store this key for this app on this device", isOn: $confirmed)
                    Button("Save protected API profile") { Task {
                        let saved = await model.save(provider: provider, label: label, model: modelID,
                            endpoint: provider == "compatible_api" ? endpoint : "", key: key, allowCharges: charges, confirmed: confirmed,
                            accountID: accountID, billingMode: billingMode, dailyLimit: dailyLimit, outputLimit: outputLimit)
                        key = ""; confirmed = false
                        if saved { label = ""; modelID = "" }
                    }}.disabled(!canSave)
                }.disabled(model.busy)
                if let listing = model.listing {
                    Section("Saved profiles") {
                        if listing.profiles.isEmpty { Text("No provider profiles saved for this app.") }
                        ForEach(listing.profiles) { profile in
                            VStack(alignment: .leading, spacing: 8) {
                                Text(profile.data.label).font(.headline)
                                Text("\(profile.data.provider) · \(profile.data.model)").font(.callout)
                                Text(profile.status.replacingOccurrences(of: "_", with: " ")).font(.caption)
                                Button("Disconnect locally", role: .destructive) { disconnecting = profile }
                                    .disabled(model.busy || profile.status == "DISCONNECTED")
                            }
                        }
                        Text("Retired-key cleanup pending: \(listing.cleanup_pending)").font(.caption)
                        Button("Retry retired-key cleanup") { Task { await model.cleanup() } }.disabled(model.busy)
                    }
                }
                if model.busy { Section { ProgressView("Checking protected profile state…") } }
                if let message = model.message { Section("Action result") { Text(message) } }
            }
            .navigationTitle("Provider access")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Done") { key = ""; dismiss() }.disabled(model.busy) }
                ToolbarItem(placement: .primaryAction) { Button("Refresh") { Task { await model.refresh() } }.disabled(model.busy) }
            }
            .confirmationDialog("Disconnect this exact profile locally?", isPresented: Binding(get: { disconnecting != nil }, set: { if !$0 { disconnecting = nil } })) {
                if let profile = disconnecting { Button("Disconnect \(profile.data.label)", role: .destructive) { Task { await model.disconnect(profile) }; disconnecting = nil } }
            } message: { Text("Local execution will be disabled. Provider-side key revocation remains a separate action in your provider account.") }
            .onChange(of: provider) { _, value in confirmed = false; key = ""; charges = false; billingMode = "free"; if value == "cloudflare_api" { modelID = "@cf/meta/llama-3.2-3b-instruct" } }
            .onChange(of: billingMode) { _, _ in confirmed = false; charges = false }
            .onChange(of: accountID) { _, _ in confirmed = false }
            .onChange(of: dailyLimit) { _, _ in confirmed = false }
            .onChange(of: outputLimit) { _, _ in confirmed = false }
            .onChange(of: endpoint) { _, _ in confirmed = false }
            .onChange(of: label) { _, _ in confirmed = false }
            .onChange(of: modelID) { _, _ in confirmed = false }
            .onChange(of: charges) { _, _ in confirmed = false }
            .onChange(of: key) { _, _ in confirmed = false }
            .task { await model.refresh() }
            .onDisappear { key = "" }
            .interactiveDismissDisabled(model.busy)
        }.privacySensitive()
    }
}
