# Windows credential isolation for restored workspaces

Exercise WMM's actual social secret wrapper and Windows Credential Manager.
A portable workspace export must exclude the credential and its native
reference. An app restored into a fresh workspace starts without a saved
social configuration or connection. Even a raw database copy at a different
path must not resolve the original credential in the same Windows user vault.

The temporary original remains readable until the test removes its exact
synthetic credential and verifies removal. Run on Windows in the normal
application test matrix. This validates namespace isolation; it does not
establish a separately operated host, another OS account, or provider access.
