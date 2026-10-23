# Local WMM operation CLI

Run from the WMM repository with the existing server running:

```powershell
python -m mission_control.agent_cli catalog
'{"app_id":"demo-route-notes","operation":"growth.read","input":{}}' | python -m mission_control.agent_cli call --origin http://127.0.0.1:57599
```

`catalog` prints the current operation contract and its content hash. `call` reads
one UTF-8 JSON envelope from stdin and prints one JSON result. Use the same
`app_id` as your selected workspace. No credential or session file is required.
Do not put API keys, OAuth tokens or personal research transcripts in inputs.

The client creates a fresh in-memory cookie/CSRF session per process. It accepts
only an exact `http://127.0.0.1:PORT` origin, ignores environment HTTP proxies,
rejects redirects and uses fixed routes. Requests/responses are limited to
16 MiB, with a 15-second network timeout. Unknown operations, extra fields,
duplicate JSON keys and nonfinite numbers fail before the operation is sent.
Nested business rules remain enforced by the actual WMM service.

## Operations

| Name | Purpose | Local effect |
|---|---|---|
| `workspace.read` | Read app workspace, experiments and job history | Private data read |
| `operations.read` | Inspect app-specific operation/authority discovery | Policy read |
| `growth.read` / `growth.history` | Read unified review or immutable growth history | Private data read |
| `growth.save` | Save listing, benchmark reference/comparison or editorial note | Evidence write |
| `customer.history` / `customer.save` | Read/save source-linked customer workflows | Private read/evidence write |
| `measurement.read` | Recalculate current ledger report | Private data read |
| `snapshot.export` | Print the private app snapshot as JSON | Private data read |
| `cohort.define` / `events.import` | Save a cohort or permitted event export | Evidence write |
| `billing.save` | Save explicit supplied billing terms/observations | Billing evidence write |
| `experiment.register` | Preregister creative or subscription variants | Plan write |
| `experiment.evaluate` | Append a current local assessment | Assessment write |
| `experiment.action` | Record observe, decide, cancel or rollback proposal | Local lifecycle write |

Every call contains exactly `app_id`, `operation` and `input`. The two experiment
resource operations also require `resource_id`. Read operations take `{}` as
their input. Inspect catalog `required` and `optional` lists for write envelopes;
copy nested definitions from the corresponding UI or domain contract. No
arbitrary HTTP route, query, shell command or database path is accepted.

Example retained listing input:

```json
{
  "app_id": "demo-route-notes",
  "operation": "growth.save",
  "input": {
    "id": "my-listing-v1",
    "manifest_version": 1,
    "kind": "ASO_LISTING",
    "data": {
      "release": "demo-build",
      "listing": {
        "platform": "iOS",
        "locale": "en-US",
        "surface": "MANUAL_METADATA",
        "test_fields": ["title"],
        "rule_version": "2026-10-22.v1",
        "fields": {
          "title": "Original app title",
          "subtitle": "Original subtitle",
          "keywords": "original,keywords",
          "description": "Original localized description."
        }
      }
    }
  }
}
```

Use the current app release, locale and manifest version returned by
`workspace.read`. The example is not a preflight approval or a real product claim.
Save errors retain the server's previous data; corrections to immutable entries
use a new ID. Reports contain private app data: redirect stdout only to an
authorized local destination.

## Results and recovery

Exit `0` writes the result to stdout. Exit `2` writes JSON `INVALID_INPUT` to
stderr. Exit `3` writes a transport/server error classification to stderr, with
the HTTP status when known. Argument-parser usage errors also use exit `2`.
No raw HTML or server error body is printed.

The client never retries a write automatically. A timeout or lost response does
not prove a write failed: inspect saved app history first. Growth/customer saves
have immutable identity replay; experiment registration creates a new identity,
so inspect experiments before resubmitting. Refresh current manifest/source data
after HTTP `400` or session failures. Existing server rejection remains decisive.

## Authority and remaining work

This is a trusted local workstation client using the existing local session
model. A session is neither an authenticated human approval nor an owner-issued
scoped agent grant. The catalog excludes identity login, credentials, human
approval, provider writes, spending and publication. Local experiment decisions
and rollback proposals do not execute provider changes.

The Python library is an adapter, not a security sandbox against code running on
the same workstation. Full generic-agent operation still requires authenticated
scoped grants, independent human checkpoint dispatch/resume, complete domain
coverage, MCP and two-client conformance. Use the working CLI for its declared
operations; do not treat it as completion of that broader requirement.
