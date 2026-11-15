# Jason McGill: Desktop Preview 8 bounded evaluation

Date: November 12, 2026. Version: `v0.1.0-preview.8`. Source commit: `777a3c1010e22493ecc49bed0ba92b300c1836e8`.

This is a summary of the reviewer's reported findings, not a certification or a claim that WMM is validated overall. It records two separate checks.

## Artifact integrity and source/build traceability

**Reviewer-reported result: PASS for the examined artifact integrity and source/build traceability only.**

The reviewer reported that the Windows release archive matched GitHub's digest, the recomputed installer SHA-256 matched the published checksum file and Windows receipt, and the recorded source SHA matched the successful build workflow.

- [Desktop Preview 8 release](https://github.com/zrk222/WMM/releases/tag/v0.1.0-preview.8)
- [Published SHA256SUMS.txt](https://github.com/zrk222/WMM/releases/download/v0.1.0-preview.8/SHA256SUMS.txt)
- [Published Windows receipt](https://github.com/zrk222/WMM/releases/download/v0.1.0-preview.8/Windows.json)
- [Build and publication workflow run](https://github.com/zrk222/WMM/actions/runs/42829848860)

`WMM-Setup.exe` SHA-256:

```text
3984fdf03d290801ab57b23ba577c01fee05597431ba064d952b443b4d3c2793
```

This finding does not establish a reproducible build, Windows publisher signing, application safety, production readiness, or marketing results. Installation, upgrade and restart checks in the publisher's release receipts were not independently reproduced by the reviewer.

## First-use task

Task: [Issue #240](https://github.com/zrk222/WMM/issues/240), using fictional data, with no account connections, agent setup, campaign approval or publishing.

**Reviewer-reported result: STOP at Windows SmartScreen.**

| Observation | Reported result |
| --- | --- |
| Operating system | Windows; version not confirmed |
| First blocker | Microsoft Defender SmartScreen: "Windows protected your PC" |
| Elapsed time | 4 minutes 48 seconds |
| Installation completed | No |
| First packet opened | No |
| Fallback guide used | No |
| Security warning bypassed | No |

This is a first-use blocker, not a failed checksum or evidence of malicious software. The reviewer reported that the warning prevented the unsigned installer from launching and that he did not proceed with installation or connect accounts. No application workflow result was obtained. The result does not count as successful installation or completion of the first packet.

## Scope and disposition

- These observations apply to Desktop Preview 8 only. They do not validate Preview 9.
- The Windows preview is unsigned. Do not weaken OS security controls to continue the test.
- Jason is a WMM contributor/reviewer. This supplementary evaluation is not counted toward the five-outside-founder cohort in the [first-run validation protocol](../VALIDATION-PROTOCOL.md).
- The broader independent security review, human first-use acceptance and measured growth remain separate, incomplete evidence requirements.
- The private messages and screenshot are not reproduced here. This entry summarizes the reported findings; it does not turn private evidence into a publicly reproducible test record.
