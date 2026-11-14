"""First-party outcome matching never turns aggregate or missing data into lift."""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast

from mission_control.common import Invalid, canonical, digest
from mission_control.db import connection
from mission_control.first_party_outcomes import OutcomeBatch, OutcomeEvent, join
from mission_control.first_party_receipts import ACTION, for_campaign, primary_outcome, read, retain
from mission_control.operator_client import ClientError, OperatorClient
from mission_control.store import Store
from tests import test_campaign_owner_reports

WINDOW = ("2026-10-01T00:00:00Z", "2026-10-05T00:00:00Z", "2026-10-20T00:00:00Z")


def event(kind: str, day: int, subject: str = "a", **changes: object) -> OutcomeEvent:
    return cast(
        OutcomeEvent,
        dict(
            {
                "event_id": kind + subject,
                "kind": kind,
                "subject_sha256": subject * 64,
                "occurred_at": f"2026-10-{day:02d}T00:00:00Z",
                "campaign": "organic" if kind == "TOUCH" else None,
                "consented": True,
                "internal_test": False,
            },
            **changes,
        ),
    )


def batch(provider: str, *events: OutcomeEvent, **changes: object) -> OutcomeBatch:
    return cast(
        OutcomeBatch,
        dict(
            {
                "app_id": "demo",
                "environment": "production",
                "provider": provider,
                "source_sha256": "e" * 64,
                "identity_namespace_sha256": "f" * 64,
                "coverage_from": WINDOW[0],
                "coverage_through": WINDOW[2],
                "complete": True,
                "events": list(events),
            },
            **changes,
        ),
    )


class OutcomeTests(unittest.TestCase):
    def test_primary_outcome_requires_exact_definition_and_full_window(self) -> None:
        plan = dict(primary_metric="paid_conversion", denominator="installs")
        report = dict(
            install_definition="SOURCE_REPORTED_FIRST_OPEN",
            coverage="DECLARED_COMPLETE",
            counts=dict(INSTALL=5, PURCHASE=0, ACTIVATION=3),
        )
        self.assertEqual(primary_outcome(plan, report)["value"], 0)
        observed = primary_outcome(dict(plan, primary_metric="activation_rate"), report)
        self.assertEqual((observed["numerator"], observed["denominator_count"], observed["value"]), (3, 5, 0.6))
        for changed_plan, changed_report, state in (
            (plan, dict(report, coverage="PARTIAL"), "PARTIAL_COVERAGE"),
            (dict(plan, denominator="visits"), report, "UNSUPPORTED_DEFINITION"),
            (dict(plan, primary_metric="retention_rate"), report, "UNSUPPORTED_DEFINITION"),
            (plan, dict(report, counts=dict(INSTALL=0, PURCHASE=0)), "NO_ELIGIBLE_FIRST_OPENS"),
            (plan, dict(report, counts=dict(INSTALL=2, PURCHASE=3)), "COUNTS_UNVERIFIED"),
        ):
            result = primary_outcome(changed_plan, changed_report)
            self.assertEqual(result["status"], state)
            self.assertIsNone(result["value"])

    def test_capture_attaches_only_exact_campaign_receipt(self) -> None:
        fixture: Any = test_campaign_owner_reports.CampaignOwnerReportsTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        window = {"starts_at": WINDOW[0], "ends_at": WINDOW[2]}
        chosen = fixture.chosen(monitor_id=None, measurement_window=window)
        with connection(fixture.store.path, write=True) as db:
            scope = db.execute("SELECT summary FROM campaign_scopes WHERE id=?", (chosen["scope_id"],)).fetchone()
            summary = test_campaign_owner_reports.core.object_data(scope["summary"])
            link = "https://example.test/?utm_campaign=organic"
            summary["measurement_plan"] = dict(
                window, campaign_tag="organic", primary_metric="paid_conversion", denominator="installs", link=link
            )
            db.execute(
                "UPDATE campaign_scopes SET summary=?,summary_hash=? WHERE id=?",
                (canonical(summary), digest(summary), chosen["scope_id"]),
            )
        body = dict(
            scope_id=chosen["scope_id"],
            acquisition_ends_at=WINDOW[1],
            as_of=WINDOW[2],
            product=batch("posthog", event("TOUCH", 2), event("INSTALL", 3), app_id="sample"),
            billing=batch("revenuecat", app_id="sample"),
        )
        client = fixture.fixture.client
        endpoint = "/api/apps/sample/campaign-owner-reports/import-outcomes"
        with self.assertRaises(ClientError):
            OperatorClient(client.origin).request("POST", endpoint, body)
        with connection(fixture.store.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM audit WHERE action=?", (ACTION,)).fetchone()[0], 0)
        receipt = client.request("POST", endpoint, body)
        self.assertEqual(client.request("POST", endpoint, body), receipt)
        without = fixture.capture(chosen)["report"]
        with_receipt = fixture.capture(dict(chosen, outcome_receipt_sha256=receipt["receipt_sha256"]))["report"]
        self.assertEqual(with_receipt["first_party_outcomes"], receipt)
        self.assertEqual(with_receipt["primary_outcome"]["value"], 0)
        self.assertEqual(with_receipt["primary_outcome"]["denominator_count"], 1)
        self.assertEqual(with_receipt["delivery_evidence"]["status"], "NO_EXACT_DELIVERY_RECEIPT")
        self.assertNotEqual(with_receipt["source_hash"], without["source_hash"])
        self.assertNotIn("first_party_outcomes", without)
        with connection(fixture.store.path, write=True) as db:
            content, rights, page = (
                summary["approved_content_hashes"][0],
                summary["approved_rights_hashes"][0],
                summary["page_id"],
            )
            result = dict(id=f"{page}_123", destination_check=dict(approved_link_sha256=digest(link)))
            changed = db.execute(
                "UPDATE campaign_intents SET scope_id=?, status='VERIFIED', remote_id=?, result=?, created=?, updated=? "
                "WHERE app_id='sample' AND page_id=? AND content_hash=? AND rights_hash=?",
                (chosen["scope_id"], result["id"], canonical(result), WINDOW[0], WINDOW[0], page, content, rights),
            )
            self.assertEqual(changed.rowcount, 1)
            evidence = test_campaign_owner_reports.core.matched_post(db, "sample", chosen["scope_id"], summary, receipt)
            self.assertEqual(evidence["status"], "EXACT_TAGGED_POST_READBACK")
            self.assertEqual(evidence["content_sha256"], content)
            self.assertEqual(evidence["outcome_sha256"], receipt["receipt_sha256"])
            self.assertNotIn(link, canonical(evidence))
            second_link = link + "&utm_content=second"
            second_summary = dict(summary, measurement_plan=dict(summary["measurement_plan"], link=second_link))
            db.execute(
                """INSERT INTO campaign_scopes
                SELECT app_id,'second-approval',owner,owner_version,?,?,'OFF',0,created,updated
                FROM campaign_scopes WHERE app_id='sample' AND id=?""",
                (canonical(second_summary), digest(second_summary), chosen["scope_id"]),
            )
            second_result = dict(id=f"{page}_456", destination_check=dict(approved_link_sha256=digest(second_link)))
            db.execute(
                "INSERT INTO campaign_intents VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "sample",
                    "second-intent",
                    "second-approval",
                    "second-request",
                    digest("second-request"),
                    digest("second-content"),
                    rights,
                    page,
                    "VERIFIED",
                    second_result["id"],
                    canonical(second_result),
                    WINDOW[0],
                    WINDOW[0],
                ),
            )
            self.assertEqual(
                test_campaign_owner_reports.core.matched_post(db, "sample", chosen["scope_id"], summary, receipt),
                {"status": "MULTIPLE_POSTS_SHARE_TAG"},
            )
            second_summary.pop("measurement_plan")
            db.execute(
                "UPDATE campaign_scopes SET summary=?,summary_hash=? WHERE app_id='sample' AND id='second-approval'",
                (canonical(second_summary), digest(second_summary)),
            )
            retained_result = dict(
                id=second_result["id"],
                destination_check=dict(approved_link_sha256=digest(second_link), final_url=second_link),
            )
            db.execute(
                "UPDATE campaign_intents SET result=? WHERE app_id='sample' AND id='second-intent'",
                (canonical(retained_result),),
            )
            self.assertEqual(
                test_campaign_owner_reports.core.matched_post(db, "sample", chosen["scope_id"], summary, receipt),
                {"status": "MULTIPLE_POSTS_SHARE_TAG"},
            )
            db.execute("UPDATE campaign_intents SET status='BLOCKED' WHERE id='second-intent'")
            self.assertEqual(
                test_campaign_owner_reports.core.matched_post(db, "sample", chosen["scope_id"], summary, receipt),
                evidence,
            )
            db.execute(
                "UPDATE campaign_intents SET updated=? WHERE app_id=? AND scope_id=?",
                (WINDOW[1], "sample", chosen["scope_id"]),
            )
            self.assertEqual(
                test_campaign_owner_reports.core.matched_post(db, "sample", chosen["scope_id"], summary, receipt)[
                    "status"
                ],
                "DELIVERY_OUTSIDE_ACQUISITION_WINDOW",
            )
        wrong_window = dict(window, ends_at=WINDOW[1])
        with self.assertRaisesRegex(Invalid, "does not match"):
            fixture.capture(
                dict(chosen, outcome_receipt_sha256=receipt["receipt_sha256"], measurement_window=wrong_window)
            )

    def test_receipt_survives_reopen_and_omits_subjects(self) -> None:
        with TemporaryDirectory() as folder:
            path = Path(folder) / "outcomes.sqlite"
            store = Store(path)
            product = batch("posthog", event("TOUCH", 2), event("INSTALL", 3), app_id="sample-one")
            billing = batch("revenuecat", app_id="sample-one")

            def capture(version: int) -> dict[str, object]:
                return retain(
                    path,
                    app_id="sample-one",
                    app_version=version,
                    environment="production",
                    campaign="organic",
                    starts_at=WINDOW[0],
                    ends_at=WINDOW[1],
                    matures_at=WINDOW[2],
                    as_of=WINDOW[2],
                    product=product,
                    billing=billing,
                )

            version = store.app("sample-one")["version"]
            saved = capture(version)
            self.assertEqual(capture(version), saved)
            receipt_hash = cast(str, saved["receipt_sha256"])
            self.assertEqual(read(Store(path).path, "sample-one", receipt_hash), saved)
            window = {"starts_at": WINDOW[0], "ends_at": WINDOW[2]}
            approved = dict(window, campaign_tag="organic")
            with connection(path) as db:
                self.assertEqual(for_campaign(db, "sample-one", version, approved, window, receipt_hash), saved)
                for invalid in (None, dict(approved, campaign_tag="other"), dict(approved, ends_at=WINDOW[1])):
                    with self.subTest(approved=invalid), self.assertRaises(Invalid):
                        for_campaign(db, "sample-one", version, invalid, window, receipt_hash)
                rows = db.execute("SELECT detail FROM audit WHERE action=?", (ACTION,)).fetchall()
            self.assertEqual(len(rows), 1)
            self.assertNotIn("a" * 64, rows[0]["detail"])
            with self.assertRaises(Invalid):
                read(path, "sample-two", receipt_hash)
            with self.assertRaisesRegex(Invalid, "current app version"):
                capture(version + 1)

    def run_join(self, product: OutcomeBatch, billing: OutcomeBatch) -> dict[str, object]:
        return join("demo", "production", "organic", *WINDOW, WINDOW[2], product, billing)

    def test_cross_source_path_counts_one_subject_and_keeps_limits(self) -> None:
        install = event("INSTALL", 3)
        product = batch("posthog", event("TOUCH", 2), install, install, event("ACTIVATION", 4))
        billing = batch(
            "revenuecat", event("RENEWAL", 10), event("PURCHASE", 9), event("TRIAL_START", 5), event("PURCHASE", 9, "b")
        )
        report = self.run_join(product, billing)
        self.assertEqual(report["counts"], dict(INSTALL=1, ACTIVATION=1, TRIAL_START=1, PURCHASE=1, RENEWAL=1))
        self.assertEqual(report["excluded"], dict(ineligible_events=0, unmatched_paid_subjects=1))
        self.assertEqual(report["provenance"], "NORMALIZED_INPUT_NOT_PROVIDER_VERIFIED")
        self.assertIs(report["incrementality_measured"], False)
        self.assertNotIn("a" * 64, str(report))
        self.assertEqual(
            self.run_join(batch("posthog", event("ACTIVATION", 4), install, event("TOUCH", 2)), billing),
            report,
        )

    def test_partial_and_complete_zero_are_distinct(self) -> None:
        product = batch("posthog")
        for complete, value in ((False, None), (True, 0)):
            with self.subTest(complete=complete):
                result = self.run_join(product, batch("revenuecat", complete=complete))
                self.assertEqual(
                    result["counts"],
                    dict.fromkeys(("INSTALL", "ACTIVATION", "TRIAL_START", "PURCHASE", "RENEWAL"), value),
                )

    def test_conflicting_first_touch_and_internal_or_unconsented_events_never_count(self) -> None:
        report = self.run_join(
            batch(
                "posthog",
                event("TOUCH", 2),
                event("TOUCH", 2, event_id="other-touch", campaign="other"),
                event("INSTALL", 3),
                event("TOUCH", 2, "b", internal_test=True),
                event("TOUCH", 2, "c", consented=False),
                event("INSTALL", 3, "b"),
                event("INSTALL", 3, "c"),
            ),
            batch("revenuecat"),
        )
        self.assertEqual(report["counts"], dict(INSTALL=0, ACTIVATION=0, TRIAL_START=0, PURCHASE=0, RENEWAL=0))
        self.assertEqual(report["excluded"], dict(ineligible_events=2, unmatched_paid_subjects=0))

    def test_scope_or_event_replay_conflict_fails_closed(self) -> None:
        for change in (dict(app_id="foreign"), dict(environment="sandbox"), dict(identity_namespace_sha256="b" * 64)):
            with self.subTest(change=change), self.assertRaises(Invalid):
                self.run_join(batch("posthog"), batch("revenuecat", **change))
        with self.assertRaisesRegex(Invalid, "Conflicting"):
            self.run_join(batch("posthog", event("INSTALL", 3), event("INSTALL", 4)), batch("revenuecat"))

    def test_untrusted_interchange_rejects_unknown_fields_and_implicit_consent(self) -> None:
        for row in (
            event("INSTALL", 3, address="private@example.test"),
            event("INSTALL", 3, event_id="private@example.test"),
            event("INSTALL", 3, consented=1),
            event("INSTALL", 3, internal_test=None),
        ):
            with self.subTest(row=row), self.assertRaises(Invalid):
                self.run_join(batch("posthog", row), batch("revenuecat"))
