# Security and privacy

Run WMM only on a trusted local workstation. Use separate app workspaces and
dedicated least-privilege provider credentials. Keep operational data, exports,
uploaded files and secrets out of Git. Local snapshots can contain sensitive
evidence and should be handled as private data.

Do not report credentials, customer content or exploit details in public issues.
Use GitHub's private vulnerability reporting if enabled by the repository owner.
Otherwise contact the owner privately before sharing sensitive findings.

Protected connection storage currently requires Windows Credential Manager.
No plaintext fallback is provided. Optional CLI process controls are application
boundaries, not an operating-system sandbox. Review every requested native
operation and external change before approving it.
