"""First-party outcome matching never turns aggregate or missing data into lift."""

import unittest
from typing import cast

from mission_control.common import Invalid
from mission_control.first_party_outcomes import OutcomeBatch, OutcomeEvent, join

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
