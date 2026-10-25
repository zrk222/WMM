"""Closed selected-blob metadata and immutable server-generated import provenance."""
import re
from pathlib import Path
from .common import Invalid
from .drive_auth import selected_files

MAX_BYTES = 67108864
MIMES = {'video/mp4': '.mp4', 'video/quicktime': '.mov', 'video/webm': '.webm'}
FIELDS = 'id,name,mimeType,size,version,md5Checksum,trashed,capabilities(canDownload)'


def metadata(value, file_id):
    """Require one complete downloadable video blob identity before reading its content."""
    if selected_files(file_id) != [file_id]:raise Invalid('Choose one Drive original per import')
    keys = {'id', 'name', 'mimeType', 'size', 'version', 'md5Checksum', 'trashed', 'capabilities'}
    if not isinstance(value, dict) or set(value) != keys or value['id'] != file_id:
        raise Invalid('Drive file metadata differs from the selected original')
    download_capability(value['trashed'], value['capabilities'])
    name = video_filename(value['name'], value['mimeType'])
    return dict(id=file_id, filename=name, mime_type=value['mimeType'], bytes=blob_size(value['size']),
                version=blob_version(value['version']), md5=checksum(value['md5Checksum']))


def download_capability(trashed, capability):
    """Only an explicit current download capability permits reading a nontrashed blob."""
    if trashed is not False or not isinstance(capability, dict) or set(capability) != {'canDownload'}:
        raise Invalid('Drive does not permit downloading this selected original')
    if capability['canDownload'] is not True:
        raise Invalid('Drive does not permit downloading this selected original')


def video_filename(name, mime):
    """The original basename and declared blob format must agree without path components."""
    if not isinstance(mime, str) or mime not in MIMES:
        raise Invalid('Choose an MP4, MOV or WebM blob; Google documents require a different export flow')
    if not isinstance(name, str) or not name or len(name) > 255 or any(ord(char) < 32 for char in name):
        raise Invalid('Drive video filename is invalid')
    if '/' in name or '\\' in name or Path(name).suffix.lower() != MIMES[mime]:
        raise Invalid('Drive filename and video format do not agree')
    return name


def blob_size(value):
    """Provider decimal strings cannot coerce booleans, floating point or signed input."""
    if not isinstance(value, str) or not re.fullmatch(r'[1-9][0-9]{0,7}', value):
        raise Invalid('Drive original size is invalid')
    size = int(value)
    if size > MAX_BYTES:raise Invalid('Drive original exceeds the64MiB media limit')
    return size


def blob_version(value):
    """Freeze Google's opaque decimal content-version marker without numeric coercion."""
    if not isinstance(value, str) or not re.fullmatch(r'[1-9][0-9]{0,29}', value):
        raise Invalid('Drive file version is unavailable; select the original again')
    return value


def checksum(value):
    """MD5 is provider byte-integrity evidence; WMM also computes its own SHA256."""
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{32}', value):
        raise Invalid('Drive original checksum is unavailable; select a video blob')
    return value


def provenance(row, selected):
    """No credential, download URL or claim of adaptation permission enters provenance."""
    return dict(kind='GOOGLE_DRIVE', connection_id=row['id'], connection_version=row['version'],
                permission_id=row['data']['account']['permission_id'], file_id=selected['id'],
                file_version=selected['version'], md5=selected['md5'], filename=selected['filename'])
