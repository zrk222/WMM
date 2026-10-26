# Spec: linux-protected-vault
Status: implementation; full platform workflow acceptance remains required

## MUST - Functional core
### Requirements (EARS)
- The system shall return the existing Windows credential backend on Windows and an explicit Secret Service backend on Linux, rejecting unsupported systems and unavailable optional dependencies without a plaintext or automatic backend fallback, identified by `linux_vault_selection`.
- The system shall store values up to 2560 bytes using exact hashed WMM credential addresses and verify item attributes before read or deletion, rejecting duplicate matching items or malformed values without exposing secrets, identified by `linux_vault_scope`.
- The system shall reject locked collections or items without automatic unlocking or collection creation, preserve existing secrets when operations fail and redact native errors from user messages, identified by `linux_vault_lock`.
- The system shall return native values through a fresh closed D-Bus connection per operation with 15 seconds bounded message replies after library D-Bus initialization and encrypted Secret Service sessions, preserving case-sensitive Linux database namespace identity and existing Windows namespace bytes, identified by `linux_vault_lifecycle`.
- The system shall emit actual isolated Linux keyring put/get/delete and cleanup evidence plus Windows regressions and synthetic lock corruption duplicate-item and unavailable-service checks before claiming this credential adapter verified, identified by `linux_vault_proof`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: linux_vault_selection
  Given an isolated protected credential address
  When `linux_vault_selection` exercises the platform backend
  Then exact scoped native storage or explicit rejection is observed
Scenario: linux_vault_scope
  Given an isolated protected credential address
  When `linux_vault_scope` exercises the platform backend
  Then exact scoped native storage or explicit rejection is observed
Scenario: linux_vault_lock
  Given an isolated protected credential address
  When `linux_vault_lock` exercises the platform backend
  Then exact scoped native storage or explicit rejection is observed
Scenario: linux_vault_lifecycle
  Given an isolated protected credential address
  When `linux_vault_lifecycle` exercises the platform backend
  Then exact scoped native storage or explicit rejection is observed
Scenario: linux_vault_proof
  Given an isolated protected credential address
  When `linux_vault_proof` exercises the platform backend
  Then exact scoped native storage or explicit rejection is observed
```

## WON'T - Out of scope
No plaintext keyring, automatic dependency installation, credential migration, native agent parity or iOS execution is supplied by this backend packet. No real provider credentials are used in tests.
