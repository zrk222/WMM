import XCTest
@testable import WMM

final class BridgeAgentTests: XCTestCase {
    @MainActor
    func testNativeProviderSetupUsesSharedRecordsAndProtectedKeychainWithoutNetworking() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: folder) }
        let databaseID = UUID()
        let store = try LocalStore(applicationSupport: folder, databaseID: databaseID)
        let identity = LocalIdentity(vault: KeychainVault(databaseID: databaseID, appID: UUID()))
        let session = try await identity.begin()
        let bridge = try DomainBridge(store: store, identity: identity)
        let appID = "provider-" + UUID().uuidString.lowercased()
        let setup = try JSONSerialization.data(withJSONObject: ["app_id": appID, "confirm_owner": true,
            "manifest": ["name": "Synthetic provider app", "release": "build-1", "locale": "en-US", "currency": "USD"]] as [String: Any])
        _ = try await bridge.createWorkspace(session: session, request: setup)
        let model = NativeProviderModel(execute: { action, request in
            try await bridge.providers(session: session, appID: appID, action: action, request: request)
        })
        let saved = await model.save(provider: "openai_api", label: "Synthetic protected API",
            model: "synthetic-model", endpoint: "", key: "synthetic-private-key-0123456789",
            allowCharges: true, confirmed: true)
        XCTAssertTrue(saved)
        let profile = try XCTUnwrap(model.listing?.profiles.first)
        XCTAssertTrue(profile.data.protected_key)
        XCTAssertEqual(model.listing?.native_inference, "NOT_RUN")
        let bytes = try await bridge.providers(session: session, appID: appID, action: "view", request: Data("{}".utf8))
        XCTAssertFalse(String(decoding: bytes, as: UTF8.self).contains("synthetic-private-key"))
        let inference = NativeInferenceModel(execute: { action, request in
            if action == "profiles" {
                return try await bridge.providers(session: session, appID: appID, action: "view", request: request)
            }
            return try await bridge.inference(session: session, appID: appID, action: action, request: request)
        })
        await inference.refresh()
        XCTAssertTrue(inference.history.isEmpty)
        await inference.prepare(task: "connection_test", focus: "", profileID: profile.id)
        XCTAssertNil(inference.message)
        XCTAssertEqual(inference.prepared?.destination, "https://api.openai.com/v1")
        XCTAssertEqual(inference.prepared?.proposal.connection_id, profile.id)
        XCTAssertEqual(inference.prepared?.source_hash.count, 64)
        XCTAssertNil(inference.job)
        inference.discardPreview()
        XCTAssertNil(inference.prepared)
        await inference.refresh()
        XCTAssertTrue(inference.history.isEmpty) // Preview/discard must not create a request or transmit a key.
        await model.disconnect(profile)
        XCTAssertEqual(model.listing?.profiles.first?.status, "DISCONNECTED")
        XCTAssertEqual(model.listing?.cleanup_pending, 0)
        await identity.lock()
        await model.refresh()
        XCTAssertNotNil(model.message)
        await bridge.close()
        try await identity.forgetPrincipal()
    }

    @MainActor
    func testNativeScopedAgentRetainsCredentialAndRespectsRevocationAndLock() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: folder) }
        let databaseID = UUID()
        let store = try LocalStore(applicationSupport: folder, databaseID: databaseID)
        let identity = LocalIdentity(vault: KeychainVault(databaseID: databaseID, appID: UUID()))
        let session = try await identity.begin()
        let bridge = try DomainBridge(store: store, identity: identity)
        let appID = "agent-" + UUID().uuidString.lowercased()
        let setup = try JSONSerialization.data(withJSONObject: ["app_id": appID, "confirm_owner": true,
            "manifest": ["name": "Synthetic agent app", "release": "build-1", "locale": "en-US", "currency": "USD"]] as [String: Any])
        _ = try await bridge.createWorkspace(session: session, request: setup)
        let vault = KeychainVault(databaseID: databaseID, appID: UUID())
        let runtime = ScopedAgentRuntime(bridge: bridge, session: session, vault: vault)
        let model = NativeAgentAccessModel(appID: appID, manifestVersion: 1, runtime: runtime, execute: { action, request in
            try await bridge.agentAccess(session: session, appID: appID, action: action, request: request)
        })
        await model.refresh()
        XCTAssertTrue(model.grants.isEmpty)
        await model.issue(agentID: "synthetic-agent", selected: ["workspace.read"], reviewed: [], hours: 1, maxCalls: 2, confirmed: true)
        let grant = try XCTUnwrap(model.grants.first)
        await model.verify(grant)
        XCTAssertEqual(model.grants.first?.used, 1)
        XCTAssertTrue(model.message?.contains("Local scoped access verified") == true)
        let listing = try await bridge.agentAccess(session: session, appID: appID, action: "list", request: Data("{}".utf8))
        XCTAssertFalse(String(decoding: listing, as: UTF8.self).contains("wmmg_"))
        await model.revoke(try XCTUnwrap(model.grants.first))
        XCTAssertEqual(model.grants.first?.status, "REVOKED")
        let request = try JSONSerialization.data(withJSONObject: ["app_id": appID, "operation": "workspace.read", "input": [:]] as [String: Any])
        do {
            _ = try await runtime.call(grantID: grant.id, request: request)
            XCTFail("Revoked local credential remained usable")
        } catch {}
        await identity.lock()
        do {
            _ = try await bridge.agentAccess(session: session, appID: appID, action: "list", request: Data("{}".utf8))
            XCTFail("Locked owner read agent grants")
        } catch {}
        await runtime.cancel()
        await bridge.close()
        try await identity.forgetPrincipal()
    }

    func testProtectedNativeVerifierRejectsLockExpiryAndPrincipalChange() async throws {
        let vault = KeychainVault(databaseID: UUID(), appID: UUID())
        let identity = LocalIdentity(vault: vault)
        let session = try await identity.begin()
        XCTAssertNotNil(identity.authority.verify(session.nonce.uuidString))
        XCTAssertNil(identity.authority.verify(UUID().uuidString))
        XCTAssertNil(identity.authority.verify(session.nonce.uuidString, now: session.expiresAt))
        try await vault.save(Data(UUID().uuidString.utf8), reference: "local-principal")
        XCTAssertNil(identity.authority.verify(session.nonce.uuidString))
        await identity.lock()
        XCTAssertNil(identity.authority.verify(session.nonce.uuidString))
        try await identity.forgetPrincipal()
    }

    @MainActor
    func testEmbeddedRuntimeUsesNativeIdentityAndClosesWithoutServer() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: folder) }
        let databaseID = UUID()
        let store = try LocalStore(applicationSupport: folder, databaseID: databaseID)
        let vault = KeychainVault(databaseID: databaseID, appID: UUID())
        let identity = LocalIdentity(vault: vault)
        let session = try await identity.begin()
        let bridge = try DomainBridge(store: store, identity: identity)
        let data = try await bridge.workspaces(session: session)
        let result = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
        XCTAssertEqual((result["apps"] as? [Any])?.count, 0)
        let appID = "native-" + UUID().uuidString.lowercased()
        let request = try JSONSerialization.data(withJSONObject: [
            "app_id": appID, "confirm_owner": true,
            "manifest": ["name": "Synthetic native app", "job": "Improve activation",
                         "release": "build-1", "locale": "en-US", "currency": "USD"]
        ])
        let created = try await bridge.createWorkspace(session: session, request: request)
        let replay = try await bridge.createWorkspace(session: session, request: request)
        XCTAssertEqual(created, replay)
        let populated = try await bridge.workspaces(session: session)
        let apps = try XCTUnwrap((JSONSerialization.jsonObject(with: populated) as? [String: Any])?["apps"] as? [[String: Any]])
        XCTAssertEqual(apps.count, 1)
        XCTAssertEqual(apps.first?["id"] as? String, appID)
        let read = try JSONSerialization.data(withJSONObject: ["app_id": appID, "operation": "growth.history", "input": [:]] as [String: Any])
        let history = try await bridge.call(session: session, request: read)
        XCTAssertEqual((try JSONSerialization.jsonObject(with: history) as? [String: Any])?["app_id"] as? String, appID)
        let workspaceRequest = try JSONSerialization.data(withJSONObject: ["app_id": appID, "operation": "workspace.read", "input": [:]] as [String: Any])
        let workspaceBytes = try await bridge.call(session: session, request: workspaceRequest)
        let workspace = try JSONDecoder().decode(NativeWorkflowSnapshot.self, from: workspaceBytes)
        XCTAssertEqual(workspace.app.id, appID)
        XCTAssertEqual(workspace.stages.map(\.id), Array(1...12))
        XCTAssertFalse(workspace.audit.isEmpty)
        XCTAssertTrue(workspace.audit.allSatisfy { !$0.action.isEmpty && !$0.created.isEmpty })
        XCTAssertEqual(workspace.audit.map(\.id), workspace.audit.map(\.id).sorted(by: >))
        XCTAssertTrue(workspace.stages.allSatisfy { ["READY", "BLOCKED"].contains($0.status) })
        let reportData = try await bridge.report(session: session, appID: appID)
        let report = try JSONDecoder().decode(AppReport.self, from: reportData)
        XCTAssertEqual(report.appID, appID)
        XCTAssertTrue(report.rows.contains { $0.observed == nil })
        XCTAssertFalse(try ReportExport.json(report).isEmpty)
        XCTAssertFalse(try ReportExport.csv(report).isEmpty)
        XCTAssertTrue(try ReportExport.pdf(report).starts(with: Data("%PDF".utf8)))
        let scheduler = LocalScheduler(execute: { action, request in
            try await bridge.jobs(session: session, appID: appID, action: action, request: request)
        })
        await scheduler.refresh()
        XCTAssertTrue(scheduler.progress?.runs.isEmpty == true)
        await scheduler.prepare()
        let preparedJob = try XCTUnwrap(scheduler.progress?.runs.first)
        XCTAssertEqual(preparedJob.status, "SUCCEEDED")
        XCTAssertEqual(preparedJob.processed_stages, 12)
        XCTAssertTrue(preparedJob.events.contains { $0.code == "STAGE_BLOCKED" })
        await scheduler.resume(preparedJob)
        XCTAssertEqual(scheduler.progress?.runs.first?.attempts, 1)
        await identity.lock()
        await scheduler.refresh()
        XCTAssertNotNil(scheduler.message)
        do {
            _ = try await bridge.workspaces(session: session)
            XCTFail("Locked native identity admitted")
        } catch {}
        await bridge.close()
        do {
            _ = try await bridge.workspaces(session: session)
            XCTFail("Closed native bridge admitted")
        } catch DomainBridge.Failure.closed {}
        try await identity.forgetPrincipal()
    }
}
