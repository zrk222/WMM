import SwiftUI
import UniformTypeIdentifiers
import CoreFoundation

@MainActor
final class NativeStoreConnectionModel: ObservableObject, Identifiable {
    static let waitingMessage = "Apple returned no daily report; no new metrics were collected. Read again later while the app is open."
    struct Connection: Identifiable { let id: String; let version: Int; let storeAppID: String; let status: String }
    enum MetricsAvailability: Equatable { case notApplicable, waiting, available, unavailable }
    struct Job: Identifiable {
        let id: String; let status: String; let operation: String; let detail: String
        let metricsAvailability: MetricsAvailability
    }
    let id = UUID()
    let storeAppID: String
    @Published var connections: [Connection] = []
    @Published var jobs: [Job] = []
    @Published var metrics = ""
    @Published var busy = false
    @Published var message: String?
    private let execute: (String, Data) async throws -> Data
    private var closed = false
    private var requests: [String: String] = [:]
    init(storeAppID: String, execute: @escaping (String, Data) async throws -> Data) {
        self.storeAppID = storeAppID; self.execute = execute
    }
    private func call(_ action: String, _ body: [String: Any] = [:]) async throws -> [String: Any] {
        guard !closed else { throw DomainBridge.Failure.closed }
        let data = try await execute(action, JSONSerialization.data(withJSONObject: body))
        guard !closed, let result = try JSONSerialization.jsonObject(with: data) as? [String: Any] else { throw DomainBridge.Failure.closed }
        return result
    }
    private func pretty(_ value: Any) throws -> String {
        String(data: try JSONSerialization.data(withJSONObject: value, options: [.prettyPrinted, .sortedKeys]), encoding: .utf8) ?? ""
    }
    private static func integer(_ value: Any?) -> Int? {
        guard let number = value as? NSNumber, CFGetTypeID(number) != CFBooleanGetTypeID(),
              number.doubleValue.isFinite, number.doubleValue == Double(number.intValue) else { return nil }
        return number.intValue
    }
    private static func hash(_ value: Any?) -> Bool {
        guard let value = value as? String else { return false }
        return value.range(of: "^[0-9a-f]{64}$", options: .regularExpression) != nil
    }
    private static func isFalse(_ value: Any?) -> Bool {
        guard let number = value as? NSNumber, CFGetTypeID(number) == CFBooleanGetTypeID() else { return false }
        return !number.boolValue
    }
    static func metricsAvailability(_ row: [String: Any], storeAppID: String) -> MetricsAvailability {
        guard row["status"] as? String == "SUCCEEDED",
              let data = row["data"] as? [String: Any],
              let options = data["options"] as? [String: Any],
              options["operation"] as? String == "analytics_metrics_latest" else { return .notApplicable }
        guard let result = row["result"] as? [String: Any],
              let appID = row["app_id"] as? String, !appID.isEmpty,
              let reportID = options["report_id"] as? String, !reportID.isEmpty,
              result["app_id"] as? String == appID, result["store_app_id"] as? String == storeAppID,
              result["report_id"] as? String == reportID,
              result["operation"] as? String == "analytics_metrics_latest",
              result["provider"] as? String == "app_store",
              result["report_family"] as? String == "App Downloads Standard",
              result["granularity"] as? String == "DAILY", result["coverage"] as? String == "COMPLETE",
              isFalse(result["external_writes"]),
              let observed = result["observed_at"] as? String, !observed.isEmpty,
              hash(result["metadata_source_hash"]) else { return .unavailable }
        if result["schema"] as? String == "wmm.apple_metrics.waiting.v1" {
            let fields: Set<String> = ["schema", "status", "operation", "provider", "app_id", "store_app_id",
                "connection_id", "connection_version", "report_id", "report_family", "granularity", "coverage",
                "metadata_source_hash", "connection_hash", "observed_at", "metric_observations", "external_writes"]
            guard Set(result.keys) == fields,
                  result["status"] as? String == "WAITING_FOR_REPORTS", result["metric_observations"] is NSNull,
                  let connectionID = data["connection_id"] as? String, !connectionID.isEmpty,
                  let connectionVersion = integer(data["connection_version"]), connectionVersion > 0,
                  result["connection_id"] as? String == connectionID,
                  integer(result["connection_version"]) == connectionVersion,
                  hash(result["connection_hash"]),
                  result["partitions"] == nil, result["partition_count"] == nil else { return .unavailable }
            return .waiting
        }
        guard result["schema"] == nil, result["status"] == nil,
              let count = integer(result["partition_count"]), count > 0,
              let total = integer(result["observation_count"]), total >= 0,
              let partitions = result["partitions"] as? [[String: Any]], partitions.count == count,
              partitions.allSatisfy({ entry in
                  guard let eventDate = entry["event_date"] as? String, !eventDate.isEmpty,
                        let state = entry["status"] as? String, ["INSERTED", "REPLACED", "UNCHANGED"].contains(state),
                        let observations = integer(entry["observation_count"]), observations >= 0,
                        let sources = integer(entry["source_count"]), sources > 0,
                        hash(entry["source_hash"]) else { return false }
                  return true
              }) else { return .unavailable }
        var observedTotal = 0
        for entry in partitions {
            guard let observations = integer(entry["observation_count"]) else { return .unavailable }
            let (sum, overflow) = observedTotal.addingReportingOverflow(observations)
            guard !overflow else { return .unavailable }
            observedTotal = sum
        }
        guard observedTotal == total else { return .unavailable }
        return .available
    }
    private func load() async throws {
        let view = try await call("view")
        connections = try (view["connections"] as? [[String: Any]] ?? []).compactMap { row in
            guard let id = row["id"] as? String, let version = row["version"] as? Int else { return nil }
            return Connection(id: id, version: version, storeAppID: row["store_app_id"] as? String ?? "",
                status: try pretty(row["status"] ?? [:]))
        }
        let history = try await call("history")
        jobs = try (history["jobs"] as? [[String: Any]] ?? []).compactMap { row in
            guard let id = row["id"] as? String, let status = row["status"] as? String else { return nil }
            let data = row["data"] as? [String: Any]
            let options = data?["options"] as? [String: Any]
            return Job(id: id, status: status, operation: options?["operation"] as? String ?? "analytics_reports",
                detail: try pretty(row), metricsAvailability: Self.metricsAvailability(row, storeAppID: storeAppID))
        }
        metrics = ""
    }
    private func perform(_ work: () async throws -> Void) async {
        guard !busy, !closed else { return }; busy = true; message = nil; defer { busy = false }
        do { try await work() }
        catch { message = "The action was not confirmed. Refresh saved connections and read history before retrying. Check the app ID, key role and current owner unlock." }
    }
    func refresh() async { await perform { try await load() } }
    func setup(keyID: String, issuer: String, pem: String) async {
        await perform {
            var body: [String: Any] = ["store_app_id": storeAppID, "key_id": keyID, "issuer_id": issuer,
                "private_key": pem, "confirm_storage": true]
            if let old = connections.first { body["id"] = old.id; body["version"] = old.version }
            _ = try await call("setup", body); try await load()
            message = "The key passed local P-256 validation and was saved in this device's Keychain. Read report inventory to verify Apple access."
        }
    }
    func disconnect(_ connection: Connection) async {
        await perform {
            _ = try await call("disconnect", ["id": connection.id, "version": connection.version, "confirm_disconnect": true])
            try await load(); message = "Local access was disconnected. Check cleanup status; Apple key revocation is separate."
        }
    }
    func cleanup() async {
        await perform { _ = try await call("cleanup"); try await load(); message = "Protected-key cleanup checked. Active connection keys are retained." }
    }
    func read(_ connection: Connection, reportID: String? = nil) async {
        await perform {
            let operation = reportID == nil ? "inventory" : "metrics"
            let identity = connection.id + ":" + String(connection.version) + ":" + (reportID ?? "inventory")
            let requestKey = requests[identity] ?? UUID().uuidString.lowercased()
            requests[identity] = requestKey
            var body: [String: Any] = ["connection_id": connection.id, "connection_version": connection.version, "request_key": requestKey]
            if let reportID { body["report_id"] = reportID }
            let job = try await call("queue_" + operation, body)
            guard let id = job["id"] as? String else { throw DomainBridge.Failure.invalidRequest }
            _ = try await call("run_" + operation, ["id": id])
            requests.removeValue(forKey: identity)
            try await load()
            message = jobs.first(where: { $0.id == id })?.metricsAvailability == .waiting
                ? Self.waitingMessage : "Read finished. Inspect the saved receipt and its coverage before interpreting the result."
        }
    }
    func resume(_ job: Job) async {
        await perform {
            _ = try await call(job.operation == "analytics_reports" ? "run_inventory" : "run_metrics", ["id": job.id])
            try await load()
            if jobs.first(where: { $0.id == job.id })?.metricsAvailability == .waiting { message = Self.waitingMessage }
        }
    }
    func inspectMetrics(_ job: Job) async {
        guard !closed else { return }
        guard job.metricsAvailability == .available else {
            metrics = ""
            message = "No saved download metrics are available for this read. Review its receipt before reading again."
            return
        }
        await perform { metrics = try pretty(await call("metrics", ["id": job.id])) }
    }
    func close() { closed = true; connections = []; jobs = []; metrics = "" }
}

@MainActor
struct NativeStoreConnectionView: View {
    @ObservedObject var model: NativeStoreConnectionModel
    @Environment(\.dismiss) private var dismiss
    @State private var keyID = ""
    @State private var issuer = ""
    @State private var pem = ""
    @State private var importing = false
    @State private var confirmed = false
    @State private var reportID = ""
    @State private var reading: NativeStoreConnectionModel.Connection?
    @State private var disconnecting: NativeStoreConnectionModel.Connection?
    @State private var readMetrics = false
    @State private var fileMessage: String?
    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text("Read your app's Apple analytics with your own private key. WMM keeps the key on this device and checks the selected app before every read.")
                    Text("These actions read reports. They do not create an Apple report request, change your store listing or spend money.").font(.caption)
                    Text("Workspace App Store ID: \(model.storeAppID.isEmpty ? "Missing — edit app facts first" : model.storeAppID)")
                }
                setupSection
                connectionsSection
                historySection
                if !model.metrics.isEmpty { Section("Observed Apple metrics and coverage") { Text(model.metrics).font(.caption.monospaced()).textSelection(.enabled) } }
                if model.busy { Section { ProgressView("Checking current app, key and read receipt…") } }
                if let message = model.message { Section("Result") { Text(message) } }
                if let fileMessage { Section("Key file") { Text(fileMessage) } }
            }
            .navigationTitle("Apple analytics")
            .toolbar { Button("Done") { pem = ""; dismiss() } }
            .task { await model.refresh() }
            .onDisappear { pem = ""; model.close() }
            .fileImporter(isPresented: $importing, allowedContentTypes: [.data]) { result in
                do {
                    let url = try result.get(); let access = url.startAccessingSecurityScopedResource()
                    defer { if access { url.stopAccessingSecurityScopedResource() } }
                    let attributes = try url.resourceValues(forKeys: [.fileSizeKey, .isRegularFileKey])
                    guard attributes.isRegularFile == true, let size = attributes.fileSize, size > 0, size <= 2000 else { throw DomainBridge.Failure.invalidRequest }
                    let data = try Data(contentsOf: url)
                    guard data.count <= 2000, let text = String(data: data, encoding: .utf8), text.contains("-----BEGIN PRIVATE KEY-----") else { throw DomainBridge.Failure.invalidRequest }
                    pem = text; fileMessage = "Key file loaded privately. Confirm storage to save it."
                } catch { pem = ""; fileMessage = "Choose an unencrypted PKCS8 .p8 file up to 2,000 bytes." }
            }
            .confirmationDialog(readMetrics ? "Read this selected Apple download report?" : "Read Apple report inventory?", isPresented: Binding(get: { reading != nil }, set: { if !$0 { reading = nil } })) {
                if let connection = reading { Button("Read approved app analytics") {
                    reading = nil; Task { await model.read(connection, reportID: readMetrics ? reportID : nil) }
                } }
            } message: { Text("Only this workspace's current app and connection are used. Runs in the foreground; inspect saved history if interrupted.") }
            .confirmationDialog("Disconnect this exact Apple connection?", isPresented: Binding(get: { disconnecting != nil }, set: { if !$0 { disconnecting = nil } })) {
                if let connection = disconnecting { Button("Disconnect", role: .destructive) { disconnecting = nil; Task { await model.disconnect(connection) } } }
            }
        }.privacySensitive()
    }
    private var setupSection: some View {
        Section("Your private App Store key") {
            Text("Use a team API key with read access, its key ID and issuer UUID. WMM binds it to the App Store app ID saved above.").font(.caption)
            TextField("Key ID", text: $keyID).textInputAutocapitalization(.characters).autocorrectionDisabled()
            TextField("Issuer UUID", text: $issuer).textInputAutocapitalization(.never).autocorrectionDisabled()
            Button(pem.isEmpty ? "Choose private .p8 key" : "Replace selected key file") { importing = true }
            Toggle("Store my key privately for this app's read-only analytics", isOn: $confirmed)
            Button("Validate and save key") {
                let selected = pem; pem = ""; confirmed = false
                Task { await model.setup(keyID: keyID, issuer: issuer, pem: selected) }
            }.disabled(!confirmed || pem.isEmpty || model.storeAppID.isEmpty || keyID.isEmpty || issuer.isEmpty || model.busy)
        }.disabled(model.busy)
    }
    private var connectionsSection: some View {
        Section("Connection and permitted reads") {
            Button("Refresh status and history") { Task { await model.refresh() } }.disabled(model.busy)
            Button("Retry protected-key cleanup") { Task { await model.cleanup() } }.disabled(model.busy)
            if model.connections.isEmpty { Text("No private Apple connection saved yet.") }
            ForEach(model.connections) { connection in
                Text("App \(connection.storeAppID) · revision \(connection.version)").font(.headline)
                Text(connection.status).font(.caption.monospaced())
                Button("Read available reports") { readMetrics = false; reading = connection }.disabled(model.busy)
                TextField("App Downloads Standard report ID", text: $reportID).textInputAutocapitalization(.never).autocorrectionDisabled()
                Text("Choose the App Downloads Standard ID shown in the inventory receipt. Apple must already have its reports enabled.").font(.caption)
                Button("Read latest daily download metrics") { readMetrics = true; reading = connection }.disabled(model.busy || reportID.isEmpty)
                Button("Disconnect private key", role: .destructive) { disconnecting = connection }.disabled(model.busy)
            }
        }
    }
    private var historySection: some View {
        Section("Durable read history") {
            if model.jobs.isEmpty { Text("No Apple reads queued for this owner and app.") }
            ForEach(model.jobs) { job in
                DisclosureGroup("\(job.operation) · \(job.status)") {
                    if ["QUEUED", "RUNNING"].contains(job.status) {
                        Button("Inspect and resume this read") { Task { await model.resume(job) } }.disabled(model.busy)
                    }
                    if job.status == "BLOCKED" { Text("This read stopped. Repair the connection or source, then explicitly queue a new read above.").font(.caption) }
                    if job.metricsAvailability == .waiting {
                        Text(NativeStoreConnectionModel.waitingMessage).font(.caption)
                    } else if job.metricsAvailability == .unavailable {
                        Text("Saved download metrics are unavailable for this receipt. Review the source before reading again.").font(.caption)
                    } else if job.metricsAvailability == .available {
                        Button("Open saved download metrics") { Task { await model.inspectMetrics(job) } }.disabled(model.busy)
                    }
                    Text(job.detail).font(.caption.monospaced()).textSelection(.enabled)
                }
            }
        }
    }
}
