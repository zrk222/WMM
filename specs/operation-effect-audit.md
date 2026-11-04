# Spec: operation-effect-audit
Status: draft

## MUST — Functional core
### Description
Provide an offline static CI tripwire comparing catalog labels with reachable provider transport calls. This is a heuristic, not a proof of absence of external effects.

### Requirements (EARS)
- The system shall return an audit result for every descriptor in OPERATIONS without importing application modules or reading private records.
- The system shall return handler roots from the execute AST and the actual iOS adapter, including finite dictionary and prefix dispatch.
- The system shall reject unresolved handler roots, parse failures and provider transport paths under local-only labels.
- The system shall emit operation, declared effect, source paths and unresolved dynamic edges.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: Local label reaches a provider
  Given a synthetic local-only handler calling a provider transport
  When the static audit runs
  Then it exits nonzero with the handler-to-sink path
Scenario: Missing handler
  Given a catalog operation with no dispatcher route
  When the audit runs
  Then it fails closed
Scenario: Complete inventory
  Given the current catalog
  When the audit runs
  Then every descriptor has an audit result
```

## SHOULD — Technical
- Use only Python standard library and synthetic fixture tests.
- Preserve labels and runtime authority; never suppress findings to manufacture a pass.

## WONT — Scope
- No runtime execution, network, private records, label repair, security certification or release authority.
- Dynamic callbacks, runtime monkeypatching and injected receiver types cannot be proven by this analysis.
