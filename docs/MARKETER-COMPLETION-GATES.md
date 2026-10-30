# Marketer completion gates and WizeMe trial priority

Status: REQUIRED / NOT COMPLETE. Added by the owner on October27,2026.
These gates supplement UPG00-06 and all accepted additions; they remove none.
Standalone iOS still requires a real app target, Swift/native runtime, local
storage/Keychain/media execution and actual-device proof. It is not a web preview.

## Execution order

1. Inspect existing WizeMe measurement setup and the authorized source account.
2. Freeze a dated baseline and preregister one narrow intervention, primary
   metric, denominator, comparison, observation/maturity window and stop rule.
3. Prove the existing live reader on that source, including scheduled refresh,
   failed/stale/empty states and recovery. Keep import as a fallback.
4. Prepare one exact governed change with rollback and separate human approval;
   execute only when that specific external change is authorized and approved.
5. Observe the follow-up window and report actual results with source receipts.
6. Close installation and platform verification gaps alongside the trial; use
   the evidence to decide later expansion. Do not invent a result to unblock work.

## MV1: Live source collection

Prove at least one authenticated read from the actual selected app/source, then
its owner-enabled scheduled refresh. Prefer App Store Connect analytics when its
permissions and relevant funnel/retention reports are available; a verified
existing PostHog path is also a valid first source for the trial. Identify exact
app/project, event definitions, aggregate grain, collection and occurrence times,
window/timezone, consent, denominators and missing coverage. Keep a durable raw
receipt hash and scoped normalized readout. Test revoked scopes, rate limits,
expiry, outage, restart, duplicate refresh and stale data. Import remains usable.

Current source correction: insights.py and insights_transport.py already provide
read-only PostHog/Clarity/RevenueCat adapters; Insights.tick and worker supervision
support automatic refresh (21600 seconds). providers.py/provider_reports.py have
App Store and ad reads. These source paths contradict an assertion that every
number is manually imported. They do not prove WizeMe is connected or that ASC
funnel/retention analytics exists. Actual WizeMe read/schedule acceptance is due.

## MV2: One real governed execution loop

Use the existing App Store promotional-text outbox as the first candidate. Freeze
the exact app, version/locale, provider destination, baseline, proposed copy, source
hashes and rollback. Preserve a fresh maker and separate checker, exact approval,
single dispatch, provider acknowledgement, readback and uncertain-effect recovery.
Verify customer-facing availability separately from API readback. Link the change
receipt to the trial; a successful write alone does not establish conversion lift.
No new advertising spend, campaign launch, publication or payment change is
authorized by adding this gate. Actual final send still needs its exact approval.

Current source correction: provider_outbox.Outbox.execute already calls
store_actions.apply and reads provider state back. Source presence and synthetic
tests are not an actual authorized production execution receipt.

## MV3: Nontechnical installation

Deliver at least one one-install experience that starts a working workspace
without terminal commands, manual Python setup or grant JSON editing. Prove fresh
installation, first useful task, account/credential onboarding, upgrade, uninstall,
offline restart and recovery on a declared supported platform with a nontechnical
operator. Keep scoped identity/approval boundaries intact while simplifying them.
A hosted option requires a separate reviewed tenant/authentication/deployment
architecture; exposing the current loopback server is not an implementation.
Do not treat an installation script or the unsupported95percent attrition claim
as measured adoption evidence. Independent platform requirements remain mandatory.

## MV4: WizeMe measured trial

Owner clarification: the owner will manually use a chosen agent to run a
marketing campaign and dogfood WMM. This development task prepares that handoff
and accepts its evidence; it must not launch the campaign itself or demand
production credentials here. Agent operation retains WMM's current scoped grants
and exact human checkpoints. Live-source, execution and outcome acceptance stay
pending until the owner-run campaign provides real receipts.

Record a real dated baseline and follow-up for one app release/audience/source.
Choose a metric WMM can actually observe, with stable definitions and a stated
denominator. Record sample sizes, time windows, maturity, attribution limits,
confounders, costs, intervention receipt and source hashes. Use randomized evidence
where available; before/after alone is descriptive. Report improvement, decline,
no detectable change or inconclusive evidence honestly. A positive result cannot
be guaranteed or manufactured. Fixtures, benchmarks and engineering scores cannot
be substituted. Growth claims require the actual observation, not this plan.

Baseline reads and preregistration may proceed under existing authorized access.
If the app environment/source is not identifiable, request its selection; never
guess an account. Use protected onboarding, not credentials pasted into reports.

## MV5: Native platform CI

Add a Linux/Ubuntu CI lane that discovers the same Python/Node suites as Windows,
installs declared native dependencies and records OS/runtime/source identity.
Run the Linux Secret Service and supported native-agent/media profiles too.
Platform-specific unavailable checks must be named, justified and remain gaps;
dropping failing suites or calling skips full parity does not satisfy acceptance.
The Windows and Ubuntu lanes are implemented in `.github/workflows/checks.yml`,
with four shards each, the same discovered Python/Node suites and Linux native
keyring dependencies. [Run 40875042321](https://github.com/zrk222/WMM/actions/runs/40875042321)
passed all eight lanes for source `d3ee08374deb3d1276a0582e6956e462efcfd340`.
This closes the Windows/Ubuntu CI-lane gap for that tested source. It does not
establish every Linux workflow or macOS support. Independent iPhone/iPad simulator
jobs are defined in `platform-checks.yml`; physical-device and full-parity
acceptance remain separate.

## MV6: Scope discipline

Freeze new business features and catalog expansion while the WizeMe trial is
being established. Existing required platform parity, security/correctness repairs,
integration verification and narrowly necessary trial work remain in scope.
Preserve already-tested commits and in-progress work without claiming it released.
Do not use another operation count, document, source stub or test score as the
commercial acceptance milestone. After the trial, prioritize from observed value.

## Completion proof

Owner instruction covers both onboarding/access defects and avoidable setup or
approval work left to the owner. Track first-owner continuation, sign-in and
session recovery, provider setup/connection health, agent grant handoff, review
queue/revocation and installation as actual workflows. Prepare all reviewable
inputs before requesting necessary human decisions. Do not replace a missing
credential, required consent, distinct checker or exact provider-send approval
with fabricated authority. Required owner actions must have a concrete in-tool
next step and retained state; no report may call all owner issues resolved while
one of these workflows lacks implementation or acceptance.

Every MV gate needs exact implementation plus applicable source-bound CF/workflow
and real execution evidence. Local preparation, CI, device support, protected
activation, provider effects and measured outcomes retain separate statuses.
MV5's Windows/Ubuntu CI-lane requirement has verified evidence above; MV1–MV4
and the trial-dependent MV6 freeze remain open. This document grants no provider access,
external write, production activation, spending, public hosting or outreach.

## Next owner-run WizeMe trial handoff

Use the [first evidence packet](../README.md#your-first-evidence-packet) to start.
The operating agent should first inspect saved WizeMe setup and existing receipts,
then return one private baseline packet: selected app/source, primary metric,
numerator/denominator, dates/timezone, data freshness, missing coverage and hashes.
If a live source is unavailable, retain that state and offer the supported import
fallback; do not manufacture observations or copy credentials into the packet.

Before execution, present one proposed intervention with expected mechanism,
observation window, stop rule, rollback and exact approval needed. Reconcile an
uncertain provider effect before retrying. At follow-up, report the observed
change and confounders, including no change or an inconclusive result. A public
case study requires a separate disclosure review and publication authorization.
