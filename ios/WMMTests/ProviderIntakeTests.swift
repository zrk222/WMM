import XCTest
import CryptoKit
import PDFKit
@testable import WMM

final class ProviderIntakeTests: XCTestCase {
    func testNativeAppleSignerVerifiesES256AndRejectsOtherAudiences() throws {
        let key = P256.Signing.PrivateKey()
        let pem = key.pemRepresentation
        func invoke(_ operation: String, _ message: String) throws -> [String: Any] {
            let body = try JSONSerialization.data(withJSONObject: ["operation": operation, "private_key": pem, "message": message])
            return try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(NativeAppleSigning.invoke(body))) as? [String: Any])
        }
        let inspection = try invoke("inspect", "")
        XCTAssertEqual(inspection["ok"] as? Bool, true)
        let publicPEM = try XCTUnwrap((inspection["value"] as? [String: String])?["public_key"])
        let publicKey = try P256.Signing.PublicKey(pemRepresentation: publicPEM)
        func encoded(_ object: [String: Any]) throws -> String {
            try JSONSerialization.data(withJSONObject: object, options: [.sortedKeys]).base64EncodedString()
                .replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "")
        }
        let issued = Int(Date().timeIntervalSince1970)
        let header = try encoded(["alg": "ES256", "kid": "ABC123DE45", "typ": "JWT"])
        let claims: [String: Any] = ["iss": UUID().uuidString.lowercased(), "iat": issued, "exp": issued + 600, "aud": "appstoreconnect-v1"]
        let message = try header + "." + encoded(claims)
        let signed = try invoke("sign", message)
        XCTAssertEqual(signed["ok"] as? Bool, true)
        let raw = try XCTUnwrap(Data(base64Encoded: XCTUnwrap((signed["value"] as? [String: String])?["signature"])))
        XCTAssertEqual(raw.count, 64)
        XCTAssertTrue(publicKey.isValidSignature(try P256.Signing.ECDSASignature(rawRepresentation: raw), for: Data(message.utf8)))
        var wrong = claims; wrong["aud"] = "https://other.invalid"
        XCTAssertEqual(try invoke("sign", header + "." + encoded(wrong))["ok"] as? Bool, false)
        wrong = claims; wrong["exp"] = issued + 601
        XCTAssertEqual(try invoke("sign", header + "." + encoded(wrong))["ok"] as? Bool, false)
        XCTAssertEqual(try invoke("sign", "unstructured message")["ok"] as? Bool, false)
        XCTAssertEqual(try invoke("inspect", "unexpected")["ok"] as? Bool, false)
        XCTAssertFalse(String(describing: signed).contains(pem))
    }

    @MainActor
    func testNativeStoreConnectionHostRejectsAgentAuthorityAndLockedRead() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: folder) }
        let databaseID = UUID()
        let identity = LocalIdentity(vault: KeychainVault(databaseID: databaseID, appID: UUID()))
        let session = try await identity.begin()
        let bridge = try DomainBridge(store: LocalStore(applicationSupport: folder, databaseID: databaseID), identity: identity)
        let appID = "apple-" + UUID().uuidString.lowercased()
        let setup = try JSONSerialization.data(withJSONObject: ["app_id": appID, "confirm_owner": true,
            "manifest": ["name": "Synthetic Apple app", "release": "build-1", "locale": "en-US", "currency": "USD", "store_app_id": "123"]] as [String: Any])
        _ = try await bridge.createWorkspace(session: session, request: setup)
        let model = NativeStoreConnectionModel(storeAppID: "123", execute: { action, request in
            try await bridge.storeConnection(session: session, appID: appID, action: action, request: request)
        })
        await model.refresh()
        XCTAssertNil(model.message); XCTAssertTrue(model.connections.isEmpty); XCTAssertTrue(model.jobs.isEmpty)
        do {
            _ = try await bridge.storeConnection(session: session, appID: appID, action: "publish", request: Data("{}".utf8))
            XCTFail("Unknown store write admitted")
        } catch {}
        await identity.lock()
        do {
            _ = try await bridge.storeConnection(session: session, appID: appID, action: "history", request: Data("{}".utf8))
            XCTFail("Locked store history admitted")
        } catch {}
        await bridge.close(); try await identity.forgetPrincipal()
    }

    func testPostHogKeychainBindingRejectsForeignScopeAndKeepsInferenceSeparate() throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: folder) }
        let store = try LocalStore(applicationSupport: folder, databaseID: UUID())
        let storage = try ProviderAuthentication(database: store.database)
        let digest = SHA256.hash(data: Data(store.database.standardizedFileURL.resolvingSymlinksInPath().path.utf8))
            .map { String(format: "%02x", $0) }.joined()
        let target = "AppGrowthInsights/" + String(digest.prefix(24)) + "/synthetic-app/" + UUID().uuidString.lowercased()
        let secret: [String: Any] = ["api_key": "phx_synthetic_private_1234567890",
            "binding": ["app_id": "synthetic-app", "id": UUID().uuidString.lowercased(), "hash": String(repeating: "a", count: 64)]]
        func invoke(_ action: String, _ destination: String, _ value: Any) throws -> [String: Any] {
            let request = try JSONSerialization.data(withJSONObject: ["action": action, "target": destination, "value": value])
            let response = try XCTUnwrap(storage.invoke(request))
            return try XCTUnwrap(JSONSerialization.jsonObject(with: response) as? [String: Any])
        }
        defer { _ = try? invoke("delete", target, NSNull()) }
        XCTAssertEqual(try invoke("put", target, secret)["ok"] as? Bool, true)
        let read = try invoke("get", target, NSNull())
        XCTAssertEqual((read["value"] as? [String: Any])?["api_key"] as? String, secret["api_key"] as? String)
        var foreign = secret
        foreign["binding"] = ["app_id": "other-app", "id": UUID().uuidString.lowercased(), "hash": String(repeating: "a", count: 64)]
        XCTAssertEqual(try invoke("put", target, foreign)["ok"] as? Bool, false)
        for token in ["sk_" + String(repeating: "S", count: 24), "header.payload." + String(repeating: "S", count: 24)] {
            var analytics = secret; analytics["api_key"] = token
            XCTAssertEqual(try invoke("put", target, analytics)["ok"] as? Bool, true)
            XCTAssertEqual((try invoke("get", target, NSNull())["value"] as? [String: Any])?["api_key"] as? String, token)
            XCTAssertEqual(try invoke("put", target, foreign)["ok"] as? Bool, false)
        }
        var publicKey = secret; publicKey["api_key"] = "phc_" + String(repeating: "S", count: 24)
        XCTAssertEqual(try invoke("put", target, publicKey)["ok"] as? Bool, false)
        XCTAssertEqual(try invoke("put", target.replacingOccurrences(of: "AppGrowthInsights/", with: "AgentGrowth/"), secret)["ok"] as? Bool, false)
        XCTAssertEqual(try invoke("get", target.replacingOccurrences(of: String(digest.prefix(24)), with: String(repeating: "0", count: 24)), NSNull())["ok"] as? Bool, false)
        XCTAssertEqual(try invoke("delete", target, NSNull())["ok"] as? Bool, true)
        XCTAssertTrue(try invoke("get", target, NSNull())["value"] is NSNull)
    }

    @MainActor
    func testNativeAnalyticsDecodesObservedCountsWithoutInventingMissingMetrics() async throws {
        let model = NativeInsightsModel(execute: { action, _ in
            XCTAssertEqual(action, "view")
            return Data("{\"sources\":[],\"reports\":[{\"id\":\"synthetic-report\",\"data\":{\"observed_at\":\"2026-01-01T00:00:00Z\",\"rows\":[{\"id\":\"app_open\",\"value\":12,\"unit\":\"events\",\"period\":\"last_7_days\"}]}}]}".utf8)
        })
        await model.refresh()
        XCTAssertNil(model.message)
        XCTAssertEqual(model.reports.count, 1)
        XCTAssertEqual(model.reports.first?.data.rows.count, 1)
        XCTAssertEqual(model.reports.first?.data.rows.first?.value, 12)
        model.close()
        XCTAssertTrue(model.reports.isEmpty)
    }

    @MainActor
    func testNativeAnalyticsKeepsClarityRowsAndRevenueCatUnitsSeparate() async throws {
        let value: [String: Any] = ["sources": [], "reports": [
            ["id": "clarity-report", "provider": "clarity", "data": ["observed_at": "2026-01-01T00:00:00Z", "rows": [
                ["id": "Traffic", "row": 0, "values": ["totalSessionCount": 12], "period": "last_72_hours"],
                ["id": "Traffic", "row": 1, "values": ["totalSessionCount": 3], "period": "last_72_hours"]]]],
            ["id": "subscription-report", "provider": "revenuecat", "data": ["observed_at": "2026-01-01T00:00:00Z", "rows": [
                ["id": "active_trials", "value": 2, "unit": "customers", "period": "P0D"]]]]]]
        let model = NativeInsightsModel(execute: { _, _ in try JSONSerialization.data(withJSONObject: value) })
        await model.refresh()
        XCTAssertNil(model.message); XCTAssertEqual(model.reports.count, 2)
        let rows = try XCTUnwrap(model.reports.first?.data.rows)
        XCTAssertNotEqual(rows[0].id, rows[1].id)
        XCTAssertNil(rows[0].value); XCTAssertEqual(rows[0].values?["totalSessionCount"], 12)
        XCTAssertEqual(model.reports.last?.data.rows.first?.unit, "customers")
        model.close()
    }

    @MainActor
    func testSavedJourneyDecodesOptionalObservationFieldsWithoutInventingPass() throws {
        let minimal = Data("{\"id\":\"core_value\",\"status\":\"NOT_RUN\"}".utf8)
        let row = try JSONDecoder().decode(NativeEvidenceModel.Journey.self, from: minimal)
        XCTAssertEqual(row.status, "NOT_RUN")
        XCTAssertTrue(row.evidence.isEmpty)
        XCTAssertTrue(row.reason.isEmpty)
        let roundTrip = try JSONDecoder().decode(NativeEvidenceModel.Journey.self, from: JSONEncoder().encode(row))
        XCTAssertEqual(row, roundTrip)
    }
    @MainActor
    func testInferencePreviewAndUncertainRequestRecoveryDoNotAutomaticallyResend() async throws {
        var actions: [String] = []
        let requestID = UUID().uuidString.lowercased()
        let model = NativeInferenceModel(execute: { action, _ in
            actions.append(action)
            let response: [String: Any]
            switch action {
            case "profiles": response = ["profiles": [], "routing": ["version": 0, "data": ["mode": "byok"]]]
            case "history": response = ["items": []]
            case "prepare": response = ["proposal": ["task": "connection_test", "focus": "", "connection_id": "synthetic",
                "provider": "openai_api", "model": "synthetic", "prompt": "Synthetic preview", "max_output_tokens": 256],
                "source_hash": String(repeating: "a", count: 64), "cost": "UNKNOWN", "destination": "https://api.openai.com/v1"]
            case "start": response = ["id": requestID, "status": "QUEUED"]
            case "run": throw URLError(.networkConnectionLost)
            case "read": response = ["id": requestID, "status": "UNKNOWN", "result": ["status": "RECONCILE_REQUIRED", "cost": "UNKNOWN"]]
            default: throw URLError(.unsupportedURL)
            }
            return try JSONSerialization.data(withJSONObject: response)
        })
        await model.prepare(task: "connection_test", focus: "", profileID: "synthetic")
        XCTAssertEqual(actions, ["prepare"])
        XCTAssertNotNil(model.prepared)
        await model.approve()
        XCTAssertEqual(model.job?.id, requestID)
        XCTAssertEqual(model.job?.status, "QUEUED")
        XCTAssertNotNil(model.message)
        XCTAssertFalse(model.busy)
        await model.open(requestID)
        XCTAssertEqual(model.job?.status, "UNKNOWN")
        XCTAssertNil(model.prepared)
        await model.approve()
        await model.refresh()
        XCTAssertEqual(actions.filter { $0 == "start" }.count, 1)
        XCTAssertEqual(actions.filter { $0 == "run" }.count, 1)
    }

    func testSelectedOriginalBytesAndNoAutomaticRightsApproval() throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: folder) }
        let store = try LocalStore(applicationSupport: folder, databaseID: UUID())
        let original = Data("synthetic user selected original".utf8)
        let receipt = try MediaIntake.retain(original, store: store)
        XCTAssertEqual(try Data(contentsOf: receipt.localURL), original)
        XCTAssertEqual(receipt.sha256, SHA256.hash(data: original).map { String(format: "%02x", $0) }.joined())
        XCTAssertFalse(receipt.reuseApproved)
        XCTAssertThrowsError(try MediaIntake.retain(Data(), store: store))
        XCTAssertThrowsError(try MediaIntake.retain(Data(repeating: 0, count: LocalStore.maximumMediaBytes + 1), store: store))
    }

    @MainActor
    func testReportUnknownAndFormulaNeutralization() throws {
        let report = AppReport(appID: "synthetic-app", appName: "Synthetic 東京", sourceHash: String(repeating: "a", count: 64),
                               observedAt: "2026-10-27T12:00:00.123456Z", rows: [
                                .init(metric: "=SUM(1,2)", observed: nil, evidence: "Synthetic fixture, not measured growth")])
        let csv = String(decoding: try ReportExport.csv(report), as: UTF8.self)
        XCTAssertTrue(csv.contains("'=SUM(1,2)"))
        XCTAssertTrue(csv.contains("Unknown"))
        let decoded = try JSONDecoder().decode(AppReport.self, from: ReportExport.json(report))
        XCTAssertNil(decoded.rows[0].observed)
        let pdf = try ReportExport.pdf(report)
        let document = try XCTUnwrap(PDFDocument(data: pdf))
        XCTAssertGreaterThan(document.pageCount, 0)
        XCTAssertTrue(document.string?.contains("Unknown") == true)
        XCTAssertTrue(document.string?.contains(report.sourceHash) == true)
        let invalid = AppReport(appID: report.appID, appName: report.appName, sourceHash: "invalid",
                                observedAt: report.observedAt, rows: report.rows)
        XCTAssertThrowsError(try ReportExport.json(invalid))
        XCTAssertThrowsError(try ReportExport.csv(invalid))
        XCTAssertThrowsError(try ReportExport.pdf(invalid))
    }
}
