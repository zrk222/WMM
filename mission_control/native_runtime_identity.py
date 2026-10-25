"""Current fixed native renderer identity without processes, private paths or installs."""
import hashlib
from pathlib import Path
from .media_native import capability
from .common import Invalid


def file_identity(path):
    """Hash the actual configured local file; never expose its filesystem address."""
    target = Path(path)
    if not target.is_file():
        raise Invalid('Native renderer file is unavailable')
    value = hashlib.sha256()
    with target.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            value.update(block)
    return value.hexdigest()


def identity():
    """Describe presence and byte identity separately from actual decoded-output proof."""
    current = capability()
    if current['status'] != 'READY':
        return dict(status='UNAVAILABLE', repair=current['repair'])
    try:
        hashes = {name: file_identity(path) for name, path in current['tools'].items()}
        hashes['font'] = file_identity(current['font'])
    except (OSError, Invalid):
        return dict(status='UNAVAILABLE', repair='Native renderer files changed or are unreadable; repair the local runtime.')
    return dict(status='READY', sha256=hashes, script_support=current['script_support'],
                output='Silent app-screen H.264 MP4; exact brief and media validation still apply.')
