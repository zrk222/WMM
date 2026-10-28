import Foundation
import SwiftUI
import LocalAuthentication
import UIKit

struct NativeWorkspace: Decodable, Identifiable {
    struct Manifest: Decodable { let name: String; let job: String?; let locale: String? }
    let id: String
    let version: Int
    let data: Manifest
}
struct NativeWorkspaceList: Decodable { let apps: [NativeWorkspace] }
struct NativeWorkflowSnapshot: Decodable {
    struct Stage: Decodable, Identifiable {
        let id: Int
        let title: String
        let description: String
        let status: String
        let missing: [String]
    }
    let app: NativeWorkspace
    let stages: [Stage]
}

@MainActor
final class NativeWorkspaceModel: ObservableObject {
    @Published private(set) var unlocked = false
    @Published private(set) var busy = false
    @Published private(set) var activity = ""
    @Published private(set) var apps: [NativeWorkspace] = []
    @Published private(set) var snapshot: NativeWorkflowSnapshot?
    @Published private(set) var report: AppReport?
    @Published private(set) var media: [NativeMediaItem] = []
    @Published private(set) var message: String?
    private var identity: LocalIdentity?
    private var bridge: DomainBridge?
    private var session: LocalIdentity.Session?
    private var generation = UUID()
    private var authentication: LAContext?
    private var editorRenderer: TimelineRenderer?
    private var agentRuntime: ScopedAgentRuntime?
    var selectionContext: UUID { generation }

    private func installationID(_ key: String) throws -> UUID {
        if let text = UserDefaults.standard.string(forKey: key) {
            guard let id = UUID(uuidString: text) else { throw CocoaError(.coderReadCorrupt) }
            return id
        }
        let id = UUID()
        // Public container routing metadata, never a credential.
        UserDefaults.standard.set(id.uuidString, forKey: key)
        return id
    }

    func unlock() async {
        guard !busy else { return }
        busy = true; message = nil; activity = "Confirming device authentication…"
        let ticket = generation
        defer { if generation == ticket { busy = false; activity = "" } }
        do {
            let context = LAContext(); authentication = context
            guard try await context.evaluatePolicy(.deviceOwnerAuthentication,
                localizedReason: "Unlock your private app marketing workspace.") else { return }
            guard generation == ticket, UIApplication.shared.applicationState == .active else { return }
            activity = "Opening the protected local engine…"
            if identity == nil {
                let databaseID = try installationID("wmm.local-database-id")
                let identityID = try installationID("wmm.local-identity-namespace")
                let support = try FileManager.default.url(for: .applicationSupportDirectory,
                    in: .userDomainMask, appropriateFor: nil, create: true)
                let store = try LocalStore(applicationSupport: support, databaseID: databaseID)
                let local = LocalIdentity(vault: KeychainVault(databaseID: databaseID, appID: identityID))
                let transport = try await Task.detached { try DomainBridge(store: store, identity: local) }.value
                guard generation == ticket else { await transport.close(); return }
                identity = local; bridge = transport
            }
            guard let identity, let bridge else { throw CocoaError(.fileReadUnknown) }
            let admitted = try await identity.begin()
            guard generation == ticket else { await identity.lock(); return }
            let data = try await bridge.workspaces(session: admitted)
            let list = try JSONDecoder().decode(NativeWorkspaceList.self, from: data)
            guard generation == ticket else { await identity.lock(); return }
            session = admitted; apps = list.apps; unlocked = true; authentication = nil
        } catch {
            guard generation == ticket else { return }
            identity?.authority.revoke(); session = nil; unlocked = false
            message = "Your workspace could not unlock. Check device authentication and the bundled engine, then try again. Saved work is retained."
        }
    }

    func lock() {
        generation = UUID(); authentication?.invalidate(); authentication = nil
        identity?.authority.revoke()
        session = nil; apps = []; snapshot = nil; report = nil; media = []; unlocked = false; busy = false; activity = ""; message = nil
        if let identity { Task { await identity.lock() } }
        if let editorRenderer { Task { await editorRenderer.cancel() } }
        if let agentRuntime { Task { await agentRuntime.cancel() } }
    }

    func create(appID: String, manifest: [String: String], confirmed: Bool) async -> Bool {
        guard !busy, unlocked, confirmed, let bridge, let session else { return false }
        busy = true; message = nil; activity = "Saving your app and owner permissions…"
        let ticket = generation
        defer { if generation == ticket { busy = false; activity = "" } }
        do {
            let request = try JSONSerialization.data(withJSONObject: [
                "app_id": appID, "manifest": manifest, "confirm_owner": true] as [String: Any])
            _ = try await bridge.createWorkspace(session: session, request: request)
            let data = try await bridge.workspaces(session: session)
            let list = try JSONDecoder().decode(NativeWorkspaceList.self, from: data)
            guard generation == ticket else { return false }
            apps = list.apps; message = "Your app is saved. Open it to see its evidence and next steps."
            return true
        } catch {
            guard generation == ticket else { return false }
            message = "Workspace creation was not confirmed. Your form is retained; retrying the same setup uses the same app identifier."
            return false
        }
    }

    func open(_ app: NativeWorkspace) async {
        guard !busy, unlocked, let bridge, let session else { return }
        busy = true; message = nil; snapshot = nil; report = nil; media = []; activity = "Reading app evidence and evaluating twelve stages…"
        let ticket = generation
        defer { if generation == ticket { busy = false; activity = "" } }
        do {
            let request = try JSONSerialization.data(withJSONObject: [
                "app_id": app.id, "operation": "workspace.read", "input": [:]] as [String: Any])
            let data = try await bridge.call(session: session, request: request)
            let value = try JSONDecoder().decode(NativeWorkflowSnapshot.self, from: data)
            guard generation == ticket, value.app.id == app.id else { return }
            snapshot = value
        } catch {
            guard generation == ticket else { return }
            message = "This app could not be read. Unlock again if your session expired, or retry the read. Saved evidence is retained."
        }
    }

    func loadReport() async {
        guard !busy, unlocked, let bridge, let session, let app = snapshot?.app else { return }
        busy = true; message = nil; report = nil; activity = "Reading app-scoped analytics and report evidence…"
        let ticket = generation
        defer { if generation == ticket { busy = false; activity = "" } }
        do {
            let data = try await bridge.report(session: session, appID: app.id)
            let value = try JSONDecoder().decode(AppReport.self, from: data)
            try ReportExport.validate(value)
            guard generation == ticket, snapshot?.app.id == app.id, value.appID == app.id else { return }
            report = value
        } catch {
            guard generation == ticket else { return }
            message = "The report could not be read. Unlock again if your session expired; saved observations remain available."
        }
    }

    func loadMedia() async {
        guard !busy, unlocked, let bridge, let session, let app = snapshot?.app else { return }
        busy = true; message = nil; activity = "Reading your app's original media and reuse decisions…"
        let ticket = generation
        defer { if generation == ticket { busy = false; activity = "" } }
        do {
            let bytes = try await bridge.mediaList(session: session, appID: app.id)
            let result = try JSONDecoder().decode(NativeMediaList.self, from: bytes)
            guard generation == ticket, snapshot?.app.id == app.id else { return }
            media = result.items
        } catch {
            guard generation == ticket else { return }
            message = "Media could not be refreshed. Unlock again if your session expired. Retained originals are unchanged."
        }
    }

    func importMedia(data: Data, filename: String, requestKey: String) async {
        guard !busy, unlocked, let bridge, let session, let app = snapshot?.app else { return }
        busy = true; message = nil; activity = "Decoding the selected original and saving its exact bytes…"
        let ticket = generation
        defer { if generation == ticket { busy = false; activity = "" } }
        do {
            guard !data.isEmpty, data.count <= LocalStore.maximumMediaBytes else { throw MediaIntake.Failure.oversized }
            let suffix = URL(fileURLWithPath: filename).pathExtension.lowercased()
            guard ["mp4", "mov", "webm"].contains(suffix) else { throw MediaIntake.Failure.invalidFile }
            let staging = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + "." + suffix)
            defer { try? FileManager.default.removeItem(at: staging) }
            try data.write(to: staging, options: [.withoutOverwriting, .completeFileProtection])
            _ = try await bridge.uploadMedia(session: session, appID: app.id, filename: filename,
                original: staging, manifestVersion: app.version, requestKey: requestKey)
            let bytes = try await bridge.mediaList(session: session, appID: app.id)
            let result = try JSONDecoder().decode(NativeMediaList.self, from: bytes)
            guard generation == ticket, snapshot?.app.id == app.id else { return }
            media = result.items
            message = "Original saved. Review your reuse rights before adding it to production."
        } catch {
            guard generation == ticket else { return }
            message = "Import was not confirmed. Check the library before retrying. Supported originals are MP4, MOV or WebM up to 64 MiB and 60 seconds; the native decoder must accept the video."
        }
    }

    func reviewMedia(_ item: NativeMediaItem, status: String, basis: String, evidence: String) async -> Bool {
        guard !busy, unlocked, let bridge, let session, let app = snapshot?.app else { return false }
        busy = true; message = nil; activity = "Saving your exact source-bound reuse decision…"
        let ticket = generation
        defer { if generation == ticket { busy = false; activity = "" } }
        do {
            let body = try JSONSerialization.data(withJSONObject: ["expected_version": item.review_version,
                "manifest_version": app.version, "source_sha256": item.source_sha256,
                "status": status, "basis": basis, "evidence": evidence] as [String: Any])
            _ = try await bridge.reviewMedia(session: session, appID: app.id, mediaID: item.id, request: body)
            let bytes = try await bridge.mediaList(session: session, appID: app.id)
            let result = try JSONDecoder().decode(NativeMediaList.self, from: bytes)
            guard generation == ticket, snapshot?.app.id == app.id else { return false }
            media = result.items; message = "Your reuse decision is saved with this original's hash and current app revision."
            return true
        } catch {
            guard generation == ticket else { return false }
            message = "The decision was not confirmed. Refresh the library and review its current source and review version."
            return false
        }
    }

    func makeEditor() -> NativeEditorModel? {
        guard unlocked, let app = snapshot?.app, let bridge, let session else { return nil }
        let ticket = generation
        let renderer = TimelineRenderer(); editorRenderer = renderer
        return NativeEditorModel(appID: app.id, manifestVersion: app.version, locale: app.data.locale ?? "en-US",
            execute: { [weak self] operation, resource, input in
                guard let self, self.unlocked, self.generation == ticket, self.snapshot?.app.id == app.id else {
                    throw DomainBridge.Failure.closed
                }
                let bytes: Data
                if operation == "native.media.list" {
                    bytes = try await bridge.mediaList(session: session, appID: app.id)
                } else {
                    guard ["editor.list", "editor.read", "editor.save", "editor.edit", "editor.history"].contains(operation) else {
                        throw DomainBridge.Failure.invalidRequest
                    }
                    var envelope: [String: Any] = ["app_id": app.id, "operation": operation, "input": input]
                    if let resource { envelope["resource_id"] = resource }
                    bytes = try await bridge.call(session: session, request: JSONSerialization.data(withJSONObject: envelope))
                }
                guard self.unlocked, self.generation == ticket, self.snapshot?.app.id == app.id else {
                    throw DomainBridge.Failure.closed
                }
                return bytes
            }, render: { [weak self] project in
                guard let self, self.unlocked, self.generation == ticket, self.snapshot?.app.id == app.id else {
                    throw DomainBridge.Failure.closed
                }
                let packet = try await bridge.prepareProduction(session: session, appID: app.id,
                    projectID: project.id, revision: project.revision, projectHash: project.hash)
                let output = try await bridge.renderProduction(session: session, packet: packet, renderer: renderer)
                guard self.unlocked, self.generation == ticket, self.snapshot?.app.id == app.id else {
                    try? FileManager.default.removeItem(at: output)
                    throw DomainBridge.Failure.closed
                }
                return output
            }, cancelRender: { await renderer.cancel() })
    }

    func makeAgentAccess() -> NativeAgentAccessModel? {
        guard unlocked, let app = snapshot?.app, let bridge, let session else { return nil }
        do {
            let databaseID = try installationID("wmm.local-database-id")
            let appNamespace = try installationID("wmm.agent-namespace." + app.id)
            let vault = KeychainVault(databaseID: databaseID, appID: appNamespace)
            let runtime = ScopedAgentRuntime(bridge: bridge, session: session, vault: vault)
            agentRuntime = runtime
            let ticket = generation
            return NativeAgentAccessModel(appID: app.id, manifestVersion: app.version, runtime: runtime,
                execute: { [weak self] action, request in
                    guard let self, self.unlocked, self.generation == ticket, self.snapshot?.app.id == app.id else {
                        throw DomainBridge.Failure.closed
                    }
                    let result = try await bridge.agentAccess(session: session, appID: app.id, action: action, request: request)
                    guard self.unlocked, self.generation == ticket, self.snapshot?.app.id == app.id else {
                        throw DomainBridge.Failure.closed
                    }
                    return result
                })
        } catch {
            message = "The app's agent credential namespace could not open. Saved grants are retained; unlock and retry."
            return nil
        }
    }

    func clearSelection() {
        if let editorRenderer { Task { await editorRenderer.cancel() } }
        if let agentRuntime { Task { await agentRuntime.cancel() } }
        snapshot = nil; report = nil; media = []
    }
}
