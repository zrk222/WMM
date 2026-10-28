"""Fixed local component supervision; no exception bodies or effect authority."""
from copy import deepcopy
import threading
import time
from .common import now

COMPONENTS = ("experiments", "analytics", "apple_metrics", "followup", "social", "queue")


class Supervision:
    def __init__(self):
        self.lock = threading.Lock()
        self.retry = threading.Event()
        self.rows = {name: {"status": "STARTING", "failures": 0,
                           "last_success": None, "next_due": 0} for name in COMPONENTS}
        self.status = "STARTING"
        self.last_success = None

    def begin(self):
        """Consume explicit recovery only between attempts in the worker thread."""
        if self.retry.is_set():
            self.retry.clear()
            with self.lock:
                for row in self.rows.values():
                    if row["failures"]:
                        row.update(status="STARTING", failures=0, next_due=0)

    def attempt(self, name, callback, interval=0):
        """Run one eligible component; cap consecutive failures at three."""
        with self.lock:
            row = self.rows[name]
            if row["status"] == "PAUSED" or time.monotonic() < row["next_due"]:
                return False
        try:
            result = callback()
        except Exception:
            with self.lock:
                row["failures"] += 1
                row["status"] = "PAUSED" if row["failures"] >= 3 else "RECOVERING"
                row["next_due"] = time.monotonic() + row["failures"]
            return False
        with self.lock:
            row.update(status="RUNNING", failures=0, last_success=now(),
                       next_due=time.monotonic() + interval)
        return result

    def finish(self):
        """Do not let a healthy unrelated component clear another's failure."""
        with self.lock:
            healthy = all(r["status"] == "RUNNING" for r in self.rows.values())
            self.status = "RUNNING" if healthy else "RECOVERING"
            if healthy:
                self.last_success = now()

    def snapshot(self):
        """Return a detached redacted view, safe during a concurrent HTTP read."""
        with self.lock:
            rows = deepcopy(self.rows)
            failed = [name for name, row in rows.items() if row["failures"]]
            for row in rows.values():
                row["retry_after_seconds"] = max(0, row.pop("next_due") - time.monotonic())
            error = ("Local automation needs attention: " + ", ".join(failed) +
                     ". Check configuration or storage, then retry failed automation. Saved work is preserved.") if failed else None
            return {"status": self.status, "last_success": self.last_success,
                    "last_error": error, "components": rows}

    def stopped(self):
        """Mark only after the worker has actually terminated."""
        with self.lock:
            self.status = "STOPPED"
