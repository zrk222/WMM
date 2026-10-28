import AVFoundation
import CoreImage
import Foundation

/// Data comes from ios_render_plan.compile_plan, after shared domain validation.
struct NativeRenderPlan: Decodable {
    struct Source: Decodable { let kind: String; let id: String; let sha256: String }
    struct Crop: Decodable { let x: Int; let y: Int; let width: Int; let height: Int }
    struct Transform: Decodable {
        let crop: Crop; let rotation: Int; let flip_x: Bool; let flip_y: Bool
        let fit: String; let background: String
    }
    struct Effects: Decodable { let brightness: Int; let contrast: Int; let saturation: Int }
    struct Clip: Decodable {
        let id: String; let source: Source; let role: String
        let source_in_frame: Int; let source_out_frame: Int; let speed_percent: Int
        let output_start_frame: Int; let output_frame_count: Int
        let transform: Transform; let effects: Effects; let audio: String
    }
    let schema: String; let project_sha256: String; let plan_sha256: String
    let fps: Int; let width: Int; let height: Int; let output_frame_count: Int
    let clips: [Clip]

    func validateBounds() throws {
        guard schema == "growth.ios-render-plan.v1", fps == 24,
              [(720,1280),(1280,720),(720,720)].contains(where: { $0.0 == width && $0.1 == height }),
              (1...24).contains(clips.count), (1...1440).contains(output_frame_count) else {
            throw TimelineRenderer.Failure.invalidPlan
        }
        var cursor = 0
        for clip in clips {
            let crop = clip.transform.crop
            guard (0...1440).contains(clip.source_in_frame),
                  (1...1440).contains(clip.source_out_frame), clip.source_out_frame > clip.source_in_frame,
                  (25...400).contains(clip.speed_percent), clip.speed_percent % 25 == 0,
                  (clip.source_out_frame - clip.source_in_frame) * 100 % clip.speed_percent == 0,
                  clip.output_frame_count == (clip.source_out_frame - clip.source_in_frame) * 100 / clip.speed_percent,
                  clip.output_start_frame == cursor,
                  ["MUTE","RETAIN"].contains(clip.audio),
                  [0,90,180,270].contains(clip.transform.rotation),
                  ["CONTAIN","COVER"].contains(clip.transform.fit),
                  (0...10000).contains(crop.x), (0...10000).contains(crop.y),
                  crop.width > 0, crop.height > 0, crop.x + crop.width <= 10000, crop.y + crop.height <= 10000,
                  (-100...100).contains(clip.effects.brightness),
                  (0...250).contains(clip.effects.contrast), (0...250).contains(clip.effects.saturation),
                  clip.transform.background.range(of: "^#[a-fA-F0-9]{6}$", options: .regularExpression) != nil else {
                throw TimelineRenderer.Failure.invalidPlan
            }
            cursor += clip.output_frame_count
        }
        guard cursor == output_frame_count else { throw TimelineRenderer.Failure.invalidPlan }
    }
}

/// Resolver and authority checks are trusted host adapters, never paths in a model response.
actor TimelineRenderer {
    enum Failure: Error { case invalidPlan, missingVideo, sourceTooShort, exportFailed, cancelled }
    private var active: AVAssetExportSession?
    private var rendering = false
    private var cancelled = false

    func cancel() { cancelled = true; active?.cancelExport() }

    func render(_ plan: NativeRenderPlan, destination: URL,
                resolve: (NativeRenderPlan.Source) async throws -> URL,
                validateAuthority: () async throws -> Void) async throws -> URL {
        guard !rendering else { throw Failure.invalidPlan }
        rendering = true; cancelled = false
        defer { rendering = false; active = nil }
        try plan.validateBounds()
        try await validateAuthority()
        guard destination.isFileURL, !FileManager.default.fileExists(atPath: destination.path), active == nil else {
            throw Failure.invalidPlan
        }
        let composition = AVMutableComposition()
        var retainedAudio = false
        for clip in plan.clips {
            try Task.checkCancellation()
            guard !cancelled else { throw Failure.cancelled }
            let url = try await resolve(clip.source)
            guard url.isFileURL else { throw Failure.invalidPlan }
            let asset = AVURLAsset(url: url)
            let duration = try await asset.load(.duration)
            let end = CMTime(value: Int64(clip.source_out_frame), timescale: 24)
            guard duration.isNumeric, CMTimeCompare(duration, end) >= 0 else { throw Failure.sourceTooShort }
            guard let sourceVideo = try await asset.loadTracks(withMediaType: .video).first,
                  let video = composition.addMutableTrack(withMediaType: .video, preferredTrackID: kCMPersistentTrackID_Invalid) else {
                throw Failure.missingVideo
            }
            let start = CMTime(value: Int64(clip.output_start_frame), timescale: 24)
            let range = CMTimeRange(start: CMTime(value: Int64(clip.source_in_frame), timescale: 24),
                                    duration: CMTime(value: Int64(clip.source_out_frame - clip.source_in_frame), timescale: 24))
            let scaled = CMTime(value: Int64(clip.output_frame_count), timescale: 24)
            try video.insertTimeRange(range, of: sourceVideo, at: start)
            video.preferredTransform = try await sourceVideo.load(.preferredTransform)
            video.scaleTimeRange(CMTimeRange(start: start, duration: range.duration), toDuration: scaled)
            if clip.audio == "RETAIN", let sourceAudio = try await asset.loadTracks(withMediaType: .audio).first,
               let audio = composition.addMutableTrack(withMediaType: .audio, preferredTrackID: kCMPersistentTrackID_Invalid) {
                try audio.insertTimeRange(range, of: sourceAudio, at: start)
                audio.scaleTimeRange(CMTimeRange(start: start, duration: range.duration), toDuration: scaled)
                retainedAudio = true
            }
        }
        let videoComposition = AVMutableVideoComposition(asset: composition, applyingCIFiltersWithHandler: { request in
            let frame = Int((CMTimeGetSeconds(request.compositionTime) * 24).rounded(.down))
            guard let clip = plan.clips.first(where: { frame >= $0.output_start_frame && frame < $0.output_start_frame + $0.output_frame_count }) else {
                request.finish(with: NSError(domain: "WMM.Render", code: 1)); return
            }
            request.finish(with: Self.transform(request.sourceImage, clip: clip, plan: plan), context: nil)
        })
        videoComposition.renderSize = CGSize(width: CGFloat(plan.width), height: CGFloat(plan.height))
        videoComposition.frameDuration = CMTime(value: 1, timescale: 24)
        guard let exporter = AVAssetExportSession(asset: composition, presetName: AVAssetExportPresetHighestQuality) else {
            throw Failure.exportFailed
        }
        active = exporter
        guard !cancelled else { throw Failure.cancelled }
        let staging = destination.deletingLastPathComponent().appendingPathComponent(UUID().uuidString + ".mp4")
        defer { try? FileManager.default.removeItem(at: staging) }
        exporter.outputURL = staging; exporter.outputFileType = .mp4
        exporter.videoComposition = videoComposition
        exporter.timeRange = CMTimeRange(start: .zero, duration: CMTime(value: Int64(plan.output_frame_count), timescale: 24))
        await withTaskCancellationHandler(operation: {
            await withCheckedContinuation { continuation in
                exporter.exportAsynchronously { continuation.resume() }
            }
        }, onCancel: { exporter.cancelExport() })
        try Task.checkCancellation()
        guard exporter.status == .completed else {
            if exporter.status == .cancelled { throw Failure.cancelled }
            throw Failure.exportFailed
        }
        try await MediaInspector.verify(staging, plan: plan, expectsAudio: retainedAudio)
        for clip in plan.clips { _ = try await resolve(clip.source) }
        try await validateAuthority()
        guard !cancelled else { throw Failure.cancelled }
        try FileManager.default.setAttributes([.protectionKey: FileProtectionType.complete], ofItemAtPath: staging.path)
        try FileManager.default.moveItem(at: staging, to: destination)
        return destination
    }

    private static func transform(_ input: CIImage, clip: NativeRenderPlan.Clip, plan: NativeRenderPlan) -> CIImage {
        let extent = input.extent, crop = clip.transform.crop
        let rectangle = CGRect(x: extent.minX + extent.width * CGFloat(crop.x) / 10000,
                               y: extent.minY + extent.height * CGFloat(10000 - crop.y - crop.height) / 10000,
                               width: extent.width * CGFloat(crop.width) / 10000,
                               height: extent.height * CGFloat(crop.height) / 10000)
        var image = input.cropped(to: rectangle).transformed(by: CGAffineTransform(translationX: -rectangle.minX, y: -rectangle.minY))
        image = image.transformed(by: CGAffineTransform(rotationAngle: -CGFloat(clip.transform.rotation) * .pi / 180))
        image = image.transformed(by: CGAffineTransform(scaleX: clip.transform.flip_x ? -1 : 1, y: clip.transform.flip_y ? -1 : 1))
        image = image.transformed(by: CGAffineTransform(translationX: -image.extent.minX, y: -image.extent.minY))
        let sx = CGFloat(plan.width) / image.extent.width, sy = CGFloat(plan.height) / image.extent.height
        let scale = clip.transform.fit == "COVER" ? max(sx,sy) : min(sx,sy)
        image = image.transformed(by: CGAffineTransform(scaleX: scale, y: scale))
        image = image.transformed(by: CGAffineTransform(translationX: (CGFloat(plan.width)-image.extent.width)/2, y: (CGFloat(plan.height)-image.extent.height)/2))
        image = image.applyingFilter("CIColorControls", parameters: [kCIInputBrightnessKey: Double(clip.effects.brightness)/100,
            kCIInputContrastKey: Double(clip.effects.contrast)/100, kCIInputSaturationKey: Double(clip.effects.saturation)/100])
        let rgb = UInt32(clip.transform.background.dropFirst(), radix: 16) ?? 0
        let background = CIImage(color: CIColor(red: CGFloat((rgb>>16)&255)/255, green: CGFloat((rgb>>8)&255)/255, blue: CGFloat(rgb&255)/255))
        return image.composited(over: background).cropped(to: CGRect(x: 0,y: 0,width: CGFloat(plan.width),height: CGFloat(plan.height)))
    }
}
