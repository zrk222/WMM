import UIKit

/// Finite time to tear down an already revoked session, never authority to run jobs.
@MainActor
final class NativeBackgroundCleanup {
    typealias Begin = @MainActor (@escaping @MainActor () -> Void) -> UIBackgroundTaskIdentifier
    typealias End = @MainActor (UIBackgroundTaskIdentifier) -> Void
    private final class Entry {
        var identifier: UIBackgroundTaskIdentifier = .invalid
        var finished = false
        var task: Task<Void, Never>?
    }
    private let begin: Begin
    private let end: End
    private var entries: [UUID: Entry] = [:]
    var isPending: Bool { !entries.isEmpty }

    init(begin: Begin? = nil, end: End? = nil) {
        self.begin = begin ?? { expired in
            UIApplication.shared.beginBackgroundTask(withName: "Finish protected WMM cleanup") {
                Task { @MainActor in expired() }
            }
        }
        self.end = end ?? { UIApplication.shared.endBackgroundTask($0) }
    }

    func start(_ cleanup: @escaping @MainActor () async -> Void) {
        let id = UUID(), entry = Entry()
        entries[id] = entry
        let identifier = begin { [weak self, weak entry] in
            guard let self, let entry else { return }
            entry.task?.cancel()
            self.finishLease(entry)
        }
        // Also balance an injected synchronous expiration during admission.
        if entry.finished {
            if identifier != .invalid { end(identifier) }
        } else {
            entry.identifier = identifier
        }
        entry.task = Task {
            await cleanup()
            finishLease(entry)
            entries.removeValue(forKey: id)
        }
        if entry.finished { entry.task?.cancel() }
    }

    private func finishLease(_ entry: Entry) {
        guard !entry.finished else { return }
        entry.finished = true
        if entry.identifier != .invalid { end(entry.identifier) }
    }
}
