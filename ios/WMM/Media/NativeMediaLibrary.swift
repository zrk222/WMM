import SwiftUI
import PhotosUI
import UniformTypeIdentifiers

struct NativeMediaItem: Decodable, Identifiable {
    struct Metadata: Decodable { let duration_seconds: Double }
    let id: String
    let filename: String
    let source_sha256: String
    let bytes: Int
    let rights_status: String
    let rights_reason: String
    let reuse_available: Bool
    let review_version: Int
    let metadata: Metadata?
}
struct NativeMediaList: Decodable { let items: [NativeMediaItem] }

@MainActor
struct NativeMediaLibrary: View {
    @ObservedObject var model: NativeWorkspaceModel
    @Environment(\.dismiss) private var dismiss
    @State private var photo: PhotosPickerItem?
    @State private var files = false
    @State private var selecting = false
    @State private var selected: NativeMediaItem?
    @State private var pickerMessage: String?

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Text("Bring your own UGC or other video clips. We retain original bytes and inspect the video locally. Import does not grant reuse rights or start production.")
                    Text("Your own uploads do not need to meet viral-discovery view thresholds.").font(.callout)
                }
                Section("Add an original") {
                    PhotosPicker(selection: $photo, matching: .videos, preferredItemEncoding: .current) {
                        Label("Choose from Photos", systemImage: "photo.on.rectangle")
                    }.disabled(model.busy || selecting)
                    Button("Choose from Files", systemImage: "folder") { files = true }.disabled(model.busy || selecting)
                    Text("Up to 64 MiB, 60 seconds. MP4, MOV and WebM are accepted only when the device can decode them.").font(.caption)
                }
                if model.busy || selecting { Section { ProgressView(selecting ? "Reading your selected video…" : model.activity) } }
                if let pickerMessage { Section { Text(pickerMessage) } }
                if let message = model.message { Section { Text(message) } }
                Section("Saved originals") {
                    if model.media.isEmpty { Text("No originals saved for this app yet.") }
                    ForEach(model.media) { item in
                        Button { selected = item } label: {
                            VStack(alignment: .leading, spacing: 6) {
                                Text(item.filename).font(.headline)
                                Text(ByteCountFormatter.string(fromByteCount: Int64(item.bytes), countStyle: .file))
                                Text(item.reuse_available ? "Reuse allowed by owner" : "Reuse: " + item.rights_status)
                                Text(item.rights_reason.replacingOccurrences(of: "_", with: " ")).font(.caption)
                            }
                        }.disabled(model.busy || selecting).accessibilityHint("Inspect this original and review reuse rights")
                    }
                }
            }
            .navigationTitle("Your media")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Done") { dismiss() } }
                ToolbarItem(placement: .primaryAction) { Button("Refresh") { Task { await model.loadMedia() } }.disabled(model.busy || selecting) }
            }
            .fileImporter(isPresented: $files, allowedContentTypes: [.movie], allowsMultipleSelection: false) { result in
                switch result {
                case .success(let urls):
                    guard let url = urls.first else { return }
                    let appID = model.snapshot?.app.id
                    let context = model.selectionContext
                    selecting = true
                    Task {
                        defer { selecting = false }
                        do {
                            let data = try await Task.detached {
                                let access = url.startAccessingSecurityScopedResource()
                                defer { if access { url.stopAccessingSecurityScopedResource() } }
                                return try MediaIntake.readBounded(url)
                            }.value
                            guard model.unlocked, model.selectionContext == context, model.snapshot?.app.id == appID else { return }
                            await model.importMedia(data: data, filename: url.lastPathComponent, requestKey: UUID().uuidString)
                        } catch { pickerMessage = "The selected file could not be read within the media limit. Choose an accessible video and try again." }
                    }
                case .failure: pickerMessage = "File selection did not finish. Your saved originals are unchanged."
                }
            }
            .sheet(item: $selected) { item in NativeMediaReview(model: model, item: item) }
        }
        .privacySensitive()
        .onChange(of: photo) { _, item in
            guard let item else { return }
            let appID = model.snapshot?.app.id
            let context = model.selectionContext
            selecting = true
            Task {
                defer { selecting = false; photo = nil }
                do {
                    guard let movie = try await item.loadTransferable(type: SelectedMovie.self), model.unlocked,
                          model.selectionContext == context, model.snapshot?.app.id == appID else { return }
                    await model.importMedia(data: movie.data, filename: movie.filename, requestKey: UUID().uuidString)
                } catch { pickerMessage = "Photos could not supply the selected original. Try Files or choose another video." }
            }
        }
        .onChange(of: model.unlocked) { _, unlocked in
            if !unlocked { selected = nil; files = false; dismiss() }
        }
    }
}

@MainActor
private struct NativeMediaReview: View {
    @ObservedObject var model: NativeWorkspaceModel
    let item: NativeMediaItem
    @Environment(\.dismiss) private var dismiss
    @State private var basis = "OWNED"
    @State private var evidence = ""
    @State private var confirmed = false
    var body: some View {
        NavigationStack {
            Form {
                Section("This exact original") {
                    Text(item.filename)
                    Text("Source SHA-256: " + item.source_sha256).font(.caption).textSelection(.enabled)
                    Text("Review version: \(item.review_version) · Current status: \(item.rights_status)")
                }
                Section("Your rights decision") {
                    Picker("Reuse basis", selection: $basis) {
                        Text("I own it").tag("OWNED")
                        Text("I hold a license").tag("LICENSED")
                        Text("I have consent").tag("CONSENT")
                    }
                    TextField("Evidence of your rights", text: $evidence, axis: .vertical)
                    Toggle("I confirm this decision for this original", isOn: $confirmed)
                    Text("This records your attestation. WMM does not independently verify the license or consent. Production checks the latest decision again.").font(.callout)
                }
                Section {
                    Button("Allow reuse") { decide("ALLOWED") }.disabled(!canSave)
                    Button("Revoke reuse", role: .destructive) { decide("REVOKED") }.disabled(!canSave)
                }
                if let message = model.message { Section { Text(message) } }
            }.navigationTitle("Review reuse rights")
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() }.disabled(model.busy) } }
            .interactiveDismissDisabled(model.busy)
        }
    }
    private var canSave: Bool { confirmed && !model.busy && !evidence.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && evidence.count <= 1000 }
    private func decide(_ status: String) {
        Task { if await model.reviewMedia(item, status: status, basis: basis, evidence: evidence) { dismiss() } }
    }
}
