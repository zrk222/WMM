import Foundation

/// Device-local principal and process-bound session; this does not grant an owner role.
/// The shared domain admission layer must separately resolve membership and grants.
actor LocalIdentity {
    struct Session: Equatable, Sendable {
        let principal: UUID
        let generation: UUID
        let nonce: UUID
        let expiresAt: Date
    }
    enum Failure: Error { case corruptIdentity, expiredOrRevokedSession, operationInProgress }
    private let vault: KeychainVault
    private var generation = UUID()
    private var admitted: Session?
    private var mutating = false

    init(vault: KeychainVault) { self.vault = vault }

    func begin(now: Date = Date()) async throws -> Session {
        guard !mutating else { throw Failure.operationInProgress }
        mutating = true
        defer { mutating = false }
        let startingGeneration = generation
        let principal: UUID
        if let data = try await vault.read(reference: "local-principal") {
            guard let text = String(data: data, encoding: .utf8), let id = UUID(uuidString: text) else {
                throw Failure.corruptIdentity
            }
            principal = id
        } else {
            principal = UUID()
            try await vault.save(Data(principal.uuidString.utf8), reference: "local-principal")
        }
        guard generation == startingGeneration else { throw Failure.expiredOrRevokedSession }
        let value = Session(principal: principal, generation: startingGeneration, nonce: UUID(),
                            expiresAt: now.addingTimeInterval(900))
        admitted = value
        return value
    }

    func requireCurrent(_ session: Session, now: Date = Date()) async throws {
        let data = try await vault.read(reference: "local-principal")
        guard admitted == session, session.generation == generation, session.expiresAt > now,
              let data = data,
              String(data: data, encoding: .utf8) == session.principal.uuidString else {
            throw Failure.expiredOrRevokedSession
        }
    }

    func lock() { admitted = nil; generation = UUID() }

    func forgetPrincipal() async throws {
        guard !mutating else { throw Failure.operationInProgress }
        mutating = true
        defer { mutating = false }
        lock()
        try await vault.delete(reference: "local-principal")
    }
}
