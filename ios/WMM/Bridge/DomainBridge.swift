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

    func close() {
        if let handle { EngineBootstrap.close(handle) }
        handle = nil
    }

    deinit {
        if let handle { EngineBootstrap.close(handle) }
    }
}
