# Spec: adoption-readiness
Status: REQUIRED; implementation and user acceptance remain pending.

## MUST - User value and platform delivery
### Requirements (EARS)
- When `FIRST_PACKET` starts from first launch in a fresh installed workspace, the system shall return an exported first-app evidence packet within 300 measured seconds using real permitted observations, prioritized next actions and explicit unknowns, and provide a verified playable Loom recording using marketer language without developer workflow jargon. [AD1]
- When `MAC_CREDENTIALS` runs on macOS, the system shall store owner and app scoped credentials in native Keychain with verified create read update lock recovery delete and cleanup and return a platform coverage matrix distinguishing observed native checks from missing checks without claiming unverified macOS credential operations or waiving platform requirements. [AD2]
- When `PUBLIC_BRAND` renders public onboarding marketing navigation or report headings, the system shall return the full name Wize Marketing Machine as the primary brand while preserving compatible internal WMM command and repository identifiers. [AD3]
- When `PUBLIC_CASE` documents an actual app experiment, the system shall return a reviewable case with dated real stages baseline intervention follow-up source receipts and honest observed results, excluding credentials account identifiers and unapproved private data, and require specific approval before public release. [AD4]
- When `CF_CROSS_SELL` offers Wize Marketing Machine to Code Factory users shipping apps, the system shall return an opt-in app-marketing handoff and draft cross-sell assets with explicit data scope and measurable activation steps, without silently transferring credentials or sending unsolicited messages. [AD5]
- When `FULL_NATIVE_IOS` is presented as completed or supported, the system shall return a built standalone native iPhone and iPad application with an actual Xcode target Swift sources bundled shared engine complete in-scope workflows local Keychain storage jobs media and exports plus source-bound simulator and physical-device receipts; a web wrapper paired desktop or omitted workflow shall reject that completion claim. [AD6]

### Acceptance criteria (Gherkin)
```gherkin
Scenario: Timed first packet
 Given FIRST_PACKET has a fresh installed workspace and a real permitted app source
 When FIRST_PACKET completes app selection observation and packet export
 Then FIRST_PACKET retains an unedited timing receipt at or below 300 seconds
 And FIRST_PACKET has a playable Loom link showing marketer language and no secrets
Scenario: Platform truthfulness
 Given MAC_CREDENTIALS has native Keychain acceptance still missing
 When MAC_CREDENTIALS reviews public distribution copy
 Then MAC_CREDENTIALS exposes the missing platform proof and preserves all required platform work
Scenario: Public name
 Given PUBLIC_BRAND has public pages onboarding and report headings
 When PUBLIC_BRAND reviews those surfaces
 Then PUBLIC_BRAND shows Wize Marketing Machine as the primary name
Scenario: Real public case
 Given PUBLIC_CASE has a real completed app experiment and dated observations
 When PUBLIC_CASE prepares its public story
 Then PUBLIC_CASE retains receipts and honest results without private account data
 And PUBLIC_CASE remains unpublished until the exact public artifact is approved
Scenario: Relevant cross-sell
 Given CF_CROSS_SELL has a Code Factory app-shipping user who opts in
 When CF_CROSS_SELL prepares the marketing handoff
 Then CF_CROSS_SELL shows the transferred app fields and retains explicit consent
 And CF_CROSS_SELL transfers no credentials and sends no external message automatically
Scenario: Fully built iOS
 Given FULL_NATIVE_IOS has an installable native candidate and the complete workflow inventory
 When FULL_NATIVE_IOS runs with all other WMM installations offline
 Then FULL_NATIVE_IOS completes every required local workflow on the device
 And FULL_NATIVE_IOS retains build install lifecycle media authority accessibility and export receipts
```

The five-minute clock includes required in-app setup, source connection/import and
export steps. Record installation-to-packet time separately; never hide prerequisites
or substitute a sped-up demonstration for the timing receipt. A local video is not
a verified Loom deliverable. The public case requires an actual experiment, not a
fixture, benchmark or account-connection demonstration; negative or inconclusive
results remain valid observations.

Windows Pro can be an honest interim package description, not an end-state scope
reduction. Native iOS remains mandatory regardless of that packaging choice. Its
full contract is specs/ios-client.md and plans/ios-client.md, including the bundled
CPython engine and native adapters. A catalog listing, scaffold, compilation alone
or mobile browser viewport does not prove functional native parity.

Preserve UPG00-06, every accepted addition and MV1-6. The owner will run the real
marketing campaign with their selected agent. This packet authorizes no campaign
launch, publication, spending, payment changes or production activation.
