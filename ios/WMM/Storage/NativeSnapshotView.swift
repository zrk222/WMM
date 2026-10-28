import SwiftUI
import UniformTypeIdentifiers

@MainActor
final class NativeSnapshotModel: ObservableObject, Identifiable {
    struct Preview { let appID: String; let name: String; let bytes: Data }
    let id = UUID()
    let selectedApp: String?
    @Published private(set) var preview: Preview?
    @Published private(set) var busy = false
    @Published private(set) var message: String?
    private let execute: @MainActor (String, String, Data) async throws -> Data
    init(selectedApp: String?, execute: @escaping @MainActor (String, String, Data) async throws -> Data) {
        self.selectedApp = selectedApp; self.execute = execute
    }

    func select(_ url: URL) {
        guard !busy else { return }; preview = nil; message = nil
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        do {
            let handle = try FileHandle(forReadingFrom: url); defer { try? handle.close() }
            let bytes = try handle.read(upToCount: 33_554_433) ?? Data()
            guard !bytes.isEmpty, bytes.count <= 33_554_432,
                  let root = try JSONSerialization.jsonObject(with: bytes) as? [String: Any],
                  let payload = root["payload"] as? [String: Any],
                  let app = payload["app"] as? [String: Any], let appID = app["id"] as? String,
                  let data = app["data"] as? [String: Any], let name = data["name"] as? String,
                  appID.utf8.count <= 120, name.utf8.count <= 1000 else { throw DomainBridge.Failure.invalidRequest }
            preview = Preview(appID: appID, name: name, bytes: bytes)
            message = "File selected. The engine will validate its hashes and contents when you confirm restore."
        } catch { message = "Choose a WMM JSON snapshot within 32 MiB. The file could not be read; saved work is unchanged." }
    }

    func export() async -> Data? {
        guard !busy, let selectedApp else { return nil }; busy = true; message = nil
        defer { busy = false }
        do { return try await execute("export", selectedApp, Data()) }
        catch { message = "Export was not confirmed. Unlock and reopen the app, then retry."; return nil }
    }

    func restore(confirmed: Bool) async {
        guard !busy, confirmed, let preview else { return }; busy = true; message = nil
        defer { busy = false }
        do {
            _ = try await execute("restore", preview.appID, preview.bytes)
            self.preview = nil
            message = "Workspace restored. Return to Your apps to open it. Connections and agent permissions must be set up again on this device."
        } catch { message = "Restore was not confirmed. An existing app is never overwritten. Return to Your apps and refresh before retrying." }
    }
}

@MainActor
struct NativeSnapshotView: View {
    @ObservedObject var model: NativeSnapshotModel
    @Environment(\.dismiss) private var dismiss
    @State private var importing = false
    @State private var exporting = false
    @State private var document: NativeReportFile?
    @State private var confirmed = false
    @State private var exportMessage: String?
    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text("Keep a portable copy of your app facts, evidence and included media. Save it in a private location, then restore it as a new workspace on another device.")
                    Text("Snapshots contain private app data. They exclude account credentials and agent permissions. Rendered videos outside the portable snapshot must be saved separately.").font(.callout)
                }
                Section("Save a copy") {
                    if let app = model.selectedApp {
                        Text("Selected app: \(app)")
                        Button("Save workspace snapshot") { Task {
                            if let bytes = await model.export() { document = NativeReportFile(data: bytes); exporting = true }
                        }}.disabled(model.busy)
                    } else { Text("Open an app first to save its snapshot.") }
                }
                Section("Restore a saved workspace") {
                    Button("Choose snapshot from Files") { confirmed = false; importing = true }.disabled(model.busy)
                    if let preview = model.preview {
                        Text(preview.name).font(.headline)
                        Text("App: \(preview.appID)")
                        Text("File size: \(preview.bytes.count) bytes")
                        Text("Restore adds this app only if its identifier is unused. Existing work is retained. You become the restored workspace's local owner.").font(.callout)
                        Toggle("I confirm restoring this selected workspace", isOn: $confirmed)
                        Button("Restore workspace") { Task { await model.restore(confirmed: confirmed); confirmed = false } }
                            .disabled(!confirmed || model.busy)
                    }
                }
                if model.busy { Section { ProgressView("Processing your workspace snapshot") } }
                if let message = model.message { Section { Text(message) } }
                if let exportMessage { Section { Text(exportMessage) } }
            }
            .navigationTitle("Backup & restore")
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Done") { dismiss() } } }
            .fileImporter(isPresented: $importing, allowedContentTypes: [.json]) { result in
                if case .success(let url) = result { model.select(url) }
            }
            .fileExporter(isPresented: $exporting, document: document, contentType: .json,
                          defaultFilename: "WMM-workspace-snapshot") { result in
                document = nil
                switch result {
                case .success: exportMessage = "Snapshot saved to your selected destination."
                case .failure: exportMessage = "Save did not finish. Your workspace is unchanged."
                }
            }
        }.privacySensitive()
    }
}
