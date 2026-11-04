# Plan: market-research-depth
Spec: specs/market-research-depth.md (approved)
Architect verdict: PASS

## Logical decomposition (phases)
1. Implement strict snapshot validation and deterministic advisory projection.
2. Integrate a new immutable GrowthReviews input/readout kind.
3. Verify validator, scope, replay, drift, and no-network behavior using isolated fixtures.

## Tasks (atomic — each independently shippable)
- [x] T1 | slice=mission_control | files=mission_control/market_research.py | verify=`python -m unittest tests.test_market_research -v` | Implement the bounded closed-schema validator and deterministic snapshot projection.
- [x] T2 | slice=mission_control | files=mission_control/growth_review_contract.py | verify=`python -m unittest tests.test_market_research -v` | Add exact app release/locale binding, immutable entry input and current readout integration.
- [x] T3 | slice=tests | files=tests/test_market_research.py | verify=`python -m unittest tests.test_market_research -v` | Prove validation, app scope, provenance, state, immutable replay, drift, tampering, and no-network behavior.
- [x] T4 | slice=specs | files=specs/market-research-depth.md | verify=`specline validate market-research-depth` | Preserve finite input limits, scope, provenance and advisory-only behavior.
