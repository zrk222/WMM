import SwiftUI

@MainActor
struct WorkflowNavigation: View {
    @StateObject private var model = NativeWorkspaceModel()
    @Environment(\.scenePhase) private var scenePhase
    @State private var showingCreate = false
    @State private var showingResults = false
    @State private var showingMedia = false
    @State private var editor: NativeEditorModel?
    @State private var agents: NativeAgentAccessModel?
    @State private var scheduler: LocalScheduler?

    var body: some View {
        NavigationStack {
            Group {
                if !model.unlocked {
                    ContentUnavailableView {
                        Label("Your app marketing workspace", systemImage: "lock.shield")
                    } description: {
                        Text("Bring your app facts, research and results together. You and your agent use the same evidence, permissions and next steps.")
                    } actions: {
                        Button("Unlock workspace") { Task { await model.unlock() } }
                            .buttonStyle(.borderedProminent).disabled(model.busy)
                            .accessibilityIdentifier("unlock-workspace")
                    }
                } else if let snapshot = model.snapshot {
                    List {
                        Section("Your next steps") {
                            Text("Follow these stages to turn app facts into reviewed marketing work. Readiness shows current evidence; it does not mean a campaign has run.")
                        }
                        ForEach(snapshot.stages) { stage in
                            Section("\(stage.id). \(stage.title)") {
                                Text(stage.description)
                                Label(stage.status == "READY" ? "Inputs ready" : "Evidence needed",
                                      systemImage: stage.status == "READY" ? "checkmark.circle" : "list.bullet.clipboard")
                                ForEach(Array(stage.missing.enumerated()), id: \.offset) { item in Text(item.element).font(.callout) }
                            }
                        }
                    }
                } else {
                    List {
                        Section { Text("Choose an app to review its marketing work, or add your first app. Each app keeps its own evidence and owner permissions.") }
                        Section("Your apps") {
                            if model.apps.isEmpty { Text("No owned apps yet. Add your app to start its local workspace.") }
                            ForEach(model.apps) { app in
                                Button { Task { await model.open(app) } } label: {
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text(app.data.name).font(.headline)
                                        Text(app.data.job ?? "Add your marketing objective").font(.subheadline)
                                    }
                                }.disabled(model.busy).accessibilityHint("Open this app's current marketing stages")
                            }
                        }
                        Section { Button("Add your app", systemImage: "plus") { showingCreate = true }.disabled(model.busy) }
                    }
                }
            }
            .navigationTitle(model.snapshot?.app.data.name ?? "Wize Marketing Machine")
            .toolbar {
                if model.unlocked {
                    ToolbarItem(placement: .topBarLeading) {
                        if model.snapshot != nil { Button("Your apps") { model.clearSelection() } }
                    }
                    ToolbarItem(placement: .topBarTrailing) { Button("Lock", systemImage: "lock") { model.lock() } }
                    ToolbarItem(placement: .bottomBar) {
                        if model.snapshot != nil {
                            Menu("Workspace tools", systemImage: "square.grid.2x2") {
                            Button("Your media", systemImage: "film") {
                                showingMedia = true
                                Task { await model.loadMedia() }
                            }.disabled(model.busy)
                            Button("Edit video", systemImage: "slider.horizontal.3") { editor = model.makeEditor() }
                                .disabled(model.busy)
                            Button("Your agents", systemImage: "person.crop.circle.badge.checkmark") { agents = model.makeAgentAccess() }
                                .disabled(model.busy)
                            Button("Work and recovery", systemImage: "clock.arrow.circlepath") { scheduler = model.makeScheduler() }
                                .disabled(model.busy)
                            Button("Results & reports", systemImage: "chart.bar.doc.horizontal") {
                                showingResults = true
                                Task { await model.loadReport() }
                            }.disabled(model.busy)
                            }
                        }
                    }
                }
            }
            .safeAreaInset(edge: .bottom) {
                VStack(spacing: 8) {
                    if model.busy { ProgressView(model.activity) }
                    if let message = model.message { Text(message).font(.callout).accessibilityIdentifier("workspace-message") }
                    Text("Native development build · Full workflow and device acceptance pending").font(.caption).foregroundStyle(.secondary)
                }.padding().frame(maxWidth: .infinity).background(.regularMaterial)
            }
            .sheet(isPresented: $showingCreate) { CreateWorkspaceView(model: model) }
            .sheet(isPresented: $showingResults) { NativeResultsView(model: model) }
            .sheet(isPresented: $showingMedia) { NativeMediaLibrary(model: model) }
            .sheet(item: $editor) { NativeEditorView(model: $0) }
            .sheet(item: $agents) { NativeAgentAccessView(model: $0) }
            .sheet(item: $scheduler) { NativeJobsView(model: $0) }
        }
        .privacySensitive()
        .overlay { if scenePhase != .active { Color(uiColor: .systemBackground).ignoresSafeArea() } }
        .onChange(of: scenePhase) { _, phase in
            if phase == .background { scheduler = nil; agents = nil; editor = nil; showingCreate = false; showingResults = false; showingMedia = false; model.lock() }
        }
        .onReceive(NotificationCenter.default.publisher(for: UIApplication.protectedDataWillBecomeUnavailableNotification)) { _ in
            scheduler = nil; agents = nil; editor = nil; showingCreate = false; showingResults = false; showingMedia = false; model.lock()
        }
        .onChange(of: model.unlocked) { _, value in if !value { scheduler = nil; agents = nil; editor = nil } }
    }
}

@MainActor
private struct CreateWorkspaceView: View {
    @ObservedObject var model: NativeWorkspaceModel
    @Environment(\.dismiss) private var dismiss
    @State private var appID = "app-" + UUID().uuidString.lowercased()
    @State private var name = ""
    @State private var objective = ""
    @State private var audience = ""
    @State private var activation = ""
    @State private var release = ""
    @State private var locale = "en-US"
    @State private var currency = "USD"
    @State private var confirmed = false

    var body: some View {
        NavigationStack {
            Form {
                Section { Text("Tell us what your app does and who it helps. This creates a private local workspace and establishes you as its first owner.") }
                Section("Your app and its purpose") {
                    TextField("App name", text: $name)
                    TextField("Marketing outcome", text: $objective, axis: .vertical)
                    TextField("Who the app is for", text: $audience, axis: .vertical)
                    TextField("The first useful action in the app", text: $activation, axis: .vertical)
                    TextField("Release or build", text: $release)
                    TextField("Locale", text: $locale).textInputAutocapitalization(.never).autocorrectionDisabled()
                    TextField("Currency", text: $currency).textInputAutocapitalization(.characters).autocorrectionDisabled()
                }
                Section {
                    Toggle("I own this local app workspace", isOn: $confirmed)
                    Text("You control later agent permissions and approvals. This does not connect accounts, publish a campaign or authorize spending.").font(.callout)
                }
                if let message = model.message { Section { Text(message) } }
            }
            .navigationTitle("Add your app")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() }.disabled(model.busy) }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Create") { Task {
                        let saved = await model.create(appID: appID, manifest: ["name": name, "job": objective,
                            "audience": audience, "activation": activation, "release": release,
                            "locale": locale, "currency": currency], confirmed: confirmed)
                        if saved { dismiss() }
                    }}.disabled(model.busy || !confirmed || [name, objective, audience, activation, release, locale, currency].contains { $0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty })
                }
            }
            .interactiveDismissDisabled(model.busy)
        }
    }
}
