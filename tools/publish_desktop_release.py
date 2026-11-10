"""Fail-closed desktop prerelease protocol; no dependencies beyond Python and gh."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.request import urlopen

ASSETS = {'Windows': 'WMM-Setup.exe', 'Linux': 'wize-marketing-machine_0.1.0_amd64.deb'}
REPOSITORY = 'zrk222/WMM'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def validate_target(sha, main_sha, ref, repository, tag):
    if (not re.fullmatch('[0-9a-f]{40}', sha) or sha != main_sha
            or ref != 'refs/heads/main' or repository != REPOSITORY
            or not re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+(?:-[a-z0-9.-]+)?', tag)):
        raise ValueError('Release requires official repository, main workflow, exact current main SHA and version tag')


def receipt(platform, sha, asset, lifecycle, destination, evidence_root=None):
    data = json.loads(Path(lifecycle).read_text(encoding='utf-8-sig').splitlines()[-1])
    removal = 'uninstall' if platform == 'Windows' else 'removal'
    if (platform not in ASSETS or not re.fullmatch('[0-9a-f]{40}', sha)
            or data.get('status') != 'PASS'
            or any(data.get(k) != 'VERIFIED' for k in ('install', 'upgrade', removal))
            or data.get('workspace') != 'SYNTHETIC_PRESERVED'):
        raise ValueError('Missing passing installer lifecycle result')
    asset = Path(asset)
    if asset.name != ASSETS[platform] or not asset.is_file() or asset.stat().st_size == 0:
        raise ValueError('Missing exact installer')
    evidence_root = Path(evidence_root) if evidence_root else Path(__file__).resolve().parents[1] / '.factory/packaged-first-packet'
    prefix = 'windows' if platform == 'Windows' else 'ubuntu'
    offline = []
    for phase in ('fresh', 'upgrade'):
        observed = json.loads((evidence_root / (prefix + '-' + phase) / 'evidence.json').read_text())
        if (observed.get('github_sha') != sha
                or observed.get('offline_restart') != 'PASS_SAME_PRIVATE_WORKSPACE_AND_BROWSER_STORAGE'
                or observed.get('network') != 'BROWSER_EXTERNAL_BLOCKED_NOT_OS_OFFLINE'):
            raise ValueError('Missing source-bound browser-isolated restart proof')
        offline.append(dict(phase=phase, evidence_sha256=digest(evidence_root / (prefix + '-' + phase) / 'evidence.json'),
                            offline_restart=observed['offline_restart'], network=observed['network']))
    Path(destination).write_text(json.dumps(dict(schema='wmm.desktop-release.v1', platform=platform,
        source_sha=sha, status='PASS', asset=asset.name, sha256=digest(asset), lifecycle=data, restart_checks=offline), indent=2) + '\n')


def validate_assets(folder, sha):
    folder = Path(folder)
    paths = []
    for platform, name in ASSETS.items():
        record = json.loads((folder / (platform + '.json')).read_text())
        path = folder / name
        if (record.get('schema') != 'wmm.desktop-release.v1' or record.get('platform') != platform
                or record.get('status') != 'PASS' or record.get('source_sha') != sha
                or record.get('asset') != name or path.is_symlink() or not path.is_file()
                or path.stat().st_size == 0 or digest(path) != record.get('sha256')):
            raise ValueError('Installer receipt or hash mismatch: ' + platform)
        lifecycle = record.get('lifecycle', {})
        removal = 'uninstall' if platform == 'Windows' else 'removal'
        if (lifecycle.get('status') != 'PASS'
                or any(lifecycle.get(k) != 'VERIFIED' for k in ('install', 'upgrade', removal))
                or lifecycle.get('workspace') != 'SYNTHETIC_PRESERVED'):
            raise ValueError('Failed installer lifecycle: ' + platform)
        checks = record.get('restart_checks', [])
        if (len(checks) != 2 or [c.get('phase') for c in checks] != ['fresh', 'upgrade']
                or any(c.get('offline_restart') != 'PASS_SAME_PRIVATE_WORKSPACE_AND_BROWSER_STORAGE'
                       or c.get('network') != 'BROWSER_EXTERNAL_BLOCKED_NOT_OS_OFFLINE'
                       or not re.fullmatch('[0-9a-f]{64}', c.get('evidence_sha256', '')) for c in checks)):
            raise ValueError('Missing browser-isolated restart checks: ' + platform)
        paths.append(path)
    sboms = []
    for platform in ASSETS:
        sbom = folder / ('sbom-' + platform + '.json')
        value = json.loads(sbom.read_text(encoding='utf-8'))
        component = value.get('metadata', {}).get('component', {})
        properties = {row.get('name'): row.get('value') for row in component.get('properties', [])}
        if (value.get('bomFormat') != 'CycloneDX' or value.get('specVersion') != '1.5'
                or component.get('version') != sha or properties.get('wmm:platform') != platform
                or properties.get('wmm:inventory_scope') != 'build_environment'
                or not isinstance(value.get('components'), list)):
            raise ValueError('Missing or invalid source-bound SBOM: ' + platform)
        sboms.append(sbom)
    manifest = folder / 'SHA256SUMS.txt'
    all_paths = paths + sboms
    manifest.write_text(''.join(f'{digest(p)}  {p.name}\n' for p in all_paths), encoding='ascii')
    return all_paths + [manifest, folder / 'Windows.json', folder / 'Linux.json']


def gh(*args):
    result = subprocess.run(['gh', *args], capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise RuntimeError(f'gh {" ".join(args[:2])} failed ({result.returncode}): {result.stderr.strip()}')
    return result.stdout


def publish(folder, sha, tag):
    repo = json.loads(gh('api', 'repos/' + REPOSITORY))
    main = gh('api', 'repos/' + REPOSITORY + '/git/ref/heads/main', '--jq', '.object.sha').strip()
    validate_target(sha, main, os.environ.get('GITHUB_REF'), os.environ.get('GITHUB_REPOSITORY'), tag)
    if repo.get('private') is not False:
        raise ValueError('Anonymous installer downloads require a public repository')
    paths = validate_assets(folder, sha)
    # A successful list proves absence. API/network errors abort rather than looking like 404.
    refs = json.loads(gh('api', 'repos/' + REPOSITORY + '/git/matching-refs/tags/' + tag))
    releases = json.loads(gh('api', '--paginate', '--slurp', 'repos/' + REPOSITORY + '/releases'))
    if any(r['ref'] == 'refs/tags/' + tag for r in refs) or any(r['tag_name'] == tag for page in releases for r in page):
        raise ValueError('Existing release/tag is immutable; choose a new version')
    notes = ('Windows and Ubuntu amd64 preview installers. No system Python required. '
             'SHA256SUMS.txt covers every uploaded file. sbom-Windows.json and sbom-Linux.json list the '
             'build-environment packages; this is not a runtime file inventory. '
             'Windows publisher signature is not provided; OS trust prompts can appear. '
             'See docs/desktop-first-run.md at source commit ' + sha + '. '
             'Automated synthetic installer checks are not human first-use acceptance.')
    gh('release', 'create', tag, '--repo', REPOSITORY, '--target', sha, '--draft',
       '--prerelease', '--title', 'WMM Desktop ' + tag, '--notes', notes)
    # Never --clobber. Failure leaves a draft for inspection and cannot overwrite assets on retry.
    gh('release', 'upload', tag, '--repo', REPOSITORY, *map(str, paths))
    uploaded = json.loads(gh('release', 'view', tag, '--repo', REPOSITORY, '--json',
                             'assets,isDraft,isPrerelease,targetCommitish'))
    expected = {p.name: p.stat().st_size for p in paths}
    if (not uploaded.get('isDraft') or not uploaded.get('isPrerelease') or uploaded.get('targetCommitish') != sha
            or {a['name']: a['size'] for a in uploaded['assets']} != expected):
        raise ValueError('Draft asset readback mismatch; draft preserved')
    gh('release', 'edit', tag, '--repo', REPOSITORY, '--draft=false', '--prerelease')
    actual = gh('api', 'repos/' + REPOSITORY + '/git/ref/tags/' + tag, '--jq', '.object.sha').strip()
    if actual != sha:
        raise ValueError('Published tag does not point to the tested commit')
    # Native HTTPS validation, anonymous full-byte download: no token, custom CA or TLS bypass.
    for path in paths:
        url = f'https://github.com/{REPOSITORY}/releases/download/{tag}/{path.name}'
        with urlopen(url, timeout=120) as response:
            downloaded = hashlib.file_digest(response, 'sha256').hexdigest()
        if downloaded != digest(path):
            raise ValueError('Public download hash mismatch: ' + url)
    print(json.dumps(dict(status='PASS', source_sha=sha, tag=tag,
        url=f'https://github.com/{REPOSITORY}/releases/tag/{tag}', anonymous_downloads_verified=True)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    record = sub.add_parser('receipt')
    for name in ('platform', 'sha', 'asset', 'lifecycle', 'destination'):
        record.add_argument('--' + name, required=True)
    release = sub.add_parser('publish')
    for name in ('folder', 'sha', 'tag'):
        release.add_argument('--' + name, required=True)
    args = vars(parser.parse_args())
    command = args.pop('command')
    (receipt if command == 'receipt' else publish)(**args)


if __name__ == '__main__':
    main()
