"""MMP export mapping produces a validated batch or a blocking checklist."""

from pathlib import Path
import json
import tempfile
import unittest
from mission_control.common import digest
from mission_control.install_attribution import record_batch, report
from mission_control.install_import import load_rows, main, map_rows
from mission_control.review_access import Access
from mission_control.store import Store

CAMPAIGN = "11111111-1111-4111-8111-111111111111"
OWNER = {"principal": "github:owner", "login": "owner"}
MAPPING = {
    "install_id": "id",
    "state": "event",
    "occurred_at": "time",
    "state_values": {"install": "ATTRIBUTED", "unattributed": "UNATTRIBUTED"},
}


class InstallImportTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.csv = self.root / "export.csv"
        self.csv.write_text(
            "id,event,time,extra\n"
            "install_a,install,2026-11-01T00:00:00+00:00,ignored\n"
            "install_b,unattributed,2026-11-01T01:00:00+00:00,ignored\n",
            encoding="utf-8",
        )
        self.mapping = self.root / "mapping.json"
        self.mapping.write_text(json.dumps(MAPPING), encoding="utf-8")

    def map(self, rows=None, **changes):
        rows = rows if rows is not None else load_rows(self.csv, "csv")
        coverage = changes.pop("coverage", {"complete": True, "source_event_count": 2})
        window = changes.pop("window", dict(starts_at="2026-10-31T00:00:00+00:00", ends_at="2026-11-03T00:00:00+00:00"))
        return map_rows(
            rows,
            MAPPING,
            "APPSFLYER",
            CAMPAIGN,
            "2026-11-03T00:00:00+00:00",
            window,
            coverage,
            columns=["id", "event", "time", "extra"],
            **changes,
        )

    def test_csv_maps_to_ready_batch_and_checklist(self):
        batch, checklist = self.map()
        self.assertEqual(checklist["status"], "READY")
        self.assertEqual(checklist["rows_read"], 2)
        self.assertEqual(checklist["rows_emitted"], 2)
        self.assertEqual(checklist["counts"], {"ATTRIBUTED": 1, "UNATTRIBUTED": 1})
        self.assertEqual(checklist["unmapped_column_count"], 1)
        self.assertEqual([row["state"] for row in batch["installs"]], ["ATTRIBUTED", "UNATTRIBUTED"])
        self.assertEqual(batch["source_receipt_sha256"], digest({"rows": load_rows(self.csv, "csv")}))

    def test_ready_output_is_accepted_by_the_owner_service(self):
        batch, checklist = self.map()
        self.assertEqual(checklist["status"], "READY")
        store = Store(self.root / "state.sqlite", seed=False)
        store.save_app(
            "sample-one",
            dict(
                name="Synthetic app",
                release="build-1",
                job="Synthetic job",
                audience="Synthetic audience",
                activation="Synthetic value",
                locale="en-US",
            ),
        )
        Access(store).bootstrap("sample-one", OWNER, {"confirm_owner": True})
        result = record_batch(store, "sample-one", OWNER, batch)
        self.assertEqual(result["inserted"], 2)
        self.assertEqual(report(store, "sample-one", OWNER, CAMPAIGN)["counts"]["ATTRIBUTED"], 1)

    def test_missing_values_unknown_states_and_future_times_block(self):
        rows = [
            dict(id="install_a", event="install", time="2026-11-01T00:00:00+00:00"),
            dict(id="", event="install", time="2026-11-01T00:00:00+00:00"),
        ]
        _, checklist = self.map(rows=rows)
        self.assertEqual(checklist["status"], "BLOCKED")
        self.assertEqual(checklist["rejected"][0]["reason"], "install_id is missing")
        rows = [dict(id="install_a", event="purchase", time="2026-11-01T00:00:00+00:00")]
        _, checklist = self.map(rows=rows)
        self.assertEqual(checklist["status"], "BLOCKED")
        self.assertIn("state", checklist["rejected"][0]["reason"].lower())
        rows = [dict(id="install_a", event="install", time="2026-11-04T00:00:00+00:00")]
        _, checklist = self.map(rows=rows)
        self.assertEqual(checklist["status"], "BLOCKED")

    def test_duplicate_rules_and_partial_coverage_warning(self):
        rows = [
            dict(id="install_a", event="install", time="2026-11-01T00:00:00+00:00"),
            dict(id="install_a", event="install", time="2026-11-01T00:00:00+00:00"),
        ]
        _, checklist = self.map(rows=rows)
        self.assertEqual(checklist["status"], "READY")
        self.assertEqual(checklist["duplicates"], [2])
        self.assertEqual(checklist["rows_emitted"], 1)
        rows[1]["time"] = "2026-10-31T20:00:00-04:00"
        _, equivalent = self.map(rows=rows)
        self.assertEqual(equivalent["duplicates"], [2])
        self.assertEqual(equivalent["status"], "READY")
        rows = [
            dict(id="install_a", event="install", time="2026-11-01T00:00:00+00:00"),
            dict(id="install_a", event="unattributed", time="2026-11-01T00:00:00+00:00"),
        ]
        _, checklist = self.map(rows=rows)
        self.assertEqual(checklist["status"], "BLOCKED")
        self.assertEqual(checklist["conflicts"], [2])
        _, checklist = self.map(coverage={"complete": False, "source_event_count": None})
        self.assertIn("warnings", checklist)

    def test_cli_writes_batch_and_checklist_with_exit_status(self):
        out, checklist = self.root / "batch.json", self.root / "checklist.json"
        code = main(
            [
                "--input",
                str(self.csv),
                "--input-format",
                "csv",
                "--mapping",
                str(self.mapping),
                "--source",
                "APPSFLYER",
                "--campaign-token",
                CAMPAIGN,
                "--observed-at",
                "2026-11-03T00:00:00+00:00",
                "--window-start",
                "2026-10-31T00:00:00+00:00",
                "--window-end",
                "2026-11-03T00:00:00+00:00",
                "--coverage-complete",
                "--source-event-count",
                "2",
                "--out",
                str(out),
                "--checklist",
                str(checklist),
            ]
        )
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["installs"][0]["install_id"], "install_a")
        self.assertEqual(json.loads(checklist.read_text(encoding="utf-8"))["status"], "READY")
        bad = self.root / "bad.csv"
        bad.write_text("id,event,time\ninstall_a,install,2026-11-04T00:00:00+00:00\n", encoding="utf-8")
        code = main(
            [
                "--input",
                str(bad),
                "--input-format",
                "csv",
                "--mapping",
                str(self.mapping),
                "--source",
                "APPSFLYER",
                "--campaign-token",
                CAMPAIGN,
                "--observed-at",
                "2026-11-03T00:00:00+00:00",
                "--window-start",
                "2026-10-31T00:00:00+00:00",
                "--window-end",
                "2026-11-03T00:00:00+00:00",
                "--coverage-complete",
                "--source-event-count",
                "1",
                "--out",
                str(self.root / "blocked.json"),
            ]
        )
        self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
