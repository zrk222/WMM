"""Owned local REA worker with no automatic retries or scheduling authority."""
import threading
from .audit_runtime import Inspections


class AuditWorker:
    def __init__(self, store):
        self.inspections = Inspections(store)
        self.event = threading.Event()
        self.thread = None
        self.health = {"status": "NOT_STARTED"}

    def start(self):
        """Interrupt only abandoned native runs before accepting explicitly queued work."""
        if self.thread and self.thread.is_alive(): return
        self.inspections.interrupt()
        self.event.clear()
        self.thread = threading.Thread(target=self.loop, daemon=True, name="owned-rea-worker")
        self.thread.start()

    def loop(self):
        """Keep failures visible and never turn a blocked job into another execution."""
        self.health = {"status": "RUNNING"}
        try:
            while not self.event.is_set():
                self.inspections.run_once(self.event.is_set)
                self.event.wait(0.5)
        except Exception:
            self.health = {"status": "BLOCKED", "repair": "Restart the worker; abandoned runs will be interrupted, never replayed"}

    def stop(self):
        """Signal the owned process boundary and wait for its bounded tree cleanup."""
        self.event.set()
        if self.thread: self.thread.join(timeout=20)
        self.health = {"status": "STOPPED" if not self.thread or not self.thread.is_alive() else "STOPPING"}
