# Plan: goal-connection-wizard
Spec: specs/goal-connection-wizard.md
Architect verdict: PASS

## Execution contract

Modify the listed existing files; create or delete no product files. Use `social_registry.catalog()` as the shared source. Its public fields are `publishing_implemented`, `publication_kinds`, `publication_connection_provider` and `execution_authority`; expose no credential values or references. `Connections.view()` and `Setup.view()` derive `publication_providers` from that catalog.

Keep Facebook Page posts on the existing campaign route. Organic publication uses `instagram_reel` through a Facebook Page linked to the professional Instagram account, `tiktok_video` through TikTok, `youtube_short` through YouTube, and `linkedin_video` or `linkedin_text` through LinkedIn. Direct Instagram Login does not satisfy the Page-linked publication path; show `PUBLICATION_CONNECTION_REQUIRED`. Every selected account must be fresh. Missing, stale, expired or incompatible selections remain blocked with the fixed Connections repair action.

The campaign goal opens Connections. The readiness wizard offers organic publication unchecked by default; selecting it still requires exact owner publication review. Its repair opens Connections → Publish an approved post. Facebook campaign authority remains separate. Readiness creates no grant, approval, schedule or job.

YouTube setup uses the existing setup form and Google web-application OAuth path: enable YouTube Data API v3, register the displayed callback, review permissions, approve app-specific configuration, then use official login. The initial form selects `campaign_access=read` with `youtube.readonly`. Upload permission requires a separate publishing-permission review; account setup and a successful read never authorize publication. Preserve each other provider's existing official setup packet and read-first default.

## Tasks
- [ ] T1 | slice=mission_control/static | files=mission_control/static/guided-workflow.js,mission_control/static/app.js,mission_control/static/ui-stories.js | verify=`node --test tests/goal_readiness_ui.test.cjs tests/ui_stories.test.cjs` | Add read-only owner connection wizard using existing readiness route.
- [ ] T2 | slice=tests | files=tests/goal_readiness_ui.test.cjs,tests/ui_stories.test.cjs | verify=`node --test tests/goal_readiness_ui.test.cjs tests/ui_stories.test.cjs` | Verify exact selection, no execution authority, stale readback and fixed repair routes.
- [ ] T3 | slice=mission_control | files=mission_control/automation_requirements.py,mission_control/social_connections.py,mission_control/social_setup.py | verify=`python -m unittest tests.test_automation_requirements tests.test_social_connections tests.test_social_setup tests.test_complete_automation -v` | Project the shared channel catalog and compatible connection path; include YouTube's read-first setup packet while keeping exact owner publication approval and read-only readiness.
- [ ] T4 | slice=tests | files=tests/test_automation_requirements.py,tests/test_goal_readiness_http.py | verify=`python -m unittest tests.test_automation_requirements tests.test_goal_readiness_http -v` | Verify all supported channels, incompatible or stale accounts, no publication authority and secret-free owner readback.
- [ ] T5 | slice=tests | files=tests/goal_journey.test.cjs,tests/test_social_connections.py,tests/test_publication_browser.py,tests/test_ci_current_candidate.py | verify=`node --test tests/goal_journey.test.cjs` | Verify catalog projection and the goal route; run the provisioned browser checkpoint below for actual desktop/mobile interaction.
- [ ] T6 | slice=tools | files=tools/test_goal_journey_browser.py | verify=`python tools/test_goal_journey_browser.py` | Preserve the existing first-packet journey with channel-neutral empty-state wording.
- [ ] T7 | slice=.github/workflows | files=.github/workflows/checks.yml | verify=`python -m unittest tests.test_ci_current_candidate -v` | Execute the full goal-first packet journey in the provisioned cloud browser lane.
- [ ] T8 | slice=tests | files=tests/goal_packet.test.cjs,tests/test_social_setup.py | verify=`python -m unittest tests.test_social_setup -v` | Preserve exact packet routing and verify every provider setup packet remains read-first with no credential or effect grant.

## Dependency order and checkpoints

1. T1 → T2: preserve the existing owner wizard and stale-response checks. Checkpoint: `node --test tests/goal_readiness_ui.test.cjs tests/ui_stories.test.cjs` passes before adding channels.
2. T3 → T4 → T8: project the catalog and add the missing YouTube packet without changing approval enforcement. Checkpoint: `python -m unittest tests.test_automation_requirements tests.test_goal_readiness_http tests.test_social_connections tests.test_social_setup tests.test_complete_automation -v` and `node --test tests/goal_packet.test.cjs` pass.
3. T5 → T6 → T7: run the channel journey in the existing provisioned Ubuntu Chromium job. Set `WMM_BROWSER_TEST_PROFILE=1`; run `python -m unittest tests.test_publication_browser -v`, then `python tools/test_goal_journey_browser.py`. At 1440px and 390px, verify explicit organic selection, no default check, no new authority/job, the Connections repair, YouTube's read-only form, Escape dismissal, keyboard review and no horizontal overflow or JavaScript errors. Retain synthetic screenshots and logs. The `tests.test_ci_current_candidate` command checks the workflow configuration only; it does not replace executing these browser commands.
4. Final checkpoint: the current candidate passes the full Python/Node CI lanes and the hash-bound workflow audit. Keep live provider acceptance and first-time human setup acceptance separate from these synthetic browser checks.
