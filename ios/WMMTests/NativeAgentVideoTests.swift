import XCTest
@testable import WMM

final class NativeAgentVideoTests: XCTestCase {
    @MainActor
    func testClosingDuringFileVerificationCannotReturnShareableURL() async throws {
        var pending: CheckedContinuation<URL, Error>?
        let model = NativeAgentVideoModel(execute: { _, _ in Data("{\"items\":[]}".utf8) }, artifact: { _ in
            try await withCheckedThrowingContinuation { pending = $0 }
        })
        let bytes = try JSONSerialization.data(withJSONObject: ["job_id": UUID().uuidString.lowercased(), "project_id": "synthetic", "revision": 1, "status": "SUCCEEDED"])
        let job = try JSONDecoder().decode(NativeAgentVideoModel.Job.self, from: bytes)
        let read = Task { await model.verifiedURL(job) }
        for _ in 0..<100 { if pending != nil { break }; await Task.yield() }
        XCTAssertNotNil(pending); XCTAssertTrue(model.busy)
        model.close()
        pending?.resume(returning: URL(fileURLWithPath: "/synthetic-fixture.mp4"))
        let output = await read.value
        XCTAssertNil(output); XCTAssertTrue(model.jobs.isEmpty)
    }

    @MainActor
    func testFailedVerificationReturnsNoPreviewOrShareFile() async throws {
        var attempts = 0
        let model = NativeAgentVideoModel(execute: { _, _ in Data("{\"items\":[]}".utf8) }, artifact: { _ in
            attempts += 1; throw DomainBridge.Failure.invalidRequest
        })
        let bytes = try JSONSerialization.data(withJSONObject: ["job_id": UUID().uuidString.lowercased(), "project_id": "synthetic", "revision": 1, "status": "SUCCEEDED"])
        let output = await model.verifiedURL(try JSONDecoder().decode(NativeAgentVideoModel.Job.self, from: bytes))
        XCTAssertNil(output); XCTAssertEqual(attempts, 1); XCTAssertNotNil(model.message)
        model.close()
    }
}
