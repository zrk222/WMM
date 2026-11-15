import CryptoKit
import SQLite3
import XCTest
@testable import WMM

final class EngineBootstrapTests: XCTestCase {
    @MainActor
    func testNativeDatabaseRecordsEveryBundledMigration() async throws {
        let root = try XCTUnwrap(Bundle.main.resourceURL)
            .appendingPathComponent("app/mission_control/migrations", isDirectory: true)
        let resources = try FileManager.default.contentsOfDirectory(at: root, includingPropertiesForKeys: nil)
            .filter { $0.lastPathComponent.range(of: #"^[0-9]{4}_[a-z0-9_]+[.]sql$"#, options: .regularExpression) != nil }
            .sorted { $0.lastPathComponent < $1.lastPathComponent }
        XCTAssertFalse(resources.isEmpty, "The app must package its ordered SQLite migration resources")

        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: folder) }
        let id = UUID()
        let store = try LocalStore(applicationSupport: folder, databaseID: id)
        let identity = LocalIdentity(vault: KeychainVault(databaseID: id, appID: UUID()))
        let bridge = try DomainBridge(store: store, identity: identity)
        await bridge.close()

        var handle: OpaquePointer?
        let opened = sqlite3_open_v2(store.database.path, &handle, SQLITE_OPEN_READONLY, nil)
        defer { if let handle { sqlite3_close(handle) } }
        XCTAssertEqual(opened, SQLITE_OK)
        let db = try XCTUnwrap(handle)
        var query: OpaquePointer?
        let prepared = sqlite3_prepare_v2(db, "SELECT version, checksum FROM schema_migrations ORDER BY version", -1, &query, nil)
        defer { sqlite3_finalize(query) }
        XCTAssertEqual(prepared, SQLITE_OK)
        let statement = try XCTUnwrap(query)
        XCTAssertEqual(sqlite3_step(statement), SQLITE_ROW)
        XCTAssertEqual(sqlite3_column_int(statement, 0), 0)
        for (index, resource) in resources.enumerated() {
            let expected = SHA256.hash(data: try Data(contentsOf: resource))
                .map { String(format: "%02x", $0) }.joined()
            let version = try XCTUnwrap(Int32(resource.lastPathComponent.prefix(4)))
            XCTAssertEqual(version, Int32(index + 1))
            XCTAssertEqual(sqlite3_step(statement), SQLITE_ROW)
            XCTAssertEqual(sqlite3_column_int(statement, 0), version)
            let checksum = try XCTUnwrap(sqlite3_column_text(statement, 1))
            XCTAssertEqual(String(cString: checksum), expected)
        }
        XCTAssertEqual(sqlite3_step(statement), SQLITE_DONE)
    }

    func testBundledInterpreterLoadsSharedDomainInventory() throws {
        let data = try XCTUnwrap(EngineBootstrap.inventory())
        let value = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual(value["schema"] as? String, "growth.ios-capability-inventory.v1")
        XCTAssertEqual(value["transport"] as? String, "IN_PROCESS_JSON")
        let operations = try XCTUnwrap(value["operations"] as? [String: Any])
        XCTAssertGreaterThanOrEqual(operations.count, 60)
        XCTAssertNotNil(operations["workspace.read"])
        XCTAssertNotNil(operations["editor.edit"])
        XCTAssertNotNil(operations["growth.read"])
        XCTAssertEqual(value["operation_count"] as? Int, operations.count)
        XCTAssertEqual(value["execution_authority"] as? Bool, false)
        // Import success must never promote unfinished native workflow acceptance.
        XCTAssertEqual(value["full_parity"] as? Bool, false)
        XCTAssertEqual(value["native_acceptance"] as? String, "NOT_RUN")
        let repeated = try XCTUnwrap(EngineBootstrap.inventory())
        XCTAssertEqual(data, repeated)
    }
}
