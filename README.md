# Wize Marketing Machine

**Your AI employees need a boss you can audit.**

You built the app. Now you need people to find it, try it and come back. The research, creative, campaign work and results should lead to one clear next move.

Wize Marketing Machine (WMM) was created for founders and teams who want agents to carry that marketing work forward. It gives people and agents one structured workspace: collect app facts and research, make creative, prepare and run supported campaigns, follow the work and review the evidence.

**You choose the goal and approve the scope. Your agent handles the work inside it. You receive the deliverables, analytics, receipts and next decision.** Approve a single action or a bounded automation agreement; review exceptions and stop future work when needed. You can inspect and edit the work yourself.

[**Try the sample workspace**](https://zrk222.github.io/WMM/demo.html) · [See the visual tour](https://zrk222.github.io/WMM/) · [Install WMM](docs/desktop-first-run.md)

![Interactive sample workspace: choose a goal, review consent, follow agent work and inspect the report](docs/images/sample-workflow.png)

*A working interactive example with synthetic data. It connects no accounts, publishes nothing and spends nothing. Try it in your browser, or open `docs/demo.html` after downloading the repository.*

## From “market my app” to a campaign you can follow

1. **Set the direction.** Describe your app, audience and outcome. Bring research, clips and your own supported accounts.
2. **Agree on the work.** Review the agent, accounts, content, destinations, schedule, expiry, quotas and spending limits before activation.
3. **Let your agent carry it forward.** Research an angle, prepare creative and execute the supported approved work. Follow progress and answer exceptions that need your decision.
4. **Open the report.** See the files, execution status, dated measurements and receipts. Choose what to continue, revise or stop.

The intended payoff is less coordination, faster creative cycles and better decisions about installs, activation, paid conversion and retention. Analytics retain source dates, definitions and missing data; receipts show what was actually done. Measure the benefit on your app—growth and time savings are not yet established by the dogfooding trial.

**Available today:** local workspaces, personal-agent CLI/MCP, creative and evidence tools, supported analytics paths, Facebook Page posts and bounded Meta engagement campaigns. Shared cloud team dashboards, broader campaign publishing and complete KPI coverage remain in development. [Current tools and limits](#what-is-included-today).

[Follow the WizeMe dogfooding journey](docs/WIZEME-DOGFOODING.md): dated operations, verified receipts and the next measurement step.

## What is included today

| Your job | WMM’s working tools |
| --- | --- |
| **Organize the app** | Separate app workspaces, versioned facts, the twelve-stage pipeline, readiness checks, next actions, history and noncredential snapshots. |
| **Find useful creative references** | App-scoped discovery queries, industry/narrative/treatment filters, saved collections, source snapshots, watch attempts and evidence cards that feed creative briefs. Viral-only qualification requires **100,000 views AND 10× a documented creator baseline**. Uploaded UGC follows its own intake path. |
| **Choose the packaging before production** | Title and thumbnail concepts, creator-relative outlier research, remix workspaces, feed previews, creative taste guidance and review checklists. A preview is a design check, not a measured performance prediction. |
| **Make and revise content** | Eight-piece copy packs; local and selected Google Drive media; UGC and clip intake; timeline editing, trimming, ordering and stitching; human/agent edits and history. Hypit guided renders create timed title/caption scenes; editor/Studio handles richer projects. Preflight checks timing, text density and prerequisites; explicit verified-render reuse avoids queuing a new build. |
| **Improve the app’s sales journey** | ASO, ASA and AEO worksheets, store/listing checks, funnel plans, paywall/offer experiments, cohorts, event/billing imports and experiment assessments. App Store promotional text has its own maker/checker approval path. |
| **Collect and understand results** | Supported App Store Connect, Apple Ads, Google Play, PostHog, Clarity and RevenueCat paths, plus imports. Coverage varies by source and platform. Reports retain dates, definitions, denominators and missing data; PDF and data exports support review and handoff. |
| **Execute supported campaigns** | Facebook Page text/link publishing and fixed Meta engagement campaigns: exact owner scope, content/rights/targeting review, expiry, quotas, media-budget ceilings, saved provider IDs, reconciliation and protective pause. Other networks do not gain publishing support merely by connecting OAuth. |
| **Delegate and monitor** | CLI/MCP operations, app-scoped grants, manual or bounded autonomous work, approval checkpoints, progress, durable jobs, cancellation and recovery. Provider-reported token/cache usage stays separate from estimated cost. |

[Campaign controls and limits](docs/campaign-automation.md) · [Hypit production guide](docs/hypit-production-preflight.md) · [Agent workflow upgrades](docs/personal-agent-upgrades.md)

## Built for personal agents—including Grok Bot

The CLI/MCP catalog gives agents an explicit operating surface. Named profiles for **Grok Bot, Instinct, Hark Pro, Meta Muse, Codex/Dots and Claude Duet**, plus generic agents and agent teams, share one current protocol: check the app and permissions, reuse current evidence, run within limits, verify the saved result and report back to the owner.

**For Grok Bot:** verify a separately approved local command connection to the computer running WMM, then read the current operation guide. Keep the repeatable method in a private skill. Use scoped grants, retain request IDs and serialize changes to the same resource. Return the artifact, actual status, KPI evidence, resource use and next action in your conversation.

A cloud browser cannot reach another computer’s localhost. Each host still needs a verified execution path; the manifest supplies guidance, not connectivity or account permission. [Agent-specific setup and owner reports](docs/personal-agent-operations.md).

Try this first task:

> Read my app and current permissions. Find the next useful marketing action, prepare its deliverable and ask only for decisions outside your approved scope. Report what you completed, link the evidence, show what remains unknown and recommend one next step. Do not publish or spend without the exact campaign authority.

## See WMM working

Actual screens with synthetic example data—not customer campaign results.

![WMM overview: app context and next actions](docs/images/overview.png)

<details>
<summary>See the pipeline and analytics screens</summary>

![Twelve-stage app marketing pipeline](docs/images/pipeline.png)

![Analytics and results workspace](docs/images/results.png)

</details>

## Start with the desktop app

[Install WMM and make your first useful marketing packet](docs/desktop-first-run.md). Windows and Ubuntu preview installers include the runtime; Python is not required. The guide identifies the current installer downloads, private data locations and first task. For unattended work, choose the [optional owner-managed always-on host](docs/always-on-runtime.md).

## Start from source

Install **Python 3.11+**, clone the repository and run:

~~~sh
git clone https://github.com/zrk222/WMM.git
cd WMM
python -m pip install --require-hashes --only-binary :all: -r requirements.txt
python -X utf8 -m mission_control.server
~~~

Open **http://127.0.0.1:8765/**, add one app and prepare one evidence packet. A private virtual environment is recommended; [Windows/Linux setup, optional tools and recovery](docs/workspace-guide.md) cover the details. Core use needs no model API key or paid service. Provider and video workflows need their own prerequisites.

**Platforms:** protected desktop credentials use Windows Credential Manager or a configured Linux/Ubuntu Secret Service. The desktop macOS credential adapter is unsupported. The separate [native iPhone/iPad app](ios/) uses on-device Keychain and media execution; see its current acceptance limits rather than assuming desktop parity. Keep the desktop server private on loopback.

**Your accounts stay yours.** Bring your own supported keys/OAuth or installed official agent CLI. A subscription is not a general API entitlement. Snapshots do not carry credentials or execution authority. Default ad spending is zero; an enabled campaign needs a separate exact owner scope. Media limits exclude provider taxes, fees and currency effects. Live provider behavior and business gains require actual account evidence.

## License and development

Free personal evaluation and internal business use under the [WMM Personal and Internal Business Use License](LICENSE). Resale, hosting, white-label products and paid external-client services require a separate commercial agreement. [Prior Apache grants and third-party rights remain preserved](docs/licensing.md).

[Development checks](docs/workspace-guide.md#development-checks) · [Release scope](RELEASE-SCOPE.md) · [Security guidance](SECURITY.md)
