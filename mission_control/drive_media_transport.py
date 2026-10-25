"""Fixed Google Drive blob reads with bounded content and credential redirects blocked."""
import hashlib
import json
import time
from urllib.parse import urlencode
from urllib.request import Request, build_opener
from .common import Invalid
from .drive_auth import selected_files
from .drive_media_contract import FIELDS, MAX_BYTES, metadata
from .payment_signature import unique_pairs
from .play_auth import opaque
from .providers import NoRedirect, report_bytes


def destination(file_id, media=False):
    """Only one selected opaque ID may form a fixed Google endpoint; never accept URLs."""
    if selected_files(file_id) != [file_id]:raise Invalid('Choose one selected Drive file per import')
    query = dict(alt='media') if media else dict(fields=FIELDS)
    return 'https://www.googleapis.com/drive/v3/files/' + file_id + '?' + urlencode(query)


def read_metadata(file_id, bearer):
    """Strict bounded JSON cannot silently replace duplicate provider identity fields."""
    request = Request(destination(file_id), headers={'Authorization': 'Bearer ' + opaque(bearer, 'Drive access token'), 'Accept': 'application/json'}, method='GET')
    try:
        raw = report_bytes(request, 15)
        if len(raw) > 8192:raise ValueError('oversize')
        value = json.loads(raw, object_pairs_hook=unique_pairs)
    except (Invalid, ValueError, TypeError, UnicodeError, RecursionError, OSError):
        raise Invalid('Drive video metadata could not be verified; check access and select again') from None
    return metadata(value, file_id)


def download(selected, bearer, alive):
    """Read original bytes once; never follow redirects or attempt a provider write."""
    request = Request(destination(selected['id'], True), headers={
        'Authorization': 'Bearer ' + opaque(bearer, 'Drive access token'), 'Accept-Encoding': 'identity'}, method='GET')
    alive(); deadline = time.monotonic() + 120
    try:
        with build_opener(NoRedirect()).open(request, timeout=15) as response:
            if response.status != 200:raise Invalid('Drive did not return the complete original')
            raw = read_chunks(response, selected['bytes'], deadline, alive)
    except (OSError, ValueError) as error:
        raise Invalid('Drive download stopped or failed; retry the selected original') from None
    if hashlib.md5(raw).hexdigest() != selected['md5']:
        raise Invalid('Drive original checksum changed; select the current file again')
    alive()
    return raw


def read_chunks(response, expected, deadline, alive):
    """Guard between bounded reads; individual socket waits remain at most15seconds."""
    chunks = []; count = 0
    while True:
        alive()
        if time.monotonic() >= deadline:raise Invalid('Drive download exceeded its120-second read budget')
        chunk = response.read1(min(65536, expected - count + 1))
        if time.monotonic() >= deadline:raise Invalid('Drive download exceeded its120-second read budget')
        if not chunk:break
        count += len(chunk)
        if count > expected or count > MAX_BYTES:raise Invalid('Drive original exceeded its declared byte limit')
        chunks.append(chunk)
    if count != expected:raise Invalid('Drive original was truncated; no media was imported')
    return b''.join(chunks)
