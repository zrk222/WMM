import Foundation

/// Synchronous callback for Python transaction guards. No waiting on an actor or UI.
/// Every read verifies the actual protected Keychain principal, not cached authority.
final class NativeSessionAuthority: @unchecked Sendable {
    private let mutex = NSLock()
    private let vault: KeychainVault
    private var admitted: LocalIdentity.Session?

    init(vault: KeychainVault) { self.vault = vault }

    func admit(_ session: LocalIdentity.Session) {
        mutex.lock(); defer { mutex.unlock() }
        admitted = session
    }

    func revoke() {
        mutex.lock(); defer { mutex.unlock() }
        admitted = nil
    }

    func verify(_ nonce: String, now: Date = Date()) -> [String: Any]? {
        mutex.lock(); defer { mutex.unlock() }
        guard let session = admitted, session.nonce.uuidString == nonce,
              session.expiresAt > now,
              let data = try? vault.read(reference: "local-principal"),
              String(data: data, encoding: .utf8) == session.principal.uuidString else { return nil }
        return ["principal": session.principal.uuidString,
                "session_generation": session.generation.uuidString,
                "expires_at_epoch": session.expiresAt.timeIntervalSince1970]
    }
}
