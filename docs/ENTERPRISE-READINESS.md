# Enterprise readiness

Status: **NOT ENTERPRISE-CERTIFIED**. This is an honest control map, not a sales claim. It does not remove an IT/InfoSec blocker; only an independent review and the buyer's own acceptance can do that.

## Implemented and testable

- Loopback-only local server with exact Host/Origin/CSRF checks.
- Exact, expiring, app-scoped grants with quota, revocation and app-version binding.
- Owner-approved publication and provider-effect boundaries; zero default ad spend.
- Append-only evidence histories, source hashes and app-scoped records.
- Team roles and invitations with one-time credentials; team sessions are local-only and now require active membership on open and verify.
- Threat model, owner-review policy, team-session review gate and independent-review packet.
- Source-bound CycloneDX SBOMs, complete `SHA256SUMS.txt`, installer receipts and anonymous download verification for releases.
- Downloaded-release verifier and per-app audit evidence bundle.
- Canonical test profiles, deterministic browser tests, Windows/Ubuntu CI and native simulator jobs.

## Partial

| Control | Current state | Gap before enterprise claim |
| --- | --- | --- |
| Authentication | GitHub device identity for the owner and local roles | SSO/SAML, SCIM, enforced MFA policy, recovery |
| Authorization | Local OWNER/MAKER/CHECKER; owner-only review accepted | Independently reviewed role matrix; remote policy enforcement |
| Audit logging | Local append-only audit rows + bundle chain digest | External WORM/immutable sink, retention/legal hold, real-time alerting |
| Attribution | Manual/imported MMP batches linked to tagged studies | Live MMP connector, identity proof, automated reconciliation |
| Encryption | OS keyring for credentials; SQLite at rest depends on disk encryption | Application-level DB encryption, key rotation, HSM/KMS option |
| Tenancy | One local owner/workspace | Multi-tenant isolation, tenant auth, per-tenant keys and quotas |
| Backup/restore | Manual snapshots and restore paths | Documented RPO/RTO, migration compatibility tests, corruption drills |
| Release integrity | Checksums/SBOM/receipts; unsigned Windows publisher | Code signing, provenance attestation, reproducible builds |
| Incident response | Private reporting guidance | Contracted SLA, on-call, breach notification and forensics |
| Privacy | Local-first, no hosted collection by default | DPA, retention/deletion policy, data residency, subprocessor list |

## Missing certifications and reviews

- Independent penetration test and security review of the combined remote boundary.
- SOC 2 Type II or ISO 27001 evidence.
- Data processing agreement and enterprise support terms.
- Hosted multi-tenant architecture and tenant isolation proof.
- External audit of the release and evidence chain.

## Gate

Do not market WMM as “fully audited”, “enterprise-grade”, “SOC 2 compliant” or as having “removed the InfoSec blocker” until the buyer’s required reports exist and an independent reviewer has passed the [security-review packet](SECURITY-REVIEW-PACKET.md). The current bundle and SBOM improve evidence quality; they do not certify it.

The validation-first scope in [ADR 0002](adr/0002-stay-narrow.md) still applies.
