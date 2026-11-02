"""Build a Debian package from the existing reviewed Linux desktop bundle."""
import os
from pathlib import Path
import shutil
import platform
import tarfile
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TIMEOUT_SECONDS = 180


def normalized(info):
    """Install public program entries as root with stable safe ownership metadata."""
    info.uid = info.gid = 0
    info.uname = info.gname = 'root'
    info.mtime = 0
    if info.isdir():
        info.mode = 0o755
    return info


def ar_member(stream, name, payload):
    """Write one short-name Debian ar member, streaming its compressed payload."""
    size = payload.stat().st_size
    if size >= 10**10 or len(name) > 15:
        raise RuntimeError('Debian archive member exceeds its format bounds')
    header = (name.ljust(16) + '0'.ljust(12) + '0'.ljust(6) + '0'.ljust(6)
              + '100644'.ljust(8) + str(size).ljust(10) + chr(96) + '\n')
    stream.write(header.encode('ascii'))
    with payload.open('rb') as source:
        shutil.copyfileobj(source, stream)
    if size % 2:
        stream.write(b'\n')


def archive(stage, destination):
    """Emit documented Debian 2.0 ar/tar format without process execution."""
    with tempfile.TemporaryDirectory(prefix='wmm-deb-members-') as folder:
        work = Path(folder)
        version = work / 'debian-binary'
        version.write_bytes(b'2.0\n')
        control = work / 'control.tar.gz'
        data = work / 'data.tar.gz'
        with tarfile.open(control, 'w:gz', format=tarfile.GNU_FORMAT) as tar:
            tar.add(stage / 'DEBIAN' / 'control', arcname='./control', filter=normalized)
        with tarfile.open(data, 'w:gz', format=tarfile.GNU_FORMAT) as tar:
            tar.add(stage / 'usr', arcname='./usr', filter=normalized)
        with destination.open('wb') as stream:
            stream.write(b'!<arch>\n')
            for member in (version, control, data):
                ar_member(stream, member.name, member)


def main():
    if not sys.platform.startswith('linux'):
        raise RuntimeError('Build the Debian package on the Linux bundle runner')
    bundle = (ROOT / 'dist/desktop/WMM').resolve()
    if not (bundle / 'WMM').is_file():
        raise RuntimeError('Build the Linux desktop bundle first')
    if platform.machine().lower() not in ('amd64', 'x86_64'):
        raise RuntimeError('This package contract supports amd64 only')
    output = ROOT / 'dist/linux'
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='wmm-deb-stage-') as temporary:
        stage = Path(temporary).resolve()
        control = stage / 'DEBIAN'
        control.mkdir()
        shutil.copy2(ROOT / 'packaging/linux/control', control / 'control')
        runtime = stage / 'usr/lib/wize-marketing-machine'
        runtime.parent.mkdir(parents=True)
        shutil.copytree(bundle, runtime, symlinks=True)
        for source, destination in (
            ('wize-marketing-machine', 'usr/bin/wize-marketing-machine'),
            ('wize-marketing-machine.desktop', 'usr/share/applications/wize-marketing-machine.desktop'),
            ('wmm-worker.service', 'usr/share/wize-marketing-machine/wmm-worker.service'),
        ):
            target = stage / destination
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / 'packaging/linux' / source, target)
        os.chmod(stage / 'usr/bin/wize-marketing-machine', 0o755)
        archive(stage, output / 'wize-marketing-machine_0.1.0_amd64.deb')


if __name__ == '__main__':
    main()
