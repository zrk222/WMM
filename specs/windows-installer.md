# Spec: windows-installer
Status: draft

## MUST - Functional core
### Description
Package the existing Windows desktop bundle as an optional per-user installer with no automatic startup or credential migration.

### Requirements (EARS)
- The system shall write program files under the current user local application directory without administrator privileges through `user_install`.
- When setup creates shortcuts, the system shall launch the existing windowless desktop controller through `shortcuts`.
- When setup is silent, the system shall reject automatic application launch through `silent_install`.
- When upgrade or uninstall runs, the system shall reject deletion of the user workspace and reject termination of active workers through `workspace_retention`.
- The system shall reject a missing local compiler before installer testing on an isolated Windows runner through `installer_test`.
- The system shall reject credential copying, provider requests and startup registration through `private_boundary`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: user_install
  Given an existing desktop bundle
  When `user_install` compiles the installer
  Then setup requires no administrator privilege and uses the user program directory
Scenario: shortcuts
  Given a completed interactive install
  When `shortcuts` creates the owner launcher
  Then the existing windowless controller is selected
Scenario: silent_install
  Given silent setup
  When `silent_install` completes
  Then no application is automatically opened
Scenario: workspace_retention
  Given a synthetic workspace outside the program folder
  When `workspace_retention` upgrades and uninstalls
  Then the workspace remains and setup does not terminate a worker
Scenario: installer_test
  Given an isolated Windows runner without the compiler
  When `installer_test` starts
  Then the test fails clearly without installing dependencies
Scenario: private_boundary
  Given a built program bundle
  When `private_boundary` inspects setup entries
  Then no credential migration, provider call or startup registration is declared
```

## SHOULD - Technical
- Installer changes do not prove Windows target acceptance until the runner executes them.
- User data remains separate from program files; ask the user to close the controller before upgrade.
- No live provider requests are part of verification.

## Authorized parameters
INSTALL_TIMEOUT_SECONDS = 180
SELF_TEST_TIMEOUT_SECONDS = 90
