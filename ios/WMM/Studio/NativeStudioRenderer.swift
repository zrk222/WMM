import AVFoundation
import UIKit

struct NativeStudioScene: Codable, Equatable {
    struct Media: Codable, Equatable {
        var id: String
        var sha256: String
        var in_frame: Int
        var audio: String
    }
    struct Item: Codable, Equatable, Identifiable {
        var text: String
        var seconds: Int
        var media: Media? = nil
        var id: String { text + "-" + String(seconds) }
    }
    var title: String
    var shape: String
    var scenes: [Item]
}

struct NativeStudioPacket: Decodable {
    let schema: String
    let app_id: String
    let project_id: String
    let revision: Int
    let source_hash: String
    let manifest_version: Int
    let scene: NativeStudioScene
    let fps: Int
    let frame_count: Int
    let status: String
    let execution_authority: Bool
    let packet_hash: String

    func validateBounds() throws {
        func literal(_ value: String) -> Bool {
            let scalars = value.unicodeScalars
            return !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && scalars.count <= 240 &&
                scalars.allSatisfy { scalar in
                    let n = scalar.value
                    return (n == 9 || n == 10 || n == 13 || (32...0xd7ff).contains(n) ||
                        (0xe000...0xfffd).contains(n) || (0x10000...0x10ffff).contains(n)) &&
                        n & 0xffff != 0xfffe && n & 0xffff != 0xffff
                }
        }
        guard schema == "growth.ios-studio-packet.v1", status == "PREPARED_NOT_RENDERED", !execution_authority,
              fps == 24, revision > 0, manifest_version > 0,
              ["PORTRAIT", "LANDSCAPE"].contains(scene.shape), literal(scene.title),
              (1...12).contains(scene.scenes.count), scene.scenes.allSatisfy({ item in
                  guard (1...15).contains(item.seconds), literal(item.text) else { return false }
                  guard let media = item.media else { return true }
                  return UUID(uuidString: media.id) != nil && media.sha256.range(of: "^[a-f0-9]{64}$", options: .regularExpression) != nil &&
                      (0...1439).contains(media.in_frame) && media.in_frame + item.seconds * 24 <= 1440 && ["MUTE", "RETAIN"].contains(media.audio)
              }),
              (1...60).contains(scene.scenes.reduce(0) { $0 + $1.seconds }),
              frame_count == 24 * scene.scenes.reduce(0, { $0 + $1.seconds }),
              source_hash.range(of: "^[a-f0-9]{64}$", options: .regularExpression) != nil,
              packet_hash.range(of: "^[a-f0-9]{64}$", options: .regularExpression) != nil else {
            throw NativeStudioRenderer.Failure.invalidPacket
        }
    }
}

/// Renders literal scene text and approved app-owned video with optional source
/// audio. The host rechecks the packet and independently decodes the output.
@MainActor
final class NativeStudioRenderer {
    enum Failure: Error { case invalidPacket, unavailable, cancelled, timeout }
    private var writer: AVAssetWriter?
    private var exporter: AVAssetExportSession?
    private var rendering = false
    private var cancelled = false

    func cancel() { cancelled = true; writer?.cancelWriting(); exporter?.cancelExport() }

    func render(_ packet: NativeStudioPacket, destination: URL,
                resolve: (NativeStudioScene.Media) async throws -> URL = { _ in throw Failure.unavailable },
                validate: () async throws -> Void, finish: (URL) async throws -> Void) async throws -> URL {
        guard !rendering else { throw Failure.unavailable }
        rendering = true; cancelled = false
        defer { rendering = false; writer = nil; exporter = nil }
        try packet.validateBounds()
        try await validate()
        guard destination.isFileURL, !FileManager.default.fileExists(atPath: destination.path) else { throw Failure.invalidPacket }
        var accepted = false, finishStarted = false
        // The finish transaction may commit even if its response is lost. Keep
        // protected bytes for reconciliation once that operation has begun.
        defer { if !accepted && !finishStarted { try? FileManager.default.removeItem(at: destination) } }
        let size = packet.scene.shape == "PORTRAIT" ? CGSize(width: 720, height: 1280) : CGSize(width: 1280, height: 720)
        let pictureURL = destination.deletingLastPathComponent().appendingPathComponent(UUID().uuidString + ".mp4")
        defer { try? FileManager.default.removeItem(at: pictureURL) }
        let writer = try AVAssetWriter(outputURL: pictureURL, fileType: .mp4)
        self.writer = writer
        defer { if !accepted { writer.cancelWriting() } }
        let input = AVAssetWriterInput(mediaType: .video, outputSettings: [AVVideoCodecKey: AVVideoCodecType.h264,
            AVVideoWidthKey: Int(size.width), AVVideoHeightKey: Int(size.height)])
        let adaptor = AVAssetWriterInputPixelBufferAdaptor(assetWriterInput: input, sourcePixelBufferAttributes: [
            kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA,
            kCVPixelBufferWidthKey as String: Int(size.width), kCVPixelBufferHeightKey as String: Int(size.height),
            kCVPixelBufferCGImageCompatibilityKey as String: true, kCVPixelBufferCGBitmapContextCompatibilityKey as String: true])
        guard writer.canAdd(input) else { throw Failure.unavailable }
        writer.add(input)
        guard writer.startWriting() else { throw Failure.unavailable }
        try FileManager.default.setAttributes([.protectionKey: FileProtectionType.complete], ofItemAtPath: pictureURL.path)
        writer.startSession(atSourceTime: .zero)
        var frame = 0
        var sources: [(NativeStudioScene.Media, URL, Int, Int)] = []
        for item in packet.scene.scenes {
            try Task.checkCancellation()
            guard !cancelled, let pool = adaptor.pixelBufferPool else { throw Failure.cancelled }
            var generator: AVAssetImageGenerator?
            if let media = item.media {
                let url = try await resolve(media)
                guard url.isFileURL else { throw Failure.invalidPacket }
                let asset = AVURLAsset(url: url)
                let duration = try await asset.load(.duration)
                guard CMTimeCompare(duration, CMTime(value: Int64(media.in_frame + item.seconds * 24), timescale: 24)) >= 0 else { throw Failure.unavailable }
                let source = AVAssetImageGenerator(asset: asset)
                source.appliesPreferredTrackTransform = true
                source.requestedTimeToleranceBefore = .zero; source.requestedTimeToleranceAfter = .zero
                generator = source
                sources.append((media, url, frame, item.seconds * 24))
            }
            let staticImage = generator == nil ? try Self.draw(title: packet.scene.title, text: item.text, size: size, background: nil) : nil
            for offset in 0..<(item.seconds * 24) {
                // Allow owner lock and cancel actions between native frames.
                await Task.yield()
                try Task.checkCancellation()
                guard !cancelled else { throw Failure.cancelled }
                let deadline = Date().addingTimeInterval(30)
                while !input.isReadyForMoreMediaData {
                    try Task.checkCancellation()
                    guard !cancelled else { throw Failure.cancelled }
                    guard writer.status == .writing else { throw Failure.unavailable }
                    guard Date() < deadline else { throw Failure.timeout }
                    try await Task.sleep(nanoseconds: 2_000_000)
                }
                let background: CGImage?
                if let generator, let media = item.media {
                    background = try generator.copyCGImage(at: CMTime(value: Int64(media.in_frame + offset), timescale: 24), actualTime: nil)
                } else { background = nil }
                let image = try staticImage ?? Self.draw(title: packet.scene.title, text: item.text, size: size, background: background)
                var buffer: CVPixelBuffer?
                guard CVPixelBufferPoolCreatePixelBuffer(nil, pool, &buffer) == kCVReturnSuccess, let pixels = buffer else { throw Failure.unavailable }
                CVPixelBufferLockBaseAddress(pixels, [])
                let context = CGContext(data: CVPixelBufferGetBaseAddress(pixels), width: Int(size.width), height: Int(size.height),
                    bitsPerComponent: 8, bytesPerRow: CVPixelBufferGetBytesPerRow(pixels), space: CGColorSpaceCreateDeviceRGB(),
                    bitmapInfo: CGImageAlphaInfo.premultipliedFirst.rawValue | CGBitmapInfo.byteOrder32Little.rawValue)
                context?.draw(image, in: CGRect(origin: .zero, size: size))
                CVPixelBufferUnlockBaseAddress(pixels, [])
                guard context != nil, !cancelled, adaptor.append(pixels, withPresentationTime: CMTime(value: Int64(frame), timescale: 24)) else { throw Failure.unavailable }
                frame += 1
            }
        }
        input.markAsFinished()
        await withTaskCancellationHandler(operation: {
            await withCheckedContinuation { continuation in writer.finishWriting { continuation.resume() } }
        }, onCancel: { writer.cancelWriting() })
        try Task.checkCancellation()
        guard !cancelled, writer.status == .completed, frame == packet.frame_count else { throw Failure.unavailable }
        if sources.contains(where: { $0.0.audio == "RETAIN" }) {
            let composition = AVMutableComposition()
            let picture = AVURLAsset(url: pictureURL)
            guard let pictureTrack = try await picture.loadTracks(withMediaType: .video).first,
                  let video = composition.addMutableTrack(withMediaType: .video, preferredTrackID: kCMPersistentTrackID_Invalid),
                  let audio = composition.addMutableTrack(withMediaType: .audio, preferredTrackID: kCMPersistentTrackID_Invalid) else { throw Failure.unavailable }
            let duration = CMTime(value: Int64(frame), timescale: 24)
            try video.insertTimeRange(CMTimeRange(start: .zero, duration: duration), of: pictureTrack, at: .zero)
            for (media, url, start, count) in sources where media.audio == "RETAIN" {
                let asset = AVURLAsset(url: url)
                guard let track = try await asset.loadTracks(withMediaType: .audio).first else { throw Failure.unavailable }
                try audio.insertTimeRange(CMTimeRange(start: CMTime(value: Int64(media.in_frame), timescale: 24), duration: CMTime(value: Int64(count), timescale: 24)), of: track, at: CMTime(value: Int64(start), timescale: 24))
            }
            guard let exporter = AVAssetExportSession(asset: composition, presetName: AVAssetExportPresetHighestQuality) else { throw Failure.unavailable }
            self.exporter = exporter
            exporter.outputURL = destination; exporter.outputFileType = .mp4
            exporter.timeRange = CMTimeRange(start: .zero, duration: duration)
            let watchdog = Task {
                do { try await Task.sleep(nanoseconds: 180_000_000_000) } catch { return }
                exporter.cancelExport()
            }
            defer { watchdog.cancel() }
            await withTaskCancellationHandler(operation: {
                await withCheckedContinuation { continuation in exporter.exportAsynchronously { continuation.resume() } }
            }, onCancel: { exporter.cancelExport() })
            try Task.checkCancellation()
            guard !cancelled, exporter.status == .completed else { throw Failure.unavailable }
        } else {
            try FileManager.default.moveItem(at: pictureURL, to: destination)
        }
        try FileManager.default.setAttributes([.protectionKey: FileProtectionType.complete], ofItemAtPath: destination.path)
        for (media, _, _, _) in sources { _ = try await resolve(media) }
        try await validate()
        finishStarted = true
        try await finish(destination)
        // Once the trusted finish commits, retain its exact artifact even if a
        // concurrent cancel arrives while that commit is returning.
        accepted = true
        return destination
    }

    private static func draw(title: String, text: String, size: CGSize, background: CGImage?) throws -> CGImage {
        let paragraph = NSMutableParagraphStyle(); paragraph.alignment = .center; paragraph.lineBreakMode = .byWordWrapping
        let titleRect = CGRect(x: size.width * 0.08, y: size.height * 0.06, width: size.width * 0.84, height: size.height * 0.16)
        let textRect = CGRect(x: size.width * 0.08, y: size.height * 0.27, width: size.width * 0.84, height: size.height * 0.61)
        func attributes(_ value: String, rect: CGRect, color: UIColor, maximum: CGFloat) -> [NSAttributedString.Key: Any]? {
            var fontSize = maximum
            while fontSize >= 14 {
                let result: [NSAttributedString.Key: Any] = [.font: UIFont.systemFont(ofSize: fontSize), .foregroundColor: color, .paragraphStyle: paragraph]
                let measured = (value as NSString).boundingRect(with: CGSize(width: rect.width, height: .greatestFiniteMagnitude), options: [.usesLineFragmentOrigin, .usesFontLeading], attributes: result, context: nil)
                if measured.height <= rect.height && measured.width <= rect.width { return result }
                fontSize -= 1
            }
            return nil
        }
        guard let titleStyle = attributes(title, rect: titleRect, color: UIColor(red: 167/255, green: 232/255, blue: 193/255, alpha: 1), maximum: 38),
              let bodyStyle = attributes(text, rect: textRect, color: .white, maximum: 42) else { throw Failure.unavailable }
        let format = UIGraphicsImageRendererFormat(); format.scale = 1; format.opaque = true
        let image = UIGraphicsImageRenderer(size: size, format: format).image { context in
            UIColor(red: 16/255, green: 33/255, blue: 36/255, alpha: 1).setFill()
            context.fill(CGRect(origin: .zero, size: size))
            if let background {
                let image = UIImage(cgImage: background)
                let scale = max(size.width / image.size.width, size.height / image.size.height)
                let fitted = CGSize(width: image.size.width * scale, height: image.size.height * scale)
                image.draw(in: CGRect(x: (size.width - fitted.width) / 2, y: (size.height - fitted.height) / 2, width: fitted.width, height: fitted.height))
                UIColor.black.withAlphaComponent(0.45).setFill()
                context.fill(CGRect(origin: .zero, size: size))
            }
            (title as NSString).draw(in: titleRect, withAttributes: titleStyle)
            (text as NSString).draw(in: textRect, withAttributes: bodyStyle)
        }
        guard let cgImage = image.cgImage else { throw Failure.unavailable }
        return cgImage
    }
}
