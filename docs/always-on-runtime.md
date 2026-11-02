# Keep approved work running

Use Wize Marketing Machine on an always-on Windows or Ubuntu machine you control. Set up that machine with its own WMM runtime, workspace and protected connections. This optional process mode reuses the existing workers.

## Start deliberately

1. Open the packaged desktop app on the chosen machine and connect accounts through WMM. Approve the exact finite workflow or campaign scope there.
2. Quit the desktop controller. One workspace cannot run in the controller and headless process at once.
3. Start the packaged executable with `--headless`. For a source checkout, run `python -m mission_control.desktop --headless`.
4. The process prints `http://127.0.0.1:8765`. Open that address on the same machine to inspect saved stages, receipts and OFF controls.
5. Keep the process and host running. On a hosted desktop, use its secured desktop session. WMM opens no public listener or remote API.

A busy port or already-running workspace stops startup. Headless mode uses a fixed port and the same per-user application-data directory as the packaged desktop, outside its executable folder. It does not copy a repository database there.

## Connections stay private

Windows uses the current user native credential store. Ubuntu requires that user unlocked Secret Service and session bus. An unavailable protected store stops credential-dependent work. There is no plaintext fallback, secret export or automatic migration. Connect accounts separately on a new host.

Closing the browser leaves the process running. Scope expiries, quotas, exact content, account checks, retained commitments and OFF controls still apply. Keeping the host awake does not extend approval. Delivery is separate from app installs or sales.

## Stop and restart

Use Ctrl+C in an attached console or SIGTERM on Ubuntu for graceful shutdown. The desktop controller Quit button stops its own workers. An OS-forced kill may interrupt an external mutation; WMM retains its intent and requires reconciliation instead of automatic replay. The OS releases the workspace lock when the process exits.

This mode registers no startup task, OS service, cloud instance, reverse proxy or public tunnel. An owner who configures a startup manager must use the same user, protected store and exact data path. Changing a database path changes credential scope.

## Acceptance boundary

Local Windows checks exercise actual HTTP startup, process exclusion and abrupt-exit recovery, fixed-port rejection, same-user data, shutdown failure, locked-vault refusal and headless dispatch without a browser or graphical initialization. Linux termination and packaged binaries need matching CI. Remote hosting, unattended reboot with a usable native keyring, provider delivery and campaign results need separate target acceptance. Native iOS remains on-device; this mode adds no iOS background execution.
