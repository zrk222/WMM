# Threat model

WMM is a local, single-owner workspace. This document states what its boundaries do and do not protect. It is not an OS sandbox, a multi-tenant service or a substitute for provider security.

## Assets

- Provider credentials, OAuth tokens and local protected-credential entries.
- App evidence, creative assets, imported exports and reports.
- Agent grants, approval envelopes, review hashes and execution receipts.
- The owner's provider accounts, audiences, budgets and public destinations.

## Adversaries and abuse cases

| Case | Current boundary | Residual risk |
| --- | --- | --- |
| Malicious or compromised local agent/plugin | Exact envelopes, app-scoped grants, expiry, call limits, operation allowlists and rechecks; CLI effects are not OS-sandboxed. | A process running as the same OS user can read local files, alter its own environment or attempt unrelated actions. Use a dedicated OS account or VM for stronger isolation. |
| Stolen grant or approval token | Grants are time-limited, app-scoped and revocable; the server rechecks version, hash, expiry, quota and review state. | A token used before revocation inside its exact scope can perform the approved action. Do not paste grants into chats, logs or shared screens. |
| Browser compromise / malicious page | Server is loopback-only; no remote bind by default; exact review surfaces and CSRF/session checks. | A compromised browser profile or malicious extension can act as the signed-in owner. Keep the boot secret private and use a separate browser profile. |
| Malicious media file | Uploaded files are app-scoped; media operations use declared local tools; previews are not publication. | Native decoders and FFmpeg are attack surface. Only process files you trust; keep FFmpeg and the OS patched. |
| Provider-side token abuse | Credentials stay in platform-protected storage; no plaintext fallback; scopes should be least-privilege. | A provider compromise or over-broad token remains the provider's and owner's responsibility. Rotate and revoke at the provider. |
| Another local OS user | Local files inherit OS permissions; protected credentials use the platform keyring. | WMM does not harden the OS account, file ACLs or disk encryption. Use full-disk encryption and separate accounts. |
| Remote network attacker | No public listener by default; optional always-on hosting is owner-managed and not a hosted tenant service. | Exposing the loopback server through a tunnel without authentication is unsupported and unsafe. |
| Agent review mistaken for independent review | CONTRIBUTING and the review policy require independent human review; agent, CI and owner self-review are implementation checks. | A PR may still merge without independent review. Record the review type and "Independent review pending" explicitly. |
| Measurement gap or false confidence | KPI rows keep unavailable values null and list CAC, ROAS_D7, ROAS_D30 and PAYBACK as MISSING; reports state supplied evidence is not causal. | A reader may still treat supplied cohort or provider figures as verified growth. Independent measurement and provider reconciliation remain required. |
| Data loss or corruption | SQLite WAL, foreign keys, immutable histories, source hashes and app-scoped records. | Backups, disk failure and migration defects remain the owner's responsibility; test restore before relying on it. |

## Not in scope

- Multi-tenant isolation, hosted sign-up, remote teams or customer billing infrastructure.
- A hardened OS sandbox for agent subprocesses or third-party tools.
- Guarantees about provider availability, entitlement, delivery, billing accuracy or marketing outcomes.
- Protecting against an attacker who already has the owner's OS account, browser session and keyring unlocked.

## Operating rules

1. Run WMM only on a trusted workstation, on loopback, with a dedicated least-privilege provider account.
2. Keep provider keys, the boot secret, grants and private evidence out of Git, chats and exports.
3. Approve exact content and destinations; an account connection is never execution authority.
4. Revoke grants and provider tokens after suspected exposure, then inspect retained receipts.
5. Treat local snapshots and uploads as sensitive private data; encrypt backups.
6. Do not expose the local server through a tunnel or reverse proxy without a separate reviewed authentication and deployment design.

Report vulnerabilities privately; see [SECURITY.md](../SECURITY.md). Do not post credentials, private evidence or exploit details publicly.
