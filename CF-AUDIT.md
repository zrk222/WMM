# Code Factory audit boundary

The public local application was checked with Code Factory, isolated synthetic
regressions, a fresh remote clone, and desktop/mobile Chromium navigation.

The first deep scan identified movable GitHub Actions references. Both actions
now use exact commit revisions resolved from their official repositories.
The database configuration declares SQLite, matching the actual local store.
Neither change modifies app data or grants provider execution authority.

The first hosted Windows run also exposed undeclared timezone data and missing
optional video-test tools. Setup now installs hash-pinned timezone data in an
isolated environment, CI explicitly installs its pinned FFmpeg test prerequisite,
and startup reports actionable missing-timezone instructions. The launcher checks
the expected local database identity before reusing an occupied port, preserving
other application workspaces.

The initial public runtime passed 577 local regression tests. A fresh GitHub
clone passed 12 additional bootstrap, persistence, isolation and acquisition
checks. Desktop and 390px mobile navigation passed without JavaScript errors
or horizontal overflow. A hash-bound workflow evidence gate passed eight
categories. These are bounded local observations, not production certification.

Code Factory's bundled Python AST scan reported no findings. Its full deep
assessment is **INCOMPLETE**: database extraction cannot fully prove all dynamic
SQLite receivers and queries; standalone JavaScript/PowerShell security workers,
documentation assessment, dependency-advisory assessment, configured pattern/guard
policies and authenticated runtime-coverage receipts are not all available in this repository. The
documentation lane inventories documents but does not itself execute link or
claim verification. No scan suppression or fabricated coverage receipt is used.

To inspect a new candidate with an installed Code Factory runtime:

```powershell
factory doctor --strict --json
factory scan --root . --deep --json
python -X utf8 -m unittest discover -s tests -p "test_*.py"
python tools/check_distribution.py
```

Keep code findings, missing audit coverage, passing local tests and live provider
acceptance separate. No static scan or test suite guarantees the absence of bugs.
