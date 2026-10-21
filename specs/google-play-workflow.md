# Spec: google-play-workflow
Status: draft

## MUST — Functional core
### Description
Add Google Play to the existing app-owned connection, queued-read and recovery
workflow. Discover Android package candidates from explicit project metadata,
show the selected package/track and official access requirements, retain OAuth
login in protected storage, and read release and subscription catalog state.
Use fixed Google hosts and existing source-bound worker jobs. Device attribution,
purchase-token processing and publishing are separate remaining requirements.

### Requirements (EARS)
- The system shall return `package_candidates` from bounded app.json, AndroidManifest.xml or build.gradle metadata without executing project code or inventing a package identity.
- The system shall bind `play_target` to one app, package name, track and manifest version before authorization or provider reads.
- When a user approves official consent, the system shall use a single-use expiring `play_oauth` flow with PKCE and the actual loopback port.
- The system shall retain `play_credentials` only in database-bound native protected storage and preserve the prior connection if replacement fails.
- The system shall permit `play_read` only through fixed HTTPS GET release and subscription endpoints, rejecting identity mismatch, redirects, unsafe pagination and malformed responses.
- The system shall record `play_receipt` with source hashes, exact package/track, coverage, observation time and unknown rollout scope without claiming publication or attribution.
- When access expires or fails, the system shall show `play_recovery` with reconnect, retry or official permission setup actions rather than an empty-success state.
- The system shall render `play_setup` at desktop1440x900 and mobile390x844 with keyboard controls and no horizontal overflow or JavaScript errors.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: Discover the Android app
  Given bounded app.json, AndroidManifest.xml or build.gradle metadata
  When `package_candidates` are requested
  Then only explicit unique package identities are returned
  And ambiguity remains a selection rather than an invented identity

Scenario: Freeze a read target
  Given an app and selected Android package and track
  When `play_target` is approved
  Then reads use that exact app, package, track and manifest version
  And a changed target invalidates prior queued authority

Scenario: Official consent
  Given the actual loopback server port and an installed OAuth client
  When `play_oauth` starts
  Then the verifier is protected and state expires after600seconds
  And a replayed, cancelled or cross-app callback is rejected

Scenario: Retain access safely
  Given an existing `play_credentials` binding
  When replacement consent or verification fails
  Then the existing connection remains intact
  And tokens and secrets never enter exported records or provider diagnostics

Scenario: Fixed read boundary
  Given an approved `play_read` request
  When Google returns a redirect, hostile next-page token or mismatched package
  Then the read fails without following another destination
  And no edit or publishing request is created

Scenario: Honest observations
  Given partial, pending or halted rollout state
  When `play_receipt` is produced
  Then exact provider state and bounded coverage remain visible
  And no global availability or install attribution is inferred

Scenario: Recover failed access
  Given an expired token or denied Play Console permission
  When `play_recovery` is shown
  Then reconnect or official permission setup is available
  And the last observation retains its original date and source

Scenario: Connection journey on both devices
  Given viewports desktop1440x900 and mobile390x844
  When the user follows `play_setup` and keyboard recovery
  Then no horizontal overflow or JavaScript error occurs
```

### Decision table
| Condition | Result |
|---|---|
| Missing package or OAuth client | SETUP_NEEDED with named resolution |
| Multiple explicit package candidates | REVIEW_TARGET before consent |
| Valid callback and verified scoped read | CONNECTED observation |
| Expired, cancelled, replayed or changed source | RECONNECT_REQUIRED, no adoption |
| Provider has no releases | Observed empty bounded collection, no readiness claim |
| Provider limit reached | Coverage LIMITED, no complete-history claim |

### Non-goals
No publishing edit, budget, subscription purchase, treatment claim or causal
attribution. Install Referrer device integration and native billing tests remain
in PLATFORM01. Real provider approval/access must be verified separately from
synthetic tests before advertising a working live connection.

### Data model and local read limits
Project metadata: at most131072 UTF-8 bytes; only app.json, AndroidManifest.xml,
  build.gradle and build.gradle.kts. No executable JavaScript configuration.
Package: at most255 characters, at least two Java-style identifier segments.
  Track: at most100 characters, no slashes or traversal segments.
Release read: at most20 non-obsolete releases and100 active artifacts per
  release. Version codes are integers from1 through2100000000. Provider lifecycle
  suffixes have at most80 uppercase/underscore characters; unknown states remain
  unrecognized, never ready. Missing optional release names remain unknown.
Subscription read: at most3 pages of100 subscriptions,100 plans and100 locales
  per subscription. Provider display labels have at most200 characters and no
  controls or bidi overrides. Opaque encoded page tokens have at most2048
  characters; repeated tokens and duplicate product identities fail the read.
Reports project only public catalog state. Localized price, purchase/restore,
  global availability, rollout fraction and install attribution are not inferred.

Desktop consent uses the fixed accounts.google.com authorization endpoint and
oauth2.googleapis.com token endpoint. Client JSON has at most8192 UTF-8 bytes;
client secrets have at most512 printable ASCII characters. PKCE uses a64character
verifier and SHA256; raw state is random and only its hash is persisted. Each
consent expires after600seconds, with at most8 pending/exchanging flows per app.
An interrupted native candidate write is retained in a cleanup queue with a
900second grace period; explicit failure or cancellation makes cleanup eligible
immediately. Access tokens are not persisted in public records. Token responses
have at most8192 bytes, a Bearer type, an explicitly verified Play scope and an
integer access lifetime from1 through86400seconds. The refresh grant remains in
native protected storage. Synthetic successful grant fixtures use expires_in =
3600 seconds; they are not a claim about an operator's actual token lifetime.
A successful connection also binds android_package,
android_track and the derived Play URL in the app manifest, preserving its Apple
Store ID and invalidating earlier app-version approvals when the target changes.
Queued Google reads require the current manifest version and exact approved
Android package/track before token renewal and again before result adoption.
Agent policy version7 adds only the two typed Play read operations. Earlier
policy approvals become stale; no publication or spending capability is added.
The Google data-reader budget is30seconds with individual reads bounded to
10seconds, leaving room for a15second token refresh within the existing worker
lease. An OAuth refresh that rotates its grant updates native storage before its
access token can be cached. Missing or altered native binding metadata fails
before any credential is sent to Google.
App setup exposes optional paired Android package and track fields. Changing
them invalidates queued source scope; it never changes or borrows a connection.
Google setup requests have at most24576 bytes, metadata discovery requests have
at most262144 bytes and parsing retains the131072byte metadata limit. Duplicate
or nonfinite JSON, alternate HTTP framing, wrong hosts and cross-origin writes
are rejected before setup or code exchange. The loopback callback clears the
authorization query before fetching a session and submitting the single-use
code. It uses local scripts only and stores no code, verifier or token in browser
storage. Only the successful app identity may select the returned workspace.

### Authorized parameters
expires_in = 3600
timeout = 15
timeout = 10
timeout = 15000
max_num_fields = 20
policy_version = 7
