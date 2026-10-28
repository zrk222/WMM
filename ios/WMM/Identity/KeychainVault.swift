import Foundation
import Security

/// Device-local credentials are never stored in domain snapshots or UserDefaults.
actor KeychainVault {
    enum Failure: Error, Equatable {
        case invalidScope
        case status(OSStatus)
        case invalidResult
    }

    private let service: String

    init(databaseID: UUID, appID: UUID) {
        service = "com.wizemarketingmachine.secrets.\(databaseID.uuidString).\(appID.uuidString)"
    }

    nonisolated private func query(_ reference: String) throws -> [String: Any] {
        guard !reference.isEmpty, reference.utf8.count <= 200,
              reference.unicodeScalars.allSatisfy({ CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "-_.")).contains($0) }) else {
            throw Failure.invalidScope
        }
        return [kSecClass as String: kSecClassGenericPassword,
                kSecAttrService as String: service,
                kSecAttrAccount as String: reference,
                kSecAttrSynchronizable as String: false]
    }

    func save(_ value: Data, reference: String) throws {
        guard !value.isEmpty, value.count <= 65536 else { throw Failure.invalidResult }
        let match = try query(reference)
        let attributes: [String: Any] = [
            kSecValueData as String: value,
            kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        ]
        let updated = SecItemUpdate(match as CFDictionary, attributes as CFDictionary)
        if updated == errSecItemNotFound {
            let added = SecItemAdd(match.merging(attributes) { _, new in new } as CFDictionary, nil)
            guard added == errSecSuccess else { throw Failure.status(added) }
        } else if updated != errSecSuccess {
            throw Failure.status(updated)
        }
    }

    nonisolated func read(reference: String) throws -> Data? {
        var match = try query(reference)
        match[kSecReturnData as String] = true
        match[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        let status = SecItemCopyMatching(match as CFDictionary, &result)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess else { throw Failure.status(status) }
        guard let data = result as? Data else { throw Failure.invalidResult }
        return data
    }

    func delete(reference: String) throws {
        let status = SecItemDelete(try query(reference) as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else { throw Failure.status(status) }
        guard try read(reference: reference) == nil else { throw Failure.invalidResult }
    }
}
