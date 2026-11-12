# Plan: measurement-completeness
Spec: specs/measurement-completeness.md
Architect verdict: PASS

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/measurement_economics.py,mission_control/ledger.py | verify=`python -m unittest tests.test_measurement_economics -q` | Add explicit optional cohort economics scope and derive install-relative CAC and ROAS with exact unavailable reasons.
- [ ] T2 | slice=tests | files=tests/test_measurement_economics.py | verify=`python -m unittest tests.test_measurement_economics tests.test_ledger -q` | Verify currency, source, late refunds, missing versus zero and D7/D30 boundaries.
- [ ] T3 | slice=mission_control/static | files=mission_control/static/app-results.mjs,mission_control/static/app-events.mjs,mission_control/static/page-reporting.js | verify=`python tools/test_page_reporting_browser.py` | Show economic denominators and all assessment outcomes with existing report/export controls.
- [ ] T4 | slice=docs | files=docs/WMM-KPI-COVERAGE.md,docs/MEASUREMENT-DATA-CONTRACT.md,docs/MECHANICS-PROGRAM.md | verify=`python -m unittest tests.test_measurement_economics -q` | Record data gap closure requirements and supplied versus verified evidence limits.
- [ ] T5 | slice=tools | files=tools/maintained_files.txt,tools/maintained_js.txt | verify=`python tools/source_ratchet.py --base codex/wmm-danger-zone-types` | Enroll all changed measurement source in ratchets.
- [ ] T6 | slice=tests | files=tests/measurement_results_ui.test.cjs,tests/page_reporting.test.cjs | verify=`node --test tests/measurement_results_ui.test.cjs tests/page_reporting.test.cjs` | Verify scoped economics and complete failed experiment report projections.
- [ ] T7 | slice=specs | files=specs/kpi-report-coverage.json | verify=`python -m unittest tests.test_kpi_data_gaps -q` | Add concrete repair inputs and closure evidence for every registered metric.
- [ ] T8 | slice=tests | files=tests/test_kpi_data_gaps.py | verify=`python -m unittest tests.test_kpi_data_gaps -q` | Reject missing coverage requirements and invented completed status.
- [ ] T9 | slice=tools | files=tools/test_page_reporting_browser.py | verify=`python tools/test_page_reporting_browser.py` | Exercise actual Results economics and unsuccessful assessment PDF rendering at desktop and mobile widths.
- [ ] T10 | slice=docs | files=docs/requirements-report-types.txt | verify=`python tools/check_types.py` | Pin optional report packages for static CI analysis without browser binaries.
- [ ] T11 | slice=.github | files=.github/workflows/checks.yml | verify=`python tools/check_types.py` | Provision declared report imports in the maintained type job.
- [ ] T12 | slice=tests | files=tests/test_ci_current_candidate.py | verify=`python -m unittest tests.test_ci_current_candidate -q` | Pin the reviewed static-only dependency step and retain existing job matrices.
