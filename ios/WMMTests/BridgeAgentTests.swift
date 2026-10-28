import XCTest
@testable import WMM

final class BridgeAgentTests: XCTestCase {
    func testProtectedNativeVerifierRejectsLockExpiryAndPrincipalChange() async throws {
        let vault = KeychainVault(databaseID: UUID(), appID: UUID())
        let identity = LocalIdentity(vault: vault)
        let session = try await identity.begin()
        XCTAssertNotNil(identity.authority.verify(session.nonce.uuidString))
        XCTAssertNil(identity.authority.verify(UUID().uuidString))
        XCTAssertNil(identity.authority.verify(session.nonce.uuidString, now: session.expiresAt))
        try await vault.save(Data(UUID().uuidString.utf8), reference: "local-principal")
        XCTAssertNil(identity.authority.verify(session.nonce.uuidString))
        await identity.lock()
        XCTAssertNil(identity.authority.verify(session.nonce.uuidString))
        try await identity.forgetPrincipal()
    }

    func testEmbeddedRuntimeUsesNativeIdentityAndClosesWithoutServer() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: folder) }
        let databaseID = UUID()
        let store = try LocalStore(applicationSupport: folder, databaseID: databaseID)
        let vault = KeychainVault(databaseID: databaseID, appID: UUID())
        let identity = LocalIdentity(vault: vault)
        let session = try await identity.begin()
        let bridge = try DomainBridge(store: store, identity: identity)
        let data = try await bridge.workspaces(session: session)
        let result = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual((result["apps"] as? [Any])?.count, 0)
        let appID = "native-" + UUID().uuidString.lowercased()
        let request = try JSONSerialization.data(withJSONObject: [
            "app_id": appID, "confirm_owner": true,
            "manifest": ["name": "Synthetic native app", "job": "Improve activation",
                         "release": "build-1", "locale": "en-US", "currency": "USD"]
        ])
        let created = try await bridge.createWorkspace(session: session, request: request)
        let replay = try await bridge.createWorkspace(session: session, request: request)
        XCTAssertEqual(created, replay)
        let populated = try await bridge.workspaces(session: session)
        let apps = try XCTUnwrap((JSONSerialization.jsonObject(with: populated) as? [String: Any])?["apps"] as? [[String: Any]])
        XCTAssertEqual(apps.count, 1)
        XCTAssertEqual(apps.first?["id"] as? String, appID)
        let read = try JSONSerialization.data(withJSONObject: ["app_id": appID, "operation": "growth.history", "input": [:]] as [String: Any])
        let history = try await bridge.call(session: session, request: read)
        XCTAssertEqual((try JSONSerialization.jsonObject(with: history) as? [String: Any])?["app_id"] as? String, appID)
        await identity.lock()
        do {
            _ = try await bridge.workspaces(session: session)
            XCTFail("Locked native identity admitted")
        } catch {}
        await bridge.close()
        do {
            _ = try await bridge.workspaces(session: session)
            XCTFail("Closed native bridge admitted")
        } catch DomainBridge.Failure.closed {}
        try await identity.forgetPrincipal()
    }
}
