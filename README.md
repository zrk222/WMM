# Wize Marketing Machine

**Give your AI a marketing goal. Keep the final say.**

Wize Marketing Machine (WMM) is a local app marketing workspace designed for founders and their AI assistants. Choose a goal, authorize the work, and get back creative, dated measurements and receipts you can inspect.

[**Get the desktop preview**](https://github.com/zrk222/WMM/releases) · [Install and create your first packet](docs/desktop-first-run.md) · [Try the interactive sample](https://zrk222.github.io/WMM/demo.html)

![WMM Start Here: choose a marketing goal, review what the agent can do, and inspect the result](docs/images/goal-to-proof.png)

*Actual WMM screen with synthetic example data. [Visual tour](https://zrk222.github.io/WMM/).*

## From goal to decision

1. **Set your goal.** Describe your app, audience and outcome. Start with research, creative, an approved campaign, or results.
2. **Set the limits.** Give your assistant a revocable permission slip for one app. Approve the exact content and destination before publication; paid Meta work also needs its own approved budget and targeting.
3. **Watch the work.** Follow recorded steps as your assistant prepares assets or runs approved work. WMM retains provider receipts and holds interrupted writes for reconciliation.
4. **Decide what’s next.** Open the evidence, see what was measured or is still missing, and choose what to continue, revise, or stop.

## What you can do

| Goal | WMM tools |
| --- | --- |
| Find a creative angle | Research Facebook, Instagram Reels, TikTok and YouTube Shorts. Viral qualification requires **100,000 observed views and 10× the creator’s documented baseline**. |
| Make or revise creative | Turn evidence into a brief, use your own UGC or approved source clips, edit and stitch video, and review a local captioned render. |
| Run an approved campaign | Queue supported organic posts and inspect provider status and receipts. Paid execution is limited to bounded Meta engagement campaigns. [Channels and account requirements](docs/agent-multichannel.md). |
| Measure app growth | Work on store listings and acquisition experiments. Review source dates, denominators and missing data. Social engagement does not establish installs, revenue, or lift. |

[WizeMe dogfooding: dated operations and evidence](docs/WIZEME-DOGFOODING.md) · [Current release scope](RELEASE-SCOPE.md)

## Run WMM

The [desktop preview](docs/desktop-first-run.md) includes the runtime on Windows and Ubuntu. The Windows preview is unsigned. For scheduled work while your computer is off, use an [optional private host you control](docs/always-on-runtime.md). The [native iPhone/iPad app](ios/) has separate acceptance limits.

Connect a [local CLI or MCP assistant](docs/agent-quickstart.md). WMM includes [operating profiles](docs/personal-agent-operations.md) for Grok Bot, Meta Muse, Codex/Dots, Claude and other personal assistants. A remote assistant needs an authorized connection to your workspace.

<details>
<summary>Run from source with Python 3.11+</summary>

~~~sh
git clone https://github.com/zrk222/WMM.git
cd WMM
python -m pip install --require-hashes --only-binary :all: -r requirements.txt
python -X utf8 -m mission_control.server
~~~

Open http://127.0.0.1:8765/. Keep the server on loopback. Core use needs no model API key; connected accounts and media workflows have separate prerequisites.

</details>

[Workspace guide](docs/workspace-guide.md) · [Contributing](CONTRIBUTING.md) · [Test profiles](docs/TESTING.md) · [Security](SECURITY.md)

WMM is source available. Personal and internal business use are free under the [license](LICENSE). Hosting, resale, white-labeling and paid services for external clients require a separate commercial agreement.
