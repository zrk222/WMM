# T8 scope review

## Change boundary

This backend-only slice adds one explicit owner-controlled Apple Analytics
refresh schedule per existing app workspace. It dispatches the newest complete
daily App Downloads Standard read through the existing leased worker. The owner
can pause or resume it. The schedule remains bound to the current app manifest
and exactly one matching Apple connection; connection or app changes disable
future reads. A maximum of three transient transport attempts is allowed per
read, and three terminal scheduled failures block the schedule pending owner
resume.

## Data and authority

- The scheduler persists only the existing opaque connection record reference,
  record version/hash, app version, report identity, cadence, state, and bounded
  failure/status fields. It does not copy credentials, API keys, signed URLs,
  or provider payloads into schedule state.
- Every provider read remains an Apple read-only request through the existing
  provider transport. Tests replace provider and signed-segment calls with
  deterministic fixtures; no live Apple account read is claimed.
- Exact owner approval remains required to enable/resume. Agent authority stays
  limited to the existing app-scoped analytics read manifest; this slice adds
  no write, publication, spending, or campaign-launch authority.
- Pause cancels an unclaimed queued read. An already-running read revalidates
  schedule version and source binding before metric persistence.

## Applicability

- Happy path: applicable; enable, dispatch, worker read, and durable success
  readback are exercised.
- Validation: applicable; opt-in, cadence, report, app, connection, and version
  boundaries are exercised.
- Failure recovery: applicable; retries are bounded, rotation blocks future
  reads, and repeated terminal failures require explicit resume.
- State consistency: applicable; job and metric writes are atomic, pause and
  source rotation fence stale workers, and restart preserves schedule state.
- Security and privacy: applicable; credentials are only resolved by the
  existing vault/provider path and are excluded from public schedule status.
- Performance: applicable; each worker tick inspects at most 100 schedules and
  each scheduled read has at most three transient attempts.
- Accessibility: not applicable to this backend-only slice; owner controls and
  UI are planned separately in T10.
- External effects: applicable; only mocked Apple report and signed-segment
  calls are covered here. Live account execution and provider acceptance remain
  unverified.

## Known limits

This slice does not expose schedule controls in the UI or admitted-agent
operation surface, export/restore behavior, additional report families, or
measured app outcomes. Those are separate T9-T11 work. Synthetic tests are not
evidence of live Apple account acceptance or product performance.
