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
        // Verify exact decoded frame positions, avoiding approximate seek/image
        // generation as a second, unrelated async pipeline in this frame test.
        let renderedAsset = AVURLAsset(url: output)
        let tracks = try await renderedAsset.loadTracks(withMediaType: .video)
        let track = try XCTUnwrap(tracks.first)
        let reader = try AVAssetReader(asset: renderedAsset)
        let decoded = AVAssetReaderTrackOutput(track: track,
            outputSettings: [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA])
        guard reader.canAdd(decoded) else { throw TimelineRenderer.Failure.exportFailed }
        reader.add(decoded)
        XCTAssertTrue(reader.startReading())
        var frame = 0, checked = 0
        while let sample = decoded.copyNextSampleBuffer() {
            if frame == 6 || frame == 30 {
                let pixels = try XCTUnwrap(CMSampleBufferGetImageBuffer(sample))
                CVPixelBufferLockBaseAddress(pixels, .readOnly)
                defer { CVPixelBufferUnlockBaseAddress(pixels, .readOnly) }
                let base = try XCTUnwrap(CVPixelBufferGetBaseAddress(pixels))
                let offset = 360 * CVPixelBufferGetBytesPerRow(pixels) + 360 * 4
                let blue = Int(base.load(fromByteOffset: offset, as: UInt8.self))
                let red = Int(base.load(fromByteOffset: offset + 2, as: UInt8.self))
                if frame == 6 { XCTAssertGreaterThan(red, blue + 100) }
                else { XCTAssertGreaterThan(blue, red + 100) }
                checked += 1
            }
            frame += 1
        }
        XCTAssertEqual(reader.status, .completed)
        XCTAssertEqual(frame, 48)
        XCTAssertEqual(checked, 2)
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

    func testNativeOriginalIntakeAndOwnerReviewThroughEmbeddedEngine() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let database = UUID()
        let store = try LocalStore(applicationSupport: folder, databaseID: database)
        let identity = LocalIdentity(vault: KeychainVault(databaseID: database, appID: UUID()))
        let session = try await identity.begin()
        let bridge = try DomainBridge(store: store, identity: identity)
        let appID = "media-" + UUID().uuidString.lowercased()
        let setup = try JSONSerialization.data(withJSONObject: ["app_id": appID, "confirm_owner": true,
            "manifest": ["name": "Synthetic intake", "release": "build-1", "locale": "en-US", "currency": "USD"]] as [String: Any])
        _ = try await bridge.createWorkspace(session: session, request: setup)
        let source = folder.appendingPathComponent("original.mp4")
        try await syntheticVideo(at: source, frames: 48, color: CGColor(red: 1, green: 0, blue: 0, alpha: 1))
        let key = UUID().uuidString
        let uploaded = try await bridge.uploadMedia(session: session, appID: appID,
            filename: "original.mp4", original: source, manifestVersion: 1, requestKey: key)
        let item = try JSONDecoder().decode(NativeMediaItem.self, from: uploaded)
        XCTAssertFalse(item.reuse_available)
        XCTAssertEqual(item.rights_status, "UNKNOWN")
        let replay = try await bridge.uploadMedia(session: session, appID: appID,
            filename: "original.mp4", original: source, manifestVersion: 1, requestKey: key)
        XCTAssertEqual(try JSONDecoder().decode(NativeMediaItem.self, from: replay).id, item.id)
        let decision = try JSONSerialization.data(withJSONObject: ["expected_version": 0, "manifest_version": 1,
            "source_sha256": item.source_sha256, "status": "ALLOWED", "basis": "OWNED",
            "evidence": "Synthetic generated test source"] as [String: Any])
        let reviewed = try await bridge.reviewMedia(session: session, appID: appID, mediaID: item.id, request: decision)
        XCTAssertTrue(try JSONDecoder().decode(NativeMediaItem.self, from: reviewed).reuse_available)
        let listing = try await bridge.mediaList(session: session, appID: appID)
        XCTAssertEqual(try JSONDecoder().decode(NativeMediaList.self, from: listing).items.count, 1)
        let clip: [String: Any] = ["id": "clip-one",
            "source": ["kind": "MANAGED", "id": item.id, "sha256": item.source_sha256],
            "role": "HOOK", "in_frame": 0, "out_frame": 24, "speed_percent": 100,
            "transform": ["crop": ["x": 0, "y": 0, "width": 10000, "height": 10000],
                "rotation": 0, "flip_x": false, "flip_y": false, "fit": "CONTAIN", "background": "#102124"] as [String: Any],
            "effects": ["brightness": 0, "contrast": 100, "saturation": 100]]
        let definition: [String: Any] = ["title": "Synthetic native edit", "purpose": "Verify retained original.",
            "locale": "en-US", "output": "SQUARE", "clips": [clip]]
        let save = try JSONSerialization.data(withJSONObject: ["app_id": appID, "operation": "editor.save",
            "input": ["id": "native-edit", "revision": 0, "manifest_version": 1,
                "data": definition, "request_key": UUID().uuidString] as [String: Any]] as [String: Any])
        let saved = try await bridge.call(session: session, request: save)
        let project = try XCTUnwrap(JSONSerialization.jsonObject(with: saved) as? [String: Any])
        let projectHash = try XCTUnwrap(project["hash"] as? String)
        let packet = try await bridge.prepareProduction(session: session, appID: appID,
            projectID: "native-edit", revision: 1, projectHash: projectHash)
        let output = try await bridge.renderProduction(session: session, packet: packet, renderer: TimelineRenderer())
        XCTAssertTrue(output.path.hasPrefix(store.root.path + "/native-exports/"))
        try await MediaInspector.verify(output, plan: packet.plan, expectsAudio: false)
        let editor = await NativeEditorModel(appID: appID, manifestVersion: 1, locale: "en-US", execute: { operation, resource, input in
            if operation == "native.media.list" { return try await bridge.mediaList(session: session, appID: appID) }
            var envelope: [String: Any] = ["app_id": appID, "operation": operation, "input": input]
            if let resource { envelope["resource_id"] = resource }
            return try await bridge.call(session: session, request: JSONSerialization.data(withJSONObject: envelope))
        }, render: { saved in
            let prepared = try await bridge.prepareProduction(session: session, appID: appID,
                projectID: saved.id, revision: saved.revision, projectHash: saved.hash)
            return try await bridge.renderProduction(session: session, packet: prepared, renderer: TimelineRenderer())
        }, cancelRender: {})
        await editor.refresh()
        let projects = await editor.projects
        XCTAssertEqual(projects.count, 1)
        try await editor.open(XCTUnwrap(projects.first))
        let before = await editor.selected
        XCTAssertEqual(before?.revision, 1)
        await editor.edit(["operation": "duplicate", "clip_id": "clip-one", "new_id": "clip-two"])
        let duplicated = await editor.selected
        XCTAssertEqual(duplicated?.data.definition.clips.count, 2)
        XCTAssertEqual(duplicated?.revision, 2)
        await editor.history("UNDO")
        let undone = await editor.selected
        XCTAssertEqual(undone?.data.definition.clips.count, 1)
        await editor.history("REDO")
        let redone = await editor.selected
        XCTAssertEqual(redone?.data.definition.clips.count, 2)
        await editor.edit(["operation": "delete", "clip_id": "unknown-clip"])
        let rejected = await editor.message
        XCTAssertNotNil(rejected)
        await editor.export()
        let shareable = await editor.prepareShare()
        XCTAssertNotNil(shareable)
        await identity.lock()
        let lockedShare = await editor.prepareShare()
        XCTAssertNil(lockedShare)
        do {
            _ = try await bridge.mediaList(session: session, appID: appID)
            XCTFail("Locked media access admitted")
        } catch {}
        do {
            try await bridge.validateProduction(session: session, packet: packet)
            XCTFail("Locked production packet admitted")
        } catch {}
        await bridge.close()
        try await identity.forgetPrincipal()
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
