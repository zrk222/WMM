import Foundation
import SwiftUI

@MainActor
final class NativeEvidenceModel: ObservableObject, Identifiable {
    struct Readiness: Decodable {
        let journeys: [String]; let required: [String]; let statuses: [String]
    }
    struct Journey: Codable, Identifiable, Equatable {
        let id: String
        var status = "NOT_RUN"
        var expected = ""
        var observed = ""
        var evidence = ""
        var reason = ""
        enum CodingKeys: String, CodingKey { case id, status, expected, observed, evidence, reason }
        init(id: String) { self.id = id }
        init(from decoder: Decoder) throws {
            let row = try decoder.container(keyedBy: CodingKeys.self)
            id = try row.decode(String.self, forKey: .id)
            status = try row.decode(String.self, forKey: .status)
            expected = try row.decodeIfPresent(String.self, forKey: .expected) ?? ""
            observed = try row.decodeIfPresent(String.self, forKey: .observed) ?? ""
            evidence = try row.decodeIfPresent(String.self, forKey: .evidence) ?? ""
            reason = try row.decodeIfPresent(String.self, forKey: .reason) ?? ""
        }
    }
    struct Record: Identifiable {
        let id: String; let kind: String; let title: String; let source: String; let version: Int
        let data: [String: Any]
    }
    let id = UUID()
    @Published private(set) var fields: [String: [String]] = [:]
    @Published private(set) var labels: [String: String] = [:]
    @Published private(set) var records: [Record] = []
    @Published private(set) var readiness: Readiness?
    @Published private(set) var busy = false
    @Published private(set) var message: String?
    private var manifestVersion: Int?
    private let execute: @MainActor (String, Data) async throws -> Data
    init(execute: @escaping @MainActor (String, Data) async throws -> Data) { self.execute = execute }

    private func load() async throws {
        let bytes = try await execute("form", Data("{}".utf8))
        guard let value = try JSONSerialization.jsonObject(with: bytes) as? [String: Any],
              let version = value["manifest_version"] as? Int,
              let schema = value["fields"] as? [String: [String]],
              let labels = value["labels"] as? [String: String],
              let rows = value["records"] as? [[String: Any]] else { throw DomainBridge.Failure.invalidRequest }
        var parsed: [Record] = []
        for row in rows {
            guard let id = row["id"] as? String, let kind = row["kind"] as? String,
                  let title = row["title"] as? String, let source = row["source"] as? String,
                  let revision = row["version"] as? Int, let data = row["data"] as? [String: Any],
                  kind != "connection", schema[kind] != nil else { throw DomainBridge.Failure.invalidRequest }
            parsed.append(Record(id: id, kind: kind, title: title, source: source, version: revision, data: data))
        }
        manifestVersion = version; fields = schema; self.labels = labels; records = parsed
        guard let checklist = value["readiness"] else { throw DomainBridge.Failure.invalidRequest }
        readiness = try JSONDecoder().decode(Readiness.self, from: JSONSerialization.data(withJSONObject: checklist))
    }
    func refresh() async {
        guard !busy else { return }; busy = true; message = nil; defer { busy = false }
        do { try await load() }
        catch { message = "Evidence could not be read. Unlock or refresh before editing." }
    }
    func save(identity: String, revision: Int?, kind: String, title: String, source: String,
              values: [String: Any], confirmed: Bool) async -> Bool {
        guard !busy, confirmed, let manifestVersion, fields[kind] != nil else { return false }
        busy = true; message = nil; defer { busy = false }
        do {
            var body: [String: Any] = ["id": identity, "manifest_version": manifestVersion,
                "kind": kind, "title": title, "source": source, "data": values]
            if let revision { body["version"] = revision }
            _ = try await execute("save", JSONSerialization.data(withJSONObject: body))
            try await load()
            message = "Evidence saved as an operator observation. Refresh your stages to see its effect; saving does not approve reuse, execute a campaign or establish measured growth."
            return true
        } catch {
            message = "Evidence was not confirmed. Check required fields, typed values and source proof, then refresh before retrying. Existing evidence and app revisions cannot be overwritten with stale values."
            return false
        }
    }
}

@MainActor
struct NativeEvidenceView: View {
    @ObservedObject var model: NativeEvidenceModel
    @Environment(\.dismiss) private var dismiss
    @State private var selected: NativeEvidenceModel.Record?
    @State private var identity = UUID().uuidString.lowercased()
    @State private var kind = "measurement"
    @State private var title = ""
    @State private var source = ""
    @State private var values: [String: String] = [:]
    @State private var extra = "{}"
    @State private var confirmed = false
    @State private var localMessage: String?
    @State private var journeys: [NativeEvidenceModel.Journey] = []
    @State private var candidateHash = ""
    @State private var testedLocale = ""
    private let flags = Set(["authentic", "rights_cleared", "consent_review", "refund_reconciliation", "installed", "fresh_install", "signed_out", "restore_tested", "trial_eligibility_tested", "mature", "confirmed"])
    private let integers = Set(["p0_count", "eligible", "retained", "installs", "activated", "paid", "budget_minor", "daily_cap_minor", "price_minor", "amount_minor", "acquisition_cost_minor", "net_proceeds_minor", "delivery_cost_minor", "refunds_minor", "rating"])

    private func reset() {
        selected = nil; identity = UUID().uuidString.lowercased(); title = ""; source = ""
        values = [:]; extra = "{}"; confirmed = false; localMessage = nil
        journeys = model.readiness?.journeys.map { .init(id: $0) } ?? []
        candidateHash = ""; testedLocale = ""
    }
    private func edit(_ record: NativeEvidenceModel.Record) {
        kind = record.kind; selected = record; identity = record.id; title = record.title; source = record.source
        values = [:]
        var additional = record.data
        candidateHash = additional["candidate_sha256"] as? String ?? ""
        testedLocale = additional["locale"] as? String ?? ""
        if let raw = additional["journeys"], let bytes = try? JSONSerialization.data(withJSONObject: raw),
           let saved = try? JSONDecoder().decode([NativeEvidenceModel.Journey].self, from: bytes) {
            journeys = saved
        } else { journeys = model.readiness?.journeys.map { .init(id: $0) } ?? [] }
        if kind == "readiness" {
            for key in ["journeys", "journey_schema", "candidate_sha256", "locale"] { additional.removeValue(forKey: key) }
        }
        for field in model.fields[kind] ?? [] {
            if let value = additional.removeValue(forKey: field) {
                if flags.contains(field), let flag = value as? Bool { values[field] = flag ? "true" : "false" }
                else if field == "analysis", JSONSerialization.isValidJSONObject(value) {
                    values[field] = (try? JSONSerialization.data(withJSONObject: value, options: [.sortedKeys]))
                        .flatMap { String(data: $0, encoding: .utf8) } ?? "{}"
                } else { values[field] = String(describing: value) }
            }
        }
        extra = (try? JSONSerialization.data(withJSONObject: additional, options: [.sortedKeys, .prettyPrinted]))
            .flatMap { String(data: $0, encoding: .utf8) } ?? "{}"
        confirmed = false
    }
    private func save() async {
        do {
            guard let bytes = extra.data(using: .utf8), bytes.count <= 1_048_576,
                  var data = try JSONSerialization.jsonObject(with: bytes) as? [String: Any] else {
                throw DomainBridge.Failure.invalidRequest
            }
            for field in model.fields[kind] ?? [] {
                let text = values[field, default: ""].trimmingCharacters(in: .whitespacesAndNewlines)
                if flags.contains(field) {
                    guard ["true", "false"].contains(text) else { throw DomainBridge.Failure.invalidRequest }
                    data[field] = text == "true"
                } else if integers.contains(field) {
                    guard let number = Int(text) else { throw DomainBridge.Failure.invalidRequest }; data[field] = number
                } else if field == "analysis" {
                    guard let objectBytes = text.data(using: .utf8), let object = try JSONSerialization.jsonObject(with: objectBytes) as? [String: Any] else { throw DomainBridge.Failure.invalidRequest }
                    data[field] = object
                } else { data[field] = text }
            }
            if kind == "readiness" {
                data["journey_schema"] = 1
                data["candidate_sha256"] = candidateHash
                data["locale"] = testedLocale
                data["journeys"] = try JSONSerialization.jsonObject(with: JSONEncoder().encode(journeys))
            }
            if await model.save(identity: identity, revision: selected?.version, kind: kind, title: title,
                                source: source, values: data, confirmed: confirmed) {
                selected = model.records.first { $0.id == identity }; confirmed = false
            }
        } catch { localMessage = "Use a whole number for counts and minor currency amounts, choose Yes or No for flags, and enter a JSON object for structured details." }
    }
    private var introduction: some View {
        Section {
                    Text("Record what you observed, where it came from and the exact release. These shared evidence forms support your marketing stages; they do not run tests or create proof for you.")
                    Text("Keep passwords, API keys and customer conversations out of evidence. Add protected connections through Provider access.").font(.callout)
                }
    }
    private var recordFields: some View {
        Section("Evidence to record") {
                    Picker("Type", selection: $kind) {
                        ForEach(model.fields.keys.sorted(), id: \.self) { key in Text(model.labels[key] ?? key).tag(key) }
                    }.disabled(selected != nil)
                    TextField("Evidence title", text: $title)
                    TextField("Source or receipt reference", text: $source, axis: .vertical)
                    ForEach(model.fields[kind] ?? [], id: \.self) { field in evidenceField(field) }
                }
    }
    private func fieldValue(_ field: String) -> Binding<String> {
        Binding(get: { values[field] ?? "" }, set: { values[field] = $0 })
    }
    private var summaryStatuses: [String] { (model.readiness?.statuses ?? []).filter { $0 != "N/A" } }
    @ViewBuilder private func evidenceField(_ field: String) -> some View {
                        if kind == "readiness", field == "result" {
                            Picker("Checklist summary", selection: fieldValue(field)) {
                                Text("Choose").tag("")
                                ForEach(summaryStatuses, id: \.self) { status in Text(status).tag(status) }
                            }
                        } else if flags.contains(field) {
                            Picker(field.replacingOccurrences(of: "_", with: " "), selection: fieldValue(field)) {
                                Text("Choose").tag(""); Text("Yes").tag("true"); Text("No").tag("false")
                            }
                        } else {
                            TextField(field.replacingOccurrences(of: "_", with: " "), text: fieldValue(field), axis: .vertical)
                                .textInputAutocapitalization(.never).autocorrectionDisabled()
                        }
    }
    @ViewBuilder private var journeyChecklist: some View {
        if kind == "readiness", let checklist = model.readiness {
                    Section("Core journey checklist") {
                        Text("Record each test's expected behavior, what happened, and its receipt. NOT_RUN preserves missing evidence. The engine checks that your summary agrees with these observations.").font(.callout)
                        TextField("Tested build SHA256", text: $candidateHash).textInputAutocapitalization(.never).autocorrectionDisabled()
                        TextField("Tested locale", text: $testedLocale).textInputAutocapitalization(.never).autocorrectionDisabled()
                        ForEach($journeys) { entry in
                            NativeJourneyFields(journey: entry, statuses: checklist.statuses,
                                required: checklist.required.contains(entry.wrappedValue.id))
                        }
                    }
                }
    }
    private var supportingDetails: some View {
        Section("Structured supporting details") {
                    DisclosureGroup("Additional evidence fields") {
                        Text("Use a JSON object for additional domain-specific fields such as an uploaded asset file_id. Guided fields above take precedence; the shared engine validates the complete record.").font(.caption)
                        TextEditor(text: $extra).frame(minHeight: 130).font(.system(.body, design: .monospaced))
                            .textInputAutocapitalization(.never).autocorrectionDisabled().accessibilityLabel("Additional evidence JSON object")
                    }
                    Toggle("I confirm these observations and their source", isOn: $confirmed)
                    Button("Save evidence revision") { localMessage = nil; Task { await save() } }
                        .disabled(!confirmed || title.isEmpty || source.isEmpty || model.fields[kind] == nil)
                    Button("Start a new record") { reset() }
                }
    }
    private var savedRecords: some View {
        Section("Saved evidence") {
                    if model.records.isEmpty { Text("No evidence records yet. Choose a type and add your first observation.") }
                    ForEach(model.records) { record in Button("\(record.title) · revision \(record.version)") { edit(record) } }
                }
    }
    private var formSignature: [String] {
        [title, source, extra] + values.keys.sorted().map { values[$0] ?? "" }
    }
    var body: some View {
        NavigationStack {
            Form {
                introduction
                recordFields
                journeyChecklist
                supportingDetails
                if let message = localMessage ?? model.message { Section("Action result") { Text(message) } }
                savedRecords
            }.disabled(model.busy)
            .navigationTitle("Your evidence")
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Done") { dismiss() }.disabled(model.busy) }
                ToolbarItem(placement: .primaryAction) { Button("Refresh") { confirmed = false; Task { await model.refresh() } }.disabled(model.busy) } }
            .overlay { if model.busy { ProgressView("Reading or saving app evidence...").padding().background(.regularMaterial) } }
            .onChange(of: kind) { _, _ in if selected == nil { values = [:]; extra = "{}" }; confirmed = false }
            .onChange(of: formSignature) { _, _ in confirmed = false }
            .onChange(of: journeys) { _, _ in confirmed = false }
            .onChange(of: [candidateHash, testedLocale]) { _, _ in confirmed = false }
            .task { await model.refresh(); journeys = model.readiness?.journeys.map { .init(id: $0) } ?? [] }
            .interactiveDismissDisabled(model.busy)
        }.privacySensitive()
    }
}

/// Keep the bound row outside the form's result builder so Swift does not need
/// to infer a nested Binding/ForEach/filter expression as one giant type.
@MainActor
private struct NativeJourneyFields: View {
    @Binding var journey: NativeEvidenceModel.Journey
    let statuses: [String]
    let required: Bool

    private var allowedStatuses: [String] {
        statuses.filter { $0 != "N/A" || !required }
    }

    var body: some View {
        DisclosureGroup(journey.id.replacingOccurrences(of: "_", with: " ") + " · " + journey.status) {
            Picker("Observed status", selection: $journey.status) {
                ForEach(allowedStatuses, id: \.self) { status in Text(status).tag(status) }
            }
            TextField("Expected behavior", text: $journey.expected, axis: .vertical)
            TextField("What you observed", text: $journey.observed, axis: .vertical)
            TextField("Evidence reference", text: $journey.evidence, axis: .vertical)
            if journey.status == "N/A" {
                TextField("Why this journey does not apply", text: $journey.reason, axis: .vertical)
            }
        }
    }
}
