import Foundation

/// Serialized in-process owner transport. A handle identifies a database, not a role.
actor DomainBridge {
    enum Failure: Error { case closed, invalidRequest }
    private var handle: String?

    init(store: LocalStore, identity: LocalIdentity) throws {
        let authority = identity.authority
        handle = try EngineBootstrap.open(database: store.database, verifier: { nonce in
            authority.verify(nonce)
        })
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

    deinit {
        if let handle { EngineBootstrap.close(handle) }
    }
}
