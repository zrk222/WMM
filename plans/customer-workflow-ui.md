# Plan: customer-workflow-ui
Spec: specs/customer-workflow-ui.md
Architect verdict: PASS

## Architecture
Add an isolated UMD module. Read the unified review's app-owned customer history, use typed repeatable rows with stable identities, and submit through the existing customer-workflows API. Reuse public field/report helpers and inject the app services. Keep all existing Results controls. Drafts remain inside the open form and never enter report models.

## Tasks
- [x] T1 | slice=mission_control | files=mission_control/static/customer-workflow.js,tests/customer_workflow.test.cjs | verify=`node --test tests/customer_workflow.test.cjs` | Implement customer_authoring, source_linkage, draft_recovery, immutable_revision, truthful_readout and customer_reports.
- [x] T2 | slice=mission_control | files=mission_control/static/app.js,mission_control/static/index.html,mission_control/server.py,tests/test_customer_workflow_ui_http.py | verify=`python -m unittest tests.test_customer_workflow_ui_http -v` | Integrate module, static boundary, authoring dispatch and current app context without dropping existing flows.
- [x] T3 | slice=tools | files=tools/test_customer_workflow_ui_browser.py | verify=`python tools/test_customer_workflow_ui_browser.py` | Implement customer_ui_proof using isolated desktop/mobile actual server/UI, immutable revision/readback, failure recovery and source-linked PDF acceptance.
- [x] T4 | slice=tests | files=tests/test_growth_review_ui_http.py | verify=`python -m unittest tests.test_growth_review_ui_http -v` | Update the earlier static wiring assertion for the additional panel while retaining checks for both existing growth and measurement panels.

## Acceptance
Use scoped Forge/SpecLine checks, direct behavior mutations, deterministic Prestige audits and hash-bound workflow evidence. Static-wrapper QA is not function coverage; include exact compiler inventory. Preserve unrelated setup-feedback and Google Play work. No full-product completion or production authority is implied by scoped passes.
