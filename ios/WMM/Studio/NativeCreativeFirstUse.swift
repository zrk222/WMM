import Foundation
import SwiftUI
import UniformTypeIdentifiers

/// Collects only owner-supplied evidence. Existing domain services decide readiness.
@MainActor
final class NativeCreativeFirstUse: ObservableObject {
    struct Choice: Identifiable { let id: String; let title: String }
    private let appID: String
    private let manifestVersion: Int
    private let execute: (String, [String: Any]) async throws -> Data
    private let upload: (String, URL) async throws -> Data
    private var workspace: [String: Any] = [:]
    private var pendingImage: [String: Any]?
    @Published var busy = false
    @Published var message: String?
    @Published var assetID = ""
    @Published var claimID = ""
    @Published var readinessID = ""
    @Published var storeID = ""
    @Published var routeID = ""
    @Published var assets: [Choice] = []
    @Published var claims: [Choice] = []
    @Published var readiness: [Choice] = []
    @Published var stores: [Choice] = []
    @Published var routes: [Choice] = []
    @Published var objective = ""
    @Published var observation = ""
    @Published var observationEvidence = ""
    @Published var uncertainty = ""
    @Published var reviewer = ""
    @Published var rightsEvidence = ""
    @Published var device = ""
    @Published var rightsConfirmed = false
    @Published var inspectedConfirmed = false
    @Published var capabilityConfirmed = false
    @Published var allowCorrections = false
    @Published var duration = 30
    @Published var editingLevel = 0
    @Published var minutes = 30
    @Published var costMinor = 0
    @Published var currency = ""
    @Published var importedName: String?

    init(appID: String, manifestVersion: Int,
         execute: @escaping (String, [String: Any]) async throws -> Data,
         upload: @escaping (String, URL) async throws -> Data) {
        self.appID = appID; self.manifestVersion = manifestVersion
        self.execute = execute; self.upload = upload
    }

    private func object(_ bytes: Data) throws -> [String: Any] {
        guard let value = try JSONSerialization.jsonObject(with: bytes) as? [String: Any] else { throw DomainBridge.Failure.invalidRequest }
        return value
    }

    func refresh() async {
        guard !busy else { return }; busy = true; defer { busy = false }
        do { try await load(); message = nil }
        catch { message = "Could not load current app evidence. Unlock the app and try again." }
    }

    private func load() async throws {
        workspace = try object(await execute("workspace.read", [:]))
        guard let records = workspace["records"] as? [[String: Any]] else { throw DomainBridge.Failure.invalidRequest }
        if let app = workspace["app"] as? [String: Any], let data = app["data"] as? [String: Any] {
            currency = data["currency"] as? String ?? ""
        }
        func choices(_ kind: String) -> [Choice] {
            records.compactMap { row in
                guard row["kind"] as? String == kind, let id = row["id"] as? String,
                      let title = row["title"] as? String else { return nil }
                if kind == "asset" {
                    guard let data = row["data"] as? [String: Any], data["authentic"] as? Bool == true,
                          data["rights_cleared"] as? Bool == true else { return nil }
                }
                return Choice(id: id, title: title)
            }
        }
        assets = choices("asset"); claims = choices("claim"); readiness = choices("readiness")
        stores = choices("store"); routes = choices("route")
        if !assets.contains(where: { $0.id == assetID }) { assetID = assets.first?.id ?? "" }
        if !claims.contains(where: { $0.id == claimID }) { claimID = claims.first?.id ?? "" }
        if !readiness.contains(where: { $0.id == readinessID }) { readinessID = readiness.first?.id ?? "" }
        if !stores.contains(where: { $0.id == storeID }) { storeID = stores.first?.id ?? "" }
        if !routes.contains(where: { $0.id == routeID }) { routeID = routes.first?.id ?? "" }
    }

    func importStill(_ url: URL) async {
        guard !busy else { return }; busy = true; defer { busy = false }
        do {
            pendingImage = try object(await upload(url.lastPathComponent, url))
            importedName = url.lastPathComponent
            rightsConfirmed = false
            message = "Image saved locally with rights and authenticity unconfirmed. Review your attestation below."
        } catch { message = "Image could not be imported. Choose a single-frame PNG or JPEG up to 8 MiB and 16,777,216 pixels, with neither dimension over 8,192 pixels." }
    }

    func confirmImage() async {
        guard !busy, rightsConfirmed, let row = pendingImage, let id = row["id"] as? String,
              let version = row["version"] as? Int, var data = row["data"] as? [String: Any],
              let title = row["title"] as? String, !rightsEvidence.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !device.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        busy = true; defer { busy = false }
        do {
            data["authentic"] = true; data["rights_cleared"] = true; data["device"] = device
            let body: [String: Any] = ["id": id, "version": version, "manifest_version": manifestVersion,
                "kind": "asset", "title": title, "source": rightsEvidence, "data": data]
            _ = try await execute("evidence.save", body)
            pendingImage = nil; importedName = nil
            try await load(); assetID = id
            message = "Your attestation was saved with this image. No public metric or publication was inferred."
        } catch { message = "The image attestation was not confirmed. Refresh the evidence and review the saved version before retrying." }
    }

    private func existing(_ group: String, matching key: String? = nil, value: String? = nil) -> [String: Any]? {
        guard let rows = workspace[group] as? [[String: Any]] else { return nil }
        return rows.compactMap { $0["current"] as? [String: Any] }.first { row in
            guard let key else { return true }
            return (row["data"] as? [String: Any])?[key] as? String == value
        }
    }

    private func save(_ operation: String, data: [String: Any], replacing old: [String: Any]?) async throws -> [String: Any] {
        var body: [String: Any] = ["data": data]
        if let old {
            guard allowCorrections, let id = old["id"] as? String, let version = old["version"] as? Int else {
                throw DomainBridge.Failure.invalidRequest
            }
            body["id"] = id; body["version"] = version
        }
        return try object(await execute(operation, body))
    }

    private func matching(_ old: [String: Any]?, data: [String: Any], keys: [String]) -> Bool {
        guard let oldData = old?["data"] as? [String: Any] else { return false }
        return keys.allSatisfy { key in
            guard let left = oldData[key], let right = data[key] else { return false }
            return NSDictionary(dictionary: [key: left]).isEqual(to: [key: right])
        }
    }

    func prepare() async {
        guard !busy, rightsConfirmed, inspectedConfirmed, capabilityConfirmed,
              ![assetID, claimID, readinessID, storeID, routeID, objective, observation,
                observationEvidence, uncertainty, reviewer, rightsEvidence].contains(where: { $0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }) else {
            message = "Complete each selection, observation and confirmation before preparing the brief."; return
        }
        busy = true; defer { busy = false }
        var stage = "current app and image"
        do {
            try await load()
            guard let app = workspace["app"] as? [String: Any], let appData = app["data"] as? [String: Any],
                  app["version"] as? Int == manifestVersion, let locale = appData["locale"] as? String,
                  let currency = appData["currency"] as? String, let records = workspace["records"] as? [[String: Any]],
                  let asset = records.first(where: { $0["id"] as? String == assetID }),
                  let image = asset["data"] as? [String: Any], image["authentic"] as? Bool == true,
                  image["rights_cleared"] as? Bool == true, let sha = image["sha256"] as? String,
                  let title = asset["title"] as? String else { throw DomainBridge.Failure.invalidRequest }
            let location = "wmm-owned://asset/\(assetID)/\(sha)"
            let stamp = ISO8601DateFormatter().string(from: Date())
            let null = NSNull()
            let source: [String: Any] = ["platform": "other", "post_id": assetID, "title": title,
                "url": location, "source": rightsEvidence, "captured_at": stamp, "published_at": null,
                "locale": locale, "traffic_class": "UNKNOWN", "creator_id": null, "format": "Owned app screenshot",
                "metric_kind": "UNKNOWN", "metric_value": null, "metric_at": null, "rights": "LICENSED",
                "permission_confirmed": true, "topic": objective, "relevance_note": observation]
            stage = "source reference"
            let references = workspace["references"] as? [[String: Any]] ?? []
            let match = references.first { (($0["current"] as? [String: Any])?["data"] as? [String: Any])?["url"] as? String == location }
            let sourceID: String
            if let match, let id = match["id"] as? String { sourceID = id }
            else { guard let id = try await save("creative.source.save", data: source, replacing: nil)["id"] as? String else { throw DomainBridge.Failure.invalidRequest }; sourceID = id }
            try await load()
            guard let refs = workspace["references"] as? [[String: Any]],
                  let reference = refs.first(where: { $0["id"] as? String == sourceID }),
                  let capture = reference["current"] as? [String: Any], let captureHash = capture["hash"] as? String else { throw DomainBridge.Failure.invalidRequest }
            let observed = ISO8601DateFormatter().string(from: Date())
            let analysis: [String: Any] = ["reference_id": sourceID, "capture_hash": captureHash,
                "inspection_kind": "DIRECT_VIEW", "inspection_confirmed": true, "inspected_at": observed,
                "analyst": reviewer, "format_family": "Owned app screenshot", "duration_seconds": null,
                "observations": [["role": "DEMO", "basis": "OBSERVED", "detail": observation,
                                  "evidence_note": observationEvidence, "start_seconds": null, "end_seconds": null]],
                "uncertainty": uncertainty]
            stage = "inspection"
            let oldAnalysis = existing("analyses", matching: "reference_id", value: sourceID)
            let analysisRow: [String: Any]
            if matching(oldAnalysis, data: analysis, keys: ["reference_id", "capture_hash", "inspection_kind", "analyst", "observations", "uncertainty"]) {
                analysisRow = oldAnalysis!
            } else {
                analysisRow = try await save("creative.analysis.save", data: analysis, replacing: oldAnalysis)
            }
            guard let analysisID = analysisRow["id"] as? String, let analysisHash = analysisRow["hash"] as? String,
                  let capabilities = workspace["capabilities"] as? [String: Any], let appHash = capabilities["app_hash"] as? String else { throw DomainBridge.Failure.invalidRequest }
            let profiles = capabilities["profile"] as? [[String: Any]] ?? []
            if profiles.isEmpty {
                stage = "production capability"
                let profile: [String: Any] = ["app_hash": appHash, "executions": ["SLIDES"], "talent": ["NONE"],
                    "audio": ["SILENT"], "channels": ["SHORT_VIDEO"], "editing_level": editingLevel,
                    "cost_minor": costMinor, "time_minutes": minutes, "capture_available": true,
                    "source": "Owner-confirmed on-device screenshot production", "checked_at": observed]
                _ = try await save("creative.profile.save", data: profile, replacing: nil)
            } else if let current = profiles.first?["current"] as? [String: Any],
                      let declared = current["data"] as? [String: Any] {
                let compatible = declared["app_hash"] as? String == appHash &&
                    (declared["executions"] as? [String] ?? []).contains("SLIDES") &&
                    (declared["talent"] as? [String] ?? []).contains("NONE") &&
                    (declared["audio"] as? [String] ?? []).contains("SILENT") &&
                    (declared["channels"] as? [String] ?? []).contains("SHORT_VIDEO") &&
                    (declared["editing_level"] as? Int ?? -1) >= editingLevel &&
                    (declared["cost_minor"] as? Int ?? -1) >= costMinor &&
                    (declared["time_minutes"] as? Int ?? 0) >= minutes && declared["capture_available"] as? Bool == true
                if !compatible {
                    guard allowCorrections else { throw DomainBridge.Failure.invalidRequest }
                    var revised = declared
                    for (key, value) in [("executions", "SLIDES"), ("talent", "NONE"), ("audio", "SILENT"), ("channels", "SHORT_VIDEO")] {
                        var values = declared[key] as? [String] ?? []
                        if !values.contains(value) { values.append(value) }; revised[key] = values
                    }
                    revised["app_hash"] = appHash; revised["capture_available"] = true
                    revised["editing_level"] = max(declared["editing_level"] as? Int ?? 0, editingLevel)
                    revised["cost_minor"] = max(declared["cost_minor"] as? Int ?? 0, costMinor)
                    revised["time_minutes"] = max(declared["time_minutes"] as? Int ?? 0, minutes)
                    revised["source"] = "Owner-confirmed on-device screenshot production"; revised["checked_at"] = observed
                    stage = "production capability revision"
                    _ = try await save("creative.profile.save", data: revised, replacing: current)
                }
            }
            stage = "source production requirements"
            let requirements = capabilities["requirement"] as? [[String: Any]] ?? []
            let oldRequirement = requirements.compactMap { $0["current"] as? [String: Any] }.first {
                ($0["data"] as? [String: Any])?["reference_id"] as? String == sourceID
            }
            let requirement: [String: Any] = ["reference_id": sourceID, "capture_hash": captureHash,
                "execution": "SLIDES", "talent": "NONE", "audio": "SILENT", "narrative": "DEMO",
                "editing_level": editingLevel, "cost_minor": costMinor, "time_minutes": minutes,
                "requires_capture": true, "rights_available": true, "source": rightsEvidence, "checked_at": observed]
            if !matching(oldRequirement, data: requirement, keys: ["reference_id", "capture_hash", "execution", "talent", "audio", "narrative", "editing_level", "cost_minor", "time_minutes", "requires_capture", "rights_available", "source"]) {
                _ = try await save("creative.requirement.save", data: requirement, replacing: oldRequirement)
            }
            stage = "proof-bound brief"
            let brief: [String: Any] = ["analysis_id": analysisID, "analysis_hash": analysisHash,
                "channel": "SHORT_VIDEO", "objective": objective, "owner": reviewer,
                "claim_ids": [claimID], "asset_ids": [assetID], "readiness_id": readinessID,
                "store_id": storeID, "route_id": routeID, "currency": currency,
                "budget_minor": costMinor, "duration_seconds": duration]
            let savedBriefs = workspace["briefs"] as? [[String: Any]] ?? []
            let alreadySaved = savedBriefs.contains { item in
                guard let current = item["current"] as? [String: Any], let data = current["data"] as? [String: Any],
                      let definition = data["definition"] as? [String: Any] else { return false }
                return NSDictionary(dictionary: definition).isEqual(to: brief)
            }
            if !alreadySaved { _ = try await save("creative.brief.save", data: brief, replacing: nil) }
            try await load()
            message = "Brief saved for review. No video has been rendered or published."
        } catch {
            message = "Could not confirm \(stage). Earlier saved steps remain. Review current app proof, rights and any existing inspection before retrying; inspect saved briefs if the last response was interrupted."
        }
    }
}

@MainActor
struct NativeCreativeFirstUseView: View {
    @ObservedObject var model: NativeCreativeFirstUse
    @Environment(\.dismiss) private var dismiss
    @State private var choosing = false
    var body: some View {
        NavigationStack {
            Form {
                Section("Your real app screenshot") {
                    Text("Choose your own app image. It stays on this device; import does not approve rights or claim viral performance.")
                    Text("One PNG or JPEG, up to 8 MiB and 16,777,216 pixels; each dimension may be at most 8,192 pixels.").font(.caption)
                    Button("Choose PNG or JPEG from Files") { choosing = true }.disabled(model.busy)
                    if let name = model.importedName { Text("Imported: \(name) · rights unconfirmed") }
                    TextField("Device or capture description", text: $model.device)
                    TextField("Why you can use this image", text: $model.rightsEvidence, axis: .vertical)
                    Toggle("This is an authentic app image and I have the rights to use it", isOn: $model.rightsConfirmed)
                    Button("Save image attestation") { Task { await model.confirmImage() } }.disabled(model.busy || !model.rightsConfirmed || model.importedName == nil)
                    picker("Rights-cleared still", selection: $model.assetID, choices: model.assets)
                }
                Section("What you actually inspected") {
                    Text("Inspect your selected image directly. Public views and creator baselines remain unknown.")
                    TextField("Your name or reviewer label", text: $model.reviewer)
                    TextField("What the image shows", text: $model.observation, axis: .vertical)
                    TextField("Where you saw that detail", text: $model.observationEvidence, axis: .vertical)
                    TextField("What remains uncertain", text: $model.uncertainty, axis: .vertical)
                    Toggle("I directly inspected this image", isOn: $model.inspectedConfirmed)
                }
                Section("Current app proof") {
                    Text("Choose current evidence you recorded in Your evidence. The app will reject stale or incomplete proof.").font(.caption)
                    picker("Approved claim", selection: $model.claimID, choices: model.claims)
                    picker("Journey readiness", selection: $model.readinessID, choices: model.readiness)
                    picker("Store destination", selection: $model.storeID, choices: model.stores)
                    picker("Tested route", selection: $model.routeID, choices: model.routes)
                    TextField("Question this original video will explore", text: $model.objective, axis: .vertical)
                }
                Section("Your production declaration") {
                    Text("A silent slideshow of your screenshot, without external talent. This is your declaration, not a measured result.")
                    Picker("Video length", selection: $model.duration) { ForEach([15, 30, 45, 60], id: \.self) { Text("\($0) seconds").tag($0) } }
                    Stepper("Editing level: \(model.editingLevel) of 3", value: $model.editingLevel, in: 0...3)
                    Stepper("Time available: \(model.minutes) minutes", value: $model.minutes, in: 1...10080)
                    TextField("Budget in \(model.currency) minor units", value: $model.costMinor, format: .number)
                        .keyboardType(.numberPad)
                    Toggle("I can make this silent slideshow with the declared time and budget", isOn: $model.capabilityConfirmed)
                    Toggle("Allow explicit corrections to an existing inspection or source requirement", isOn: $model.allowCorrections)
                    Button("Prepare original brief") { Task { await model.prepare() } }.disabled(model.busy)
                }
                if model.busy { Section { ProgressView("Checking and saving your declarations…") } }
                if let message = model.message { Section("Status") { Text(message) } }
            }
            .navigationTitle("Prepare an original brief")
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Done") { dismiss() }.disabled(model.busy) } }
            .task { await model.refresh() }
            .fileImporter(isPresented: $choosing, allowedContentTypes: [.png, .jpeg], allowsMultipleSelection: false) { result in
                if case .success(let urls) = result, let url = urls.first { Task { await model.importStill(url) } }
            }
        }.privacySensitive().interactiveDismissDisabled(model.busy)
    }

    private func picker(_ label: String, selection: Binding<String>, choices: [NativeCreativeFirstUse.Choice]) -> some View {
        Picker(label, selection: selection) {
            Text("Choose evidence").tag("")
            ForEach(choices) { choice in Text(choice.title).tag(choice.id) }
        }
    }
}
