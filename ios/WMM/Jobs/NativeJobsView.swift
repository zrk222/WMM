import SwiftUI

@MainActor
struct NativeJobsView: View {
    @ObservedObject var model: LocalScheduler
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Text("Prepare the twelve-stage evidence packets on this device. The queue and stage events are saved locally, so you can inspect unfinished work after reopening.")
                    Text("This driver runs while the app is active. iOS can suspend it; the screen does not promise continuous background work. Provider and media jobs use separate adapters.").font(.callout)
                    Button("Prepare all twelve stages") { Task { await model.prepare() } }.disabled(model.busy)
                }
                if model.busy { Section { ProgressView("Working with the durable preparation queue…") } }
                if let message = model.message { Section("Action result") { Text(message) } }
                if let progress = model.progress {
                    Section("Observed progress") { Text("Read at \(progress.observed_at)").font(.caption) }
                    if progress.runs.isEmpty { Section { Text("No local jobs recorded yet. Prepare your first packet above.") } }
                    ForEach(progress.runs) { run in
                        Section("\(run.action.replacingOccurrences(of: "_", with: " ").capitalized) · \(run.status)") {
                            Text(run.activity)
                            Text("Attempt \(run.attempts) · \(run.processed_stages) stages checked · \(run.blocked_stages) with evidence gaps").font(.callout)
                            if run.action == "pipeline", ["QUEUED", "RUNNING"].contains(run.status) {
                                Button("Resume eligible preparation") { Task { await model.resume(run) } }.disabled(model.busy)
                                Button("Cancel preparation", role: .destructive) { Task { await model.cancel(run) } }.disabled(model.busy)
                                Text("Resume waits for any live 60-second lease to expire and stops after three attempts. Changed app setup requires a new preparation request.").font(.caption)
                            }
                            DisclosureGroup("Saved stage events") {
                                ForEach(Array(run.events.enumerated()), id: \.offset) { item in
                                    VStack(alignment: .leading) {
                                        Text(item.element.message)
                                        Text(item.element.observed_at).font(.caption).foregroundStyle(.secondary)
                                    }
                                }
                            }
                        }
                    }
                }
            }
            .navigationTitle("Work and recovery")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Done") { dismiss() }.disabled(model.busy) }
                ToolbarItem(placement: .primaryAction) { Button("Refresh") { Task { await model.refresh() } }.disabled(model.busy) }
            }
            .task { await model.refresh() }
            .interactiveDismissDisabled(model.busy)
        }.privacySensitive()
    }
}
