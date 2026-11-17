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
        let timestamp = ISO8601DateFormatter()
        timestamp.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let validDate = timestamp.date(from: report.observedAt) != nil || ISO8601DateFormatter().date(from: report.observedAt) != nil
        guard !report.appID.isEmpty, report.appID.count <= 200,
              !report.appName.isEmpty, report.appName.count <= 200,
              report.sourceHash.range(of: "^[a-f0-9]{64}$", options: .regularExpression) != nil,
              validDate,
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

    private static let ink = UIColor(red: 20 / 255, green: 44 / 255, blue: 53 / 255, alpha: 1)
    private static let supportingInk = UIColor(red: 41 / 255, green: 68 / 255, blue: 75 / 255, alpha: 1)
    private static let accent = UIColor(red: 203 / 255, green: 229 / 255, blue: 132 / 255, alpha: 1)

    static func nextStep(_ report: AppReport) -> String {
        if report.rows.isEmpty || report.rows.contains(where: { $0.observed == nil }) {
            return "Refresh the missing observations before comparing results."
        }
        return "Compare these observations with a matching baseline before changing your campaign."
    }

    private static func reportText(_ report: AppReport) -> NSAttributedString {
        let text = NSMutableAttributedString(string: "")
        func line(_ value: String, size: CGFloat = 11, weight: UIFont.Weight = .regular,
                  color: UIColor? = nil, space: CGFloat = 6) {
            let paragraph = NSMutableParagraphStyle()
            paragraph.paragraphSpacing = space
            paragraph.lineSpacing = 2
            text.append(NSAttributedString(string: value + "\n", attributes: [
                .font: UIFont.systemFont(ofSize: size, weight: weight),
                .foregroundColor: color ?? supportingInk, .paragraphStyle: paragraph
            ]))
        }
        line(report.appName, size: 25, weight: .bold, color: ink)
        line("What to do next", size: 15, weight: .semibold, color: ink)
        line(nextStep(report), space: 16)
        line("Statistics and analytics", size: 16, weight: .bold, color: ink, space: 10)
        if report.rows.isEmpty { line("No usable observations for this app were saved.") }
        for row in report.rows {
            let metric = row.metric.replacingOccurrences(of: "_", with: " ")
            line("\(metric): \(row.observed ?? "Unknown")", size: 12, weight: .semibold, color: ink)
            line("Evidence: " + row.evidence, space: 12)
        }
        line("Scope and sources", size: 15, weight: .bold, color: ink)
        line("App: " + report.appID)
        line("Observed: " + report.observedAt)
        line("Source hash: " + report.sourceHash)
        line("Unavailable observations remain unknown. The report alone does not establish causal lift.")
        return text
    }

    private static func drawPageBrand(in graphics: CGContext, page: CGRect, number: Int) {
        let brand = CGRect(x: 40, y: 36, width: page.width - 80, height: 42)
        graphics.setFillColor(ink.cgColor)
        graphics.fill(brand)
        graphics.setFillColor(accent.cgColor)
        graphics.fill(CGRect(x: brand.minX, y: brand.minY, width: 5, height: brand.height))
        ("WMM  /  Wize Marketing Machine" as NSString).draw(
            at: CGPoint(x: brand.minX + 16, y: brand.minY + 10),
            withAttributes: [.font: UIFont.systemFont(ofSize: 13, weight: .semibold), .foregroundColor: UIColor.white]
        )
        ("Evidence report  ·  Page \(number)" as NSString).draw(
            at: CGPoint(x: brand.minX, y: page.height - 40),
            withAttributes: [.font: UIFont.systemFont(ofSize: 9), .foregroundColor: supportingInk]
        )
    }

    static func pdf(_ report: AppReport) throws -> Data {
        try validate(report)
        let text = reportText(report)
        let framesetter = CTFramesetterCreateWithAttributedString(text)
        let page = CGRect(x: 0, y: 0, width: 595, height: 842)
        let format = UIGraphicsPDFRendererFormat()
        format.documentInfo = [kCGPDFContextTitle as String: report.appName + " — WMM evidence report",
                               kCGPDFContextAuthor as String: "Wize Marketing Machine"]
        var offset = 0, failed = false, number = 0
        let data = UIGraphicsPDFRenderer(bounds: page, format: format).pdfData { context in
            repeat {
                context.beginPage()
                let graphics = context.cgContext
                number += 1
                drawPageBrand(in: graphics, page: page, number: number)
                graphics.saveGState()
                graphics.translateBy(x: 0, y: page.height)
                graphics.scaleBy(x: 1, y: -1)
                let path = CGPath(rect: CGRect(x: 40, y: 58, width: page.width - 80, height: page.height - 153), transform: nil)
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
