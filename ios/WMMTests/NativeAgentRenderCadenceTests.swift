import XCTest
import CryptoKit
import UIKit
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

    func testCreativePacketPreservesQuarterSecondFrameRanges() throws {
        let fileID = UUID().uuidString.lowercased() + ".png"
        let hash = String(repeating: "a", count: 64)
        let scenes = (0..<4).map { NativeCreativePacket.Scene(start_frame: $0 * 90, frame_count: 90,
            caption: "Approved caption \($0)", source_id: fileID, source_hash: hash) }
        let packet = NativeCreativePacket(schema: "growth.ios-creative-batch-packet.v1", app_id: "fixture",
            title: "Fixture app", shape: "PORTRAIT", fps: 24, frame_count: 360, scenes: scenes,
            audio: "SILENT", publication: "NOT_RUN", packet_hash: hash)
        let scene = try packet.studioPacket(jobID: UUID().uuidString, manifestVersion: 1)
        XCTAssertEqual(scene.frame_count, 360)
        XCTAssertEqual(scene.scene.scenes.map(\.frameCount), [90, 90, 90, 90])
        let broken = NativeCreativePacket(schema: packet.schema, app_id: packet.app_id, title: packet.title,
            shape: packet.shape, fps: packet.fps, frame_count: 359, scenes: scenes,
            audio: packet.audio, publication: packet.publication, packet_hash: packet.packet_hash)
        XCTAssertThrowsError(try broken.studioPacket(jobID: UUID().uuidString, manifestVersion: 1))
    }

    @MainActor
    func testCreativeStillProducesRealSilentDecodedVideo() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString, isDirectory: true)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let fileID = UUID().uuidString.lowercased() + ".png"
        let image = UIGraphicsImageRenderer(size: CGSize(width: 24, height: 32)).image { context in
            UIColor.systemTeal.setFill(); context.fill(CGRect(x: 0, y: 0, width: 24, height: 32))
        }
        let bytes = try XCTUnwrap(image.pngData())
        let source = folder.appendingPathComponent(fileID); try bytes.write(to: source)
        let hash = SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
        let scenes = (0..<4).map { NativeCreativePacket.Scene(start_frame: $0 * 6, frame_count: 6,
            caption: "Synthetic caption \($0)", source_id: fileID, source_hash: hash) }
        let packet = NativeCreativePacket(schema: "growth.ios-creative-batch-packet.v1", app_id: "fixture",
            title: "Synthetic app", shape: "PORTRAIT", fps: 24, frame_count: 24, scenes: scenes,
            audio: "SILENT", publication: "NOT_RUN", packet_hash: String(repeating: "a", count: 64))
        let renderer = NativeStudioRenderer()
        let studio = try packet.studioPacket(jobID: UUID().uuidString, manifestVersion: 1)
        let output = folder.appendingPathComponent(UUID().uuidString + ".mp4")
        var inspected = false
        _ = try await renderer.render(studio, destination: output, resolveStill: { _ in source }, validate: {}, finish: { url in
            let proof = try await MediaInspector.inspectOriginal(url)
            let value = try XCTUnwrap(JSONSerialization.jsonObject(with: proof) as? [String: Any])
            let metadata = try XCTUnwrap(value["metadata"] as? [String: Any])
            let decoded = try XCTUnwrap(value["decoded"] as? [String: Any])
            XCTAssertEqual(metadata["width"] as? Int, 720)
            XCTAssertEqual(metadata["height"] as? Int, 1280)
            XCTAssertEqual(metadata["audio"] as? Bool, false)
            XCTAssertEqual(decoded["video_frames"] as? Int, 24)
            inspected = true
        })
        XCTAssertTrue(inspected)
        XCTAssertTrue(renderer.stopConfirmed)
    }
}
