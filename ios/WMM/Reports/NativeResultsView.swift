import SwiftUI
import UniformTypeIdentifiers

struct NativeReportFile: FileDocument {
    static var readableContentTypes: [UTType] { [.pdf, .json, .commaSeparatedText] }
    let data: Data
    init(data: Data) { self.data = data }
    init(configuration: ReadConfiguration) throws {
        guard let data = configuration.file.regularFileContents else { throw CocoaError(.fileReadCorruptFile) }
        self.data = data
    }
    func fileWrapper(configuration: WriteConfiguration) throws -> FileWrapper {
        FileWrapper(regularFileWithContents: data)
    }
}

@MainActor
struct NativeResultsView: View {
    @ObservedObject var model: NativeWorkspaceModel
    @Environment(\.dismiss) private var dismiss
    @State private var exporting = false
    @State private var document: NativeReportFile?
    @State private var contentType: UTType = .pdf
    @State private var resultMessage: String?

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Text("See what your app's saved observations show. Unknown values stay unknown, and a measured count does not establish that marketing caused a sale.")
                }
                if let report = model.report {
                    Section("Export this report") {
                        Button("Save PDF report") { Task { await prepare(type: .pdf) } }.disabled(model.busy)
                        Button("Save JSON report") { Task { await prepare(type: .json) } }.disabled(model.busy)
                        Button("Save CSV report") { Task { await prepare(type: .commaSeparatedText) } }.disabled(model.busy)
                        Text("Choose a private destination. Reports include this app's reviewed analytics projection, not credentials or raw customer events.").font(.callout)
                    }
                    ForEach(Array(report.rows.enumerated()), id: \.offset) { item in
                        Section(item.element.metric.replacingOccurrences(of: "_", with: " ")) {
                            Text(item.element.observed ?? "Unknown — no usable observation yet")
                            Text(item.element.evidence).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    Section("Report evidence") {
                        Text("Observed: " + report.observedAt)
                        Text("Source: " + report.sourceHash).font(.caption).textSelection(.enabled)
                    }
                } else if model.busy {
                    ProgressView(model.activity)
                } else {
                    Section { Text(model.message ?? "No report has been read yet.") }
                }
                if let resultMessage { Section { Text(resultMessage) } }
            }
            .navigationTitle("Results & reports")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Done") { dismiss() } }
                ToolbarItem(placement: .primaryAction) {
                    Button("Refresh", systemImage: "arrow.clockwise") { Task { await model.loadReport() } }.disabled(model.busy)
                }
            }
            .fileExporter(isPresented: $exporting, document: document, contentType: contentType,
                          defaultFilename: "WMM-app-report") { result in
                document = nil
                switch result {
                case .success: resultMessage = "The report was saved to your chosen destination."
                case .failure: resultMessage = "The export did not finish. Your saved app observations are unchanged."
                }
            }
        }
        .privacySensitive()
        .onChange(of: model.unlocked) { _, unlocked in
            if !unlocked { document = nil; exporting = false; dismiss() }
        }
    }

    private func prepare(type: UTType) async {
        guard model.unlocked, !model.busy else { return }
        // A cached report is display evidence, not a fresh export authorization.
        await model.loadReport()
        guard model.unlocked, let report = model.report else { return }
        do {
            let bytes: Data
            if type == .pdf { bytes = try ReportExport.pdf(report) }
            else if type == .json { bytes = try ReportExport.json(report) }
            else { bytes = try ReportExport.csv(report) }
            document = NativeReportFile(data: bytes); contentType = type
            resultMessage = nil; exporting = true
        } catch { resultMessage = "The report could not be prepared. Refresh the app evidence and try again." }
    }
}
