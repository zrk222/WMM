# Spec: browser-client-login
Status: implementation candidate; public hosted release incomplete

## MUST - Functional core
### Description
Connect a configured OpenID Connect authorization-code provider to the existing isolated client read service and provide a browser dashboard. Human sign-in must not require a GitHub developer token or terminal command. Reuse Control sessions, membership epochs, Registry and Service projection; keep all desktop/mutation/credential boundaries unchanged.

### Requirements (EARS)
- When a browser starts sign-in, the system shall return one-use browser-bound state, nonce and S256 PKCE through `login_start`, with a 600 second lifetime and at most 256 pending browsers.
- When a configured provider returns a code, the system shall consume the matching state once through `login_callback` before token exchange, rejecting replay, wrong browser, changed origin, duplicate fields and unknown callback fields, with 0 codes or tokens in receipts or diagnostics.
- The system shall verify signed ID tokens with PyJWT using fixed RS256, issuer and client audience through `identity`, requiring expiry, issued-at, subject, nonce and matching authorized party; expired tokens receive 0 seconds of grace and future issued-at tolerance is 5 seconds.
- The system shall send provider requests only to administrator-configured public HTTPS endpoints through `provider_transport`, using existing pinned DNS/TLS, 0 redirects, a 20 second deadline and 256 KiB response cap, with no URL selected by browser or token header.
- When identity verification succeeds, the system shall return only the existing currently assigned read session through `membership`, denying identities without provisioned membership and creating 0 owner roles or domain authority.
- The system shall return the opaque read session only in an HttpOnly SameSite Lax cookie through `browser_session`, with 0 session tokens in URLs, local storage or browser-readable JSON; logout shall require exact Origin and current CSRF before revoking the session.
- The system shall return an accessible dashboard at 1440 px and 390 px through `dashboard`, showing only current assigned client/app summaries, read-only scope, job counts, receipt references and actionable signed-out, expired and unavailable states.
- If membership or session is revoked, expires or changes epoch, the system shall reject subsequent summaries and clear prior client data through `revocation`, preserving existing final transaction checks and receipts with 0 seconds of grace.
- The system shall reject ambiguous headers, callbacks, raw desktop APIs, external return URLs and unsupported writes through `http_boundary`, preserving exact Host/Origin and finite routes with a 4 KiB request-body cap.
- The system shall retain existing desktop and marketing authority through `compatibility`, adding 0 public listeners, production HTTPS claims, provider accounts, credential migrations or campaign permissions from sign-in.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: login_start
 Given a configuredproviderand syntheticbrowser
 When `login_start` beginsconsent
 Then exactstate nonce andS256PKCEareboundtoonebrowserandexpireat600seconds
Scenario: login_callback
 Given a returnedcode
 When `login_callback` checksbrowserstate replay andcallbackgrammar
 Then onlyonevalidexchangeoccursandnoprovidersecretleaks
Scenario: identity
 Given realRSAsignedsyntheticIDtokens
 When `identity` verifiesnonceissuerandaudience
 Then tamperedexpiredwrongalgorithmorwrongidentitytokensarerejected
Scenario: provider_transport
 Given fixedproviderendpointsandredirectorprivateDNSresponses
 When `provider_transport` exchangesorreadskeys
 Then onlypinnedpublicHTTPSwithboundedresponsesissupported
Scenario: membership
 Given assignedandunassignedverifiedidentities
 When `membership` completeslogin
 Then onlycurrentprovisionedclientreadaccessisissued
Scenario: browser_session
 Given anauthenticatedbrowser
 When `browser_session` reportsstateorlogsout
 Then noopaquecredentialentersJSONorURLandlogoutrequiresOriginandCSRF
Scenario: dashboard
 Given desktop1440andmobile390browserprofiles
 When `dashboard` followsloginreadlogoutkeyboardandrecovery
 Then onlyassignedclientcountsandreceiptmetadataappearwithnooverflow
Scenario: revocation
 Given visibleclientdata
 When `revocation` changesmembershiporsessionepoch
 Then refreshfailsclosedandclearspriorclientdata
Scenario: http_boundary
 Given ambiguousheaderscallbacksandunsupportedroutes
 When `http_boundary` handlesactualHTTP
 Then nootherclientordesktopendpointisdispatched
Scenario: compatibility
 Given existingdesktopandprivate-readregressions
 When `compatibility` runs
 Then thecurrentauthorityandreadisolationcontractsremainintact
```

## SHOULD - Exact architecture and rollout
BrowserServer subclasses the finite ReadServer handler only; it never inherits desktop Handler. Bind only127.0.0.1for this increment; productionHTTPSingress/securecookies and publichosting remain laterrequired. RootGETserves one static HTML/CSS/JS application understrictCSP/no-store. GET /auth/context mints browserchallengecookie and returns only CSRF/loginconfiguredstate; POST /auth/start checks exactOrigin/CSRF and redirects to configuredauthorize endpoint; GET /auth/callback accepts exactlycode,state orerror,state, consumes challenge before network and returns303 / with a generic status marker only. Browserchallenge/verifier/nonce remain RAM-only, capped256/600seconds; restart invalidatespendingloginwithoutreplayingexchange. GET /api/session validates HttpOnlycookie/currentassignmentsandreturns finiteclient/app choices plus sessionboundCSRF; POST /auth/logout requires sameOrigin/currentCSRF and revokescookie. GET dashboard route consumescookieinternallyandcalls existingcollect; no bearer exposedtoJS.

Config is trustedstartup only: issuer, authorization_endpoint, token_endpoint, jwks_uri, client_id, optional client_secret, and displaylabel. Everyendpoint is canonical publicHTTPSwith noquerycredentialsfragment; clientID/secretbounded, no dynamicdiscovery. Testprovider transport is explicitly injected byPythonfixture; no HTTP/envtestbypass. Tokens/keys are realRSAsignedfixturedata, no staticproductionkey. Lazy optional PyJWT==2.15.1withcryptography==49.0.0 is declared andinstalled inCI; missing optionalprofile disablesloginwithactionablemessageandneveracceptsunverifiedtokens. Existingauth consumers neednotimporttheseextras.

Control adds trusted read-only assigned-listing method that rechecks sessionandepoch perclient; Registry enumerates existingappIDs/names withread-onlySQLite and finiteprojection, not rawbootstrap. Cap initialdashboard choices20clients and20appsperclient, indicate explicitmoreavailable ratherthanomitwithoutnotice. Appoptions andjobsummary checks revalidatecurrentassignmentbeforeexposingbytes. HTML/JS neverstores sensitivepreviousresponseafterlogout/errorandhas requestgeneration guards forlate responses. Idle15minutes/absolute8hours remain Controlpolicy; sessionCSRF mayrotateonserverrestart requiringreload; no false durablependingOAuthclaim.

Identitytokens are notsaved. JWT headers/payloads mustbestrictJSONwithoutduplicatesbeforemaintainedlibrarysignatureverification; allowonlyRS256, requiredclaims iss,sub,aud,exp,iat,nonce; issued-at at most 5 seconds after current time, expiry strictly after current time with zero grace, nbfifpresentvalid. Max16JWKRSAkeys,2048–8192bits,noheader-providedjku/x5uurls; rejectunknownkid, duplicatekids, asymmetric/symmetricconfusion andprivatekeymembers. aud containingmultiplevalues requiresazp==client_id; anypresentazpmustmatch. IDs andclaims nevergrantmembershipbyemailmatching.

UIcopy states signintoassignedworkspaces, inspectcurrentcountsandreceipts, and use localMissionControl for existingfullworkflowactions. This increment cannotclaim completehostedmarketingoperationsorzero-installfirstpacket; those remain required. No publishing/spending/DMs/accountsettings/providerconsentwillbeperformedbyfixtures.

## Authorized parameters
Successful HTML uses Referrer-Policy same-origin so browser form submissions send exact Origin; callback, error and JSON responses retain no-referrer. No referrer is sent to the external authorization provider. Chromium acceptance must verify this distinction without permitting null Origin.

timeout = 5
timeout = 10
max_workers = 4
MAX_PENDING = 256
MAX_EXCHANGES = 4
limit = 1024
max_num_fields = 4
FLOW_SECONDS = 600
MAX_CLIENTS = 20
MAX_APPS = 20
MAX_RESPONSE = 262144
DEADLINE_SECONDS = 20

## Binding architecture conditions
The reviewed C1-C6 conditions in .factory/browser-client-login/architecture-review.md are mandatory acceptance details. Atomically consume each flow before exchange; maintain browser generation through final session commit, replacement start and logout; cap all contexts at 256 and concurrent exchanges at 4 with no waiting queue. Recheck verified ID-token temporal bounds inside Control issuance transaction after SQLite lock acquisition. Choice/app collection must finish with current epoch/session and Registry identity checks. Explicitly reject duplicate Cookie headers/names and missing, null or foreign Origin on POST; bodies have exact form grammar and a 4096-byte cap. Use only the fixed single-provider configuration and exact redirect binding. Test late callbacks, lock-wait expiry, concurrent replay, choice revocation and delayed UI responses.
