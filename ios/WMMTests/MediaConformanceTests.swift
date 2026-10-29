import XCTest
import AVFoundation
import CoreImage
@testable import WMM

final class MediaConformanceTests: XCTestCase {
    @MainActor
    func testStudioUsesApprovedVideoFramesAndRechecksSource() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let source = folder.appendingPathComponent("red.mp4")
        try await syntheticVideo(at: source, frames: 48, color: CGColor(red: 1, green: 0, blue: 0, alpha: 1))
        let mediaID = UUID().uuidString.lowercased()
        let payload: [String: Any] = ["schema": "growth.ios-studio-packet.v1", "app_id": "synthetic",
            "project_id": "scene-one", "revision": 1, "source_hash": String(repeating: "a", count: 64),
            "manifest_version": 1, "scene": ["title": "Title", "shape": "LANDSCAPE", "scenes": [
                ["text": "Caption", "seconds": 1, "media": ["id": mediaID, "sha256": String(repeating: "b", count: 64), "in_frame": 12, "audio": "MUTE"]]]],
            "fps": 24, "frame_count": 24, "status": "PREPARED_NOT_RENDERED", "execution_authority": false,
            "packet_hash": String(repeating: "c", count: 64)]
        let packet = try JSONDecoder().decode(NativeStudioPacket.self, from: JSONSerialization.data(withJSONObject: payload))
        let output = folder.appendingPathComponent("output.mp4")
        var resolutions = 0
        let renderer = NativeStudioRenderer()
        _ = try await renderer.render(packet, destination: output, resolve: { sourceMedia in
            XCTAssertEqual(sourceMedia.id, mediaID); resolutions += 1; return source
        }, validate: {}, finish: { _ in })
        XCTAssertEqual(resolutions, 2)
        let asset = AVURLAsset(url: output)
        let tracks = try await asset.loadTracks(withMediaType: .video)
        let video = try XCTUnwrap(tracks.first)
        let reader = try AVAssetReader(asset: asset)
        let decoded = AVAssetReaderTrackOutput(track: video, outputSettings: [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA])
        XCTAssertTrue(reader.canAdd(decoded)); reader.add(decoded); XCTAssertTrue(reader.startReading())
        var frames = 0
        while let sample = decoded.copyNextSampleBuffer() {
            if frames == 6 {
                let pixels = try XCTUnwrap(CMSampleBufferGetImageBuffer(sample))
                CVPixelBufferLockBaseAddress(pixels, .readOnly)
                let base = try XCTUnwrap(CVPixelBufferGetBaseAddress(pixels))
                let offset = 700 * CVPixelBufferGetBytesPerRow(pixels) + 100 * 4
                XCTAssertGreaterThan(Int(base.load(fromByteOffset: offset + 2, as: UInt8.self)), Int(base.load(fromByteOffset: offset, as: UInt8.self)) + 80)
                CVPixelBufferUnlockBaseAddress(pixels, .readOnly)
            }
            frames += 1
        }
        XCTAssertEqual(reader.status, .completed); XCTAssertEqual(frames, 24)
        let audios = try await asset.loadTracks(withMediaType: .audio)
        XCTAssertTrue(audios.isEmpty)
        let denied = folder.appendingPathComponent("denied.mp4")
        resolutions = 0
        do {
            _ = try await renderer.render(packet, destination: denied, resolve: { _ in
                resolutions += 1
                if resolutions == 2 { throw DomainBridge.Failure.closed }
                return source
            }, validate: {}, finish: { _ in XCTFail("Revoked source was committed") })
            XCTFail("Revoked source accepted")
        } catch DomainBridge.Failure.closed {}
        XCTAssertFalse(FileManager.default.fileExists(atPath: denied.path))
    }

    @MainActor
    func testStudioRetainsDecodedSourceAudio() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let picture = folder.appendingPathComponent("picture.mp4")
        try await syntheticVideo(at: picture, frames: 48, color: CGColor(red: 0, green: 0, blue: 1, alpha: 1))
        let wave = folder.appendingPathComponent("tone.wav")
        let format = try XCTUnwrap(AVAudioFormat(standardFormatWithSampleRate: 48000, channels: 1))
        let pcm = try XCTUnwrap(AVAudioPCMBuffer(pcmFormat: format, frameCapacity: 96000))
        pcm.frameLength = 96000
        let samples = try XCTUnwrap(pcm.floatChannelData?[0])
        for index in 0..<96000 { samples[index] = 0.2 * sin(Float(index) * 2 * .pi * 440 / 48000) }
        do {
            let file = try AVAudioFile(forWriting: wave, settings: format.settings)
            try file.write(from: pcm)
        }
        let composition = AVMutableComposition()
        let videoSource = AVURLAsset(url: picture), soundSource = AVURLAsset(url: wave)
        let videoTracks = try await videoSource.loadTracks(withMediaType: .video)
        let soundTracks = try await soundSource.loadTracks(withMediaType: .audio)
        let video = try XCTUnwrap(composition.addMutableTrack(withMediaType: .video, preferredTrackID: kCMPersistentTrackID_Invalid))
        let audio = try XCTUnwrap(composition.addMutableTrack(withMediaType: .audio, preferredTrackID: kCMPersistentTrackID_Invalid))
        let duration = CMTime(value: 48, timescale: 24)
        try video.insertTimeRange(CMTimeRange(start: .zero, duration: duration), of: try XCTUnwrap(videoTracks.first), at: .zero)
        try audio.insertTimeRange(CMTimeRange(start: .zero, duration: duration), of: try XCTUnwrap(soundTracks.first), at: .zero)
        let source = folder.appendingPathComponent("with-audio.mp4")
        let exporter = try XCTUnwrap(AVAssetExportSession(asset: composition, presetName: AVAssetExportPresetHighestQuality))
        exporter.outputURL = source; exporter.outputFileType = .mp4
        await withCheckedContinuation { continuation in exporter.exportAsynchronously { continuation.resume() } }
        XCTAssertEqual(exporter.status, .completed)
        let mediaID = UUID().uuidString.lowercased()
        let payload: [String: Any] = ["schema": "growth.ios-studio-packet.v1", "app_id": "synthetic", "project_id": "sound",
            "revision": 1, "source_hash": String(repeating: "a", count: 64), "manifest_version": 1,
            "scene": ["title": "Title", "shape": "LANDSCAPE", "scenes": [["text": "Caption", "seconds": 1,
                "media": ["id": mediaID, "sha256": String(repeating: "b", count: 64), "in_frame": 12, "audio": "RETAIN"]]]],
            "fps": 24, "frame_count": 24, "status": "PREPARED_NOT_RENDERED", "execution_authority": false,
            "packet_hash": String(repeating: "c", count: 64)]
        let packet = try JSONDecoder().decode(NativeStudioPacket.self, from: JSONSerialization.data(withJSONObject: payload))
        let output = folder.appendingPathComponent("result.mp4")
        _ = try await NativeStudioRenderer().render(packet, destination: output, resolve: { _ in source }, validate: {}, finish: { _ in })
        let proof = try await MediaInspector.inspectOriginal(output)
        let value = try XCTUnwrap(JSONSerialization.jsonObject(with: proof) as? [String: Any])
        let metadata = try XCTUnwrap(value["metadata"] as? [String: Any])
        let decoded = try XCTUnwrap(value["decoded"] as? [String: Any])
        XCTAssertEqual(metadata["audio"] as? Bool, true)
        XCTAssertEqual(decoded["video_frames"] as? Int, 24)
        XCTAssertGreaterThan(decoded["audio_frames"] as? Int ?? 0, 0)
    }

    @MainActor
    func testStudioEmbeddedRevisionRenderReopenAndAuthorityDenials() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let database = UUID()
        let store = try LocalStore(applicationSupport: folder, databaseID: database)
        let identity = LocalIdentity(vault: KeychainVault(databaseID: database, appID: UUID()))
        let session = try await identity.begin()
        let bridge = try DomainBridge(store: store, identity: identity)
        let appID = "studio-" + UUID().uuidString.lowercased()
        let setup: [String: Any] = ["app_id": appID, "confirm_owner": true,
            "manifest": ["name": "Synthetic studio", "release": "build-1", "locale": "en-US", "currency": "USD"]]
        _ = try await bridge.createWorkspace(session: session, request: JSONSerialization.data(withJSONObject: setup))
        let scene: [String: Any] = ["title": "Synthetic", "shape": "LANDSCAPE", "scenes": [
            ["text": "First scene", "seconds": 1], ["text": "Second scene", "seconds": 1]]]
        let saved = try await bridge.studio(session: session, appID: appID, action: "save", body: [
            "project_id": "scene-one", "base_revision": 0, "manifest_version": 1,
            "request_key": UUID().uuidString, "scene": scene])
        let project = try JSONDecoder().decode(NativeStudioProject.self, from: saved)
        struct Start: Decodable { let job: NativeStudioJob; let packet: NativeStudioPacket }
        func start() async throws -> Start {
            let data = try await bridge.studio(session: session, appID: appID, action: "start", body: [
                "project_id": project.project_id, "revision": project.revision, "source_hash": project.source_hash,
                "request_key": UUID().uuidString])
            return try JSONDecoder().decode(Start.self, from: data)
        }
        let started = try await start()
        XCTAssertEqual(started.packet.frame_count, 48)
        let renderer = NativeStudioRenderer()
        let output = try await bridge.studioDestination(jobID: started.job.job_id)
        let request: [String: Any] = ["job_id": started.job.job_id, "packet_hash": started.packet.packet_hash]
        do {
            _ = try await renderer.render(started.packet, destination: output, validate: {
                _ = try await bridge.studio(session: session, appID: appID, action: "validate", body: request)
            }, finish: { url in
                _ = try await bridge.finishStudio(session: session, appID: appID, jobID: started.job.job_id,
                    packetHash: started.packet.packet_hash, output: url)
                throw DomainBridge.Failure.closed // Model a lost response after commit.
            })
            XCTFail("Lost finish response was treated as accepted")
        } catch DomainBridge.Failure.closed {}
        XCTAssertTrue(FileManager.default.fileExists(atPath: output.path))
        _ = try await bridge.finishStudio(session: session, appID: appID, jobID: started.job.job_id,
            packetHash: started.packet.packet_hash, output: output)
        let reopened = try await bridge.studioArtifact(session: session, appID: appID, jobID: started.job.job_id)
        XCTAssertEqual(reopened, output)
        let inspected = try JSONDecoder().decode(NativeStudioJob.self,
            from: await bridge.studio(session: session, appID: appID, action: "inspect", body: ["job_id": started.job.job_id]))
        XCTAssertEqual(inspected.status, "SUCCEEDED")
        XCTAssertEqual(inspected.result?.frames, 48)

        let cancelled = try await start()
        _ = try await bridge.studio(session: session, appID: appID, action: "cancel", body: ["job_id": cancelled.job.job_id])
        let denied = try await bridge.studioDestination(jobID: cancelled.job.job_id)
        do {
            _ = try await renderer.render(cancelled.packet, destination: denied, validate: {
                _ = try await bridge.studio(session: session, appID: appID, action: "validate", body: [
                    "job_id": cancelled.job.job_id, "packet_hash": cancelled.packet.packet_hash])
            }, finish: { _ in XCTFail("Cancelled render reached completion") })
            XCTFail("Cancelled render accepted")
        } catch {}
        XCTAssertFalse(FileManager.default.fileExists(atPath: denied.path))

        let stale = try await start()
        var changed = scene; changed["title"] = "Revised"
        let savedRevision = try await bridge.studio(session: session, appID: appID, action: "save", body: ["project_id": project.project_id,
            "base_revision": 1, "manifest_version": 1, "request_key": UUID().uuidString, "scene": changed])
        let revision = try JSONDecoder().decode(NativeStudioProject.self, from: savedRevision)
        do {
            _ = try await bridge.studio(session: session, appID: appID, action: "validate", body: [
                "job_id": stale.job.job_id, "packet_hash": stale.packet.packet_hash])
            XCTFail("Old project revision remained current")
        } catch {}
        let historical = try await bridge.studioArtifact(session: session, appID: appID, jobID: started.job.job_id)
        XCTAssertEqual(historical, output)
        let lockedStart = try JSONDecoder().decode(Start.self, from: await bridge.studio(session: session, appID: appID, action: "start", body: [
            "project_id": revision.project_id, "revision": revision.revision, "source_hash": revision.source_hash,
            "request_key": UUID().uuidString]))
        let lockedOutput = try await bridge.studioDestination(jobID: lockedStart.job.job_id)
        var checks = 0
        do {
            _ = try await renderer.render(lockedStart.packet, destination: lockedOutput, validate: {
                checks += 1
                if checks == 2 { await identity.lock() }
                _ = try await bridge.studio(session: session, appID: appID, action: "validate", body: [
                    "job_id": lockedStart.job.job_id, "packet_hash": lockedStart.packet.packet_hash])
            }, finish: { _ in XCTFail("Locked render reached completion") })
            XCTFail("Locked render accepted")
        } catch {}
        XCTAssertEqual(checks, 2)
        XCTAssertFalse(FileManager.default.fileExists(atPath: lockedOutput.path))
        do {
            _ = try await bridge.studioArtifact(session: session, appID: appID, jobID: started.job.job_id)
            XCTFail("Locked session reopened a studio artifact")
        } catch {}
        await bridge.close()
        try await identity.forgetPrincipal()
    }

    @MainActor
    func testSceneStudioRendersExactFramesAndRejectsRevokedOutput() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: folder) }
        let value: [String: Any] = ["schema": "growth.ios-studio-packet.v1", "app_id": "synthetic-app",
            "project_id": "scene-one", "revision": 1, "source_hash": String(repeating: "a", count: 64),
            "manifest_version": 1, "scene": ["title": "Synthetic", "shape": "LANDSCAPE", "scenes": [
                ["text": "First scene", "seconds": 1], ["text": "Second scene", "seconds": 1]]],
            "fps": 24, "frame_count": 48, "status": "PREPARED_NOT_RENDERED", "execution_authority": false,
            "packet_hash": String(repeating: "b", count: 64)]
        let packet = try JSONDecoder().decode(NativeStudioPacket.self, from: JSONSerialization.data(withJSONObject: value))
        let renderer = NativeStudioRenderer()
        let destination = folder.appendingPathComponent(UUID().uuidString + ".mp4")
        var checks = 0, finished = false
        let output = try await renderer.render(packet, destination: destination, validate: { checks += 1 }, finish: { url in
            let proof = try await MediaInspector.inspectOriginal(url)
            let root = try XCTUnwrap(JSONSerialization.jsonObject(with: proof) as? [String: Any])
            let decoded = try XCTUnwrap(root["decoded"] as? [String: Any])
            XCTAssertEqual(decoded["video_frames"] as? Int, 48)
            finished = true
        })
        XCTAssertEqual(checks, 2)
        XCTAssertTrue(finished)
        let asset = AVURLAsset(url: output)
        let tracks = try await asset.loadTracks(withMediaType: .video)
        let track = try XCTUnwrap(tracks.first)
        let reader = try AVAssetReader(asset: asset)
        let decoded = AVAssetReaderTrackOutput(track: track, outputSettings: [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA])
        XCTAssertTrue(reader.canAdd(decoded)); reader.add(decoded); XCTAssertTrue(reader.startReading())
        var index = 0, images: [Data] = []
        while let sample = decoded.copyNextSampleBuffer() {
            if index == 6 || index == 30 {
                let pixels = try XCTUnwrap(CMSampleBufferGetImageBuffer(sample))
                CVPixelBufferLockBaseAddress(pixels, .readOnly)
                let base = try XCTUnwrap(CVPixelBufferGetBaseAddress(pixels))
                images.append(Data(bytes: base, count: CVPixelBufferGetDataSize(pixels)))
                CVPixelBufferUnlockBaseAddress(pixels, .readOnly)
            }
            index += 1
        }
        XCTAssertEqual(reader.status, .completed)
        XCTAssertEqual(index, 48)
        XCTAssertEqual(images.count, 2)
        if images.count == 2 { XCTAssertNotEqual(images[0], images[1]) }
        let denied = folder.appendingPathComponent(UUID().uuidString + ".mp4")
        checks = 0; finished = false
        do {
            _ = try await renderer.render(packet, destination: denied, validate: {
                checks += 1
                if checks == 2 { throw DomainBridge.Failure.closed }
            }, finish: { _ in finished = true })
            XCTFail("Revoked scene output was accepted")
        } catch DomainBridge.Failure.closed {}
        XCTAssertEqual(checks, 2)
        XCTAssertFalse(finished)
        XCTAssertFalse(FileManager.default.fileExists(atPath: denied.path))
        let uncertain = folder.appendingPathComponent(UUID().uuidString + ".mp4")
        do {
            _ = try await renderer.render(packet, destination: uncertain, validate: {}, finish: { _ in
                throw DomainBridge.Failure.closed
            })
            XCTFail("Failed finish was reported as accepted")
        } catch DomainBridge.Failure.closed {}
        XCTAssertTrue(FileManager.default.fileExists(atPath: uncertain.path), "Retain bytes while finish outcome is uncertain")
    }

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
        var phase = "create fixture directory"
        defer { print("WMM_STITCH_PHASE=\(phase); taskCancelled=\(Task.isCancelled)") }
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at:folder,withIntermediateDirectories:true)
        defer { try? FileManager.default.removeItem(at:folder) }
        let red = folder.appendingPathComponent("red.mp4"), blue = folder.appendingPathComponent("blue.mp4")
        phase = "write red source"
        try await syntheticVideo(at:red,frames:48,color:CGColor(red:1,green:0,blue:0,alpha:1))
        phase = "write blue source"
        try await syntheticVideo(at:blue,frames:48,color:CGColor(red:0,green:0,blue:1,alpha:1))
        phase = "compile native plan"
        let timeline = try plan()
        let renderer = TimelineRenderer()
        let destination = folder.appendingPathComponent("stitched.mp4")
        phase = "render with internal decode and authority checks"
        let output = try await renderer.render(timeline,destination:destination,resolve:{ source in
            source.id.hasPrefix("1111") ? red : blue
        }, validateAuthority:{})
        XCTAssertEqual(output, destination)
        XCTAssertTrue(FileManager.default.fileExists(atPath: destination.path))
        phase = "independent output verification"
        try await MediaInspector.verify(output,plan:timeline,expectsAudio:false)
        // Verify exact decoded frame positions, avoiding approximate seek/image
        // generation as a second, unrelated async pipeline in this frame test.
        let renderedAsset = AVURLAsset(url: output)
        phase = "open final output track"
        let tracks = try await renderedAsset.loadTracks(withMediaType: .video)
        let track = try XCTUnwrap(tracks.first)
        let reader = try AVAssetReader(asset: renderedAsset)
        let decoded = AVAssetReaderTrackOutput(track: track,
            outputSettings: [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA])
        guard reader.canAdd(decoded) else { throw TimelineRenderer.Failure.exportFailed }
        reader.add(decoded)
        XCTAssertTrue(reader.startReading())
        var frame = 0, checked = 0
        phase = "verify decoded red and blue frame order"
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
        let deniedOutput = folder.appendingPathComponent("denied.mp4")
        var authorityChecks = 0
        phase = "reject revoked authority and remove partial output"
        do {
            _ = try await renderer.render(timeline, destination: deniedOutput, resolve: { source in
                source.id.hasPrefix("1111") ? red : blue
            }, validateAuthority: {
                authorityChecks += 1
                if authorityChecks > 1 { throw DomainBridge.Failure.closed }
            })
            XCTFail("Output returned after authority was revoked")
        } catch DomainBridge.Failure.closed {}
        XCTAssertEqual(authorityChecks, 2)
        XCTAssertFalse(FileManager.default.fileExists(atPath: deniedOutput.path))
        phase = "completed all assertions"
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
        // Exercise actual scoped-agent rendering and the owner's decoded export handoff.
        let scopedRuntime = ScopedAgentRuntime(bridge: bridge, session: session,
            vault: KeychainVault(databaseID: database, appID: UUID()))
        let issued = try await bridge.agentAccess(session: session, appID: appID, action: "issue",
            request: JSONSerialization.data(withJSONObject: ["confirm_scope": true, "grant": [
                "agent_id": "synthetic-render-agent", "manifest_version": 1, "operations": ["ios.timeline.queue"],
                "expires": ISO8601DateFormatter().string(from: Date().addingTimeInterval(3600)), "max_calls": 2]]))
        let grantID = try await scopedRuntime.retainIssuedGrant(issued)
        let agentRequest = try JSONSerialization.data(withJSONObject: ["app_id": appID, "operation": "ios.timeline.queue",
            "input": ["project_id": "native-edit", "revision": 1, "project_hash": projectHash, "request_key": UUID().uuidString.lowercased()]])
        let rendered = try await scopedRuntime.call(grantID: grantID, request: agentRequest)
        let receipt = try XCTUnwrap(JSONSerialization.jsonObject(with: rendered) as? [String: Any])
        let nativeRender = try XCTUnwrap(receipt["native_render"] as? [String: Any])
        XCTAssertEqual(nativeRender["status"] as? String, "SUCCEEDED")
        let agentJobID = try XCTUnwrap(nativeRender["job_id"] as? String)
        let agentOutput = try await bridge.agentTimelineArtifact(session: session, appID: appID, jobID: agentJobID)
        try await MediaInspector.verify(agentOutput, plan: packet.plan, expectsAudio: false)
        let originalBytes = try Data(contentsOf: agentOutput)
        try Data("synthetic corrupt video".utf8).write(to: agentOutput)
        do {
            _ = try await bridge.agentTimelineArtifact(session: session, appID: appID, jobID: agentJobID)
            XCTFail("Corrupt agent output remained shareable")
        } catch {}
        try originalBytes.write(to: agentOutput)
        let videoModel = await NativeAgentVideoModel(execute: { action, request in
            try await bridge.agentTimeline(session: session, appID: appID, action: action,
                body: NativeAgentLoopModel.object(request))
        }, artifact: { identity in try await bridge.agentTimelineArtifact(session: session, appID: appID, jobID: identity) })
        await videoModel.refresh()
        let videoJobs = await videoModel.jobs
        let videoJob = try XCTUnwrap(videoJobs.first)
        XCTAssertEqual(videoJob.job_id, agentJobID)
        let verifiedShare = await videoModel.verifiedURL(videoJob)
        XCTAssertEqual(verifiedShare, agentOutput)
        await videoModel.close(); await scopedRuntime.cancel()
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
