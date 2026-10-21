# Weekly decision controls — bounded runtime slice

Requirements: derive separate readiness, measurement, economics and retention
states from authoritative stage evaluations; missing stages remain unknown;
duplicate/malformed evaluations reject; each missing gate has an evidence-linked
repair; no local readiness grants spending, a learning pilot or scale.

Scope: mission_control/weekly_controls.py, mission_control/packets.py,
tests/test_weekly_controls.py. Preserve all existing weekly fields. This is the
first F01/F02 packet slice; cross-app inbox, worker gates, pilot envelopes and
measured founder usability remain incomplete. No new dependency or provider call.

Verification: focused positive/negative/scope tests, existing packet tests,
distribution check and hash-bound project-neutral workflow audit. No deployment
or performance improvement claim follows from these checks.
