# Owner onboarding continuation repair

Owner asks to remove all avoidable onboarding/access and configuration/approval
blockers. This packet fixes one demonstrated interruption: Establish app owner
while signed out currently loses the intended owner step after sign-in.

Owned: static/verified-review.js, a focused Node test and actual loopback browser
acceptance tool. Preserve current backend identity, explicit first-owner checkbox,
maker/checker boundaries and current app context. Continue only if the same app
and version remain selected, the login dialog was still active and the app has no
owner. No silent ownership assignment, no existing-owner replacement, no token
retention, no campaign launch or new catalog operation.

Use exact-body scoped QA; test successful login, cancelled/stale/app-switch
responses, preconfigured owner and generic sign-in. Execute actual browser owner
setup and rerun owner regressions, Node suites, design and workflow/privacy gates.
All-owner completion still needs the full configuration/installation/platform
inventory and real account acceptance; this repair alone does not establish it.
