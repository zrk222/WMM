import Foundation
import CryptoKit

/// Protected storage adapter only. Configuration is not provider authentication proof.
/// OAuth and desktop subscription sessions are never inferred from a saved API key.
struct ProviderAuthentication: Sendable {
    private let vault: KeychainVault
    private let prefix: String
    private let insightsPrefix: String
    private let storePrefix: String

    init(database: URL) throws {
        guard let databaseID = UUID(uuidString: database.deletingLastPathComponent().lastPathComponent) else {
            throw KeychainVault.Failure.invalidScope
        }
        vault = KeychainVault(databaseID: databaseID, appID: UUID(uuidString: "412D70C7-30C7-443A-88A3-BCDD07F95063")!)
        let digest = SHA256.hash(data: Data(database.standardizedFileURL.resolvingSymlinksInPath().path.utf8))
            .map { String(format: "%02x", $0) }.joined()
        prefix = "AgentGrowth/" + String(digest.prefix(24)) + "/"
        insightsPrefix = "AppGrowthInsights/" + String(digest.prefix(24)) + "/"
        storePrefix = "AppGrowth/" + String(digest.prefix(24)) + "/"
    }

    /// Called synchronously by the bundled engine under current owner admission.
    /// No callback data is logged, exported or given to a model.
    func invoke(_ request: Data) -> Data? {
        do {
            guard !request.isEmpty, request.count <= 8192 else { throw KeychainVault.Failure.invalidResult }
            if let body = try JSONSerialization.jsonObject(with: request) as? [String: Any], body["operation"] != nil {
                return NativeAppleSigning.invoke(request)
            }
            guard request.count <= 8192,
                  let body = try JSONSerialization.jsonObject(with: request) as? [String: Any],
                  Set(body.keys) == ["action", "target", "value"],
                  let action = body["action"] as? String, ["put", "get", "delete"].contains(action),
                  let target = body["target"] as? String,
                  target.hasPrefix(prefix) || target.hasPrefix(insightsPrefix) || target.hasPrefix(storePrefix) else {
                throw KeychainVault.Failure.invalidScope
            }
            let insights = target.hasPrefix(insightsPrefix)
            let store = target.hasPrefix(storePrefix)
            let selectedPrefix = store ? storePrefix : insights ? insightsPrefix : prefix
            let scope = String(target.dropFirst(selectedPrefix.count)).split(separator: "/", omittingEmptySubsequences: false)
            guard scope.count == (store ? 3 : 2), (!store || scope[1] == "app_store"),
                  String(scope[0]).range(of: "^[a-z0-9][a-z0-9-]{0,79}$", options: .regularExpression) != nil,
                  let referenceID = UUID(uuidString: String(scope.last!)), referenceID.uuidString.lowercased() == scope.last! else {
                throw KeychainVault.Failure.invalidScope
            }
            let reference = "provider-" + SHA256.hash(data: Data(target.utf8)).map { String(format: "%02x", $0) }.joined()
            var result: Any = NSNull()
            if action == "put" {
                guard let value = body["value"] as? [String: Any],
                      Self.valid(value, appID: String(scope[0]), insights: insights, store: store) else {
                    throw KeychainVault.Failure.invalidResult
                }
                try vault.save(JSONSerialization.data(withJSONObject: value), reference: reference)
            } else {
                guard body["value"] is NSNull else { throw KeychainVault.Failure.invalidResult }
                if action == "delete" { try vault.delete(reference: reference) }
                else if let data = try vault.read(reference: reference) {
                    let value = try JSONSerialization.jsonObject(with: data)
                    guard let dictionary = value as? [String: Any],
                          Self.valid(dictionary, appID: String(scope[0]), insights: insights, store: store) else {
                        throw KeychainVault.Failure.invalidResult
                    }
                    result = value
                }
            }
            return try JSONSerialization.data(withJSONObject: ["ok": true, "value": result])
        } catch { return try? JSONSerialization.data(withJSONObject: ["ok": false, "value": NSNull()]) }
    }

    private static func valid(_ value: [String: Any], appID: String, insights: Bool, store: Bool) -> Bool {
        if store {
            guard Set(value.keys) == ["provider", "key_id", "issuer_id", "client_id", "private_key"],
                  value["provider"] as? String == "app_store", value["client_id"] as? String == "",
                  let keyID = value["key_id"] as? String, keyID.range(of: "^[A-Z0-9]{10}$", options: .regularExpression) != nil,
                  let issuer = value["issuer_id"] as? String, UUID(uuidString: issuer) != nil,
                  let pem = value["private_key"] as? String, pem.utf8.count <= 2000,
                  pem.contains("-----BEGIN PRIVATE KEY-----"),
                  (try? P256.Signing.PrivateKey(pemRepresentation: pem)) != nil else { return false }
            return true
        }
        guard let key = value["api_key"] as? String,
              key.range(of: "^[!-~]{16,1800}$", options: .regularExpression) != nil else { return false }
        if !insights { return Set(value.keys) == ["api_key"] }
        guard Set(value.keys) == ["api_key", "binding"],
              key.range(of: "^ph[xs]_[A-Za-z0-9_-]{16,}$", options: .regularExpression) != nil,
              let binding = value["binding"] as? [String: String], Set(binding.keys) == ["app_id", "id", "hash"],
              binding["app_id"] == appID, let id = binding["id"], UUID(uuidString: id) != nil,
              let hash = binding["hash"], hash.range(of: "^[a-f0-9]{64}$", options: .regularExpression) != nil else { return false }
        return true
    }
}

/// Trusted local App Store Connect ES256 adapter. It accepts no generic signing
/// destination or executable content and never returns private key material.
enum NativeAppleSigning {
    static func invoke(_ request: Data) -> Data? {
        do {
            guard request.count <= 8192,
                  let body = try JSONSerialization.jsonObject(with: request) as? [String: String],
                  Set(body.keys) == ["operation", "private_key", "message"],
                  let operation = body["operation"], ["inspect", "sign"].contains(operation),
                  let pem = body["private_key"], pem.utf8.count <= 2000,
                  pem.contains("-----BEGIN PRIVATE KEY-----"), let message = body["message"] else {
                throw KeychainVault.Failure.invalidResult
            }
            let key = try P256.Signing.PrivateKey(pemRepresentation: pem)
            let value: [String: String]
            if operation == "inspect" {
                guard message.isEmpty else { throw KeychainVault.Failure.invalidResult }
                value = ["public_key": key.publicKey.pemRepresentation]
            } else {
                guard validMessage(message) else { throw KeychainVault.Failure.invalidResult }
                let signature = try key.signature(for: Data(message.utf8)).rawRepresentation
                guard signature.count == 64 else { throw KeychainVault.Failure.invalidResult }
                value = ["signature": signature.base64EncodedString()]
            }
            return try JSONSerialization.data(withJSONObject: ["ok": true, "value": value])
        } catch { return try? JSONSerialization.data(withJSONObject: ["ok": false, "value": NSNull()]) }
    }

    private static func validMessage(_ message: String) -> Bool {
        guard message.utf8.count <= 4096,
              message.range(of: "^[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+$", options: .regularExpression) != nil else { return false }
        func part(_ input: Substring) -> [String: Any]? {
            var value = String(input).replacingOccurrences(of: "-", with: "+").replacingOccurrences(of: "_", with: "/")
            value += String(repeating: "=", count: (4 - value.count % 4) % 4)
            guard let data = Data(base64Encoded: value) else { return nil }
            return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
        }
        let pieces = message.split(separator: ".")
        guard pieces.count == 2, let header = part(pieces[0]), let claims = part(pieces[1]),
              Set(header.keys) == ["alg", "kid", "typ"], header["alg"] as? String == "ES256", header["typ"] as? String == "JWT",
              let keyID = header["kid"] as? String, keyID.range(of: "^[A-Z0-9]{10}$", options: .regularExpression) != nil,
              Set(claims.keys) == ["iss", "iat", "exp", "aud"], claims["aud"] as? String == "appstoreconnect-v1",
              let issuer = claims["iss"] as? String, UUID(uuidString: issuer) != nil,
              let issued = claims["iat"] as? Int, let expiry = claims["exp"] as? Int,
              issued > 0, issued <= 4_102_444_800, expiry > 0, expiry <= 4_102_444_800,
              expiry > issued, expiry - issued <= 600,
              abs(Double(issued) - Date().timeIntervalSince1970) <= 60 else { return false }
        return true
    }
}
