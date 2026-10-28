import AVFoundation
import CryptoKit

enum MediaInspector {
    enum Failure: Error { case invalidOutput, decodeFailed }

    /// Inspect actual selected bytes. Only trusted native code supplies this proof
    /// to the embedded media adapter; no agent JSON can claim decoding happened.
    static func inspectOriginal(_ url: URL) async throws -> Data {
        let original = try MediaIntake.readBounded(url)
        let sha = SHA256.hash(data: original).map { String(format: "%02x", $0) }.joined()
        let asset = AVURLAsset(url: url)
        let videos = try await asset.loadTracks(withMediaType: .video)
        let audios = try await asset.loadTracks(withMediaType: .audio)
        guard videos.count == 1, audios.count <= 1, let video = videos.first else { throw Failure.invalidOutput }
        let size = try await video.load(.naturalSize)
        let duration = CMTimeGetSeconds(try await asset.load(.duration))
        let rate = Double(try await video.load(.nominalFrameRate))
        guard size.width.isFinite, size.height.isFinite, size.width.rounded() == size.width,
              size.height.rounded() == size.height, size.width >= 2, size.width <= 4096,
              size.height >= 2, size.height <= 4096, size.width * size.height <= 8_388_608,
              duration.isFinite, duration > 0, duration <= 60,
              rate.isFinite, (1...120).contains(rate) else { throw Failure.invalidOutput }
        let formats = try await video.load(.formatDescriptions)
        guard let format = formats.first else { throw Failure.invalidOutput }
        let codec = CMFormatDescriptionGetMediaSubType(format)
        let codecText = String(bytes: [UInt8((codec >> 24) & 255), UInt8((codec >> 16) & 255),
                                      UInt8((codec >> 8) & 255), UInt8(codec & 255)], encoding: .ascii)
        guard let codecText, codecText.range(of: "^[a-zA-Z0-9_+-]{1,64}$", options: .regularExpression) != nil else {
            throw Failure.invalidOutput
        }
        let reader = try AVAssetReader(asset: asset)
        let output = AVAssetReaderTrackOutput(track: video,
            outputSettings: [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA])
        output.alwaysCopiesSampleData = false
        guard reader.canAdd(output) else { throw Failure.decodeFailed }
        reader.add(output)
        guard reader.startReading() else { throw Failure.decodeFailed }
        defer { if reader.status == .reading { reader.cancelReading() } }
        var frames = 0
        let deadline = Date().addingTimeInterval(180)
        while let sample = output.copyNextSampleBuffer() {
            try Task.checkCancellation()
            guard Date() < deadline, CMSampleBufferGetImageBuffer(sample) != nil else { reader.cancelReading(); throw Failure.decodeFailed }
            frames += 1
            guard frames <= 7201 else { reader.cancelReading(); throw Failure.invalidOutput }
        }
        guard reader.status == .completed, frames > 0 else { throw Failure.decodeFailed }
        var metadata: [String: Any] = ["codec": codecText.lowercased(), "width": Int(size.width),
            "height": Int(size.height), "duration_seconds": duration, "frame_rate": rate, "audio": !audios.isEmpty]
        var audioFrames = 0
        if let audio = audios.first {
            let audioFormats = try await audio.load(.formatDescriptions)
            guard let audioFormat = audioFormats.first,
                  let description = CMAudioFormatDescriptionGetStreamBasicDescription(audioFormat) else { throw Failure.invalidOutput }
            let sampleRate = description.pointee.mSampleRate
            let channels = Int(description.pointee.mChannelsPerFrame)
            guard sampleRate.isFinite, sampleRate.rounded() == sampleRate,
                  sampleRate >= 8000, sampleRate <= 192000, (1...2).contains(channels) else { throw Failure.invalidOutput }
            let audioReader = try AVAssetReader(asset: asset)
            let samples = AVAssetReaderTrackOutput(track: audio, outputSettings: [AVFormatIDKey: kAudioFormatLinearPCM])
            samples.alwaysCopiesSampleData = false
            guard audioReader.canAdd(samples) else { throw Failure.decodeFailed }
            audioReader.add(samples)
            guard audioReader.startReading() else { throw Failure.decodeFailed }
            defer { if audioReader.status == .reading { audioReader.cancelReading() } }
            while let sample = samples.copyNextSampleBuffer() {
                try Task.checkCancellation()
                guard Date() < deadline else { audioReader.cancelReading(); throw Failure.decodeFailed }
                let count = CMSampleBufferGetNumSamples(sample)
                guard count > 0, count <= 11_712_000 - audioFrames else { audioReader.cancelReading(); throw Failure.invalidOutput }
                audioFrames += count
            }
            guard audioReader.status == .completed, audioFrames > 0 else { throw Failure.decodeFailed }
            metadata["audio_metadata"] = ["codec": "decoded_pcm", "channels": channels, "sample_rate": Int(sampleRate)]
        }
        let current = try MediaIntake.readBounded(url)
        guard current.count == original.count, SHA256.hash(data: current) == SHA256.hash(data: original) else {
            throw Failure.invalidOutput
        }
        return try JSONSerialization.data(withJSONObject: ["sha256": sha, "bytes": original.count,
            "metadata": metadata, "decoded": ["video_frames": frames, "audio_frames": audioFrames]], options: [.sortedKeys])
    }

    /// Decode every video frame. An export-session success flag alone is insufficient.
    static func verify(_ url: URL, plan: NativeRenderPlan, expectsAudio: Bool) async throws {
        let asset = AVURLAsset(url: url)
        guard let video = try await asset.loadTracks(withMediaType: .video).first else { throw Failure.invalidOutput }
        let size = try await video.load(.naturalSize)
        let duration = try await asset.load(.duration)
        guard Int(size.width) == plan.width, Int(size.height) == plan.height,
              abs(CMTimeGetSeconds(duration) - Double(plan.output_frame_count)/24) <= 1.0/24 else {
            throw Failure.invalidOutput
        }
        let reader = try AVAssetReader(asset: asset)
        let output = AVAssetReaderTrackOutput(track: video,
            outputSettings: [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA])
        guard reader.canAdd(output) else { throw Failure.decodeFailed }
        reader.add(output)
        guard reader.startReading() else { throw Failure.decodeFailed }
        var frames = 0
        while let sample = output.copyNextSampleBuffer() {
            try Task.checkCancellation()
            guard CMSampleBufferGetImageBuffer(sample) != nil else { throw Failure.decodeFailed }
            frames += 1
        }
        guard reader.status == .completed, frames == plan.output_frame_count else { throw Failure.decodeFailed }
        let audio = try await asset.loadTracks(withMediaType: .audio)
        guard expectsAudio == !audio.isEmpty else { throw Failure.invalidOutput }
        for track in audio {
            let audioReader = try AVAssetReader(asset: asset)
            let samples = AVAssetReaderTrackOutput(track: track,
                outputSettings: [AVFormatIDKey: kAudioFormatLinearPCM])
            guard audioReader.canAdd(samples) else { throw Failure.decodeFailed }
            audioReader.add(samples)
            guard audioReader.startReading() else { throw Failure.decodeFailed }
            var sampleCount = 0
            while let buffer = samples.copyNextSampleBuffer() {
                try Task.checkCancellation()
                sampleCount += CMSampleBufferGetNumSamples(buffer)
            }
            guard audioReader.status == .completed, sampleCount > 0 else { throw Failure.decodeFailed }
        }
    }
}
