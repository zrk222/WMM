# Spec: linux-provider-signing

## MUST - Functional core
### Requirements (EARS)
- The system shall return Linux provider key inspection and ES256 signatures using cryptography library calls without Windows CNG, subprocess invocation or private key filesystem writes, identified by `linux_signer`.
- The system shall reject RSA keys, encrypted keys, public keys and curves other than P-256 including P-384 before signing, retain the existing 2000 characters private PEM limit and return a redacted error, identified by `linux_key_validation`.
- The system shall emit a 64 bytes P1363 signature verified against the exact original message with SHA-256 and reject messages exceeding 65536 bytes, identified by `linux_signature`.
- The system shall return actionable dependency guidance when the optional Linux cryptography backend is unavailable and preserve the existing Windows CNG route, identified by `linux_dependency`.
- The system shall store and read Linux Apple connection credentials through the native protected vault, rotate and disconnect them with existing app/database bindings and retain secret-free history, identified by `linux_connection`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: linux_signer
  Given a synthetic private P-256 key
  When `linux_signer` inspects and signs with process and filesystem helpers denied
  Then the key and signature operations succeed in process
Scenario: linux_key_validation
  Given encrypted public malformed RSA or P-384 keys
  When `linux_key_validation` inspects the supplied input
  Then each invalid key is rejected without disclosing its bytes
Scenario: linux_signature
  Given a message within 65536 bytes
  When `linux_signature` signs the exact message
  Then the 64 bytes signature verifies for that message and fails for changed bytes
Scenario: linux_dependency
  Given a missing optional library or an existing Windows runtime
  When `linux_dependency` selects the backend
  Then missing dependencies reject with guidance and Windows retains CNG
Scenario: linux_connection
  Given an isolated Ubuntu keyring and synthetic provider responses
  When `linux_connection` saves rotates reads and disconnects credentials
  Then app/database scope and secret-free history remain enforced
```

## WON'T - Out of scope
No live Apple API request, publication, deployment, signing-key migration, iOS support or full Linux acceptance is established by this packet. Windows CNG remains the existing backend. Optional cryptography loads only for the declared Linux route; no automatic installation or plaintext fallback is added.
