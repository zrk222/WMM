# Wize Marketing Machine

**Your app marketing, operated by your personal AI agent.**

You have an app to grow. The research is in one place, the video clips in another, and yesterday’s decisions are buried in a chat. Wize Marketing Machine (WMM) brings that work together so your agent can pick up the next task—and show you what it finished.

WMM collects app facts, research, media and analytics. It turns them into marketing briefs, edited creative, store checks, experiments and reports. With the right connected account and your approved scope, it also publishes Facebook Page posts and runs bounded Meta campaigns.

**You choose the goal and permissions. Your agent does the supported work. You get the files, receipts, results and next decision.** The same controls are available for you to inspect and use yourself.

[See the visual tour](docs/index.html) · [Connect your agent](docs/agent-quickstart.md) · [Detailed setup and operator guide](docs/workspace-guide.md)

## From “market my app” to work you can inspect

1. **Tell WMM what your app does.** Add its audience, the problem it solves and the action you want users to take.
2. **Bring the material.** Add research, upload clips or select Drive media, and connect your own supported analytics accounts.
3. **Give your agent a clear job.** Research a hook, prepare a video, check a listing, run an approved campaign or assess an experiment.
4. **See what happened.** Follow progress, review the creative, inspect delivery receipts and export the evidence. Decide what to keep, change or stop.

The aim is shorter creative cycles, less repeated research and better decisions about installs, activation, paid conversion and retention. Measure those changes on your app; WMM does not guarantee growth or turn public video views into sales evidence.

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

The current CLI/MCP catalog exposes **79 operations**. Named profiles for **Grok Bot, Instinct, Hark Pro, Meta Muse, Codex/Dots and Claude Duet**, plus generic agents and teams, share one current operating protocol. It tells an agent to check the app and permissions, reuse current evidence, run within limits, verify the saved result and report back to its owner.

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

## Start locally

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
