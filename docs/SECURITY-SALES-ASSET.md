# Security summary for buyers

Status: **DRAFT — DO NOT SEND UNTIL INDEPENDENT REVIEW IS COMPLETE**

This is the sales-asset scaffold. It becomes usable only after the reviewer named in [SECURITY-REVIEW-PACKET.md](SECURITY-REVIEW-PACKET.md) returns findings and disposition. Until then, do not present it as an attestation, certification or “InfoSec clearance”.

## Review record (complete before sending)

- Reviewer:
- Reviewer independence confirmed: YES / NO
- Review date:
- Candidate source SHA:
- Findings summary:
- Open high/critical findings:
- Disposition:
- Buyer-specific questionnaire reference:

## Boundary

- Local, single-owner workspace; loopback-only server.
- Team sessions are local-only and currently have no remote HTTP route.
- Grants are exact, expiring, app-scoped and revocable.
- Publishing and spending need separate exact approvals; default ad spend is zero.
- Owner-only review is accepted for the preview and is a documented residual risk.
- No hosted multi-tenant service, SSO/SAML or SOC 2 certification is claimed.

## Evidence available

- [Threat model](THREAT-MODEL.md)
- [Security policy](../SECURITY.md)
- [Team-session security review](TEAM-SESSION-SECURITY-REVIEW.md)
- [Audit evidence bundle](AUDIT-BUNDLE.md)
- `SHA256SUMS.txt`, installer receipts and source-bound SBOMs on the release
- [Downloaded-release verifier](VERIFY-RELEASE.md)
- [Independent review packet](SECURITY-REVIEW-PACKET.md)

## Buyer conversation

Ask for the buyer’s specific security questionnaire and required evidence. Do not claim a control that [ENTERPRISE-READINESS.md](ENTERPRISE-READINESS.md) lists as partial or missing. The only thing that removes the buyer’s blocker is the buyer’s acceptance, supported by the independent review.
