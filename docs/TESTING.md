# Testing profiles and clean-checkout expectations

Use `tools/test.py`; it is the canonical entry point. Do not infer a profile from CI YAML.

```sh
python tools/test.py --profile inventory
python tools/test.py --profile core
python tools/test.py --profile browser
python tools/test.py --profile node
python tools/test.py --profile all
```

Add `--install` to install the declared Python profile. Add `--allow-missing` to run anyway and see which suites skip because optional tools are absent. `pytest` is not required.

## Profiles

| Profile | What runs | Prerequisites | Expected on a clean core install |
| --- | --- | --- | --- |
| `inventory` | No tests. Prints profiles and the declared surface. | Python 3.11+ | PASS |
| `core` | All Python unittest modules, including browser modules that self-skip without Playwright. | Hash-pinned `requirements.txt`; `docs/requirements-mcp.txt`; `docs/requirements-auth.txt`; FFmpeg; a platform keyring. | Deterministic core tests PASS; browser and OS-specific suites may SKIP. A SKIP is not proof. |
| `browser` | Python browser unittest modules; sets `WMM_BROWSER_TEST_PROFILE=1`. | Core profile plus `docs/requirements-browser.txt`, Chromium (`python -m playwright install chromium`) and FFmpeg. | PASS, or explicit failure with the missing browser prerequisite. |
| `node` | `tests/*.test.cjs` and `tests/*.test.mjs` via `node --test`. | Node.js. | PASS. |
| `all` | Core Python + browser Python + Node. | All of the above. | PASS only when every layer passes. |

## OS tools

- **Windows:** the core profile needs FFmpeg on `PATH` and Windows Credential Manager for protected-credential tests.
- **Ubuntu:** install `ffmpeg`, `dbus`, `gnome-keyring` and `SecretStorage`; CI runs core tests inside a disposable `dbus-run-session` keyring.
- **macOS:** not a declared supported desktop-credential target; do not report macOS parity from skips.

CI still uses `tools/run_ci_tests.py` for deterministic sharding. That is an execution detail, not the contributor interface. `tools/test.py` runs the same discovered tests without sharding and prints a concise failure/error list.

## Failure summary

The tool prints:

```text
PROFILE core
SELECTED 3240 python tests; EXCLUDED 0 browser tests
SUMMARY profile=core ran=3240 failures=0 errors=0 skipped=103
```

A skipped optional suite is an exclusion, not a pass. Record the profile and any `PROFILE GAPS` line with a failure report. Do not mix results from different profiles or OS services.

## Known environment-sensitive area

Experiment-tracking and provider-read tests can report `SOURCE_OR_TRACKING_CHANGED` when the expected provider/tracking fixture or optional package is missing. Run the core profile with its declared packages before treating that as a release regression. If it still fails with the profile present, it is a real test failure.
