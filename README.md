# WMM — Wize Marketing Machine

A local marketing operations workspace for planning, evidence collection,
creative experiments and app-specific growth decisions. Keep multiple apps in
separate workspaces, review agent recommendations, and retain a record of what
was actually tested or executed.

## Start locally

Install **Python 3.11 or newer**, clone this repository, and run:

```powershell
git clone https://github.com/zrk222/WMM.git
cd WMM
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes --only-binary :all: -r requirements.txt
.\.venv\Scripts\python.exe -X utf8 -m mission_control.server
```

Open **http://127.0.0.1:8765/**. On Windows you can also right-click
`mission_control/launch.ps1` and run it with PowerShell. It creates a private
Python environment and installs the hash-pinned timezone data automatically.
First setup needs internet access. No API key, paid account, Node.js or cloud
service is required for the core workspace.
Stop the foreground server with Ctrl+C. Data persists on your machine.

Windows is the supported platform for protected credential connections and
native agent discovery. The core server uses Python's standard library plus
the declared IANA timezone data package;
macOS/Linux protected credential and native CLI integrations are not supported
by this release. Do not deploy this workstation server to a public host or
expose it through a reverse proxy. It intentionally binds only to loopback.

To use another port or choose a local database location:

```powershell
.\.venv\Scripts\python.exe -X utf8 -m mission_control.server --port 8766 --database ./data/workspace.sqlite3
```

## First campaign workflow

1. Use **Add an app**, or edit one of the clearly labeled example workspaces.
   Enter its consumer job, audience, release, website and useful activation.
2. Follow **Workflow** and **Pipeline**. Each of the twelve stages explains its
   deliverable, missing inputs and acceptance checks. Unknown inputs stay unknown.
3. Add real evidence in **Evidence & assets**. Preparation creates saved stage
   packets; it does not publish campaigns or prove product readiness.
4. Optionally connect an agent in **Agent access**. Inspect its exact proposed
   context and operation, approve it, then review the draft and its sources.
5. Use the evidence-resolution actions to gather supported public observations
   or review a proposed remedy. Reuse is limited to current, matching evidence.
6. In **Results**, import actual cohort and retention evidence. Define an
   experiment before inspecting its results; retain uncertainty and guardrails.

No private app details, notebook research, customer records, account credentials
or operational databases are supplied. Example apps start unverified.

### Approve a plan and follow its progress

In **Pipeline**, choose **Review execution plan**. WMM proposes the available
evidence actions from the app's current gaps and connected sources. Remove any
actions you do not want, then approve the list. The local worker records each
result, continues independent approved actions after a failed check, and resumes
saved checkpoints when the service restarts. Keep WMM running for work to advance;
closing the browser does not cancel it.

Use **Inspect progress** to open the evidence or **Stop this plan** to cancel
remaining work owned by that plan. Reads started elsewhere are retained. Approval
expires after 30 minutes; changed app or source details can require fresh review.
An ended run means its approved actions were attempted, not that the campaign is
ready or published. Missing access leads to connection setup and another review.

### Inspect experiment tracking

In **Pipeline**, select **Inspect live tracking** for a registered experiment.
WMM derives the expected PostHog flag key, variant split and event scope. Review
the setup, then approve the read-only check. Its project, flag and aggregate reads
use the app's protected PostHog connection. Results and permission/setup failures
remain available under **Saved tracking reads**. Stop a pending check at any time.

The key needs project, feature-flag and query read access. No write permission is
used. Your app must separately implement the displayed assignment and exposure
event contract. Counts deduplicate provider distinct IDs; they do not establish
human views, complete instrumentation, conversion or causal lift. This release
does not create flags, install the SDK or launch an A/B campaign. Reads can repeat
under the existing worker recovery limit after an interruption; provider usage
limits still apply. See [PostHog experiments](https://posthog.com/docs/experiments).

## Capabilities and boundaries

| Capability | Included behavior |
| --- | --- |
| App registry | Versioned local manifests, isolated workspaces, snapshots |
| Twelve-stage pipeline | Readiness checks, missing-evidence remedies, durable preparation jobs |
| Approved follow-through | Editable finite evidence-action lists, saved checkpoints, cancellation and result links |
| Agent assistance | Supported native Codex/Claude discovery and BYOK setup, exact context review, saved drafts and typed action feedback |
| Analytics | Optional PostHog, Microsoft Clarity and RevenueCat aggregate reads using your authorized keys |
| ASA / AEO | App-specific worksheets, public-site observations, source-bound recommendations |
| Creative work | Local assets, briefs, rankings; optional detected FFmpeg tools for supported rendering |
| Experiments | Local A/B plans, schedules, evidence evaluation and retained learning |
| Social connections | Guided Facebook, Instagram, TikTok and LinkedIn setup; requires your own developer apps, allowed scopes and provider approval |
| External changes | A narrowly supported App Store promotional-text action requires separate verified maker/checker review and exact final approval |

**This release is not a fully autonomous advertising or social publishing
service.** Broad campaign publication, autonomous spending and guaranteed growth
are not implemented. Preparing a packet or passing a local fixture does not mean
a campaign ran. Provider availability, permissions and API limits remain external
requirements. A model subscription is usable only through a supported installed
official CLI; it is not a general-purpose API entitlement.

## Optional connections

Use **Connections** to configure your own supported project IDs and authorized
server-side keys. Windows Credential Manager protects saved secrets, scoped to
the app and local database location. Never paste credentials into evidence,
campaign text, screenshots or Git. Connection tests do not install analytics SDKs
in the apps you promote. Automatic aggregate reads run only while WMM is running.

For social OAuth, see [callback relay setup](callback_relay/README.md). No shared
relay, developer app, login or provider account is bundled. Providers may require
review before granting scopes. Saved local authorization cannot bypass that.

Optional security/audit tools must already be installed and detected. They are
not downloaded or executed merely by starting the core application.

## Local data and recovery

The default database is `mission_control/data/mission-control.sqlite3`; uploaded
files live beside it. Keep this directory private. Back it up with WMM stopped,
including its associated files. The UI also offers per-app JSON snapshots;
restored snapshots do not restore credentials, verified roles or execution
authority. Reconnect and reauthorize on the new installation. Never replace a
live database with an older snapshot without preserving the current copy.

This is a trusted-workstation application, not multi-user hosted authentication.
Loopback, Host checks, HTTP-only sessions, CSRF checks and a restrictive content
policy are enabled. Do not disable them to expose the app remotely.

## Development checks

```powershell
.\.venv\Scripts\python.exe -X utf8 -m unittest discover -s tests -p "test_*.py"
.\.venv\Scripts\python.exe tools/check_distribution.py
```

Tests use synthetic data and temporary databases. They do not make purchases,
publish posts or prove live provider integration. The full test profile also
requires FFmpeg and FFprobe on PATH and a supported Segoe UI font. These native
tools are optional for normal non-video use; the CI profile installs them.
See [release scope](RELEASE-SCOPE.md)
and [security guidance](SECURITY.md). Licensed under the [Apache License, Version 2.0](LICENSE).
