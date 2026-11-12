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
        # Scope lookups to the unlocked fixture. Searching the old login
        # keychain for a missing item can trigger an interactive unlock.
        security('list-keychains', '-d', 'user', '-s', keychain)
        security('default-keychain', '-d', 'user', '-s', keychain)
        yield security_environment
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


def engine_check(binary, flag, profile, environment):
    """Run an exact frozen executable with a bounded, synthetic-only diagnostic."""
    try:
        result = subprocess.run([str(binary), flag], cwd=profile, env=environment,
                                capture_output=True, text=True, timeout=90)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f'Frozen Mac engine check timed out: {flag}') from None
    if result.returncode != 0:
        raise RuntimeError(f'Frozen Mac engine check failed: {flag}, exit {result.returncode}')
    try:
        return json.loads(result.stdout)
    except ValueError:
        raise RuntimeError(f'Frozen Mac engine returned invalid JSON: {flag}') from None


def main() -> None:
    require_disposable_runner()
    app = ROOT / 'dist/macos/extracted/Wize Marketing Machine.app'
    bundle = app / 'Contents/MacOS'
    binary = bundle / 'WMM'
    native = runpy.run_path(str(ROOT / 'tools/test_native_desktop_bundle.py'))
    with tempfile.TemporaryDirectory(prefix='wmm-mac-package-') as temporary:
        profile = Path(temporary)
        environment = native['isolated_environment'](profile)
        checks = {flag: engine_check(binary, flag, profile, environment)
                  for flag in ('--check', '--self-test')}
        with temporary_native_keychain(profile, environment) as vault_environment:
            # This flag accesses only a fresh synthetic item and never opens
            # a workspace. Use the same Security context as provisioning.
            checks['--vault-self-test'] = engine_check(
                binary, '--vault-self-test', profile, vault_environment)
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
    with binary.open('rb') as stream:
        engine_sha256 = hashlib.file_digest(stream, 'sha256').hexdigest()
    try:
        pair = native['verify_bundle'](bundle)
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired):
        failure = dict(schema='wmm.macos-native-pair-failure.v1',
                       source_sha=os.environ['GITHUB_SHA'], architecture=platform.machine(),
                       run=os.environ['GITHUB_RUN_ID'], attempt=os.environ['GITHUB_RUN_ATTEMPT'],
                       engine_sha256=engine_sha256, shell_sha256=native['digest'](bundle / 'WMM-Mission-Control'),
                       keychain='SYNTHETIC_REMOVED', packaged_agent_setup='PASS',
                       native_pair='FAIL')
        print(json.dumps(failure))
        (ROOT / 'dist/macos/failure.json').write_text(json.dumps(failure) + '\n', encoding='utf-8')
        raise
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
