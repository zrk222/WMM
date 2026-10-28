import SwiftUI
import AVKit
import UIKit

@MainActor
struct NativeEditorView: View {
    @ObservedObject var model: NativeEditorModel
    @Environment(\.dismiss) private var dismiss
    @State private var title = ""
    @State private var purpose = ""
    @State private var inspecting: NativeEditDefinition.Clip?
    @State private var player: AVPlayer?
    @State private var sharing: NativeVideoShare?

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Text("Build a video from your approved originals. Set the story, order and look, save each revision, then render a local video to review.")
                }
                if let project = model.selected {
                    Section("Saved timeline") {
                        Text(project.data.definition.title).font(.headline)
                        Text(project.data.definition.purpose)
                        Text("Revision \(project.revision) · \(project.data.definition.clips.count) clips · \(project.data.definition.output.lowercased())")
                        Label(project.source_status == "CURRENT" ? "Sources and reuse decisions current" : "Source review needed before export",
                              systemImage: project.source_status == "CURRENT" ? "checkmark.circle" : "exclamationmark.triangle")
                        Picker("Output frame", selection: Binding(get: { project.data.definition.output }, set: { value in
                            var definition = project.data.definition; definition.output = value
                            Task { await model.save(definition) }
                        })) {
                            Text("Portrait").tag("PORTRAIT"); Text("Landscape").tag("LANDSCAPE"); Text("Square").tag("SQUARE")
                        }.disabled(model.busy)
                        HStack {
                            Button("Undo") { Task { await model.history("UNDO") } }.disabled(model.busy || project.can_undo != true)
                            Button("Redo") { Task { await model.history("REDO") } }.disabled(model.busy || project.can_redo != true)
                        }
                    }
                    Section("Clip order — first to last") {
                        ForEach(Array(project.data.definition.clips.enumerated()), id: \.element.id) { index, clip in
                            VStack(alignment: .leading, spacing: 8) {
                                Button { inspecting = clip } label: {
                                    VStack(alignment: .leading) {
                                        Text("\(index + 1). \(clip.role.capitalized)").font(.headline)
                                        Text("Frames \(clip.in_frame)–\(clip.out_frame) · \(clip.speed_percent)% speed").font(.callout)
                                        Text("Edit trim, framing, color and audio").font(.caption)
                                    }.frame(maxWidth: .infinity, alignment: .leading)
                                }.disabled(model.busy)
                                Menu("Arrange this clip") {
                                    Button("Move earlier") { command(["operation": "move", "clip_id": clip.id, "index": index - 1]) }.disabled(index == 0)
                                    Button("Move later") { command(["operation": "move", "clip_id": clip.id, "index": index + 1]) }.disabled(index == project.data.definition.clips.count - 1)
                                    Button("Duplicate") { command(["operation": "duplicate", "clip_id": clip.id, "new_id": "clip-" + UUID().uuidString.lowercased()]) }
                                    Button("Split at midpoint") { command(["operation": "split", "clip_id": clip.id,
                                        "at_frame": (clip.in_frame + clip.out_frame) / 2, "new_id": "clip-" + UUID().uuidString.lowercased()]) }.disabled(clip.out_frame - clip.in_frame < 2)
                                    Button("Remove from timeline", role: .destructive) { command(["operation": "delete", "clip_id": clip.id]) }.disabled(project.data.definition.clips.count == 1)
                                }.disabled(model.busy)
                            }.padding(.vertical, 4)
                        }
                    }
                    Section("Add another original") { originalButtons(creating: false) }
                    Section("Render and review") {
                        Button("Render local video", systemImage: "film.stack") { Task { await model.export() } }
                            .disabled(model.busy || project.source_status != "CURRENT")
                            .accessibilityIdentifier("render-native-video")
                        Text("Up to 24 clips and 60 seconds at 24 frames per second. Rendering rechecks the saved revision and source rights, then decodes the output.").font(.callout)
                        if let output = model.output {
                            VideoPlayer(player: player).frame(minHeight: 220)
                                .onAppear { player = AVPlayer(url: output) }
                            Button("Save or share your video") { Task {
                                if let current = await model.prepareShare() { sharing = NativeVideoShare(url: current) }
                            }}.disabled(model.busy)
                            Text("Choose who receives it. A local export has not been published by Wize Marketing Machine.").font(.caption)
                        }
                    }
                } else {
                    Section("Start a timeline") {
                        TextField("Video title", text: $title)
                        TextField("What should this video help your audience do?", text: $purpose, axis: .vertical)
                        Text("Choose your first original below. You can add and stitch more clips after saving.").font(.callout)
                        originalButtons(creating: true)
                    }
                }
                if model.busy { Section { ProgressView(model.activity); Button("Cancel rendering") { Task { await model.cancel() } } } }
                if let message = model.message { Section("Action result") { Text(message).accessibilityIdentifier("editor-message") } }
                Section("Open a saved timeline") {
                    if model.projects.isEmpty { Text("No saved timelines yet. Import and approve an original in Your media, then refresh here.") }
                    ForEach(model.projects) { project in
                        Button(project.data.definition.title) { Task { await model.open(project) } }.disabled(model.busy)
                    }
                }
            }
            .navigationTitle("Video editor")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Done") { player?.pause(); Task { await model.cancel() }; dismiss() } }
                ToolbarItem(placement: .primaryAction) { Button("Refresh") { Task { await model.refresh() } }.disabled(model.busy) }
            }
            .sheet(item: $inspecting) { clip in NativeClipControls(model: model, clip: clip) }
            .sheet(item: $sharing) { NativeVideoShareSheet(url: $0.url) }
            .task { await model.refresh() }
            .onChange(of: model.output) { _, value in player?.pause(); player = value.map { AVPlayer(url: $0) } }
            .onDisappear { player?.pause(); Task { await model.cancel() } }
            .interactiveDismissDisabled(model.busy)
        }
        .privacySensitive()
    }

    private func command(_ value: [String: Any]) { Task { await model.edit(value) } }

    @ViewBuilder private func originalButtons(creating: Bool) -> some View {
        if model.originals.isEmpty { Text("No originals available. Add media in your app workspace first.") }
        ForEach(model.originals) { original in
            Button {
                Task {
                    if creating { await model.create(from: original, title: title, purpose: purpose) }
                    else { await model.insert(original) }
                }
            } label: {
                VStack(alignment: .leading) {
                    Text(original.filename)
                    Text(original.reuse_available ? "Reuse approved" : "Review reuse rights in Your media").font(.caption)
                }
            }.disabled(model.busy || !original.reuse_available || (creating && (title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || purpose.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)))
        }
    }
}

private struct NativeVideoShare: Identifiable { let id = UUID(); let url: URL }
private struct NativeVideoShareSheet: UIViewControllerRepresentable {
    let url: URL
    func makeUIViewController(context: Context) -> UIActivityViewController {
        UIActivityViewController(activityItems: [url], applicationActivities: nil)
    }
    func updateUIViewController(_ controller: UIActivityViewController, context: Context) {}
}

@MainActor
private struct NativeClipControls: View {
    @ObservedObject var model: NativeEditorModel
    @State var clip: NativeEditDefinition.Clip
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            Form {
                Section { Text("Adjust this saved source slice. Frames use a 24 fps timeline. The shared engine checks timing, crop bounds and current rights when you save.") }
                Section("Story and timing") {
                    Picker("Scene purpose", selection: $clip.role) {
                        ForEach(["HOOK", "PROBLEM", "DEMO", "PROOF", "OBJECTION", "CTA", "OTHER"], id: \.self) { Text($0.capitalized).tag($0) }
                    }
                    Stepper("Start frame: \(clip.in_frame)", value: $clip.in_frame, in: 0...1439)
                    Stepper("End frame: \(clip.out_frame)", value: $clip.out_frame, in: 1...1440)
                    Stepper("Speed: \(clip.speed_percent)%", value: $clip.speed_percent, in: 25...400, step: 25)
                    Text("End must follow start. Trim and speed must produce whole output frames.").font(.caption)
                }
                Section("Framing") {
                    Picker("Rotation", selection: $clip.transform.rotation) { ForEach([0,90,180,270], id: \.self) { Text("\($0)°").tag($0) } }
                    Toggle("Flip horizontally", isOn: $clip.transform.flip_x)
                    Toggle("Flip vertically", isOn: $clip.transform.flip_y)
                    Picker("Fit", selection: $clip.transform.fit) { Text("Contain entire frame").tag("CONTAIN"); Text("Cover output").tag("COVER") }
                    TextField("Background RGB, for example #102124", text: $clip.transform.background).textInputAutocapitalization(.characters).autocorrectionDisabled()
                    Stepper("Crop left: \(clip.transform.crop.x)/10000", value: $clip.transform.crop.x, in: 0...10000, step: 100)
                    Stepper("Crop top: \(clip.transform.crop.y)/10000", value: $clip.transform.crop.y, in: 0...10000, step: 100)
                    Stepper("Crop width: \(clip.transform.crop.width)/10000", value: $clip.transform.crop.width, in: 1...10000, step: 100)
                    Stepper("Crop height: \(clip.transform.crop.height)/10000", value: $clip.transform.crop.height, in: 1...10000, step: 100)
                }
                Section("Color and audio") {
                    Stepper("Brightness: \(clip.effects.brightness)", value: $clip.effects.brightness, in: -100...100)
                    Stepper("Contrast: \(clip.effects.contrast)", value: $clip.effects.contrast, in: 0...250)
                    Stepper("Saturation: \(clip.effects.saturation)", value: $clip.effects.saturation, in: 0...250)
                    Picker("Source audio", selection: Binding(get: { clip.audio ?? "MUTE" }, set: { clip.audio = $0 })) {
                        Text("Mute").tag("MUTE"); Text("Retain source audio").tag("RETAIN")
                    }
                }
                if let message = model.message { Section { Text(message) } }
                Section { Button("Save clip revision") { Task { await model.replace(clip) } }.disabled(model.busy) }
            }
            .navigationTitle("Edit clip")
            .toolbar { ToolbarItem(placement: .cancellationAction) { Button("Done") { dismiss() }.disabled(model.busy) } }
            .interactiveDismissDisabled(model.busy)
        }
    }
}
