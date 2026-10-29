import SwiftUI

@MainActor
final class NativeInsightsModel: ObservableObject, Identifiable {
    struct Source: Decodable, Identifiable {
        struct Config: Decodable { let project_id: String; let region: String; let automatic: Bool; let event_map: [String: String]? }
        let id: String; let provider: String; let version: Int; let status: String
        let data: Config; let last_error: String?
    }
    struct Metric: Decodable, Identifiable {
        let name: String; let row: Int?; let value: Double?; let unit: String?; let period: String?; let values: [String: Double]?
        enum CodingKeys: String, CodingKey { case name = "id", row, value, unit, period, values }
        var id: String { row.map { name + ":" + String($0) } ?? name }
    }
    struct Report: Decodable, Identifiable {
        struct Observation: Decodable { let observed_at: String; let rows: [Metric] }
        let id: String; let provider: String?; let data: Observation
    }
    struct Listing: Decodable { let sources: [Source]; let reports: [Report]; let event_roles: [String: String]?; let event_defaults: [String: String]? }
    let id = UUID()
    @Published var sources: [Source] = []
    @Published var reports: [Report] = []
    @Published var eventRoles: [String: String] = [:]
    @Published var eventDefaults: [String: String] = [:]
    @Published var busy = false
    @Published var message: String?
    private let execute: (String, Data) async throws -> Data
    private var closed = false
    init(execute: @escaping (String, Data) async throws -> Data) { self.execute = execute }
    private func call(_ action: String, _ body: [String: Any] = [:]) async throws -> Data {
        guard !closed else { throw DomainBridge.Failure.closed }
        let result = try await execute(action, JSONSerialization.data(withJSONObject: body))
        guard !closed else { throw DomainBridge.Failure.closed }
        return result
    }
    private func read() async throws {
        let listing = try JSONDecoder().decode(Listing.self, from: await call("view"))
        sources = listing.sources; reports = listing.reports
        eventRoles = listing.event_roles ?? [:]; eventDefaults = listing.event_defaults ?? [:]
    }
    private func perform(_ work: () async throws -> Void) async {
        guard !busy, !closed else { return }; busy = true; message = nil; defer { busy = false }
        do { try await work() }
        catch { message = "The analytics action was not confirmed. Refresh the saved connection before repeating setup. Check project, read permissions and network access." }
    }
    func refresh() async { await perform { try await read() } }
    func setup(provider: String = "posthog", project: String, region: String, key: String, automatic: Bool, version: Int?, events: [String: String]) async {
        await perform {
            var body: [String: Any] = ["provider": provider, "project_id": project, "region": region,
                "api_key": key, "automatic": automatic, "confirm_read": true, "dedicated_project": true, "confirm_storage": true]
            if let version { body["version"] = version }
            if provider == "posthog" { body["event_map"] = events }
            _ = try await call("setup", body); try await read()
            message = "\(provider) project checked and its aggregate report saved. The key is in this device's protected Keychain. Scheduled reads run only while this screen is open and WMM is unlocked."
        }
    }
    func readNow(_ source: Source) async {
        await perform {
            let result = try await call("refresh", ["id": source.id, "confirm_read": true])
            let value = try JSONSerialization.jsonObject(with: result) as? [String: Any]
            try await read(); message = "Read result: \(value?["status"] as? String ?? "Inspect saved status"). Counts are observations, not proof of causal lift."
        }
    }
    func disconnect(_ source: Source) async {
        await perform {
            let result = try await call("disconnect", ["id": source.id, "version": source.version, "confirm_disconnect": true])
            let value = try JSONSerialization.jsonObject(with: result) as? [String: Any]
            try await read(); message = "Connection result: \(value?["status"] as? String ?? "Inspect saved status"). Local disconnection does not revoke the provider key."
        }
    }
    func tick() async {
        guard !closed, !busy else { return }
        await perform { _ = try await call("tick"); try await read() }
    }
    func close() { closed = true; sources = []; reports = [] }
}

@MainActor
struct NativeInsightsView: View {
    @ObservedObject var model: NativeInsightsModel
    @Environment(\.dismiss) private var dismiss
    @State private var project = ""
    @State private var provider = "posthog"
    @State private var region = "us"
    @State private var key = ""
    @State private var automatic = false
    @State private var confirmed = false
    @State private var disconnecting: NativeInsightsModel.Source?
    @State private var eventNames: [String: String] = [:]

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text("Connect your app's analytics projects to see funnel events from PostHog, aggregate usability signals from Clarity and subscription metrics from RevenueCat.")
                    Text("Choose a dedicated project and its read-scoped key. WMM saves aggregate observations; event counts, usability signals and subscription metrics keep their own units and periods.").font(.callout)
                }
                setupSection
                connectionsSection
                reportsSection
                if model.busy { Section { ProgressView("Checking this app's analytics connection…") } }
                if let message = model.message { Section("Result") { Text(message) } }
            }
            .navigationTitle("Live analytics")
            .toolbar { Button("Done") { key = ""; dismiss() } }
            .task {
                await model.refresh()
                while !Task.isCancelled {
                    do { try await Task.sleep(nanoseconds: 30_000_000_000) }
                    catch { break }
                    if !Task.isCancelled { await model.tick() }
                }
            }
            .onDisappear { key = ""; model.close() }
            .onChange(of: provider) { _, _ in key = ""; project = ""; confirmed = false; eventNames = [:] }
            .onChange(of: project) { _, _ in confirmed = false }
            .onChange(of: region) { _, _ in confirmed = false }
            .onChange(of: key) { _, _ in confirmed = false }
            .onChange(of: automatic) { _, _ in confirmed = false }
            .onChange(of: eventNames) { _, _ in confirmed = false }
            .confirmationDialog("Disconnect this exact analytics connection?", isPresented: Binding(get: { disconnecting != nil }, set: { if !$0 { disconnecting = nil } })) {
                if let source = disconnecting { Button("Disconnect \(source.provider)", role: .destructive) {
                    disconnecting = nil; Task { await model.disconnect(source) }
                } }
            } message: { Text("Scheduled reads stop and WMM removes its protected local key. Existing reports remain available.") }
        }.privacySensitive()
    }
    private var setupSection: some View {
        Section("Connect or replace an analytics source") {
            Picker("Provider", selection: $provider) {
                Text("PostHog").tag("posthog"); Text("Microsoft Clarity").tag("clarity"); Text("RevenueCat").tag("revenuecat")
            }
            TextField("Dedicated app project ID", text: $project).textInputAutocapitalization(.never).autocorrectionDisabled()
            if provider == "posthog" { Picker("PostHog cloud", selection: $region) { Text("US").tag("us"); Text("EU").tag("eu") } }
            Text(provider == "clarity" ? "Use your project's Data Export token. WMM imports numeric diagnostics, without recordings or browsing URLs."
                : provider == "revenuecat" ? "Use a secret REST API v2 key with charts_metrics:overview:read and a proj… project ID. Public SDK keys cannot read this report."
                : "Use a Personal API read key and the numeric project ID from its URL. Public capture keys cannot read analytics.").font(.caption)
            SecureField("Project read key", text: $key).textInputAutocapitalization(.never).autocorrectionDisabled()
            if provider == "posthog" { DisclosureGroup("Map your app's event names") {
                Text("Use the exact event names your app sends. Leave an unknown role blank; WMM will keep that measure unknown.").font(.caption)
                ForEach(model.eventRoles.keys.sorted(), id: \.self) { role in
                    TextField(model.eventRoles[role] ?? role, text: Binding(get: {
                        eventNames[role] ?? selectedSource?.data.event_map?[role] ?? model.eventDefaults[role] ?? ""
                    }, set: { eventNames[role] = $0 })).textInputAutocapitalization(.never).autocorrectionDisabled()
                }
            } }
            Toggle("Refresh when due while this screen is open", isOn: $automatic)
            Text("Automatic reads are checked every 30 seconds while this screen is open; the permitted read interval is six hours. Locking, closing or suspending WMM stops execution until you reopen it.").font(.caption)
            Toggle("This is my app's dedicated project; I approve aggregate reads and protected key storage", isOn: $confirmed)
            Button(selectedSource == nil ? "Connect and verify project" : "Replace connection and verify project") {
                let credential = key; key = ""; confirmed = false
                let selectedProvider = provider, selectedProject = project, selectedRegion = provider == "posthog" ? region : "global"
                let selectedVersion = selectedSource?.version
                let selectedAutomatic = automatic
                let events = Dictionary(uniqueKeysWithValues: model.eventRoles.keys.map { role in
                    (role, eventNames[role] ?? selectedSource?.data.event_map?[role] ?? model.eventDefaults[role] ?? "")
                })
                Task { await model.setup(provider: selectedProvider, project: selectedProject, region: selectedRegion, key: credential,
                    automatic: selectedAutomatic, version: selectedVersion, events: events) }
            }.disabled(model.busy || !confirmed || project.isEmpty || key.isEmpty)
        }.disabled(model.busy)
    }
    private var selectedSource: NativeInsightsModel.Source? { model.sources.first { $0.provider == provider } }
    private var connectionsSection: some View {
        Section("Connection health") {
            Button("Refresh saved status") { Task { await model.refresh() } }.disabled(model.busy)
            if model.sources.isEmpty { Text("No native analytics source is connected for this app.") }
            ForEach(model.sources) { source in
                VStack(alignment: .leading, spacing: 6) {
                    Text("\(source.provider) project \(source.data.project_id) · \(source.data.region.uppercased())").font(.headline)
                    Text(source.status.replacingOccurrences(of: "_", with: " "))
                    Text(source.data.automatic ? "Six-hour schedule enabled for foreground reads" : "Manual reads").font(.caption)
                    if let error = source.last_error { Text(error).font(.callout) }
                    Button("Read current aggregates") { Task { await model.readNow(source) } }.disabled(model.busy || source.status == "DISCONNECTED" || source.status == "CLEANUP_REQUIRED")
                    Button("Disconnect", role: .destructive) { disconnecting = source }.disabled(model.busy || source.status == "DISCONNECTED")
                }
            }
        }
    }
    private var reportsSection: some View {
        Section("Observed analytics") {
            if model.reports.isEmpty { Text("No successful aggregate read is saved yet. Missing observations remain unknown.") }
            ForEach(model.reports) { report in
                DisclosureGroup("\(report.provider ?? "Analytics") · observed \(report.data.observed_at)") {
                    if report.data.rows.isEmpty { Text("The provider returned no matching event counts for this query.") }
                    ForEach(report.data.rows) { metric in
                        if let value = metric.value {
                            LabeledContent(metric.name.replacingOccurrences(of: "_", with: " "), value: "\(value.formatted()) \(metric.unit ?? "provider units")")
                        }
                        ForEach((metric.values ?? [:]).keys.sorted(), id: \.self) { name in
                            if let value = metric.values?[name] { LabeledContent("\(metric.name) · \(name)", value: value.formatted()) }
                        }
                        if let period = metric.period { Text(period.replacingOccurrences(of: "_", with: " ")).font(.caption) }
                    }
                }
            }
            Text("Open Results & reports from Workspace tools for the app's PDF, JSON and CSV evidence exports.").font(.caption)
        }
    }
}
