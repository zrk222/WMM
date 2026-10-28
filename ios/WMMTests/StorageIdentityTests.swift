import XCTest
@testable import WMM

final class StorageIdentityTests: XCTestCase {
    func testSessionExpiryLockAndRestartRevokeAdmission() async throws {
        let vault = KeychainVault(databaseID: UUID(), appID: UUID())
        let identity = LocalIdentity(vault: vault)
        let now = Date()
        let session = try await identity.begin(now: now)
        try await identity.requireCurrent(session, now: now)
        do {
            try await identity.requireCurrent(session, now: now.addingTimeInterval(901))
            XCTFail("Expired session admitted")
        } catch LocalIdentity.Failure.expiredOrRevokedSession {}
        await identity.lock()
        do {
            try await identity.requireCurrent(session, now: now)
            XCTFail("Locked session admitted")
        } catch LocalIdentity.Failure.expiredOrRevokedSession {}
        let restarted = LocalIdentity(vault: vault)
        do {
            try await restarted.requireCurrent(session, now: now)
            XCTFail("Restored process session admitted")
        } catch LocalIdentity.Failure.expiredOrRevokedSession {}
        try await restarted.forgetPrincipal()
    }

    func testDeviceLocalKeychainRoundTripAndNamespaceIsolation() async throws {
        let database = UUID(), app = UUID()
        let vault = KeychainVault(databaseID: database, appID: app)
        let foreign = KeychainVault(databaseID: database, appID: UUID())
        let value = Data(UUID().uuidString.utf8)
        try await vault.save(value, reference: "synthetic-key")
        let actual = try await vault.read(reference: "synthetic-key")
        let absent = try await foreign.read(reference: "synthetic-key")
        XCTAssertEqual(actual, value)
        XCTAssertNil(absent)
        try await vault.delete(reference: "synthetic-key")
        let removed = try await vault.read(reference: "synthetic-key")
        XCTAssertNil(removed)
    }

    func testOriginalMediaIsImmutableAndProtected() throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: folder) }
        let store = try LocalStore(applicationSupport: folder, databaseID: UUID())
        let id = UUID(), data = Data("synthetic-original".utf8)
        let path = try store.retainMedia(data, id: id)
        XCTAssertEqual(try Data(contentsOf: path), data)
        XCTAssertThrowsError(try store.retainMedia(Data("changed".utf8), id: id))
        XCTAssertEqual(try Data(contentsOf: path), data)
        XCTAssertThrowsError(try store.retainMedia(Data(), id: UUID()))
        let attributes = try FileManager.default.attributesOfItem(atPath: path.path)
        XCTAssertEqual(attributes[.protectionKey] as? FileProtectionType, .complete)
    }
}
