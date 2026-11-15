# Browser sign-in after installation

An installed desktop must retain the publisher's public GitHub device Client ID
without asking users to configure an environment variable. Packaging serializes
only that allowlisted public value. It never copies credentials or other environment
variables. An invalid configured value fails packaging; an unset value clears any
previous generated value for a generic build. Official releases require a public
Client ID before building; recognizable GitHub token formats are rejected.

The runtime reads the bundled configuration beside its frozen Python module.
An explicit constructor value or present runtime environment value takes priority,
including an empty value to disable browser sign-in. Missing, malformed, oversized
or unrecognized configuration leaves browser sign-in unavailable. Existing manual
sign-in, identity checks, consent, scopes and credential retention remain unchanged.

Acceptance: configuration boundary tests pass; existing device-flow tests pass;
the actual frozen executable, in an unrelated directory and disposable workspace,
reports the expected sign-in availability with the build environment variable
removed. The package probe makes no provider calls and establishes no owner.
Provider consent and independent human setup are separate acceptance evidence.
