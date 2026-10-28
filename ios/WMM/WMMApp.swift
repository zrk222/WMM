import SwiftUI

@main
struct WMMApp: App {
    var body: some Scene {
        WindowGroup { EngineReadinessView() }
    }
}

/// Temporary development entry point until native workflow navigation is wired.
/// A loaded inventory is deliberately not presented as workflow readiness.
private struct EngineReadinessView: View {
    @State private var status = "Checking the bundled app engine…"
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    Text("Wize Marketing Machine").font(.largeTitle.bold())
                    Text("Native development build").font(.headline)
                    Text(status).accessibilityIdentifier("engine-status")
                    Text("Workflow navigation, native media execution and device acceptance remain in development. This screen does not establish iOS support.")
                }.padding(24).frame(maxWidth: 700, alignment: .leading)
            }.navigationTitle("Engine readiness")
        }.task {
            do {
                let data = try EngineBootstrap.inventory()
                guard let value = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                      let count = value["operation_count"] as? Int else {
                    status = "The engine returned an invalid inventory."
                    return
                }
                status = "Bundled engine loaded. \(count) shared operation contracts found. Native workflow acceptance is still pending."
            } catch {
                status = "Engine initialization failed. Rebuild with the required bundled Python runtime."
            }
        }
    }
}
