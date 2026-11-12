"""Profile discovery, permanent counterexamples and real shrinking/database replay."""

import random
import tempfile
import unittest
from pathlib import Path

from hypothesis import Phase, find, settings
from hypothesis import strategies as st
from hypothesis.database import DirectoryBasedExampleDatabase

from tests import test_parser_properties as properties

PERMANENT_CASES = {
    "MediaRangeProperties.test_parsed_range_is_always_bounded",
    "MediaRangeProperties.test_invalid_and_unsatisfiable_headers_raise",
    "MediaRangeProperties.test_zero_length_file_rejects_every_range",
    "CanonicalProperties.test_round_trip_is_idempotent_and_key_order_independent",
    "CanonicalProperties.test_non_finite_numbers_and_unknown_values_are_rejected",
    "CommonInputProperties.test_identifier_accepts_only_portable_namespaces",
    "CommonInputProperties.test_amount_rejects_non_integral_and_negative_values",
    "CommonInputProperties.test_fraction_is_finite_and_closed",
    "CommonInputProperties.test_iso_time_requires_timezone_and_round_trips",
    "AuthorityDeadlineProperties.test_deadline_consent_boundary",
    "GrantTokenProperties.test_grant_token_digest_is_stable_and_format_bound",
    "Base64UrlProperties.test_canonical_urlsafe_round_trip_and_cap",
    "Base64UrlProperties.test_standard_base64_certificate_round_trip_and_bounds",
    "StrictJSONProperties.test_random_objects_round_trip",
    "StrictJSONProperties.test_ambiguous_unbounded_or_nonobject_payloads_are_rejected",
}


class PropertyProfileTests(unittest.TestCase):
    def test_ci_profile_keeps_shrinking_and_persistent_synthetic_examples(self):
        profile = settings.get_profile("wmm-ci")
        self.assertEqual(profile.max_examples, 200)
        self.assertIsNone(profile.deadline)
        self.assertTrue(profile.print_blob)
        self.assertFalse(profile.derandomize)
        self.assertIn(Phase.reuse, profile.phases)
        self.assertIn(Phase.generate, profile.phases)
        self.assertIn(Phase.shrink, profile.phases)
        self.assertIs(profile.database, properties.EXAMPLE_DATABASE)

    def test_all_permanent_named_parser_cases_remain_discoverable(self):
        discovered = set()
        for case_type in vars(properties).values():
            if isinstance(case_type, type) and issubclass(case_type, unittest.TestCase):
                discovered.update(
                    f"{case_type.__name__}.{name}" for name in unittest.defaultTestLoader.getTestCaseNames(case_type)
                )
        self.assertEqual(discovered, PERMANENT_CASES)

    def test_real_counterexample_shrinks_and_replays_from_reopened_database(self):
        # This intentionally false synthetic invariant is never an application failure.
        # A real discovered bug must also become a committed named regression case.
        observed = []

        def violates(value):
            if value >= 37:
                observed.append(value)
                return True
            return False

        key = b"wmm.synthetic.shrinking-replay.v1"
        with tempfile.TemporaryDirectory(prefix="wmm-hypothesis-replay-") as folder:
            database = DirectoryBasedExampleDatabase(Path(folder) / "examples")
            minimum = find(
                st.integers(min_value=0, max_value=1000),
                violates,
                settings=settings(
                    database=None,
                    max_examples=200,
                    deadline=None,
                    phases=(Phase.generate, Phase.shrink),
                ),
                random=random.Random(20261112),
                database_key=key,
            )
            self.assertEqual(minimum, 37)
            self.assertGreater(observed[0], minimum)
            # Explicit seeds disable Hypothesis database access. Populate it in a
            # separate ordinary search and require the same minimized example.
            persisted = find(
                st.integers(min_value=0, max_value=1000),
                lambda value: value >= 37,
                settings=settings(database=database, max_examples=200, deadline=None),
                database_key=key,
            )
            self.assertEqual(persisted, minimum)
            self.assertTrue(tuple(database.fetch(key)))

            # A fresh instance and reuse-only phases cannot discover new examples.
            replayed = []

            def still_violates(value):
                replayed.append(value)
                return value >= 37

            restored = DirectoryBasedExampleDatabase(Path(folder) / "examples")
            replay = find(
                st.integers(min_value=0, max_value=1000),
                still_violates,
                settings=settings(
                    database=restored,
                    max_examples=1,
                    deadline=None,
                    phases=(Phase.reuse,),
                ),
                database_key=key,
            )
            self.assertEqual(replay, minimum)
            self.assertIn(minimum, replayed)


if __name__ == "__main__":
    unittest.main()
