# Start here: install WMM and make your first plan

WMM helps you plan and check marketing for one app, then keep the receipts. You
can use it on your own or hand approved work to an AI assistant. This guide is
for the desktop preview.

## What you need

- Windows 10/11, or Ubuntu 24.04 on a graphical desktop.
- A browser and, on Ubuntu, your normal unlocked keyring.
- No terminal, Python install or developer account for the preview.

## Install

1. Open the [WMM releases](https://github.com/zrk222/WMM/releases) and download
   **WMM-Setup.exe** (Windows) or **wize-marketing-machine_0.1.0_amd64.deb**
   (Ubuntu). Public downloads do not need a GitHub sign-in.
2. Install it the normal way for your system, then open **Wize Marketing
   Machine** from the Start menu or Applications.
3. Keep the WMM window open while you work. Closing it stops its local engine
   and any approved scheduled work.

If no installer is listed, the desktop preview has not been published yet.

**Windows note:** the preview installer is not publisher-signed. Windows may
warn you. Do not disable OS security controls or install a root certificate to
get past it.

## Your first 15 minutes

You do not need an account, a paid model or a provider connection for these
steps.

1. **Add your app.** Give it a name, who it helps, what it helps them do, the
   first useful action, the version or build you tested, and the language/locale.
   Choose **Save and choose a goal**.
2. **Pick a goal.** Start with **Find a useful marketing angle**, then choose
   **Open your first packet**.
3. **Read the packet.** It lists the research and creative steps for this app
   and the missing pieces you can add next.
4. **Keep a copy.** Choose **Download goal packet**. This works before you
   connect anything, publish anything or spend anything.
5. **Add one reference.** Choose **Add a research reference** and save a source
   you want to study. To qualify as viral, a source also needs 100,000 views and
   10× a documented creator baseline. That is evidence, not a promise.

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

1. Sign in as the app owner under **Activity & reviews**.
2. Open **Connect your agent** and review the setup for this installation.
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

- **No installer:** the desktop preview has not been published.
- **Windows warns about the publisher:** expected for this preview; do not
  weaken OS security.
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
