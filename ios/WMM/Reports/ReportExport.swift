import Foundation
import UIKit
import CoreText

/// Construct only from the selected app's reviewed report projection, not a snapshot.
struct AppReport: Codable {
    struct Row: Codable { let metric: String; let observed: String?; let evidence: String }
    let appID: String
    let appName: String
    let sourceHash: String
    let observedAt: String
    let rows: [Row]
}

@MainActor
enum ReportExport {
    enum Failure: Error { case invalidReport, cannotPaginate }

    static func validate(_ report: AppReport) throws {
        guard !report.appID.isEmpty, report.appID.count <= 200,
              !report.appName.isEmpty, report.appName.count <= 200,
              report.sourceHash.range(of: "^[a-f0-9]{64}$", options: .regularExpression) != nil,
              ISO8601DateFormatter().date(from: report.observedAt) != nil,
              report.rows.count <= 1000,
              report.rows.allSatisfy({ $0.metric.count <= 200 && ($0.observed?.count ?? 0) <= 4000 && $0.evidence.count <= 4000 }) else {
            throw Failure.invalidReport
        }
    }

    static func json(_ report: AppReport) throws -> Data {
        try validate(report)
        let encoder = JSONEncoder(); encoder.outputFormatting = [.sortedKeys, .prettyPrinted]
        return try encoder.encode(report)
    }

    private static func cell(_ value: String) -> String {
        // Spreadsheet applications may evaluate formulas even in quoted CSV cells.
        let dangerous = value.drop(while: { $0.isWhitespace }).first.map { "=+-@".contains($0) } ?? false
        let safe = dangerous ? "'" + value : value
        return "\"" + safe.replacingOccurrences(of: "\"", with: "\"\"") + "\""
    }

    static func csv(_ report: AppReport) throws -> Data {
        try validate(report)
        let header = ["App", "Metric", "Observed", "Evidence", "Source hash", "Observed at"]
        let rows = report.rows.map { [report.appID, $0.metric, $0.observed ?? "Unknown", $0.evidence, report.sourceHash, report.observedAt] }
        return Data(([header] + rows).map { $0.map(cell).joined(separator: ",") }.joined(separator: "\r\n").utf8)
    }

    static func pdf(_ report: AppReport) throws -> Data {
        try validate(report)
        let lines = [report.appName, "App: " + report.appID, "Observed: " + report.observedAt,
                     "Source hash: " + report.sourceHash, "Unavailable observations remain unknown."] +
            report.rows.map { "\($0.metric): \($0.observed ?? "Unknown")\nEvidence: \($0.evidence)" }
        let text = NSAttributedString(string: lines.joined(separator: "\n\n"), attributes: [
            .font: UIFont.systemFont(ofSize: 12), .foregroundColor: UIColor.black
        ])
        let framesetter = CTFramesetterCreateWithAttributedString(text)
        let page = CGRect(x: 0, y: 0, width: 595, height: 842)
        var offset = 0, failed = false
        let data = UIGraphicsPDFRenderer(bounds: page).pdfData { context in
            repeat {
                context.beginPage()
                let graphics = context.cgContext
                graphics.saveGState()
                graphics.translateBy(x: 0, y: page.height)
                graphics.scaleBy(x: 1, y: -1)
                let path = CGPath(rect: page.insetBy(dx: 40, dy: 40), transform: nil)
                let frame = CTFramesetterCreateFrame(framesetter, CFRange(location: offset, length: 0), path, nil)
                CTFrameDraw(frame, graphics)
                let visible = CTFrameGetVisibleStringRange(frame)
                graphics.restoreGState()
                if visible.length == 0 { failed = true; break }
                offset += visible.length
            } while offset < text.length
        }
        guard !failed else { throw Failure.cannotPaginate }
        return data
    }
}
