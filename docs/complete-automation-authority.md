# Complete automation: authority and onboarding design

Status: LOCAL BACKEND IMPLEMENTED; owner UI and full-domain acceptance pending.
`complete_automation.py` and `automation_execution.py` implement owner-confirmed
standing scope, atomic grant attachment, admission/commit checks and owned-job
revocation for implemented local workflows. Their HTTP service routes are covered
by synthetic authenticated tests. This document does not authorize a real agent,
enable a real app or certify incomplete workflow families as implemented.

## Owner journey and explicit summary

The Complete automation switch starts OFF. Selecting ON opens setup and scope
review. It does not save an active preference. The owner chooses the agent, app,
release, workflows, accounts, destinations and resource limits. WMM checks each
required capability and shows READY, SETUP REQUIRED, EXPIRED or NOT IMPLEMENTED,
with the exact repair or onboarding link. One blocked selected requirement blocks
activation; WMM must not silently omit it or downgrade to a smaller scope.

Show these fields before the final owner confirmation and beside the active switch:

| Field | Explicit information |
| --- | --- |
| Agent | Named agent and inference connection, provider/model or official signed-in tool; WMM operation credential is a separate identity |
| App | App name/ID, release and bound policy revision |
| Work | Every selected workflow and every permitted action, including publish if selected and supported |
| Accounts | Source account and destination identity, provider, permitted scopes, last successful verification, expiry and renewal state |
| Content | Purpose, audience, language, brand/claim constraints, rights evidence, permitted source/media types, output constraints and required stop rules |
| Viral discovery | At least 100,000 observed views AND 10 times the creator's typical views; absent baseline evidence does not qualify |
| Resources | Expiry within 24 hours, 1–10,000 calls, owned-command timeout at most 180 seconds, cadence/concurrency limits and exact spend currency/ceiling |
| Cost | Default ceiling zero; provider price, subscription quota and downstream local-server billing remain UNKNOWN until verified or explicitly bounded |
| Exceptions | Missing credentials/evidence, changed account/scope, exhausted limits, uncertain result or an action outside scope stops affected execution |
| Control | OFF prevents future admissions; dispatched work is listed with cancellation/reconciliation status and saved remote IDs |

Use a final action such as “Approve this scope and enable automation”. The server
must independently authenticate the owner and compare the submitted summary hash
with current facts. Neither model instructions, a browser checkbox, agent bearer
access nor an imported snapshot can issue authority. The grant receipt contains
public configuration and IDs only; credentials stay in protected storage.

## Workflow, operation and credential map

This is a source-inspected inventory, not a runtime readiness result. A future
machine-readable map must enumerate all selected operations and reject missing
or unknown mappings. Final acceptance still covers all parent goal features.

| Workflow | Current operation surface | Credential/capability prerequisite | Current gap/effect |
| --- | --- | --- | --- |
| Local evidence, subscription journey, customer evidence and measurement | `evidence.save`, `growth.*`, `customer.*`, `measurement.read`, `cohort.define`, `events.import`, `billing.save` | Scoped WMM grant and current app; selected inference connection onboarded and verified | Local reads/writes and standing-scope admission exist; complete automation report aggregation pending |
| Plans, experiments and founder review | `pipeline.prepare`, `experiment.*`, `jobs.read`, `job.cancel`, `operations.read`, `workspace.read`, `snapshot.export` | Same WMM authority; model route if invoked; existing typed experiment/evidence validators | Local preparation exists; no implied live paywall, payment or provider mutation |
| Local Hypit video | `hypit.read`, `hypit.queue` | Current approved brief, source/rights proof, installed verified local compiler/renderer and required media tools/font | Caption composition and durable local jobs exist; selected-agent authoring, richer media and shared editing remain parent requirements |
| Native app-screen video | Human guided production routes; no fixed catalog queue operation yet | Current source proof, cleared assets and native renderer capability | Add catalog/conformance and standing-scope job interlock before selectable autonomous execution |
| TikTok/FB/IG viral discovery and repurposing | Supplied-count qualification policy; social OAuth read-tested accounts | Verified permitted discovery source, exact account/scopes, observed view counts and creator baseline, approved reuse rights | Live viral collector and complete repurposing/editor operation coverage pending; OAuth connection alone does not implement collection |
| Inference and original authoring | AgentAccess profiles/routes and controlled task adapters | App-owned TESTED profile, successful verification within 24 hours, required protected key or official signed-in tool, supported task and pinned route/tool identity | Saving CONFIGURED_UNTESTED is insufficient; a text test does not establish media, publishing, billing allowance or universal API compatibility |
| Provider analytics | Provider-specific connection/read routes | Exact provider/account/destination, fresh successful authorized read, required scopes/expiry and protected credential availability | Add catalog and complete KPI reconciliation/report coverage; missing values remain missing |
| Social publishing | Not in the operation catalog; `Connections.view` says `publishing_implemented=False` | Exact verified subject/destination, official publish scopes and executable adapter, source/content/rights approval in standing policy | NOT IMPLEMENTED; read-tested OAuth cannot authorize or prove a publish adapter |
| Store, build and deployment actions | Provider-specific preparation/checker routes; no general agent provider-mutation operation | Exact project/provider/environment, action-specific credential and effect adapter, resource limits and explicit standing policy coverage | Complete release-workbench and effect adapters remain required; preparation is not deployment |
| Paid actions | `spend` currently denied by operation catalog | Explicit exact effect, currency, price/maximum reservation, budget and credential authority | Zero default; no paid effect can become selectable through an unknown-price fallback |

The inventory must be exhaustive against the fixed operation catalog and workflow
registry. Schema drift or a new action is a blocker until explicitly mapped and
tested. An owner can select a bounded implemented subset; the UI must name it and
must not label that subset as every WMM workflow being fully automated.

## Authoritative credential facts

AgentAccess stores opaque protected references and app-owned versioned profiles.
Execution tests, not save success or executable detection, establish TESTED and
last successful test. Subscription sign-in stays with the official tool; WMM
does not extract another application's OAuth token. A successful inference call
does not establish the provider billing account or available subscription quota.
Where no account-identity endpoint exists, display that identity limitation; do
not manufacture a verified account name from a user-entered label.

Social Connections retains app/provider/config version, subject ID, confirmed
destination, scopes/facts, successful read timestamp, expiry and renewal state.
CONNECTED_READ_TESTED is read authority only. Future publication needs its own
exact capability proof and standing scope. Disconnect, account change, scope loss,
protected-secret loss or expired verification must invalidate affected admission.
Do not read secret values merely to display readiness or include them in exports.

Routine refresh may continue only under the same approved subject, destinations,
capabilities and renewal policy. Bind the stable account/authorization revision
separately from a rotated token revision. A refresh cannot widen scopes or switch
accounts. This separation needs implementation and race tests; current versioned
connection rows alone do not prove it.

## Admission, revocation and dispatched work

Legacy unlinked grants retain their existing admission behavior. Standing-linked
grants now create an immutable admitted execution and enter a request-local scope
before fixed dispatch. The central SQLite connection checks the policy again
before business commits; queued local preparation inherits a durable job scope
checked by the worker. OFF serializes with admissions and cancels owned pending
work. The owner UI must use this service rather than an app preference. Future
provider/media effects remain blocked until their effect-specific contracts pass.

Use a versioned standing policy, immutable summary receipt, scope-bound agent
grant, resource reservations and durable execution records. All ingress paths
(UI/CLI/MCP), direct enqueue paths and workers must reach the same domain gate.
Owner setup/status/revoke controls remain independently authenticated and cannot
be stranded by an exhausted agent quota.

1. Under BEGIN IMMEDIATE, validate owner membership, policy epoch/status/expiry,
   app/release/account revisions, exact action/target/content evidence and limits.
   Reserve quota/budget and create an immutable execution intent with a unique
   idempotency key. Roll back all reservations if validation fails.
2. Queued intent is not dispatched authority. The worker checks the current policy
   and credential facts again at each effect boundary. A local business write and
   its final policy/resource check must commit in the same writer transaction.
3. External dispatch atomically changes the owned intent to DISPATCHING under the
   current policy epoch before network/process handoff. Do not hold SQLite locks
   during provider calls. This transaction is the documented dispatch boundary;
   OFF after it cannot guarantee an effect was never sent. Preserve the provider
   idempotency key and remote/build ID immediately when available.
4. OFF increments the policy epoch, revokes linked grants, cancels undispatched
   intents and marks dispatched intents CANCEL_REQUESTED or NEEDS_RECONCILIATION
   in one transaction. Workers observe cancellation and stop owned processes where
   supported. No local switch may claim an external post/build was cancelled
   without the provider or owned-process receipt.
5. Lost responses become UNKNOWN. Reconcile by the saved identity; never blindly
   resubmit. Distinguish reserved, dispatched, actual and reconciled usage. Release
   a reservation only with evidence that the corresponding effect was not charged
   or dispatched. Snapshot restore cannot recreate policies, grants or credentials.

## Required executable acceptance before enabling the switch

Prove positive owner activation and inside-scope autonomous execution; missing,
stale, expired, foreign-account and unimplemented capability rejection; exact
summary/version races; agent self-expansion rejection; quota/budget reservation
races; simultaneous OFF/admission and OFF/worker-dispatch orderings; alternate
HTTP/UI/CLI/MCP enqueue bypass denial; credential refresh/disconnect races; restart,
lost response and no-resubmission recovery; secret-free action/KPI/PDF/data reports;
snapshot non-restoration; accessible desktop/mobile ON/OFF/BLOCKED states and
actual owner onboarding. External acceptance uses only authorized test accounts
and effects. Until these pass, UPG-13 remains IMPLEMENTATION PENDING.
