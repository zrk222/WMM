# Spec: http-comparison-benchmark
Status: approved

## MUST - Functional core
### Description
Measure the existing HTTP engine against a bounded thread-pool adapter with the same handler before making any framework decision.
### Requirements (EARS)
- The system shall return p50 and p95 round-trip latency in milliseconds and resident memory in bytes across 100 requests for each isolated adapter under `measurement`.
- The system shall reject comparison when identical route, authentication or CSRF checks differ between adapters under `parity`.
- The system shall store source hashes, runtime, request counts and actual results without switching the production server under `receipt`.
### Acceptance criteria (Gherkin)
```gherkin
Scenario: measurement
 Given isolated local baseline and candidate servers
 When `measurement` executes
 Then actual latency percentiles and process memory are recorded
Scenario: parity
 Given the same application handler and HTTP checks
 When `parity` executes
 Then differing outcomes prevent a successful comparison
Scenario: receipt
 Given measured local samples
 When `receipt` executes
 Then source and environment evidence accompany results without a framework-switch claim
```

## SHOULD - Technical
No production server edits. Candidate is a bounded thread pool reusing the exact handler, not a new web framework. The comparison does not establish framework parity or authorize a framework switch. Use small synthetic workspaces, ephemeral loopback ports and subprocesses; no dependencies or local package builds.
