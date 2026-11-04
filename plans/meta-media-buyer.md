# Plan: meta-media-buyer

Architect verdict: PASS

Additive read-only contract over the existing app/grant gateway. The compact
index is general; full guidance loads on demand. Selector validation is closed
and consistent in local GET and scoped RPC. Existing campaign gates enforce all
effects; public research is captured offline and never fetched during policy reads.

- [x] T1 | slice=mission_control | files=mission_control/meta_media_buyer.py,tests/test_meta_media_buyer.py | verify=`python -m unittest tests.test_meta_media_buyer -v` | Implement deterministic app-bound specialist rules, actual catalog capability references, research provenance, decisions and owner-report contract.
- [x] T2 | slice=mission_control | files=mission_control/marketing_agent_manifest.py,mission_control/agent_operations.py,tests/test_meta_media_buyer.py | verify=`python -m unittest tests.test_meta_media_buyer -v` | Add compact specialist discovery and exact on-demand profile loading without general authority changes.
- [x] T3 | slice=mission_control | files=mission_control/operation_catalog.py,mission_control/operation_runtime.py,mission_control/server.py | verify=`python -m unittest tests.test_meta_media_buyer_clients -v` | Validate and route the optional exact profile selector through existing read-only local and scoped paths.
- [x] T4 | slice=mission_control | files=tests/test_meta_media_buyer_clients.py,mission_control/operation_catalog.py | verify=`python -m unittest tests.test_meta_media_buyer_clients -v` | Prove current host-independent HTTP, actual CLI and official MCP profile reads and reject malformed or wrong-app authority.
- [x] T5 | slice=docs | files=docs/agents/meta-media-buyer.md,docs/research/meta-media-buying-patterns.md | verify=`python -m unittest tests.test_meta_media_buyer -v` | Document operation-mapped media-buying practice and dated public REA findings with source availability and vendor-claim limits.
