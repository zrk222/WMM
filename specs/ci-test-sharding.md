# Spec: ci-test-sharding
Status: draft

## MUST - Complete deterministic CI inventory
### Requirements (EARS)
- The system shall assign every discovered TestCase occurrence including duplicate IDs skips and import failures through `complete_inventory`.
- The system shall assign module groups to 4 workers using deterministic greedy test-count balancing and preserve within-group order through `balanced_assignment`.
- The system shall reject invalid shard bounds empty discovery and empty selected shards through `invalid_shards`.
- The system shall emit total count full ordered ID inventory hash selected count and verbose test outcomes with nonzero failure status through `visible_execution`.
- The system shall return planning metadata without claiming tests passed when plan-only is selected through `planning_only`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: complete_inventory
  Given nested discovery with duplicate IDs skipped tests and import failures
  When `complete_inventory` assigns occurrences
  Then the assigned ID multiset and occurrence identities equal discovery exactly
Scenario: balanced_assignment
  Given stable discovered module groups
  When `balanced_assignment` creates 4 shards
  Then all assignments are deterministic and each module retains discovery order
Scenario: invalid_shards
  Given invalid count index or empty inventory
  When `invalid_shards` validates a selection
  Then the command exits nonzero instead of reporting a green empty run
Scenario: visible_execution
  Given passing failing and erroring miniature suites
  When `visible_execution` runs the selected shard
  Then verbose outcomes and inventory metadata appear and failures or errors return nonzero
Scenario: planning_only
  Given a discovered suite with an execution marker
  When `planning_only` is requested
  Then inventory metadata appears without running the marker or claiming a pass
```

## Authorized parameters
Default shards = 4. Counts must be positive and index must satisfy
0 <= index < shards. Grouping uses defining module to preserve its fixture order.
Discovery keeps unittest discover -s tests -p test_*.py import semantics;
standalone script execution adds repository root without excluding tests.
Miniature CLI fixture subprocess bound is 15 seconds.
timeout = 15
