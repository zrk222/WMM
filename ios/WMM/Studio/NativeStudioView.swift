import SwiftUI
import AVKit
import UIKit

@MainActor
struct NativeStudioView: View {
    @ObservedObject var model: NativeStudioModel
    @Environment(\.dismiss) private var dismiss
    @State private var player: AVPlayer?
    @State private var batchPlayer: AVPlayer?
    @State private var firstUseShown = false
    @State private var sharing: StudioShare?

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text("Write a sequence of text scenes, save a revision, then render and review it on this device.")
                    Text("Add an approved video to a scene and choose whether to retain its source audio.").font(.caption)
                }
                Section("Original video batch") {
                    Text("Turn a current proof-bound brief into local videos. Review the exact captions and frame allowance before queueing; nothing is published.")
                    Button("Prepare a brief on this device") { firstUseShown = true }.disabled(model.busy)
                    if model.batchBriefs.isEmpty {
                        Text("No current short-video briefs are available in this app.").font(.caption)
                    } else {
                        Picker("Current brief", selection: $model.batchBriefID) {
                            ForEach(model.batchBriefs) { brief in
                                Text("\(brief.objective) · \(brief.seconds) seconds").tag(brief.id)
                            }
                        }
                        Toggle("Also make a landscape version", isOn: $model.batchBothShapes)
                        Text("Portrait is included. Work expires in 1 hour; each local MP4 is limited to 8 MiB.").font(.caption)
                        Button("Review video batch") { Task { await model.prepareBatch() } }.disabled(model.busy)
                    }
                    if let review = model.batchReview {
                        Text(review).textSelection(.enabled)
                        Button("Queue reviewed batch") { Task { await model.queueBatch() } }.disabled(model.busy)
                    }
                    ForEach(model.batchProgress.indices, id: \.self) { index in
                        Text(model.batchProgress[index]).font(.caption)
                        Button("Inspect or resume batch \(index + 1)") { Task { await model.resumeBatch(index) } }.disabled(model.busy)
                        ForEach(model.completedVariants(index), id: \.self) { ordinal in
                            Button("Preview batch \(index + 1), video \(ordinal + 1)") { Task { await model.previewBatch(index, ordinal: ordinal) } }.disabled(model.busy)
                        }
                    }
                    if model.batchOutput != nil {
                        VideoPlayer(player: batchPlayer).frame(minHeight: 220)
                        Button("Save or share batch video") { Task {
                            if let url = await model.prepareBatchShare() { sharing = StudioShare(url: url) }
                        }}.disabled(model.busy)
                        Text("Preview every caption and the framing. This video has not been published.").font(.caption)
                    }
                }.disabled(model.busy)
                Section("Story") {
                    TextField("Video title", text: $model.draft.title, axis: .vertical)
                    Picker("Output shape", selection: $model.draft.shape) {
                        Text("Portrait").tag("PORTRAIT")
                        Text("Landscape").tag("LANDSCAPE")
                    }
                    if let project = model.selected {
                        Text("Saved revision \(project.revision)\(model.hasUnsavedChanges ? " · unsaved changes" : "")").font(.caption)
                    }
                }.disabled(model.busy)
                Section("Scenes, first to last") {
                    ForEach(model.draft.scenes.indices, id: \.self) { index in
                        VStack(alignment: .leading, spacing: 8) {
                            Text("Scene \(index + 1)").font(.headline)
                            TextField("Scene text", text: $model.draft.scenes[index].text, axis: .vertical)
                                .accessibilityLabel("Scene \(index + 1) text")
                            Stepper("Duration: \(model.draft.scenes[index].seconds) seconds", value: $model.draft.scenes[index].seconds, in: 1...15)
                            Menu("Scene background") {
                                Button("Text only") { model.draft.scenes[index].media = nil }
                                ForEach(model.originals) { original in
                                    Button(original.filename) {
                                        model.draft.scenes[index].media = .init(id: original.id, sha256: original.source_sha256, in_frame: 0, audio: "MUTE")
                                    }.disabled(!original.reuse_available)
                                }
                            }
                            if let media = model.draft.scenes[index].media {
                                Text(model.originals.first(where: { $0.id == media.id })?.filename ?? "Original unavailable; restore or choose another source").font(.caption)
                                Stepper("Source start frame: \(media.in_frame)", value: Binding(get: { model.draft.scenes[index].media?.in_frame ?? 0 }, set: { model.draft.scenes[index].media?.in_frame = $0 }), in: 0...1439)
                                Picker("Source audio", selection: Binding(get: { model.draft.scenes[index].media?.audio ?? "MUTE" }, set: { model.draft.scenes[index].media?.audio = $0 })) {
                                    Text("Mute").tag("MUTE"); Text("Retain").tag("RETAIN")
                                }
                            }
                            HStack {
                                Button("Move earlier") { model.draft.scenes.swapAt(index, index - 1) }.disabled(index == 0)
                                Button("Move later") { model.draft.scenes.swapAt(index, index + 1) }.disabled(index == model.draft.scenes.count - 1)
                                Button("Remove", role: .destructive) { model.draft.scenes.remove(at: index) }.disabled(model.draft.scenes.count == 1)
                            }
                        }.padding(.vertical, 4)
                    }
                    Button("Add scene") { model.draft.scenes.append(.init(text: "", seconds: 3)) }
                        .disabled(model.draft.scenes.count >= 12)
                    Text("Up to 12 scenes, 15 seconds per scene and 60 seconds total. Each title and scene has up to 240 characters.").font(.caption)
                }.disabled(model.busy)
                Section("Save and render") {
                    Button("Save scene revision") { Task { await model.save() } }.disabled(model.busy)
                    Button("Review render plan") { Task { await model.plan() } }.disabled(model.busy || model.selected == nil || model.hasUnsavedChanges)
                    Button("Render local video") { Task { await model.export() } }.disabled(model.busy || model.selected == nil || model.hasUnsavedChanges)
                    if let output = model.output, !model.hasUnsavedChanges {
                        Text("Preview of revision \(model.outputRevision ?? 0)").font(.caption)
                        VideoPlayer(player: player).frame(minHeight: 220)
                            .onAppear { player = AVPlayer(url: output) }
                        Button("Save or share video") { Task {
                            if let url = await model.prepareShare() { sharing = StudioShare(url: url) }
                        }}.disabled(model.busy)
                        Text("This is a local preview. It has not been published.").font(.caption)
                    }
                }
                if model.busy {
                    Section { ProgressView(model.activity); Button("Cancel render") { Task { await model.cancel() } } }
                }
                if let message = model.message { Section("Action result") { Text(message) } }
                Section("Saved projects") {
                    Button("New scene project") { player?.pause(); model.newProject() }.disabled(model.busy)
                    if model.projects.isEmpty { Text("No saved scene projects yet.") }
                    ForEach(model.projects) { project in
                        Button("\(project.scene.title) · revision \(project.revision)") { Task { await model.open(project) } }.disabled(model.busy)
                    }
                }
                if !model.jobs.isEmpty {
                    Section("Render history") {
                        ForEach(model.jobs) { job in
                            if job.status == "SUCCEEDED" {
                                Button("Open revision \(job.revision) video") { Task { await model.reopen(job) } }.disabled(model.busy)
                            } else if job.status == "PREPARED" {
                                Button("Inspect and recover revision \(job.revision) render") { Task { await model.recover(job) } }.disabled(model.busy)
                            } else { Text("Revision \(job.revision) · \(job.status.lowercased())") }
                        }
                    }
                }
            }
            .navigationTitle("Scene studio")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Done") { player?.pause(); Task { await model.cancel() }; dismiss() } }
                ToolbarItem(placement: .primaryAction) { Button("Refresh") { Task { await model.refresh() } }.disabled(model.busy) }
            }
            .task { await model.refresh() }
            .onChange(of: model.batchBriefID) { _, _ in model.clearBatchReview() }
            .onChange(of: model.batchBothShapes) { _, _ in model.clearBatchReview() }
            .sheet(item: $sharing) { StudioShareSheet(url: $0.url) }
            .sheet(isPresented: $firstUseShown, onDismiss: { Task { await model.refresh() } }) {
                NativeCreativeFirstUseView(model: model.firstUse)
            }
            .onChange(of: model.output) { _, value in player?.pause(); player = value.map { AVPlayer(url: $0) } }
            .onChange(of: model.batchOutput) { _, value in batchPlayer?.pause(); batchPlayer = value.map { AVPlayer(url: $0) } }
            .onDisappear { player?.pause(); batchPlayer?.pause(); Task { await model.cancel() } }
            .interactiveDismissDisabled(model.busy)
        }.privacySensitive()
    }
}

private struct StudioShare: Identifiable { let id = UUID(); let url: URL }
private struct StudioShareSheet: UIViewControllerRepresentable {
    let url: URL
    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: [url], applicationActivities: nil)
    }
    func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}
