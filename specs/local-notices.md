# Spec: local-notices

Status: draft

## MUST - Functional core
### Description
Offer an opt-in local terminal notice channel for saved operational state that
needs attention. Notices are quiet by default, derive only from durable
app-owned rows, are deduplicated across restarts and never repeat a delivered,
dismissed or failed notice for the same observed state. No browser, provider
read or provider write is required.

### Requirements (EARS)
- The system shall keep notices disabled by default and enable them only through one explicit boolean `configure` per app through `opt_in`.
- The system shall project bounded notices from failed, blocked or interrupted jobs, active grants expiring within seven days, blocked campaign monitors and blocked Apple analytics schedules through `notice_sources`.
- The system shall retain only a closed kind, a fixed title, the observed state and saved timestamps, and shall exclude job results, provider payloads, credentials and private messages.
- The system shall give each notice a stable identity derived from kind, source identity and observed state so collection and sync are idempotent across restarts.
- When a notice is delivered, dismissed or fails to deliver, the system shall record one terminal outcome and shall not repeat that notice.
- The system shall expose `--enable`, `--disable`, `--status`, `--once` and `--dismiss` through `notice_cli` and shall not collect notices while disabled.
- The system shall state that the supported channel is the local terminal and that it carries saved local state only.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: opt_in
  Given a local workspace
  When notices have not been enabled
  Then collection and the CLI remain quiet
  And an explicit enable is required
Scenario: notice_dedupe
  Given failed work, expiring grants and blocked schedules
  When notices are collected repeatedly and after restart
  Then each observed state produces one notice
Scenario: notice_terminal_outcome
  Given a pending notice
  When it is delivered, dismissed or delivery fails
  Then the outcome is recorded once
  And the notice never repeats
Scenario: notice_privacy
  Given job results and provider messages
  When notices are rendered
  Then only kind, title, state and timestamps appear
```
