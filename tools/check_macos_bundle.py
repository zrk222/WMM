"""Actual Mac bundle/native Keychain probe, restricted to disposable hosted CI."""
import hashlib
from contextlib import contextmanager
import json
import os
from pathlib import Path
import platform
import runpy
import secrets
import shlex
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def require_disposable_runner():
    if (sys.platform != 'darwin' or os.environ.get('GITHUB_ACTIONS') != 'true'
            or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted'
            or os.environ.get('WMM_MAC_PACKAGE_TEST') != '1'):
        raise SystemExit('Mac package acceptance requires an opted-in disposable GitHub runner')


@contextmanager
def temporary_native_keychain(profile, environment):
    """Provision an unlocked native keychain only inside opted-in hosted CI."""
    require_disposable_runner()
    keychain = str(profile / 'acceptance.keychain-db')
    password = secrets.token_urlsafe(32)
    # Security preferences belong to the runner account. Only the WMM engine
    # gets the synthetic application-data home; retain the sanitized environment.
    security_environment = dict(environment, HOME=str(Path.home()))

    def security(*arguments):
        try:
            result = subprocess.run(['/usr/bin/security', *arguments], env=security_environment,
                                    stdin=subprocess.DEVNULL, capture_output=True,
                                    text=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            # Never propagate argv-bearing exceptions: passwords occur in argv.
            raise RuntimeError(f'Native test Keychain {arguments[0]} unavailable or timed out') from None
        if result.returncode:
            raise RuntimeError(f'Native test Keychain {arguments[0]} failed (exit {result.returncode})')
        return result.stdout

    original_default = shlex.split(security('default-keychain', '-d', 'user'))
    original_search = shlex.split(security('list-keychains', '-d', 'user'))
    if len(original_default) != 1 or not original_search:
        raise RuntimeError('Cannot preserve native user Keychain configuration')
    try:
        security('create-keychain', '-p', password, keychain)
        security('unlock-keychain', '-p', password, keychain)
        security('list-keychains', '-d', 'user', '-s', *original_search, keychain)
        security('default-keychain', '-d', 'user', '-s', keychain)
        yield
    finally:
        # Attempt every restoration even when an earlier cleanup operation fails.
        failures = []
        for arguments in [('default-keychain', '-d', 'user', '-s', *original_default),
                          ('list-keychains', '-d', 'user', '-s', *original_search),
                          ('delete-keychain', keychain)]:
            try:
                security(*arguments)
            except RuntimeError as error:
                failures.append(error)
        if failures:
            raise RuntimeError('Native test Keychain cleanup failed') from None


def main() -> None:
    require_disposable_runner()
    app = ROOT / 'dist/macos/extracted/Wize Marketing Machine.app'
    bundle = app / 'Contents/MacOS'
    binary = bundle / 'WMM'
    native = runpy.run_path(str(ROOT / 'tools/test_native_desktop_bundle.py'))
    with tempfile.TemporaryDirectory(prefix='wmm-mac-package-') as temporary:
        profile = Path(temporary)
        environment = native['isolated_environment'](profile)
        checks = {}
        with temporary_native_keychain(profile, environment):
            for flag in ('--check', '--self-test', '--vault-self-test'):
                result = subprocess.run([str(binary), flag], cwd=profile, env=environment,
                                        capture_output=True, text=True, timeout=90)
                if result.returncode != 0:
                    print(json.dumps(dict(check=flag, exit_code=result.returncode,
                                          stdout=result.stdout[-4096:], stderr=result.stderr[-4096:])))
                    raise RuntimeError('Frozen Mac engine check failed')
                checks[flag] = json.loads(result.stdout)
        expected = profile / 'Library/Application Support/Wize Marketing Machine'
        if Path(checks['--check']['data_directory']).resolve() != expected.resolve():
            raise AssertionError('Mac bundle did not isolate the workspace outside the app')
        for flag in ('--self-test', '--vault-self-test'):
            if checks[flag].get('status') != 'PASS':
                raise AssertionError('Mac bundle native check failed')
        if checks['--vault-self-test'].get('synthetic_item_removed') is not True:
            raise AssertionError('Mac native Keychain fixture was not removed')
        adapters = runpy.run_path(str(ROOT / 'tools/smoke_desktop_bundle.py'))
        adapters['setup_smoke'](binary, profile, environment, label='macos-' + platform.machine())
    pair = native['verify_bundle'](bundle)
    with binary.open('rb') as stream:
        engine_sha256 = hashlib.file_digest(stream, 'sha256').hexdigest()
    receipt = dict(schema='wmm.macos-package-check.v1', status='PASS',
                   source_sha=os.environ['GITHUB_SHA'], architecture=platform.machine(),
                   native_pair=pair, checks=checks, engine_sha256=engine_sha256,
                   credential_fixture='SYNTHETIC_REMOVED', provider='NOT_RUN',
                   interactive_webview='NOT_RUN', independent_human_setup='NOT_RUN',
                   signing='UNSIGNED_DEVELOPMENT', notarization='NOT_RUN')
    output = ROOT / 'dist/macos/acceptance.json'
    output.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
