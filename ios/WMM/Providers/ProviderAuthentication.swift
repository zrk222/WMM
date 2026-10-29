import Foundation
import CryptoKit

/// Protected storage adapter only. Configuration is not provider authentication proof.
/// OAuth and desktop subscription sessions are never inferred from a saved API key.
struct ProviderAuthentication: Sendable {
    private let vault: KeychainVault
    private let prefix: String
    private let insightsPrefix: String

    init(database: URL) throws {
        guard let databaseID = UUID(uuidString: database.deletingLastPathComponent().lastPathComponent) else {
            throw KeychainVault.Failure.invalidScope
        }
        vault = KeychainVault(databaseID: databaseID, appID: UUID(uuidString: "412D70C7-30C7-443A-88A3-BCDD07F95063")!)
        let digest = SHA256.hash(data: Data(database.standardizedFileURL.resolvingSymlinksInPath().path.utf8))
            .map { String(format: "%02x", $0) }.joined()
        prefix = "AgentGrowth/" + String(digest.prefix(24)) + "/"
        insightsPrefix = "AppGrowthInsights/" + String(digest.prefix(24)) + "/"
    }

    /// Called synchronously by the bundled engine under current owner admission.
    /// No callback data is logged, exported or given to a model.
    func invoke(_ request: Data) -> Data? {
        do {
            guard request.count <= 8192,
                  let body = try JSONSerialization.jsonObject(with: request) as? [String: Any],
                  Set(body.keys) == ["action", "target", "value"],
                  let action = body["action"] as? String, ["put", "get", "delete"].contains(action),
                  let target = body["target"] as? String,
                  target.hasPrefix(prefix) || target.hasPrefix(insightsPrefix) else {
                throw KeychainVault.Failure.invalidScope
            }
            let insights = target.hasPrefix(insightsPrefix)
            let selectedPrefix = insights ? insightsPrefix : prefix
            let scope = String(target.dropFirst(selectedPrefix.count)).split(separator: "/", omittingEmptySubsequences: false)
            guard scope.count == 2,
                  String(scope[0]).range(of: "^[a-z0-9][a-z0-9-]{0,79}$", options: .regularExpression) != nil,
                  let referenceID = UUID(uuidString: String(scope[1])), referenceID.uuidString.lowercased() == scope[1] else {
                throw KeychainVault.Failure.invalidScope
            }
            let reference = "provider-" + SHA256.hash(data: Data(target.utf8)).map { String(format: "%02x", $0) }.joined()
            var result: Any = NSNull()
            if action == "put" {
                guard let value = body["value"] as? [String: Any],
                      Self.valid(value, appID: String(scope[0]), insights: insights) else {
                    throw KeychainVault.Failure.invalidResult
                }
                try vault.save(JSONSerialization.data(withJSONObject: value), reference: reference)
            } else {
                guard body["value"] is NSNull else { throw KeychainVault.Failure.invalidResult }
                if action == "delete" { try vault.delete(reference: reference) }
                else if let data = try vault.read(reference: reference) {
                    let value = try JSONSerialization.jsonObject(with: data)
                    guard let dictionary = value as? [String: Any],
                          Self.valid(dictionary, appID: String(scope[0]), insights: insights) else {
                        throw KeychainVault.Failure.invalidResult
                    }
                    result = value
                }
            }
            return try JSONSerialization.data(withJSONObject: ["ok": true, "value": result])
        } catch { return try? JSONSerialization.data(withJSONObject: ["ok": false, "value": NSNull()]) }
    }

    private static func valid(_ value: [String: Any], appID: String, insights: Bool) -> Bool {
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
