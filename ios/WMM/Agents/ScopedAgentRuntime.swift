import Foundation

/// A local tool transport for configured agents. Tokens stay in app-scoped Keychain;
/// models supply only bounded operation JSON, never credentials or owner sessions.
actor ScopedAgentRuntime {
    enum Failure: Error { case invalidGrant, credentialUnavailable, cancelled, resultNeedsReconciliation }
    private let bridge: DomainBridge
    private let session: LocalIdentity.Session
    private let vault: KeychainVault
    private var generation = UUID()
    private var stopped = false

    init(bridge: DomainBridge, session: LocalIdentity.Session, vault: KeychainVault) {
        self.bridge = bridge; self.session = session; self.vault = vault
    }

    private func reference(_ grantID: String) throws -> String {
        guard let id = UUID(uuidString: grantID) else { throw Failure.invalidGrant }
        return "agent-grant-" + id.uuidString.lowercased()
    }

    /// The owner grant control calls this once. The returned value is an opaque ID,
    /// not a token. On storage failure, leave the grant visible for owner revocation.
    func retainIssuedGrant(_ response: Data) async throws -> String {
        guard !stopped else { throw Failure.cancelled }
        struct Issued: Decodable {
            struct Grant: Decodable { let id: String }
            let grant: Grant; let token: String; let token_delivery: String
        }
        let issued = try JSONDecoder().decode(Issued.self, from: response)
        guard issued.token_delivery == "ONCE_ONLY", issued.token.utf8.count == 48,
              issued.token.range(of: "^wmmg_[A-Za-z0-9_-]{43}$", options: .regularExpression) != nil else {
            throw Failure.invalidGrant
        }
        let key = try reference(issued.grant.id)
        try await vault.save(Data(issued.token.utf8), reference: key)
        return issued.grant.id
    }

    func call(grantID: String, request: Data) async throws -> Data {
        guard !stopped else { throw Failure.cancelled }
        guard !request.isEmpty, request.count <= 1_048_576 else { throw Failure.invalidGrant }
        let ticket = generation
        guard let credential = try await vault.read(reference: reference(grantID)) else { throw Failure.credentialUnavailable }
        try Task.checkCancellation()
        guard !stopped, ticket == generation else { throw Failure.cancelled }
        let result = try await bridge.agentCall(session: session, credential: credential, request: request)
        guard !stopped, ticket == generation else { throw Failure.resultNeedsReconciliation }
        return result
    }

    func forgetCredential(grantID: String) async throws {
        try await vault.delete(reference: reference(grantID))
    }

    /// Stops future dispatch. An in-flight effect needs read-back, never blind replay.
    /// Shared grant revocation remains a separate exact owner action.
    func cancel() { stopped = true; generation = UUID() }
}
