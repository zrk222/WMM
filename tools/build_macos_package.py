"""Stage the existing native desktop as an unsigned Mac development app bundle."""
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import shutil
import stat
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
APP_NAME = 'Wize Marketing Machine.app'


def stage(bundle: Path, destination: Path) -> Path:
    """Copy only a completed frozen bundle; reject source links outside that bundle."""
    bundle = bundle.resolve(strict=True)
    for name in ('WMM', 'WMM-Mission-Control'):
        binary = bundle / name
        if not binary.is_file() or binary.is_symlink():
            raise ValueError('Build both native Mac executables before staging the app')
    if not (bundle / '_internal').is_dir() or (bundle / '_internal').is_symlink():
        raise ValueError('Frozen Mac runtime libraries are missing')
    for item in bundle.rglob('*'):
        if item.is_symlink():
            if Path(os.readlink(item)).is_absolute() or not item.resolve(strict=True).is_relative_to(bundle):
                raise ValueError('Mac bundle contains an external symbolic link')
    if destination.exists():
        raise ValueError('Mac app destination exists; preserve it and use a clean build directory')
    executables = destination / 'Contents/MacOS'
    executables.parent.mkdir(parents=True)
    shutil.copytree(bundle, executables, symlinks=True)
    # PyInstaller recognizes .app/Contents/MacOS and resolves its library root
    # as Contents/Frameworks, regardless of the onedir _internal setting.
    (executables / '_internal').rename(destination / 'Contents/Frameworks')
    info = dict(CFBundleName='Wize Marketing Machine',
                CFBundleDisplayName='Wize Marketing Machine',
                CFBundleIdentifier='app.wizemarketing.missioncontrol',
                CFBundleExecutable='WMM-Mission-Control', CFBundlePackageType='APPL',
                CFBundleShortVersionString='0.1.0', CFBundleVersion='1',
                LSMinimumSystemVersion='15.0', NSHighResolutionCapable=True)
    with (destination / 'Contents/Info.plist').open('wb') as stream:
        plistlib.dump(info, stream)
    (destination / 'Contents/DEVELOPMENT-PREVIEW.txt').write_text(
        'WMM macOS development preview\n'
        'Unsigned and not notarized. CI artifact only; Gatekeeper acceptance is not established.\n'
        'Do not disable security controls to open this app.\n'
        'Synthetic package checks do not establish human setup or live provider results.\n',
        encoding='utf-8')
    return destination


def archive_app(app: Path, destination: Path) -> None:
    """Preserve Unix modes and relative framework links without a shell command."""
    with zipfile.ZipFile(destination, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
        for item in [app, *sorted(app.rglob('*'))]:
            relative = item.relative_to(app.parent).as_posix()
            if item.is_symlink():
                entry = zipfile.ZipInfo(relative)
                entry.create_system = 3
                entry.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(entry, os.readlink(item).encode('utf-8'))
            else:
                archive.write(item, relative)


def main() -> None:
    if sys.platform != 'darwin' or platform.machine() not in ('arm64', 'x86_64'):
        raise SystemExit('Build Mac artifacts on a declared native macOS runner')
    folder = ROOT / 'dist/macos'
    folder.mkdir(parents=True, exist_ok=True)
    app = stage(ROOT / 'dist/desktop/WMM', folder / APP_NAME)
    archive = folder / f'WMM-macOS-{platform.machine()}.zip'
    if archive.exists():
        raise SystemExit('Mac archive already exists; existing artifacts are preserved')
    archive_app(app, archive)
    with archive.open('rb') as stream:
        archive_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
    result = dict(schema='wmm.macos-build.v1', source_sha=os.environ.get('GITHUB_SHA'),
                  architecture=platform.machine(), os=platform.mac_ver()[0],
                  asset=archive.name, sha256=archive_hash,
                  signing='UNSIGNED_DEVELOPMENT', notarization='NOT_RUN',
                  distribution='CI_ARTIFACT_NOT_PUBLIC_RELEASE')
    (folder / 'build.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
