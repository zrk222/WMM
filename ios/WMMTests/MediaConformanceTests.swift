import XCTest
import AVFoundation
import CoreImage
@testable import WMM

final class MediaConformanceTests: XCTestCase {
    private func syntheticVideo(at url: URL, frames: Int, color: CGColor) async throws {
        let writer = try AVAssetWriter(outputURL: url, fileType: .mp4)
        let input = AVAssetWriterInput(mediaType: .video, outputSettings: [
            AVVideoCodecKey: AVVideoCodecType.h264, AVVideoWidthKey: 720, AVVideoHeightKey: 720
        ])
        let adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: input, sourcePixelBufferAttributes: [
            kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32ARGB,
            kCVPixelBufferWidthKey as String: 720, kCVPixelBufferHeightKey as String: 720,
            kCVPixelBufferCGImageCompatibilityKey as String: true,
            kCVPixelBufferCGBitmapContextCompatibilityKey as String: true
        ])
        guard writer.canAdd(input) else { throw TimelineRenderer.Failure.exportFailed }
        writer.add(input)
        guard writer.startWriting() else { throw TimelineRenderer.Failure.exportFailed }
        writer.startSession(atSourceTime: .zero)
        for frame in 0..<frames {
            let deadline = Date().addingTimeInterval(10)
            while !input.isReadyForMoreMediaData {
                guard Date() < deadline, writer.status == .writing else { throw TimelineRenderer.Failure.exportFailed }
                try await Task.sleep(nanoseconds: 2_000_000)
            }
            var buffer: CVPixelBuffer?
            guard let pool = adaptor.pixelBufferPool,
                  CVPixelBufferPoolCreatePixelBuffer(nil, pool, &buffer) == kCVReturnSuccess,
                  let pixels = buffer else { throw TimelineRenderer.Failure.exportFailed }
            CVPixelBufferLockBaseAddress(pixels, [])
            let context = CGContext(data: CVPixelBufferGetBaseAddress(pixels), width: 720, height: 720,
                bitsPerComponent: 8, bytesPerRow: CVPixelBufferGetBytesPerRow(pixels),
                space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.noneSkipFirst.rawValue)
            context?.setFillColor(color); context?.fill(CGRect(x: 0,y: 0,width: 720,height: 720))
            CVPixelBufferUnlockBaseAddress(pixels, [])
            guard context != nil, adaptor.append(pixels, withPresentationTime: CMTime(value: Int64(frame), timescale: 24)) else {
                throw TimelineRenderer.Failure.exportFailed
            }
        }
        input.markAsFinished()
        await withCheckedContinuation { continuation in writer.finishWriting { continuation.resume() } }
        guard writer.status == .completed else { throw TimelineRenderer.Failure.exportFailed }
    }

    private func plan(total: Int = 48) throws -> NativeRenderPlan {
        let source: [String: Any] = ["kind":"MANAGED", "id":"11111111-1111-1111-1111-111111111111", "sha256":String(repeating:"a",count:64)]
        let transform: [String: Any] = ["crop":["x":0,"y":0,"width":10000,"height":10000],
            "rotation":0,"flip_x":false,"flip_y":false,"fit":"CONTAIN","background":"#000000"]
        let effects = ["brightness":0,"contrast":100,"saturation":100]
        let clips: [[String: Any]] = [
            ["id":"red-clip","source":source,"role":"HOOK","source_in_frame":12,"source_out_frame":36,
             "speed_percent":100,"output_start_frame":0,"output_frame_count":24,"transform":transform,"effects":effects,"audio":"MUTE"],
            ["id":"blue-clip","source":source.merging(["id":"22222222-2222-2222-2222-222222222222"]) { _,new in new },
             "role":"DEMO","source_in_frame":0,"source_out_frame":48,"speed_percent":200,"output_start_frame":24,
             "output_frame_count":24,"transform":transform,"effects":effects,"audio":"MUTE"]
        ]
        let value: [String: Any] = ["schema":"growth.ios-render-plan.v1","project_sha256":String(repeating:"b",count:64),
            "plan_sha256":String(repeating:"c",count:64),"fps":24,"width":720,"height":720,"output_frame_count":total,"clips":clips]
        return try JSONDecoder().decode(NativeRenderPlan.self, from: JSONSerialization.data(withJSONObject:value))
    }

    func testActualTrimStitchSpeedAndDecodedColorOrder() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at:folder,withIntermediateDirectories:true)
        defer { try? FileManager.default.removeItem(at:folder) }
        let red = folder.appendingPathComponent("red.mp4"), blue = folder.appendingPathComponent("blue.mp4")
        try await syntheticVideo(at:red,frames:48,color:CGColor(red:1,green:0,blue:0,alpha:1))
        try await syntheticVideo(at:blue,frames:48,color:CGColor(red:0,green:0,blue:1,alpha:1))
        let timeline = try plan()
        let renderer = TimelineRenderer()
        let destination = folder.appendingPathComponent("stitched.mp4")
        let output = try await renderer.render(timeline,destination:destination,resolve:{ source in
            source.id.hasPrefix("1111") ? red : blue
        }, validateAuthority:{})
        try await MediaInspector.verify(output,plan:timeline,expectsAudio:false)
        let generator = AVAssetImageGenerator(asset:AVURLAsset(url:output))
        generator.requestedTimeToleranceBefore = .zero; generator.requestedTimeToleranceAfter = .zero
        let context = CIContext()
        for (frame,redExpected) in [(6,true),(30,false)] {
            let cg = try generator.copyCGImage(at:CMTime(value:Int64(frame),timescale:24),actualTime:nil)
            let image = CIImage(cgImage:cg)
            var pixel = [UInt8](repeating:0,count:4)
            context.render(image,toBitmap:&pixel,rowBytes:4,bounds:CGRect(x:360,y:360,width:1,height:1),format:.RGBA8,colorSpace:CGColorSpaceCreateDeviceRGB())
            if redExpected { XCTAssertGreaterThan(Int(pixel[0]),Int(pixel[2])+100) }
            else { XCTAssertGreaterThan(Int(pixel[2]),Int(pixel[0])+100) }
        }
    }

    func testOriginalInspectionDecodesRealFramesAndRejectsCorruptBytes() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let source = folder.appendingPathComponent("original.mp4")
        try await syntheticVideo(at: source, frames: 48, color: CGColor(red: 1, green: 0, blue: 0, alpha: 1))
        let proof = try await MediaInspector.inspectOriginal(source)
        let value = try XCTUnwrap(JSONSerialization.jsonObject(with: proof) as? [String: Any])
        let metadata = try XCTUnwrap(value["metadata"] as? [String: Any])
        let decoded = try XCTUnwrap(value["decoded"] as? [String: Any])
        XCTAssertEqual(metadata["width"] as? Int, 720)
        XCTAssertEqual(metadata["height"] as? Int, 720)
        XCTAssertEqual(metadata["audio"] as? Bool, false)
        XCTAssertEqual(decoded["video_frames"] as? Int, 48)
        XCTAssertEqual(decoded["audio_frames"] as? Int, 0)
        XCTAssertEqual(value["bytes"] as? Int, try Data(contentsOf: source).count)
        let corrupt = folder.appendingPathComponent("corrupt.mp4")
        try Data("synthetic invalid video".utf8).write(to: corrupt)
        do {
            _ = try await MediaInspector.inspectOriginal(corrupt)
            XCTFail("Corrupt original accepted as decoded")
        } catch {}
    }

    func testInvalidPlanCannotInvokeResolver() async throws {
        let json = Data("{}".utf8)
        XCTAssertThrowsError(try JSONDecoder().decode(NativeRenderPlan.self,from:json))
        let invalid = try plan(total:47)
        let renderer = TimelineRenderer()
        let destination = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString + ".mp4")
        do {
            _ = try await renderer.render(invalid,destination:destination,resolve:{ _ in
                XCTFail("Invalid frame count reached source resolution")
                throw TimelineRenderer.Failure.invalidPlan
            },validateAuthority:{ XCTFail("Invalid frame count reached authority admission") })
            XCTFail("Invalid timeline rendered")
        } catch TimelineRenderer.Failure.invalidPlan {}
        XCTAssertFalse(FileManager.default.fileExists(atPath:destination.path))
    }
}
