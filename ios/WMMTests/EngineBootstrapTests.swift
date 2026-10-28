import XCTest
@testable import WMM

final class EngineBootstrapTests: XCTestCase {
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
