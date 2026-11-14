# Reject contradictory protective pause readback

An approved monitor must stop if the exact campaign is configured as paused
but the same provider observation still reports effective delivery as active.
Retain both states and the reserved commitment. The monitor must omit its
verified pause marker, direct the owner to verify provider status, and never
automatically retry the mutation. Test with a synthetic provider and a single
authorized pause attempt.

The `protect` check in `mission_control/campaign_monitor.py` evaluates the
returned pause readback after the campaign service has saved the immutable
observation. `execute` then records a blocked monitor job with no verified pause
marker. This adds a rejection for explicit effective ACTIVE; it does not change
how a provider response with unavailable effective status is retained.

The monitor regression verifies one provider write, a persisted blocked job,
no claim or additional mutation after reopening the workspace, and the
owner-facing verify-provider action. Schedule evidence and process-restart
regressions continue to exercise the existing no-replay boundary.
