import XCTest
import UIKit
@testable import WMM

final class NativeBackgroundCleanupTests: XCTestCase {
    @MainActor
    func testRevokedSessionCannotRemainAuthorizedWhileCleanupIsSuspended() async throws {
        let vault = KeychainVault(databaseID: UUID(), appID: UUID())
        let identity = LocalIdentity(vault: vault)
        let session = try await identity.begin()
        XCTAssertNotNil(identity.authority.verify(session.nonce.uuidString))
        var resume: CheckedContinuation<Void, Never>?
        let cleanup = NativeBackgroundCleanup(begin: { _ in .invalid }, end: { _ in XCTFail("Invalid lease must not be ended") })
        identity.authority.revoke()
        cleanup.start {
            await withCheckedContinuation { resume = $0 }
            await identity.lock()
        }
        for _ in 0..<100 { if resume != nil { break }; await Task.yield() }
        XCTAssertTrue(cleanup.isPending)
        XCTAssertNil(identity.authority.verify(session.nonce.uuidString))
        resume?.resume()
        for _ in 0..<100 { if !cleanup.isPending { break }; await Task.yield() }
        XCTAssertFalse(cleanup.isPending)
        let fresh = try await identity.begin()
        XCTAssertNotEqual(session.nonce, fresh.nonce)
        XCTAssertNotNil(identity.authority.verify(fresh.nonce.uuidString))
        XCTAssertNil(identity.authority.verify(session.nonce.uuidString))
        await identity.lock()
        try await vault.delete(reference: "local-principal")
    }

    @MainActor
    func testCompletedCleanupEndsGrantedLeaseExactlyOnce() async {
        var expiry: (@MainActor () -> Void)?
        var ended: [UIBackgroundTaskIdentifier] = []
        var cleaned = false
        let token = UIBackgroundTaskIdentifier(rawValue: 42)
        let cleanup = NativeBackgroundCleanup(begin: { expiry = $0; return token }, end: { ended.append($0) })
        cleanup.start { cleaned = true }
        XCTAssertTrue(cleanup.isPending)
        for _ in 0..<100 { if !cleanup.isPending { break }; await Task.yield() }
        XCTAssertTrue(cleaned); XCTAssertFalse(cleanup.isPending); XCTAssertEqual(ended, [token])
        expiry?(); XCTAssertEqual(ended, [token])
    }

    @MainActor
    func testExpirationCancelsAndEndsLeaseButRetainsPendingTeardown() async {
        var expiry: (@MainActor () -> Void)?
        var resume: CheckedContinuation<Void, Never>?
        var ended: [UIBackgroundTaskIdentifier] = []
        var cancelled = false
        let token = UIBackgroundTaskIdentifier(rawValue: 43)
        let cleanup = NativeBackgroundCleanup(begin: { expiry = $0; return token }, end: { ended.append($0) })
        cleanup.start {
            await withCheckedContinuation { resume = $0 }
            cancelled = Task.isCancelled
        }
        for _ in 0..<100 { if resume != nil { break }; await Task.yield() }
        XCTAssertNotNil(resume)
        expiry?(); expiry?()
        XCTAssertTrue(cleanup.isPending); XCTAssertEqual(ended, [token])
        resume?.resume()
        for _ in 0..<100 { if !cleanup.isPending { break }; await Task.yield() }
        XCTAssertTrue(cancelled); XCTAssertFalse(cleanup.isPending); XCTAssertEqual(ended, [token])
    }

    @MainActor
    func testDeniedLeaseStillCleansWithoutEndingInvalidIdentifier() async {
        var cleaned = false
        var ended = false
        let cleanup = NativeBackgroundCleanup(begin: { _ in .invalid }, end: { _ in ended = true })
        cleanup.start { cleaned = true }
        for _ in 0..<100 { if !cleanup.isPending { break }; await Task.yield() }
        XCTAssertTrue(cleaned); XCTAssertFalse(ended); XCTAssertFalse(cleanup.isPending)
    }

    @MainActor
    func testRepeatedLocksBalanceDistinctLeasesAndImmediateExpiry() async {
        var expirations: [@MainActor () -> Void] = []
        var ended: [UIBackgroundTaskIdentifier] = []
        var cleanups = 0
        let cleanup = NativeBackgroundCleanup(begin: {
            expirations.append($0)
            if expirations.count == 1 { $0() }
            return UIBackgroundTaskIdentifier(rawValue: expirations.count)
        }, end: { ended.append($0) })
        cleanup.start { cleanups += 1 }
        cleanup.start { cleanups += 1 }
        for _ in 0..<100 { if !cleanup.isPending { break }; await Task.yield() }
        expirations.forEach { $0() }
        XCTAssertEqual(cleanups, 2); XCTAssertFalse(cleanup.isPending)
        XCTAssertEqual(ended.map(\.rawValue).sorted(), [1, 2])
    }
}
