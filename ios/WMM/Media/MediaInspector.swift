import AVFoundation

enum MediaInspector {
    enum Failure: Error { case invalidOutput, decodeFailed }

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
