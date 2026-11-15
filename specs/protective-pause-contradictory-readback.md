# Reject contradictory protective pause readback

An approved monitor verifies a pause only when the exact campaign is
configured as paused and the same provider read reports effective PAUSED.
Retain both states and the reserved commitment. The monitor must omit its
verified pause marker, direct the owner to verify provider status, and never
automatically retry the mutation. Test with a synthetic provider and a single
authorized pause attempt.

The `protect` check in `mission_control/campaign_monitor.py` evaluates the
returned pause readback after the campaign service has saved the immutable
observation. `execute` then records a blocked monitor job with no verified pause
marker when effective status is missing or anything other than PAUSED. The
original provider observation is still retained for owner reconciliation.
Historical monitor results without positive effective-status evidence no longer
show a verified pause marker. Their original stored result and provider
receipts remain available.

The monitor regression verifies one provider write, a persisted blocked job,
no claim or additional mutation after reopening the workspace, and the
owner-facing verify-provider action. Schedule evidence and process-restart
regressions continue to exercise the existing no-replay boundary.
