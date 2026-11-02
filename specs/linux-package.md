# Spec: linux-package
Status: draft

## MUST - Functional core
### Description
Package the existing Linux desktop runtime as an owner-installed Debian package with no startup or credential migration.

### Requirements (EARS)
- The system shall write only the bundled runtime, fixed launcher and desktop entry through `package_layout`.
- The system shall store required desktop and video runtime dependencies through `dependencies`.
- The system shall reject maintainer scripts, automatic startup and credential migration through `private_boundary`.
- When the isolated Ubuntu runner tests the package, the system shall install, upgrade and remove only the exact WMM package through `package_test`.
- When removal completes, the system shall return the unchanged synthetic XDG workspace marker through `workspace_retention`.
- The system shall reject package lifecycle testing outside the explicitly enabled isolated runner through `isolated_test`.

- The system shall return a Debian 2.0 archive with debian-binary, control.tar.gz and data.tar.gz in order using standard-library packaging without executing subprocesses through `archive_format`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: package_layout
  Given a frozen desktop bundle
  When `package_layout` creates a package
  Then the runtime and fixed desktop launcher are present
Scenario: dependencies
  Given a clean Ubuntu host
  When `dependencies` are inspected
  Then desktop, keyring and video dependencies are declared
Scenario: private_boundary
  Given package metadata
  When `private_boundary` checks its files
  Then startup registration and maintainer scripts are absent
Scenario: package_test
  Given an isolated Ubuntu runner
  When `package_test` runs the exact package
  Then installation, upgrade and removal are checked
Scenario: workspace_retention
  Given a synthetic XDG workspace
  When `workspace_retention` checks removal
  Then its marker remains unchanged
Scenario: isolated_test
  Given an unapproved local machine
  When `isolated_test` starts
  Then no package operation is run
Scenario: archive_format
 Given a fixed reviewed program staging tree
 When `archive_format` writes a Debian archive
 Then native dpkg inspection can read the exact format and staged paths
```

## SHOULD - Technical
- Existing Secret Service remains separately unlocked by the owner.
- No local package install, provider access or target acceptance occurs during source preparation.

## Authorized parameters
TIMEOUT_SECONDS = 180

WMM_LINUX_PACKAGE_TEST = 1
WMM_ISOLATED_NATIVE_KEYRING = 1
