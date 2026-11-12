"""Actual Mac bundle/native Keychain probe, restricted to disposable hosted CI."""
import hashlib
import json
import os
from pathlib import Path
import platform
import runpy
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    if (sys.platform != 'darwin' or os.environ.get('GITHUB_ACTIONS') != 'true'
            or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted'
            or os.environ.get('WMM_MAC_PACKAGE_TEST') != '1'):
        raise SystemExit('Mac package acceptance requires an opted-in disposable GitHub runner')
    app = ROOT / 'dist/macos/extracted/Wize Marketing Machine.app'
    bundle = app / 'Contents/MacOS'
    binary = bundle / 'WMM'
    native = runpy.run_path(str(ROOT / 'tools/test_native_desktop_bundle.py'))
    pair = native['verify_bundle'](bundle)
    with tempfile.TemporaryDirectory(prefix='wmm-mac-package-') as temporary:
        profile = Path(temporary)
        environment = native['isolated_environment'](profile)
        checks = {}
        for flag in ('--check', '--self-test', '--vault-self-test'):
            result = subprocess.run([str(binary), flag], cwd=profile, env=environment,
                                    check=True, capture_output=True, text=True, timeout=90)
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
