# Plan: creative-taste-guidance
Spec: specs/creative-taste-guidance.md
Architect verdict: PASS

## Architecture
Static product-readable policy, adapted from the reviewed Prestige five laws
and purpose lenses. Reference existing approved public app_manifest preferences;
do not read personal skills, files or provider credentials at runtime. Bind as
creative_taste in the existing context and strict citation registry. Existing
proposal and worker source-hash guards deliver and revalidate the policy.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/creative_taste.py | verify=`python -m unittest tests.test_creative_taste -q` | Implement video_taste, taste_provenance, taste_review and taste_authority.
- [ ] T2 | slice=mission_control | files=mission_control/agent_context.py,mission_control/agent_registry.py,mission_control/agent_contract.py | verify=`python -m unittest tests.test_creative_taste tests.test_agent_context tests.test_agent_context_tasks -q` | Deliver taste_delivery through the actual approved prompt source path and reject duplicate citations.
- [ ] T3 | slice=tests | files=tests/test_creative_taste.py,tests/test_agent_context.py | verify=`python -m unittest tests.test_creative_taste tests.test_agent_context tests.test_agent_context_tasks -q` | Prove exact citations, source hashes, no private data, context limits and stale-guidance rejection.

## Gates
CF strict, validator mutations, atomic tasks, source drift, focused real proposal/
synthetic-provider worker tests and hash-bound workflow evidence. Full executing
video-agent acceptance remains REQUIRED_NOT_COMPLETE as specified above.
