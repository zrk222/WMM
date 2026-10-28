import Foundation
import SwiftUI

struct NativeEditDefinition: Codable {
    struct Source: Codable { var kind: String; var id: String; var sha256: String }
    struct Crop: Codable { var x = 0; var y = 0; var width = 10000; var height = 10000 }
    struct Transform: Codable {
        var crop = Crop(); var rotation = 0; var flip_x = false; var flip_y = false
        var fit = "CONTAIN"; var background = "#102124"
    }
    struct Effects: Codable { var brightness = 0; var contrast = 100; var saturation = 100 }
    struct Clip: Codable, Identifiable {
        var id: String; var source: Source; var role = "DEMO"
        var in_frame = 0; var out_frame: Int; var speed_percent = 100
        var transform = Transform(); var effects = Effects(); var audio: String? = "MUTE"
    }
    var title: String; var purpose: String; var locale: String; var output = "PORTRAIT"
    var clips: [Clip]
}

struct NativeEditProject: Decodable, Identifiable {
    struct Content: Decodable { let manifest_version: Int; let definition: NativeEditDefinition }
    let id: String; let revision: Int; let hash: String; let data: Content
    let source_status: String
    let can_undo: Bool?; let can_redo: Bool?
}

/// Native presentation state only. Shared Python remains the validator and revision store.
@MainActor
final class NativeEditorModel: ObservableObject, Identifiable {
    let id = UUID()
    let appID: String
    let manifestVersion: Int
    let locale: String
    @Published private(set) var projects: [NativeEditProject] = []
    @Published private(set) var originals: [NativeMediaItem] = []
    @Published private(set) var selected: NativeEditProject?
    @Published private(set) var busy = false
    @Published private(set) var activity = ""
    @Published private(set) var message: String?
    @Published private(set) var output: URL?
    private var outputProjectHash: String?
    private let execute: @MainActor (String, String?, [String: Any]) async throws -> Data
    private let render: @MainActor (NativeEditProject) async throws -> URL
    private let cancelRender: @MainActor () async -> Void

    init(appID: String, manifestVersion: Int, locale: String,
         execute: @escaping @MainActor (String, String?, [String: Any]) async throws -> Data,
         render: @escaping @MainActor (NativeEditProject) async throws -> URL,
         cancelRender: @escaping @MainActor () async -> Void) {
        self.appID = appID; self.manifestVersion = manifestVersion; self.locale = locale
        self.execute = execute; self.render = render; self.cancelRender = cancelRender
    }

    private func object<T: Encodable>(_ value: T) throws -> [String: Any] {
        guard let result = try JSONSerialization.jsonObject(with: JSONEncoder().encode(value)) as? [String: Any] else {
            throw DomainBridge.Failure.invalidRequest
        }
        return result
    }

    private func perform(_ label: String, _ work: () async throws -> Void) async {
        guard !busy else { return }
        busy = true; activity = label; message = nil
        defer { busy = false; activity = "" }
        do { try await work() }
        catch { message = "This action was not confirmed. Refresh the saved project before retrying; your saved revisions are retained." }
    }

    func refresh() async {
        await perform("Reading saved timelines and eligible originals…") {
            struct Listing: Decodable { let items: [NativeEditProject] }
            let bytes = try await execute("editor.list", nil, [:])
            projects = try JSONDecoder().decode(Listing.self, from: bytes).items
            let media = try await execute("native.media.list", nil, [:])
            originals = try JSONDecoder().decode(NativeMediaList.self, from: media).items
            if let current = selected { try await read(current.id) }
        }
    }

    private func read(_ projectID: String) async throws {
        selected = try JSONDecoder().decode(NativeEditProject.self,
            from: await execute("editor.read", projectID, [:]))
        output = nil
        outputProjectHash = nil
    }

    func open(_ project: NativeEditProject) async {
        await perform("Opening the exact saved revision…") { try await read(project.id) }
    }

    func clip(_ media: NativeMediaItem) throws -> NativeEditDefinition.Clip {
        guard media.reuse_available, let seconds = media.metadata?.duration_seconds,
              seconds.isFinite, seconds >= 1.0 / 24 else { throw DomainBridge.Failure.invalidRequest }
        return NativeEditDefinition.Clip(id: "clip-" + UUID().uuidString.lowercased(),
            source: .init(kind: "MANAGED", id: media.id, sha256: media.source_sha256),
            out_frame: min(1440, Int((seconds * 24).rounded(.down))))
    }

    func create(from media: NativeMediaItem, title: String, purpose: String) async {
        await perform("Saving your first source-bound timeline…") {
            let definition = NativeEditDefinition(title: title, purpose: purpose, locale: locale, clips: [try clip(media)])
            let projectID = "edit-" + UUID().uuidString.lowercased()
            _ = try await execute("editor.save", nil, ["id": projectID, "revision": 0,
                "manifest_version": manifestVersion, "data": try object(definition), "request_key": UUID().uuidString])
            try await read(projectID)
            message = "Timeline saved. Set the clip order, trim and look before rendering."
        }
    }

    func save(_ definition: NativeEditDefinition) async {
        guard let project = selected else { return }
        await perform("Saving a new immutable timeline revision…") {
            _ = try await execute("editor.save", nil, ["id": project.id, "revision": project.revision,
                "manifest_version": manifestVersion, "data": try object(definition), "request_key": UUID().uuidString])
            try await read(project.id)
        }
    }

    func edit(_ command: [String: Any]) async {
        guard let project = selected else { return }
        await perform("Applying the edit to the current saved revision…") {
            _ = try await execute("editor.edit", project.id, ["revision": project.revision,
                "manifest_version": manifestVersion, "command": command, "request_key": UUID().uuidString])
            try await read(project.id)
        }
    }

    func replace(_ clip: NativeEditDefinition.Clip) async {
        do { await edit(["operation": "replace", "clip_id": clip.id, "clip": try object(clip)]) }
        catch { message = "The clip could not be encoded. Reopen its saved controls." }
    }

    func insert(_ media: NativeMediaItem) async {
        guard let project = selected else { return }
        do { await edit(["operation": "insert", "index": project.data.definition.clips.count, "clip": try object(clip(media))]) }
        catch { message = "Choose an original with current reuse rights and at least one frame of decoded video." }
    }

    func history(_ operation: String) async {
        guard let project = selected, ["UNDO", "REDO"].contains(operation) else { return }
        await perform("Restoring timeline content as a new saved revision…") {
            _ = try await execute("editor.history", project.id, ["revision": project.revision,
                "manifest_version": manifestVersion, "operation": operation, "request_key": UUID().uuidString])
            try await read(project.id)
        }
    }

    func export() async {
        guard let project = selected, project.source_status == "CURRENT" else { return }
        await perform("Rendering locally, decoding output and rechecking current rights…") {
            output = nil
            outputProjectHash = nil
            output = try await render(project)
            outputProjectHash = project.hash
            message = "Local video exported and decoded. Review it before sharing; this did not publish a campaign."
        }
    }

    func cancel() async { await cancelRender() }

    func prepareShare() async -> URL? {
        guard !busy, let project = selected, let output, outputProjectHash == project.hash else { return nil }
        var allowed: URL?
        await perform("Rechecking the current owner session and rendered source revision…") {
            let bytes = try await execute("editor.read", project.id, [:])
            let current = try JSONDecoder().decode(NativeEditProject.self, from: bytes)
            guard current.hash == project.hash, current.source_status == "CURRENT" else {
                throw DomainBridge.Failure.invalidRequest
            }
            allowed = output
        }
        return allowed
    }
}
