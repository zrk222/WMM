# Spec: hypit-studio-installation
Status: draft

## MUST - Functional core
### Description
Implement the installation-identity prerequisite for the owned Studio broker in
specs/hypit-studio-controls.md. Bind executing Node, the real Hypit entrypoint,
reviewed Studio source and the contained installed package tree. This preflight
does not open Studio, render, acquire packages, access accounts or approve code.

### Requirements (EARS)
- The system shall return an installed Node and Hypit entrypoint identity using fixed local discovery arguments and reject unsupported layouts through `installation_discovery`.
- The system shall reject a missing or changed reviewed Studio source file and an unsupported distribution manifest through `reviewed_abi`.
- The system shall hash all regular installed package files and the executing Node bytes, reject links and reparse paths, and reject more than 10000 files, 128 MiB per file or 256 MiB total package bytes through `execution_fingerprint`.
- The system shall reject a changed tree, entrypoint, Node executable or manifest when an expected installation fingerprint is revalidated through `installation_staleness`.
- The system shall return fingerprint status with runtime execution marked NOT_RUN and omit local filesystem paths from its public summary through `evidence_boundary`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: installation_discovery
  Given a direct Node entrypoint, a supported npm layout or the installed Volta launcher
  When `installation_discovery` resolves the existing installation
  Then fixed read-only arguments locate the real files without executing Hypit or installing code
Scenario: reviewed_abi
  Given supported distribution bytes and reviewed Studio source
  When `reviewed_abi` encounters changed or missing source or the wrong manifest
  Then no fingerprint is accepted
Scenario: execution_fingerprint
  Given a contained installed package tree
  When `execution_fingerprint` encounters a linked path, changed file or exceeded bound
  Then the fingerprint fails without starting any runtime
Scenario: installation_staleness
  Given a recorded installation fingerprint
  When `installation_staleness` follows changed dependency bytes or membership
  Then the old fingerprint is rejected even when the command wrapper is unchanged
Scenario: evidence_boundary
  Given an actual installed fingerprint
  When `evidence_boundary` returns a public summary
  Then it exposes aggregate hashes and counts while runtime execution remains explicitly unverified
```

## SHOULD - Technical
The supported ABI is installed Hypit version0.3.1 with the six reviewed Studio
source files from upstream revision e26d9142fd8a6f78bf4f3cdb800d6205f4ecca16.
Use the existing restricted child environment for fixed Volta discovery. Reject
unknown installation layouts without silently installing or changing providers.
Use sorted relative filenames for the aggregate tree digest and verify membership
again after hashing. Check opened-file metadata before and after reading. This is
an integrity preflight under the trusted local-user boundary, not a kernel sandbox
or protection against a hostile administrator rewriting code during execution.
Revalidation is required before the future broker starts or admits runtime work.
The public summary has no executable capability or approval effect. Full Studio
session lifecycle and every parent control requirement remain mandatory.

## Authorized parameters
MAX_FILES = 10000
MAX_FILE_BYTES = 134217728
MAX_TREE_BYTES = 268435456
DISCOVERY_TIMEOUT = 15
CHUNK_BYTES = 1048576
