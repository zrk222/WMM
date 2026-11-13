# Start here: install WMM and make your first plan

Built for founders and marketing teams, WMM helps you promote and manage one
app or a portfolio. Keep a separate question, evidence and permissions for each
app, and hand approved work to your AI assistant. This guide is for the desktop preview.

**First time here?** If you want to help test setup without coaching, read the
[first-run trial guide](founder-trial.md) before trying the demo or following
the steps below. You can report a blocked install, too.

## What you need

- Windows 10/11, or Ubuntu 24.04 on a graphical desktop.
- A browser and, on Ubuntu, your normal unlocked keyring.
- No terminal, Python install or developer account for the preview.

## Install

1. Open the [desktop releases](https://github.com/zrk222/WMM/releases) and choose
   the newest published **Desktop Preview**. Under **Assets**, download
   **WMM-Setup.exe** (Windows) or **wize-marketing-machine_0.1.0_amd64.deb**
   (Ubuntu). Public downloads do not need a GitHub sign-in.
2. Install it the normal way for your system, then open **Wize Marketing
   Machine** from the Start menu or Applications.
3. You can close the browser tab. Approved scheduled work continues while WMM
   is running and your computer is awake. To stop the local worker, choose
   **Quit WMM** in the desktop window. To keep approved work running while your
   computer sleeps, see [run WMM on your own always-on host](always-on-runtime.md).

**Windows note:** The Windows installer for [Desktop Preview 10](https://github.com/zrk222/WMM/releases/tag/v0.1.0-preview.10) is unsigned. SmartScreen or your device policy may block it.
For a release advertised as signed, check that Windows reports a valid signature
and the publisher matches the release's verification instructions. A matching
checksum alone does not identify the publisher. Do not weaken OS security to
install. If your device policy blocks installation, ask IT or try the
[interactive sample](https://zrk222.github.io/WMM/demo.html), which uses synthetic
data and does not connect accounts.

## Your first 15 minutes

**Day 1 â€” a clearer next marketing move.** Choose one app-growth question and
prepare your first evidence packet: a plan, its sources and what is still missing.

You do not need an account, a paid model or a provider connection for these
steps.

1. **Add your app.** Give it a name, who it helps, what it helps them do, the
   first useful action, the version or build you tested, and the language/locale.
   Choose **Save and choose a goal**.
2. **Pick a goal.** Choose **Find a useful marketing angle**. In **Start here**
   above, choose **Open your first packet**.
3. **Read the packet.** It lists the research and creative steps for this app
   and the missing pieces you can add next.
4. **Keep your place.** Choose **Save packet in this workspace**. Reopen it
   under **Pick up where you left off** after restarting WMM. Once it is saved,
   **Report / Save PDF** opens a readable report. **Download goal packet** keeps
   a JSON copy if you need one. These steps do not publish or spend.
5. **Add one reference.** Choose **Add a research reference** and save a source
   you want to study. To qualify as viral, a source also needs 100,000 views and
   10Ã— a documented creator baseline. That is evidence, not a promise.

## Around Day 30, with regular use

**A record you can build on.** Return to your
question, add research, review creative, and inspect approved work and available
results. Keep dated decisions about what to continue, revise or stop.

This can help you repeat less research and focus your marketing effort.
Measurements depend on the sources you connect and the work you complete.
Missing measurements stay unknown. Growth and time savings are not guaranteed.

## Words you will see

- **Permission slip (also called a grant):** a time-limited list of actions you
  allow an AI assistant to take for one app. It has an expiry and a call limit.
  You can revoke it.
- **Packet:** saved work for one step, with its sources and what is still
  missing. A packet is not a published post or a measured result.
- **Connection:** a saved provider login or key that lets WMM read one kind of
  data. A saved login is not analytics permission and does not approve a post.
- **Prepare vs publish vs measure:** three separate things. WMM can prepare
  work, you approve a specific publish, and only a connected source can show
  what happened.

## Optional: let an AI assistant help

Any assistant that can run a local command on this computer can work with WMM.
WMM does not require a particular AI product or plan.

1. Choose a goal, then select **Connect your agent**. In **Delegate work.
   Review exact changes**, choose **Set up app owner** if this app is new, or
   **Sign in with GitHub** if it already has an owner. Setting up the first
   owner requires an explicit confirmation for this app.
2. Select **Review agent setup** for this installation.
3. Create a permission slip for only the actions you want, with an expiry and a
   call limit. Give the one-time token to the assistant through its own
   protected environment, never in a prompt, chat, file or screenshot.
4. Ask the assistant to inspect the app first and report what it found. Give it
   more permission later only if you choose to.

For technical setup details, see the [assistant setup guide](agent-quickstart.md).

## What WMM will not do on its own

- It will not publish, message anyone, change a provider account or spend money
  without a separate exact approval. Default ad spending is zero.
- It will not treat a saved login, a key or a prepared packet as verified
  delivery or a business result.
- It does not yet establish growth. Installs, retention and paid conversion are
  only reported when a connected source supplies them.
- It does not store provider credentials in exports or snapshots.

## Where your work lives

Your workspace is stored in your user application-data folder, outside the
installed program. Install a newer preview over this one; uninstalling removes
the program and keeps your workspace. Back it up before upgrading if it matters
to you.

## If something goes wrong

- **No installer listed:** open **Assets** on the preview page. Choose the
  installer for your system; the source archives are for developers.
- **Windows warns about the publisher:** check the release notes and [verification guide](VERIFY-RELEASE.md).
  Do not weaken OS security.
- **Ubuntu package tools missing:** use a graphical desktop with the normal
  Debian package installer, or wait for a later build.
- **Your workspace will not open:** keep a copy of the data folder and open an
  issue with the version, the error text and the steps you took. Never include
  tokens, keys or private customer data.

## Current limits

This is an automated-tested preview. A nontechnical first-use acceptance test,
a signed Windows publisher and measured growth remain separate evidence. The
macOS desktop credential adapter is unsupported. Native iPhone/iPad support is
separate from this desktop guide.

## Releasing a preview (maintainers)

The installer and publication steps moved to the
[release handoff guide](release-handoff.md).
