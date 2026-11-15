# Implement recurring private rule reports

Use the existing owner rule schedule, private report builder and SQLite receipt storage. Include the explicitly reviewed report limit in the immutable schedule definition. Keep the current capture key for one-shot schedules. For opt-in recurring runs, derive a suffix from the retained evidence used in the prepared report. Count and find saves through the existing app/owner/capture-key index. Preserve exact binding rechecks, atomic save and expiry rollback. Do not add a worker, schema migration, endpoint, external effect, or provider authority.

Verify real synthetic cohort changes, replay and restart, unchanged records and reverted evidence, input bounds, unchanged one-shot defaults, owner-only report history, and stop and expiry. Exercise the Results form in the browser with a disposable app; local tests and CI are not live account acceptance.
