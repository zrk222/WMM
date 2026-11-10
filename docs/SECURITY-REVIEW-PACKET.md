# Independent security-review packet

Status: **PREPARED, NOT REVIEWED**. This packet is input for an external reviewer. It is not a security attestation and does not authorize remote access.

## Scope

Review the local desktop/server boundary and the security-sensitive change set:

- loopback server, exact Host/Origin/CSRF checks and session cookies;
- GitHub identity bootstrap, invitations, roles and team sessions;
- agent grants, exact envelopes, expiry, quota, revocation and app-version binding;
- publication/campaign approvals and provider effect boundaries;
- credential storage and log/export boundaries;
- release workflow, checksums, SBOMs and installer receipts;
- team-session remote-access gate.

Out of scope unless separately contracted: provider infrastructure, operating-system hardening, model/provider behavior, and full native iOS device assurance.

## Inputs

- [Threat model](THREAT-MODEL.md)
- [Review policy](REVIEW-POLICY.md)
- [Team-session security review](TEAM-SESSION-SECURITY-REVIEW.md)
- [Measurement runbook](WIZEME-MEASUREMENT-RUNBOOK.md)
- [Security policy](../SECURITY.md)
- [Architecture and authority map](SERVER-ENFORCEMENT-AUDIT.md)

## Reproduction

Use a disposable workstation and synthetic data only:

```sh
python -m pip install --require-hashes --only-binary :all: -r requirements.txt
python tools/test.py --profile inventory
python tools/test.py --profile core --install
python tools/test.py --profile browser --install
python tools/test.py --profile node
python tools/check_distribution.py
```

Do not use production provider credentials. No review step requires publishing or spending.

## Required questions

1. Can any request select an app, principal, role, grant or reviewer from the request body and have the server trust it?
2. Can a revoked/expired grant, session, invitation or membership still authorize an effect?
3. Does every provider or filesystem effect require an exact current approval bound to app/version/source and the reviewed content?
4. Can the loopback server be reached remotely through a supported configuration without HTTPS, authentication and tenant isolation?
5. Can credentials, tokens, private evidence or customer identifiers enter logs, reports, exports, SBOMs or release notes?
6. Does the team-session primitive expose an HTTP route, and if so, are transport, fixation, replay, logout, role downgrade and revocation reviewed together?
7. Can an agent or malformed import escape its app, path, file-type, size or authority boundary?
8. Do installer/SBOM/checksum verification and anonymous download checks fail closed?
9. Are owner-only review and its residual risk explicitly accepted, with an independent gate before remote/paid expansion?
10. What is the single highest-severity finding that would block a pilot with real provider credentials?

## Deliverable

Provide:

- reviewer identity/independence and review dates;
- exact commit and commands run;
- findings by severity with reproduction and affected boundary;
- explicit pass/fail for the ten questions;
- residual risk and recommendations;
- disposition required before remote access, hosted tenancy or materially expanded paid execution.

Do not post credentials, exploit details or private evidence publicly. Use private vulnerability reporting where available.
