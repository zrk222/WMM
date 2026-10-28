import Foundation

/// Paths for the shared SQLite engine and original media, not a second domain DB.
struct LocalStore {
    enum Failure: Error { case invalidContainer, symbolicLink, oversizedMedia }
    static let maximumMediaBytes = 67_108_864
    let root: URL
    let database: URL
    let media: URL

    init(applicationSupport: URL, databaseID: UUID) throws {
        guard applicationSupport.isFileURL else { throw Failure.invalidContainer }
        root = applicationSupport.appendingPathComponent("WMM", isDirectory: true)
            .appendingPathComponent(databaseID.uuidString, isDirectory: true)
        database = root.appendingPathComponent("workspace.sqlite3")
        media = root.appendingPathComponent("media", isDirectory: true)
        try Self.createProtectedDirectory(root)
        try Self.createProtectedDirectory(media)
    }

    private static func createProtectedDirectory(_ url: URL) throws {
        let manager = FileManager.default
        if manager.fileExists(atPath: url.path) {
            let values = try url.resourceValues(forKeys: [.isSymbolicLinkKey, .isDirectoryKey])
            guard values.isSymbolicLink != true, values.isDirectory == true else { throw Failure.symbolicLink }
        }
        try manager.createDirectory(at: url, withIntermediateDirectories: true,
                                    attributes: [.protectionKey: FileProtectionType.complete])
        try manager.setAttributes([.protectionKey: FileProtectionType.complete], ofItemAtPath: url.path)
        var protected = url
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        try protected.setResourceValues(values)
    }

    /// UUID destinations prevent untrusted filenames escaping the managed container.
    func retainMedia(_ data: Data, id: UUID) throws -> URL {
        guard !data.isEmpty, data.count <= Self.maximumMediaBytes else { throw Failure.oversizedMedia }
        let destination = media.appendingPathComponent(id.uuidString)
        // Existing originals are immutable; edits create new project revisions.
        let staging = media.appendingPathComponent(".intake-" + UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: staging) }
        try data.write(to: staging, options: [.withoutOverwriting, .completeFileProtection])
        try FileManager.default.moveItem(at: staging, to: destination)
        return destination
    }
}
