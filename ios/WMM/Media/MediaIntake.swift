import Foundation
import CryptoKit
import CoreTransferable
import UniformTypeIdentifiers

enum MediaIntake {
    enum Failure: Error { case invalidFile, oversized, empty }
    struct Receipt: Sendable {
        let id: UUID
        let byteCount: Int
        let sha256: String
        let localURL: URL
        // Intake is not reuse approval: the shared domain must bind current rights.
        let reuseApproved = false
    }

    static func readBounded(_ url: URL) throws -> Data {
        guard url.isFileURL else { throw Failure.invalidFile }
        let values = try url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey])
        guard values.isRegularFile == true, values.isSymbolicLink != true else { throw Failure.invalidFile }
        let file = try FileHandle(forReadingFrom: url)
        defer { try? file.close() }
        var data = Data()
        while let chunk = try file.read(upToCount: 262144), !chunk.isEmpty {
            guard data.count + chunk.count <= LocalStore.maximumMediaBytes else { throw Failure.oversized }
            data.append(chunk)
        }
        guard !data.isEmpty else { throw Failure.empty }
        return data
    }

    /// Called only for URLs returned by Files' system picker.
    static func importFile(_ url: URL, store: LocalStore) throws -> Receipt {
        let scoped = url.startAccessingSecurityScopedResource()
        defer { if scoped { url.stopAccessingSecurityScopedResource() } }
        let data = try readBounded(url)
        return try retain(data, store: store)
    }

    static func retain(_ data: Data, store: LocalStore) throws -> Receipt {
        guard !data.isEmpty else { throw Failure.empty }
        guard data.count <= LocalStore.maximumMediaBytes else { throw Failure.oversized }
        let identity = UUID()
        let destination = try store.retainMedia(data, id: identity)
        return Receipt(id: identity, byteCount: data.count,
                       sha256: SHA256.hash(data: data).map { String(format: "%02x", $0) }.joined(),
                       localURL: destination)
    }
}

/// PhotosPicker(preferredItemEncoding: .current) supplies the selected representation.
/// Copy during transfer lifetime; never retain Photos' ephemeral URL as app storage.
struct SelectedMovie: Transferable {
    let data: Data
    static var transferRepresentation: some TransferRepresentation {
        FileRepresentation(importedContentType: .movie) { received in
            SelectedMovie(data: try MediaIntake.readBounded(received.file))
        }
    }
}
