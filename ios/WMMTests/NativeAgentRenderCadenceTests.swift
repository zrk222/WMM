import XCTest
@testable import WMM

final class NativeAgentRenderCadenceTests: XCTestCase {
    @MainActor
    func testDecodedFramesRequireExpectedDurationAndNominalCadence() throws {
        XCTAssertNoThrow(try NativeAgentRenderPump.validateCadence(frames: 24, duration: 1, rate: 24, expectedFrames: 24))
        XCTAssertThrowsError(try NativeAgentRenderPump.validateCadence(frames: 24, duration: 2, rate: 12, expectedFrames: 24))
        XCTAssertThrowsError(try NativeAgentRenderPump.validateCadence(frames: 24, duration: 1, rate: 12, expectedFrames: 24))
        XCTAssertThrowsError(try NativeAgentRenderPump.validateCadence(frames: 23, duration: 1, rate: 24, expectedFrames: 24))
        XCTAssertThrowsError(try NativeAgentRenderPump.validateCadence(frames: 24, duration: .nan, rate: 24, expectedFrames: 24))
    }
}
