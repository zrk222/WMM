import Foundation

/// Serialized in-process owner transport. A handle identifies a database, not a role.
actor DomainBridge {
    enum Failure: Error { case closed, invalidRequest }
    private var handle: String?
    private let storeRoot: URL

    init(store: LocalStore, identity: LocalIdentity) throws {
        storeRoot = store.root.standardizedFileURL.resolvingSymlinksInPath()
        let authority = identity.authority
        let providerStorage = try ProviderAuthentication(database: store.database)
        handle = try EngineBootstrap.open(database: store.database, verifier: { nonce in
            authority.verify(nonce)
        }, vault: { request in providerStorage.invoke(request) })
    }

    func workspaces(session: LocalIdentity.Session) throws -> Data {
        guard let handle else { throw Failure.closed }
        return try EngineBootstrap.workspaces(handle: handle, session: session.nonce.uuidString)
    }

    /// Call only after explicit owner confirmation in the UI.
    func enroll(session: LocalIdentity.Session, appID: String) throws -> Data {
        guard let handle else { throw Failure.closed }
        return try EngineBootstrap.enroll(handle: handle, session: session.nonce.uuidString, appID: appID)
    }

    func call(session: LocalIdentity.Session, request: Data) throws -> Data {
        guard let handle else { throw Failure.closed }
        guard !request.isEmpty, request.count <= 1_048_576 else { throw Failure.invalidRequest }
        return try EngineBootstrap.ownerCall(handle: handle, session: session.nonce.uuidString, request: request)
    }

    /// Fixed first-app path. The request must include explicit owner confirmation.
    func createWorkspace(session: LocalIdentity.Session, request: Data) throws -> Data {
        guard let handle else { throw Failure.closed }
        guard !request.isEmpty, request.count <= 1_048_576 else { throw Failure.invalidRequest }
        return try EngineBootstrap.createWorkspace(handle: handle, session: session.nonce.uuidString, request: request)
    }

    func close() {
        if let handle { EngineBootstrap.close(handle) }
        handle = nil
    }

    func evidenceForm(session: LocalIdentity.Session, appID: String) throws -> Data {
        guard let handle else { throw Failure.closed }
        return try EngineBootstrap.evidenceForm(handle: handle, session: session.nonce.uuidString, appID: appID)
    }

    func snapshotExport(session: LocalIdentity.Session, appID: String) throws -> Data {
        guard let handle else { throw Failure.closed }
        return try EngineBootstrap.snapshotExport(handle: handle, session: session.nonce.uuidString, appID: appID)
    }

    func snapshotRestore(session: LocalIdentity.Session, appID: String, request: Data, confirmed: Bool) throws -> Data {
        guard let handle else { throw Failure.closed }
        guard confirmed, !request.isEmpty, request.count <= 33_554_432 else { throw Failure.invalidRequest }
        return try EngineBootstrap.snapshotRestore(handle: handle, session: session.nonce.uuidString,
            appID: appID, request: request, confirmed: confirmed)
    }

    func updateWorkspace(session: LocalIdentity.Session, appID: String, request: Data) throws -> Data {
        guard let handle else { throw Failure.closed }
        guard !request.isEmpty, request.count <= 1_048_576 else { throw Failure.invalidRequest }
        return try EngineBootstrap.updateWorkspace(handle: handle, session: session.nonce.uuidString,
            appID: appID, request: request)
    }

    func report(session: LocalIdentity.Session, appID: String) throws -> Data {
        guard let handle else { throw Failure.closed }
        return try EngineBootstrap.report(handle: handle, session: session.nonce.uuidString, appID: appID)
    }

    func uploadMedia(session: LocalIdentity.Session, appID: String, filename: String,
                     original: URL, manifestVersion: Int, requestKey: String) async throws -> Data {
        guard let handle else { throw Failure.closed }
        // Produce inspection here from actual bytes, never from an agent envelope.
        let inspection = try await MediaInspector.inspectOriginal(original)
        try Task.checkCancellation()
        let content = try MediaIntake.readBounded(original)
        let body = try JSONSerialization.data(withJSONObject: [
            "manifest_version": manifestVersion, "request_key": requestKey] as [String: Any])
        guard self.handle == handle else { throw Failure.closed }
        return try EngineBootstrap.uploadMedia(handle: handle, session: session.nonce.uuidString,
            appID: appID, filename: filename, content: content, request: body, inspection: inspection)
    }

    func mediaList(session: LocalIdentity.Session, appID: String) throws -> Data {
        guard let handle else { throw Failure.closed }
        return try EngineBootstrap.mediaList(handle: handle, session: session.nonce.uuidString, appID: appID)
    }

    func reviewMedia(session: LocalIdentity.Session, appID: String, mediaID: String, request: Data) throws -> Data {
        guard let handle else { throw Failure.closed }
        return try EngineBootstrap.reviewMedia(handle: handle, session: session.nonce.uuidString,
            appID: appID, mediaID: mediaID, request: request)
    }

    struct ProductionPacket: Decodable {
        let schema: String; let app_id: String; let manifest_version: Int
        let project_id: String; let revision: Int; let project_hash: String
        let packet_hash: String; let status: String; let execution_authority: Bool
        let plan: NativeRenderPlan

        fileprivate func request() -> [String: Any] {
            ["project_id": project_id, "revision": revision, "project_hash": project_hash,
             "packet_hash": packet_hash]
        }
    }

    func prepareProduction(session: LocalIdentity.Session, appID: String,
                           projectID: String, revision: Int, projectHash: String) throws -> ProductionPacket {
        let result = try production(session: session, appID: appID, action: "prepare", body: [
            "project_id": projectID, "revision": revision, "project_hash": projectHash])
        let packet = try JSONDecoder().decode(ProductionPacket.self, from: result)
        guard packet.schema == "growth.ios-production-packet.v1", packet.app_id == appID,
              packet.project_id == projectID, packet.revision == revision,
              packet.project_hash == projectHash, packet.status == "PREPARED_NOT_RENDERED",
              !packet.execution_authority else { throw Failure.invalidRequest }
        try packet.plan.validateBounds()
        return packet
    }

    func validateProduction(session: LocalIdentity.Session, packet: ProductionPacket) throws {
        _ = try production(session: session, appID: packet.app_id, action: "validate", body: packet.request())
    }

    func productionSource(session: LocalIdentity.Session, packet: ProductionPacket,
                          source: NativeRenderPlan.Source) throws -> URL {
        var body = packet.request()
        body["kind"] = source.kind; body["source_id"] = source.id; body["sha256"] = source.sha256
        let result = try production(session: session, appID: packet.app_id, action: "source", body: body)
        struct SourceLocation: Decodable { let path: String }
        let location = try JSONDecoder().decode(SourceLocation.self, from: result)
        let url = URL(fileURLWithPath: location.path).standardizedFileURL.resolvingSymlinksInPath()
        guard url.path.hasPrefix(storeRoot.path + "/"),
              try url.resourceValues(forKeys: [.isRegularFileKey]).isRegularFile == true else {
            throw Failure.invalidRequest
        }
        return url
    }

    /// Authority and reuse rights are checked during resolution and after decoded output verification.
    /// A returned file is a local export, not a published campaign or shared production receipt.
    func renderProduction(session: LocalIdentity.Session, packet: ProductionPacket,
                          renderer: TimelineRenderer) async throws -> URL {
        try validateProduction(session: session, packet: packet)
        let directory = storeRoot.appendingPathComponent("native-exports", isDirectory: true)
        try LocalStore.createProtectedDirectory(directory)
        let destination = directory.appendingPathComponent(UUID().uuidString + ".mp4")
        return try await renderer.render(packet.plan, destination: destination, resolve: { source in
            try await self.productionSource(session: session, packet: packet, source: source)
        }, validateAuthority: {
            try await self.validateProduction(session: session, packet: packet)
        })
    }

    private func production(session: LocalIdentity.Session, appID: String,
                            action: String, body: [String: Any]) throws -> Data {
        guard let handle else { throw Failure.closed }
        return try EngineBootstrap.production(handle: handle, session: session.nonce.uuidString,
            appID: appID, action: action, request: JSONSerialization.data(withJSONObject: body))
    }

    deinit {
        if let handle { EngineBootstrap.close(handle) }
    }

    func agentAccess(session: LocalIdentity.Session, appID: String, action: String, request: Data) throws -> Data {
        guard let handle else { throw Failure.closed }
        guard ["list", "issue", "revoke"].contains(action), !request.isEmpty, request.count <= 1_048_576 else {
            throw Failure.invalidRequest
        }
        return try EngineBootstrap.agentAccess(handle: handle, session: session.nonce.uuidString,
            appID: appID, action: action, request: request)
    }

    func jobs(session: LocalIdentity.Session, appID: String, action: String, request: Data) throws -> Data {
        guard let handle else { throw Failure.closed }
        guard ["queue", "run", "monitor", "cancel"].contains(action), !request.isEmpty, request.count <= 1_048_576 else {
            throw Failure.invalidRequest
        }
        return try EngineBootstrap.jobs(handle: handle, session: session.nonce.uuidString,
            appID: appID, action: action, request: request)
    }

    func providers(session: LocalIdentity.Session, appID: String, action: String, request: Data) throws -> Data {
        guard let handle else { throw Failure.closed }
        guard ["view", "save", "disconnect", "cleanup"].contains(action), !request.isEmpty, request.count <= 1_048_576 else {
            throw Failure.invalidRequest
        }
        return try EngineBootstrap.providers(handle: handle, session: session.nonce.uuidString,
            appID: appID, action: action, request: request)
    }

    func inference(session: LocalIdentity.Session, appID: String, action: String, request: Data) throws -> Data {
        guard let handle else { throw Failure.closed }
        guard ["prepare", "start", "run", "read", "history", "mode"].contains(action),
              !request.isEmpty, request.count <= 1_048_576 else { throw Failure.invalidRequest }
        return try EngineBootstrap.inference(handle: handle, session: session.nonce.uuidString,
            appID: appID, action: action, request: request)
    }

    func agentCall(session: LocalIdentity.Session, credential: Data, request: Data) throws -> Data {
        guard let handle else { throw Failure.closed }
        guard credential.count == 48, let text = String(data: credential, encoding: .utf8),
              !request.isEmpty, request.count <= 1_048_576 else { throw Failure.invalidRequest }
        return try EngineBootstrap.agentCall(handle: handle, session: session.nonce.uuidString,
            credential: text, request: request)
    }
}
