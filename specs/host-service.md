# Owner-managed Linux host service

The owner may explicitly install and enable a per-user systemd unit for the installed WMM binary. The unit uses the same user, data path and native vault as the existing headless process; it does not copy credentials or grant campaign authority. A logged-in user session with an unlocked Secret Service keyring is required for protected credentials. Background operation after logout requires separately configured user lingering and a usable unlocked keyring. iOS background operation is not implied.

The service starts `/usr/lib/wize-marketing-machine/WMM --headless`, inheriting the existing fixed loopback-only listener and workspace lock. SIGTERM requests normal shutdown. Files created by the service use a private umask. Failed starts have a finite restart limit. No install, activation or enablement occurs automatically.

Acceptance: an isolated disposable Ubuntu CI user manager starts a uniquely named copy of the installed inert `/usr/share/wize-marketing-machine/wmm-worker.service` using synthetic data; the installed binary answers loopback bootstrap, rejects another runtime for the same workspace, stops cleanly, restarts, and leaves no test unit link or process. This is distinct from a source contract test and from owner-host or real-keyring acceptance.

The package CI harness may create one unique locked, non-login user and its user manager only after root, GitHub CI and both explicit package and host isolation opt-ins are checked. It stops only the new user's manager, disables only that user's lingering, removes only the exact created account without recursive user deletion, and checks cleanup. The user's empty temporary home must be contained in RUNNER_TEMP; no existing account, runtime directory or manager may be reused.
