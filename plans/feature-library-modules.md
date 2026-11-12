# Plan: feature-library-modules
Spec: specs/feature-library-modules.md
Architect verdict: PASS

## Tasks
- [ ] T1 | slice=mission_control/static | files=mission_control/static/analytics-inventory.mjs,mission_control/static/campaign-plan.mjs,mission_control/static/mmp-import-model.mjs,mission_control/static/feature-apis.mjs | verify=`node tools/check_es_modules.mjs` | Convert pure libraries to explicit named exports and re-exports.
- [ ] T2 | slice=tests | files=tests/analytics_inventory.test.mjs,tests/campaign_plan.test.mjs,tests/mmp_import_model.test.mjs,tests/feature_library_types.test.mjs | verify=`node --test tests/*inventory*.mjs tests/campaign_plan.test.mjs tests/mmp_import_model.test.mjs tests/feature_library_types.test.mjs` | Preserve fixtures and reject global writes and wrong types.
- [ ] T3 | slice=mission_control | files=mission_control/server.py | verify=`python -m unittest tests.test_page_reporting_http -q` | Serve exact migrated module paths.
- [ ] T4 | slice=tools | files=tools/check_es_modules.mjs,tools/maintained_files.txt,tools/maintained_js.txt,tools/check_js_types.mjs | verify=`node tools/check_es_modules.mjs` | Enforce shrinking adapter budget and maintained checkJs.
- [ ] T5 | slice=package.json | files=package.json | verify=`npm ls typescript` | Pin test-only compiler.
- [ ] T6 | slice=package-lock.json | files=package-lock.json | verify=`npm ls typescript` | Retain lock integrity.
- [ ] T7 | slice=tsconfig.maintained-js.json | files=tsconfig.maintained-js.json | verify=`node tools/check_js_types.mjs` | Type-check three native libraries only.
- [ ] T8 | slice=.github | files=.github/workflows/checks.yml,tests/test_ci_current_candidate.py | verify=`python -m unittest tests.test_ci_current_candidate -q` | Run maintained library type check in CI.
- [ ] T9 | slice=tests | files=tests/test_page_reporting_http.py | verify=`python -m unittest tests.test_page_reporting_http -q` | Verify native library route MIME and obsolete or unknown route rejection.
