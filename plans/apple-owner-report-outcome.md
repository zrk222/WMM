# Plan: apple-owner-report-outcome
Spec: specs/apple-owner-report-outcome.md
Architect verdict: PASS

## Logical decomposition (phases)
1. Use the existing owner report selection and receipt projection to attach exact saved Apple rows under the owned campaign scope.
2. Show an optional storefront field, human-readable row states and the retained count in the existing private report and PDF flow.
3. Bind the synthetic HTTP and browser logic acceptance to the source changes, keeping live E15 acceptance separate.

## Tasks (atomic — each independently shippable)
- [x] T1 | slice=mission_control | files=mission_control/campaign_owner_reports.py,mission_control/apple_owner_outcome.py,mission_control/campaign_report_delivery.py,tests/test_campaign_owner_reports_integration.py | verify=`python -B -m unittest tests.test_campaign_owner_reports_integration` | Bind the exact Apple source, verified delivery and unknown versus zero in the private owner report backend.
- [x] T2 | slice=mission_control/static | files=mission_control/static/campaign-owner-reports.mjs,tests/campaign_owner_report_ui.test.cjs | verify=`node --test tests/campaign_owner_report_ui.test.cjs` | Show storefront evidence and distinct states in the private owner report and print view.
- [x] T3 | slice=specs | files=specs/apple-native-measurement-plan.md | verify=`python -B -m unittest tests.test_apple_campaign_attribution tests.test_campaign_owner_reports` | Describe how the existing Apple file and private owner report views fit together.
- [x] T4 | slice=tools | files=tools/maintained_files.txt | verify=`python -B tools/source_ratchet.py --base b3cdd14a19ce070c49357e61fbd5341fc554ac39` | Enroll the new source modules in the existing format and types ratchets.
