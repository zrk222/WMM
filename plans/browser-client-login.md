# Plan: browser-client-login
Spec: specs/browser-client-login.md
Architect verdict: PASS for implementation with mandatory C1-C6 conditions in .factory/browser-client-login/architecture-review.md (SHA256 07664ddf6e85e8dad478c92e5dd4623e5af8a70919aae7d1c3f895c5c06343f5)

## Architecture
Reuse Control/Registry/ReadServer/Service for all read scope. Add fixedproviderOIDCtransportandmaintainedRS256validation; RAM-only one-usebrowserflows; finitecookieUIhandlerandstaticdashboard. No publicingress/domainauthority.

## Tasks
- [ ] T1 | slice=mission_control | files=mission_control/hosted_oidc.py,mission_control/hosted_login_flow.py | verify=`python -m unittest tests.test_hosted_oidc tests.test_hosted_login_flow` | Add bounded configuredprovidertransport, realsignatureverification and one-usebrowserboundOAuthstate.
- [ ] T2 | slice=tests | files=tests/test_hosted_oidc.py,tests/test_hosted_login_flow.py | verify=`python -m unittest tests.test_hosted_oidc tests.test_hosted_login_flow` | Prove actualRSA/tokenclaimsnegativecases, PKCE/replay/browserexpiryandtransportboundaries.
- [ ] T3 | slice=mission_control | files=mission_control/hosted_read_control.py,mission_control/hosted_read_registry.py,mission_control/hosted_browser_http.py | verify=`python -m unittest tests.test_hosted_browser_http` | Integrate cookie-basedsignin/logoutandcurrentassignedchoices through existingisolatedreadscope withCSRF/nobearerexposure.
- [ ] T4 | slice=mission_control/static | files=mission_control/static/client-dashboard.html,mission_control/static/client-dashboard.js,mission_control/static/client-dashboard.css | verify=`python tools/test_client_dashboard_browser.py` | AddplainlanguagekeyboardresponsiveworkspacejobsummaryandreceiptUXwithlate-responseprivacyguards.
- [ ] T5 | slice=tests | files=tests/test_hosted_browser_http.py | verify=`python -m unittest tests.test_hosted_browser_http` | ExerciseactualHTTP/browserloginwithrealfixtureRSAprovider, roles/isolation/revocation/logout/exportsand1440/390rendering.
- [ ] T6 | slice=.github | files=.github/workflows/checks.yml | verify=`python -m unittest tests.test_ci_current_candidate` | DeclareoptionalmaintainedauthprofileandrunrealbrowseracceptanceinCIwithoutweakeningexistingchecks.

- [ ] T7 | slice=tools | files=tools/test_client_dashboard_browser.py | verify=`python tools/test_client_dashboard_browser.py` | Run real browser acceptance.
- [ ] T8 | slice=docs | files=docs/requirements-auth.txt | verify=`python -m pip check` | Declare maintained optional auth dependencies.
- [ ] T9 | slice=tests | files=tests/test_ci_current_candidate.py | verify=`python -m unittest tests.test_ci_current_candidate` | Preserve full CI current-candidate checks.

## Full goal retained
PublicHTTPSproviderconfiguration/liveidentityacceptance, ownerprovisioningUI, hostedfirstpacketcreation, protectedhostedcredentials, workflowwritesandworkerrevocationremainrequired. Thispacketmustdeliversyntheticendtoendbrowsercapability, notclaimrealproviderorwholegoalcompletion.
