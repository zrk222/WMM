# Ownership, bus factor and release authority

**Current status: bus factor 1.** One human maintainer (`@zrk222`) owns the
repository, release credentials and production decisions. Automated agents can
write, test and review code, but they are not independent humans and do not
reduce the bus factor.

This is acceptable only for a local single-owner preview. It is not sufficient
for a production release, commercial delivery, hosted service or sale.

## Required before production

1. Add a second human maintainer to the repository and the `release`
   environment.
2. Require independent human approval for every change to `main` and record the
   reviewed SHA in the pull request.
3. Move release authority to a two-person rule: the build may run automatically,
   but publication needs an approval from a human who did not author the release.
4. Complete the inventory in `IP-DILIGENCE.md` for the exact candidate SHA and
   retain the evidence outside the public repository.
5. Sign release installers with the publisher's code-signing identity and retain
   verification output for the exact artifact hashes.

## Critical paths and recovery

| Area | Owner | Recovery entry |
| --- | --- | --- |
| HTTP entry and local server | `@zrk222` | `mission_control/server.py`, `docs/desktop-first-run.md` |
| Authority, grants, credentials | `@zrk222` | `mission_control/operation_authority.py`, `agent_grants.py`, `agent_access.py` |
| Campaign and publication effects | `@zrk222` | `mission_control/campaign_execution.py`, `publication_schedule.py` |
| Native desktop packages | `@zrk222` | `.github/workflows/desktop-packages.yml`, `packaging/windows/` |
| Release publication | `@zrk222` | `.github/workflows/desktop-release.yml`, `docs/release-handoff.md` |
| CI and review gates | `@zrk222` | `.github/workflows/`, `tools/check_*.py` |
| Third-party and vendored assets | `@zrk222` | `NOTICE`, `licenses/`, `docs/*/provenance.json` |

Keep recovery instructions current when changing a critical path. A maintainer
must be able to reproduce a release from a clean checkout, a documented toolchain
and repository/environment variables without private chat context.

## Second-maintainer onboarding

1. Grant repository write access and access to the `release` environment.
2. Walk through one synthetic local operation from `docs/desktop-first-run.md`.
3. Review one authority change and one release workflow change.
4. Rotate or add a signing credential under the organization's custody policy.
5. Record the new owner in `CODEOWNERS`, this file and the release environment.

Do not represent the project as production-ready or transferable while the
second-maintainer, IP and signing items above remain open.
