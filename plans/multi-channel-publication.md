# Plan: multi-channel-publication
Spec: specs/multi-channel-publication.md
Architect verdict: PASS

## Logical decomposition (phases)
1. Enable explicit provider publish consent and the missing YouTube connection.
2. Implement transfer, finalize and observation adapters behind one closed publication contract.
3. Bind exact owner approvals to durable intents using existing authority, jobs and scheduling.
4. Connect UI, agent operations, reports and manifests to the same service.
5. Verify denials, lost-response recovery, scope isolation and actual provider status interpretation.

## Tasks (atomic — each independently shippable)
- [ ] T1 | slice=mission_control | files=mission_control/social_registry.py,mission_control/social_contract.py,mission_control/social_auth.py | verify=`python -m unittest tests.test_social_contract tests.test_social_boundaries -v` | Add provider scopes with read defaults and ads restricted to Facebook.
- [ ] T2 | slice=mission_control | files=mission_control/social_youtube.py,mission_control/social_tokens.py,mission_control/social_profiles.py,mission_control/social_transport.py | verify=`python -m unittest tests.test_social_providers tests.test_social_transport -v` | Add Google token flow and verified YouTube channel identity.
- [ ] T3 | slice=tests | files=tests/test_social_multichannel.py,tests/test_social_youtube.py | verify=`python -m unittest tests.test_social_multichannel tests.test_social_youtube -v` | Verify exact scopes, consent URLs, expiry, partial grants, channel selection and Facebook regressions.
- [ ] T4 | slice=mission_control | files=mission_control/publication_contract.py,mission_control/publication_transport.py,mission_control/publication_meta.py,mission_control/publication_linkedin.py | verify=`python -m unittest tests.test_publication_contract tests.test_publication_meta_linkedin -v` | Define organic payloads and Instagram/LinkedIn protocols.
- [ ] T5 | slice=mission_control | files=mission_control/publication_youtube.py,mission_control/publication_tiktok.py | verify=`python -m unittest tests.test_publication_youtube tests.test_publication_tiktok -v` | Implement resumable YouTube transfer and TikTok creator consent, transfer and status.
- [ ] T6 | slice=mission_control | files=mission_control/publication_authority.py,mission_control/publication_execution.py,mission_control/publication_schedule.py,mission_control/publication_reports.py | verify=`python -m unittest tests.test_publication_execution tests.test_publication_schedule -v` | Bind authority to durable intents and reuse the queue lifecycle.
- [ ] T7 | slice=mission_control | files=mission_control/publication_http.py,mission_control/worker.py,mission_control/operation_catalog.py,mission_control/agent_dispatch.py | verify=`python -m unittest tests.test_publication_http tests.test_publication_agents -v` | Wire owner and agent operations through one service and existing worker.
- [ ] T8 | slice=mission_control/static | files=mission_control/static/social-access.js,mission_control/static/publication.js,mission_control/static/app.js,mission_control/static/index.html | verify=`node --test tests/publication_ui.test.cjs` | Add channel setup, reviewed publishing, progress and recovery.
- [ ] T9 | slice=tests | files=tests/test_publication_contract.py,tests/test_publication_execution.py,tests/test_publication_schedule.py,tests/test_publication_agents.py | verify=`python -m unittest tests.test_publication_contract tests.test_publication_execution tests.test_publication_schedule tests.test_publication_agents -v` | Verify changed media/destinations, concurrent requests, unknown effects, restart and OFF.

- [ ] T10 | slice=mission_control | files=mission_control/publication_artifacts.py,mission_control/publication_sessions.py,mission_control/publication_credentials.py,mission_control/publication_instagram_connection.py | verify=`python -m unittest tests.test_publication_artifacts tests.test_publication_sessions tests.test_publication_credentials tests.test_publication_instagram_connection` | Bind current media/rights and protect upload capabilities using native vault chunks.
- [ ] T11 | slice=callback_relay | files=callback_relay/worker.mjs | verify=`node --test tests/callback_relay.test.mjs` | Accept documented Google callback metadata and strip it from the fixed private handoff.
- [ ] T12 | slice=tests | files=tests/test_publication_server.py,tests/test_publication_browser.py | verify=`python -m unittest tests.test_publication_server tests.test_publication_browser` | Exercise real owner HTTP and keyboard-accessible desktop/mobile approval, queue and revoke.
- [ ] T13 | slice=mission_control | files=mission_control/publication_service.py,mission_control/publication_reports.py | verify=`python -m unittest tests.test_publication_http tests.test_publication_reports tests.test_publication_metrics` | Project queue and provider phases separately and export dated scoped observations with no attribution claims.

- [ ] T14 | slice=.github/workflows | files=.github/workflows/checks.yml | verify=`python -m unittest tests.test_publication_server` | Run the new desktop/mobile browser journey in the provisioned cloud browser lane.
- [ ] T15 | slice=tests | files=tests/test_publication_reports.py,tests/test_publication_metrics.py | verify=`python -m unittest tests.test_publication_reports tests.test_publication_metrics` | Verify the full receipt chain and truthful observed counts and unavailable metrics.
- [ ] T16 | slice=tests | files=tests/callback_relay.test.mjs | verify=`node --test tests/callback_relay.test.mjs` | Verify Google metadata is stripped and invalid callbacks are denied.
- [ ] T17 | slice=mission_control | files=mission_control/automation_requirements.py,mission_control/marketing_agent_manifest.py,mission_control/operation_runtime.py | verify=`python -m unittest tests.test_publication_agents tests.test_operation_catalog` | Expose bounded agent preparation, read and approved enqueue through existing dispatch and manifests.
- [ ] T18 | slice=docs | files=docs/agent-multichannel.md,docs/reportsanalytics/organic-observations.md | verify=`python tools/check_distribution.py` | Document the approved workflow, observed metrics and live-account evidence boundaries.
- [ ] T19 | slice=mission_control/static | files=mission_control/static/ui-stories.js | verify=`node --test tests/ui_stories.test.cjs` | Explain the new owner forms in plain language.

## Authority and evidence
The owner explicitly added Instagram, TikTok, YouTube Shorts and LinkedIn execution to the remaining goal on November 6. Connection scaffolds and preview logos do not complete this requirement. Publication requires exact current consent; no ad-spending authority is added. Provider eligibility and delivery are verified separately from tested adapters. The attributable WizeMe experiment remains a parallel priority.
