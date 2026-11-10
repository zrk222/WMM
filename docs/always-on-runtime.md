# Keep approved work running on your own host

The default is simple: leave WMM running on your computer. Choose a separate always-on host when you want approved jobs to continue while your everyday computer is asleep. This is an optional owner-managed installation using the same WMM engine and worker.

## Choose where the work lives

| Choice | What keeps running | What you set up |
| --- | --- | --- |
| This computer | The desktop controller and its existing worker, while the computer is awake. | Open the installed app. Closing its browser is fine; quitting WMM stops the worker. |
| Your Windows host | The same packaged runtime in explicit `--headless` mode, while that Windows user session and computer stay available. | Install WMM and configure that user's own protected connections. Start the process below or use the host's secured desktop session. No Windows startup task is registered. |
| Your Ubuntu host | The same packaged runtime in explicit `--headless` mode, optionally managed by your user service manager. | Install the Ubuntu package, configure your own host account and protected keyring, then explicitly enable the service below. |

The host needs supported network access, an awake operating system and current account credentials. Windows uses that user's Credential Manager. Linux Secret Service must be available and unlocked for credential-dependent work. A process starting at boot does not unlock that keyring. Automatic account renewal uses only the provider permissions already granted; interactive sign-in still needs you.

Set up the host as a new private WMM workspace. Connect your own accounts there and approve its exact scopes. Do not copy credential files, protected-store contents, bearer grants or operational databases from another machine. Noncredential workspace imports do not transfer execution authority.

## Start explicitly

For the default per-user Windows installation, open PowerShell on the host:

```powershell
& "$env:LOCALAPPDATA\Programs\Wize Marketing Machine\WMM.exe" --check
& "$env:LOCALAPPDATA\Programs\Wize Marketing Machine\WMM.exe" --headless
```

Use the selected installation folder if you changed it. For a source checkout, the same mode is `python -m mission_control.desktop --headless`.

The installed Ubuntu executable supports:

```sh
/usr/lib/wize-marketing-machine/WMM --check
/usr/lib/wize-marketing-machine/WMM --headless
```

`--check` reports the selected data path without starting work. `--headless` starts the existing server and workers on **127.0.0.1:8765**, with no browser or graphical controller. Keep it in the foreground for this first check; Ctrl+C requests shutdown. A second desktop or headless process using that workspace is rejected. An occupied port fails startup instead of silently selecting another host endpoint.

Open the workspace on the host and complete owner setup, account connections and exact approvals. Verify one supported job and inspect its receipt before relying on a schedule. New generated creative is not automatically approved for publication.

## Optional Ubuntu user service

The package includes an inert service template. Installation does not register, enable or start it. After closing the foreground WMM process, explicitly install it for the same user:

```sh
mkdir -p ~/.config/systemd/user
install -m 600 /usr/share/wize-marketing-machine/wmm-worker.service ~/.config/systemd/user/wmm-worker.service
systemctl --user daemon-reload
systemctl --user enable --now wmm-worker.service
systemctl --user status wmm-worker.service
```

The service uses the same user's application data and vault, requests private file permissions, and permits at most three startup attempts in five minutes. A normal stop does not restart it. After fixing a startup problem, use `systemctl --user reset-failed wmm-worker.service` and `systemctl --user start wmm-worker.service`.

Its [systemd `exec` service type](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html#Type=) reports an error when the executable cannot start. WMM's own bootstrap and job receipts establish whether the application is ready and work actually ran.

User-service availability after logout depends on your host's session configuration. This setup does not enable lingering, automatic login or keyring unlocking. Keep an authenticated host session available, or have your administrator configure its lifecycle deliberately. Do not place keyring passwords or provider keys in the service file.

To stop and disable this WMM service:

```sh
systemctl --user disable --now wmm-worker.service
```

Stopping WMM does not stop an ad already running at Meta. Use the campaign's protective pause controls and verify the saved provider readback first. Keep uncertain delivery receipts and retained budget commitments for reconciliation.

Ctrl+C requests shutdown for an attached headless process; Ubuntu also supports SIGTERM. A forced process exit can interrupt an external mutation. Its durable intent remains for reconciliation, and an uncertain mutation is not automatically replayed when WMM restarts.

## Reach your private host

WMM remains bound to loopback. For an existing SSH-enabled host you control, an authenticated [OpenSSH local tunnel](https://man.openbsd.org/ssh.1#L) can preserve WMM's exact origin:

```sh
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:8765:127.0.0.1:8765 account@your-host
```

Close local WMM first so that port is available, verify your host's SSH identity, then open **http://127.0.0.1:8765/**. The workspace now belongs to the host. Closing the tunnel leaves its worker running. Do not expose WMM's port publicly or place the workstation server behind a public reverse proxy.

An agent needs its own verified local or SSH execution path and a grant issued for that host. Follow the [agent quickstart](agent-quickstart.md); the manifest supplies operating instructions, not remote connectivity or account permission. An iPhone or iPad does not become an always-on background worker through this setup; its [native app](../ios/) retains its independent execution and lifecycle limits.

## Check the result

An active service proves a running process. In **Watch the work**, the live status identifies desktop, headless or server mode and shows the last healthy poll. Headless mode describes how WMM started; it does not verify that the host can stay awake or that the protected credential store is unlocked. In WMM, inspect worker health, the selected account's connection status, the exact agreement and the last job receipt. Saved progress, confirmed provider delivery and measured app outcomes remain separate. The [package workflow](https://github.com/zrk222/WMM/actions/workflows/desktop-packages.yml) retains native setup evidence; isolated CI fixtures do not prove your own host, provider account or marketing outcome.
