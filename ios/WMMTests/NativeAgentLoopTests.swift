import XCTest
@testable import WMM

final class NativeAgentLoopTests: XCTestCase {
    @MainActor
    func testReservedReviewRecoveryUsesStableIdentityWithoutDispatchOrReservation() async throws {
        let grantID = UUID().uuidString.lowercased(), turnID = UUID().uuidString.lowercased()
        let envelope: [String: Any] = ["app_id": "loop-fixture", "operation": "evidence.save", "input": [:]]
        var checkpointIDs: [String] = []
        let model = NativeAgentLoopModel(appID: "loop-fixture", execute: { action, _ in
            XCTAssertEqual(action, "read")
            return try NativeAgentLoopModel.bytes(["id": turnID, "status": "SUCCEEDED", "tool_dispatch": "RESERVED_RECONCILE_REQUIRED",
                "data": ["request": ["grant_id": grantID]], "result": ["turn": ["kind": "tool", "envelope": envelope]]])
        }, dispatch: { _, _ in XCTFail("Recovery dispatched business action"); throw DomainBridge.Failure.invalidRequest },
           review: { actualGrant, action, request in
            XCTAssertEqual(actualGrant, grantID); XCTAssertEqual(action, "prepare")
            let body = try NativeAgentLoopModel.object(request)
            checkpointIDs.append(try XCTUnwrap(body["id"] as? String))
            let actualEnvelope = try XCTUnwrap(body["envelope"] as? [String: Any])
            XCTAssertEqual(try NativeAgentLoopModel.bytes(actualEnvelope), try NativeAgentLoopModel.bytes(envelope))
            return try NativeAgentLoopModel.bytes(["id": "turn-" + turnID])
        }, teardown: {})
        await model.open(turnID); await model.prepareReservedReview()
        await model.open(turnID); await model.prepareReservedReview()
        XCTAssertEqual(checkpointIDs, ["turn-" + turnID, "turn-" + turnID])
        XCTAssertFalse(model.canDispatch)
        XCTAssertTrue(model.message?.contains("Checkpoint retained") == true)
        await model.close()
    }

    @MainActor
    func testAgentTurnHistoryUsesBundledEngineAndCurrentUnlockedOwner() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: folder) }
        let databaseID = UUID()
        let identity = LocalIdentity(vault: KeychainVault(databaseID: databaseID, appID: UUID()))
        let session = try await identity.begin()
        let bridge = try DomainBridge(store: LocalStore(applicationSupport: folder, databaseID: databaseID), identity: identity)
        let appID = "loop-" + UUID().uuidString.lowercased()
        _ = try await bridge.createWorkspace(session: session, request: NativeAgentLoopModel.bytes([
            "app_id": appID, "confirm_owner": true,
            "manifest": ["name": "Synthetic agent workspace", "release": "build-1", "locale": "en-US", "currency": "USD"]]))
        let history = try NativeAgentLoopModel.object(await bridge.agentLoop(session: session, appID: appID, action: "history", request: Data("{}".utf8)))
        XCTAssertEqual((history["items"] as? [[String: Any]])?.count, 0)
        await identity.lock()
        do {
            _ = try await bridge.agentLoop(session: session, appID: appID, action: "history", request: Data("{}".utf8))
            XCTFail("Locked model-turn history was admitted")
        } catch {}
        await bridge.close(); try await identity.forgetPrincipal()
    }

    @MainActor
    func testReviewedActionUsesActualCheckpointHashBeforeResume() async throws {
        let grantID = UUID().uuidString.lowercased(), turnID = UUID().uuidString.lowercased()
        let checkpointID = UUID().uuidString.lowercased(), hash = String(repeating: "b", count: 64)
        let envelope: [String: Any] = ["app_id": "loop-fixture", "operation": "workspace.read", "input": [:]]
        var actions: [String] = []
        let model = NativeAgentLoopModel(appID: "loop-fixture", execute: { action, _ in
            XCTAssertEqual(action, "read")
            return try NativeAgentLoopModel.bytes(["id": turnID, "status": "SUCCEEDED", "tool_dispatch": "RESERVED_RECONCILE_REQUIRED",
                "data": ["request": ["grant_id": grantID]], "result": ["turn": ["kind": "tool", "envelope": envelope]]])
        }, dispatch: { _, _ in throw DomainBridge.Failure.invalidRequest }, review: { actualGrant, action, bytes in
            XCTAssertEqual(actualGrant, grantID); actions.append(action)
            let body = try NativeAgentLoopModel.object(bytes)
            XCTAssertEqual(body["id"] as? String, checkpointID)
            if action == "inspect" {
                return try NativeAgentLoopModel.bytes(["envelope": envelope, "checkpoint": ["revision": 7, "hash": hash], "result": NSNull()])
            }
            XCTAssertEqual(action, "resume")
            XCTAssertEqual(body["revision"] as? Int, 7)
            XCTAssertEqual(body["packet_hash"] as? String, hash)
            return try NativeAgentLoopModel.bytes(["result": ["outcome": "SUCCEEDED"]])
        }, teardown: {})
        await model.open(turnID); await model.inspectReview(checkpointID, resume: true)
        XCTAssertEqual(actions, ["inspect", "resume"])
        XCTAssertNil(model.message); XCTAssertNotNil(model.toolReceipt)
        await model.close()
    }

    @MainActor
    func testReservedActionIsNotRepeatedAfterDispatchFailureOrReopen() async throws {
        let grantID = UUID().uuidString.lowercased(), turnID = UUID().uuidString.lowercased()
        let envelope: [String: Any] = ["app_id": "loop-fixture", "operation": "workspace.read", "input": [:]]
        var reserved = false, reservations = 0, dispatches = 0
        func saved() -> [String: Any] {
            ["id": turnID, "status": "SUCCEEDED", "tool_dispatch": reserved ? "RESERVED_RECONCILE_REQUIRED" : "NOT_RESERVED",
             "data": ["request": ["grant_id": grantID]], "result": ["turn": ["kind": "tool", "envelope": envelope]]]
        }
        let model = NativeAgentLoopModel(appID: "loop-fixture", execute: { action, _ in
            let result: [String: Any]
            switch action {
            case "profiles": result = ["profiles": [], "routing": ["version": 1, "data": ["mode": "byok"]]]
            case "grants": result = ["grants": [["id": grantID, "agent_id": "fixture", "operations": ["workspace.read"],
                "expires": "2099-01-01T00:00:00Z", "max_calls": 10, "used": 0, "status": "ACTIVE", "version": 1, "review_operations": []]], "operations": [:]]
            case "history": result = ["items": []]
            case "read": result = saved()
            case "reserve_tool":
                reservations += 1; reserved = true
                result = ["id": turnID, "envelope": envelope, "tool_dispatch": "RESERVED_RECONCILE_REQUIRED"]
            default: throw DomainBridge.Failure.invalidRequest
            }
            return try NativeAgentLoopModel.bytes(result)
        }, dispatch: { _, _ in
            dispatches += 1; throw DomainBridge.Failure.closed
        }, review: { _, _, _ in throw DomainBridge.Failure.invalidRequest }, teardown: {})
        await model.refresh(); await model.open(turnID)
        XCTAssertTrue(model.canDispatch)
        await model.runTool()
        XCTAssertEqual(reservations, 1); XCTAssertEqual(dispatches, 1)
        XCTAssertFalse(model.canDispatch); XCTAssertNotNil(model.message)
        await model.open(turnID); await model.runTool()
        XCTAssertEqual(reservations, 1); XCTAssertEqual(dispatches, 1)
        XCTAssertTrue(model.canContinue)
        await model.close()
    }

    @MainActor
    func testClosingDuringPreparationCannotPublishOrSendPrompt() async throws {
        var pending: CheckedContinuation<Data, Never>?
        var sends = 0, closed = false
        let model = NativeAgentLoopModel(appID: "loop-fixture", execute: { action, _ in
            if action == "prepare" { return await withCheckedContinuation { pending = $0 } }
            sends += 1; throw DomainBridge.Failure.invalidRequest
        }, dispatch: { _, _ in throw DomainBridge.Failure.invalidRequest },
           review: { _, _, _ in throw DomainBridge.Failure.invalidRequest }, teardown: { closed = true })
        let preparation = Task { await model.prepare(task: "campaign_plan", focus: "Synthetic fixture", profile: "profile", grant: "grant", operations: ["workspace.read"]) }
        for _ in 0..<100 { if pending != nil { break }; await Task.yield() }
        XCTAssertNotNil(pending)
        await model.close()
        pending?.resume(returning: try NativeAgentLoopModel.bytes(["proposal": ["provider": "openai_api", "model": "fixture", "prompt": "Synthetic fixture", "native_turn": 1],
            "source_hash": String(repeating: "a", count: 64), "destination": "https://example.invalid", "cost": "UNKNOWN"]))
        await preparation.value; await model.approve()
        XCTAssertTrue(closed); XCTAssertNil(model.prepared); XCTAssertEqual(sends, 0)
    }
}
