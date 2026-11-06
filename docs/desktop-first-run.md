# Install and open WMM

Open the [official WMM releases](https://github.com/zrk222/WMM/releases) and choose a published desktop preview. Download **WMM-Setup.exe** for Windows or **wize-marketing-machine_0.1.0_amd64.deb** for Ubuntu 24.04 amd64. GitHub sign-in is not required for these public release downloads. Source archives are for developers. If no installer release is listed, the desktop distribution has not been published yet.

On Windows, open the downloaded installer and follow its per-user setup screens. Launch **Wize Marketing Machine** from the Start menu. No terminal or separate Python installation is required. The current installer has no verified Windows publisher signature; Windows may display an unknown-publisher warning. An organization that requires a signed publisher should wait for a signed release. Do not disable OS security controls or install a root certificate to proceed.

On Ubuntu, open the downloaded Debian package with your graphical software installer and approve the system package installation. Open **Wize Marketing Machine** from Applications. Use a graphical desktop with a browser and unlocked Secret Service keyring. A Linux distribution without a graphical Debian package installer is outside this no-terminal path. Ubuntu's normal package and desktop prerequisites still apply.

WMM opens its private workspace in your browser. Use the controller to stop it. Your workspace lives in your user application-data directory, outside the installed program. Keep a private backup before upgrading. Install a later preview over the current version; uninstall removes program files and preserves workspace data. Preview-to-preview schema compatibility still requires each release's acceptance checks.

Start with a practice app and choose a goal. Add optional agent integrations using the in-app agent setup, review the proposed configuration, and approve the handoff in your chosen agent. Installing WMM does not authorize a campaign, payment, external message or provider connection. Agent and provider credentials remain optional separate setup; never paste them into an issue or public release report.

These are automated-tested preview packages. Synthetic fresh-install, upgrade, uninstall and offline-restart checks do not establish a nontechnical person's first-use acceptance. That acceptance and signed Windows publisher verification remain separate evidence.

## Maintainer release handoff

Merge the reviewed candidate into main. Use **Desktop runtime packages** for a build-only hosted check. After reviewing that evidence and obtaining explicit approval to publish, dispatch **Desktop public prerelease** from main with the exact current main commit SHA and a new version tag such as `v0.1.0-preview.1`. The workflow reruns the Windows and Ubuntu installer checks, records the tested installer hashes, and publishes only when both jobs pass. Only the final publication job receives repository contents write permission. Pull requests cannot trigger publication.

The publisher creates a draft prerelease, uploads only the two native installers, SHA256SUMS.txt and their source-bound lifecycle receipts, checks the draft asset names/sizes, then publishes. It downloads the public assets anonymously over normal verified HTTPS and compares full SHA256 hashes. Retain the successful run URL and publisher readback as release evidence. CI logs and source archives alone are not installer distribution proof.

Existing tags/releases/assets are never overwritten. An interrupted upload leaves a draft for inspection; choose a new tag after resolving the cause. A public-download verification failure may occur after publication: inspect that release and its logs explicitly before claiming successful distribution. This workflow does not sign Windows binaries, install trust roots, bypass TLS, or prove human first-use acceptance.

## Make one packet

1. **Add your app.** Enter its name, who it helps, what it helps them do, the first useful action, the app version or build and the locale you tested. Choose **Save and choose a goal**. WMM generates a workspace ID. To choose your own ID, open **Optional settings** before saving. The saved ID is permanent. Other optional details stay editable in **App setup**.
2. **Choose “Find a useful marketing angle.”** Select **Open your first packet**. The packet shows the research and creative steps for this app, including missing inputs you can add next.
3. **Keep a copy.** Choose **Download goal packet** to save the local draft for yourself, your agent or your teammate. You can do this before connecting an account, publishing or spending.
4. **Add a reference to study.** Choose **Add a research reference** from the packet, then add the source you want to study. Viral-only qualification requires 100,000 views and 10× a documented creator baseline. Open a new packet after adding evidence to see the updated next steps.

Core preparation needs no model key or paid account. Connected reads, video tools and campaign execution show their own prerequisites. The goal-specific **Check connections for this goal** control identifies the selected agent and account setup. Owner sign-in is required before inspecting private account readiness or granting authority.

## Let your agent take over

Open **Connect your agent** from the selected goal and follow the [CLI/MCP quickstart](agent-quickstart.md). Choose its app, supported operations, expiry and limits. Review the combined automation agreement before enabling supported autonomous work; local workflow permission and campaign authority remain separately enforced.

Use **Watch the work** for saved progress, **Monitor approved campaigns** for the exact protective monitor, and **Review private campaign outcomes** for saved results and PDF reports. **Advanced tools → Weekly review** brings actionable exceptions together. The receipt distinguishes prepared work, confirmed delivery and observed app results.

Want this work to continue on another computer? Choose the [optional owner-managed always-on path](always-on-runtime.md). It uses that host's own private workspace and account connections; installing the desktop app does not enable a service or move credentials.
