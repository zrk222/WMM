import XCTest
import CryptoKit
import PDFKit
@testable import WMM

final class ProviderIntakeTests: XCTestCase {
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
