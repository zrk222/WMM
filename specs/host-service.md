# Spec: host-service

## MUST - Functional core

### Requirements (EARS)

- When a user installs the Ubuntu package, the system shall store an inert per-user systemd unit. The owner must explicitly install and enable the delivered unit in the user service manager.
- When the owner starts the unit, the system shall run `/usr/lib/wize-marketing-machine/WMM --headless` with the existing fixed loopback listener, workspace lock, private file creation mask and the selected user's data path and vault. Startup shall carry no campaign authority and copy no credentials.
- If the service fails to start, the user service manager shall allow at most 3 starts in 300 seconds. A normal service stop uses SIGTERM.
- Where a job needs protected credentials, the system shall read the host user's unlocked Secret Service keyring and reject protected access while the keyring is locked. Operation after logout requires explicit user lingering and an available unlocked keyring.

### Acceptance criteria (Gherkin)

```gherkin
Scenario: isolated_ubuntu_service
 Given an installed package and a disposable opted-in Ubuntu CI user manager
 When the test starts a copy of the installed unit against synthetic data
 Then loopback bootstrap responds and the workspace lock rejects another runtime for the same workspace
 And a normal stop and restart preserve the workspace
 And cleanup leaves no test unit link or process
```

## SHOULD - Technical

The package test uses `/usr/share/wize-marketing-machine/wmm-worker.service`. Source contract tests, isolated package tests, owner-host operation and protected keyring tests provide different evidence.
Native iOS has its own execution lifecycle.
The package CI harness may create one unique locked, non-login user and its user manager only after root, GitHub CI and both explicit package and host isolation opt-ins are checked. It stops only the new user's manager, disables only that user's lingering, removes only the exact created account without recursive user deletion, and checks cleanup. The user's empty temporary home must be contained in RUNNER_TEMP; no existing account, runtime directory or manager may be reused.
