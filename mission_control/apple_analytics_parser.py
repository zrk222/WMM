"""Offline validation of complete Apple App Downloads Standard instances."""
import csv
from collections import Counter
from datetime import date
import gzip
import hashlib
import io
import re
import zlib

from .common import Invalid, canonical

MAX_SEGMENTS = 50
MAX_COMPRESSED = 16777216
MAX_DECOMPRESSED = 67108864
MAX_ROWS = 250000
REQUIRED = frozenset(('date', 'app apple identifier', 'download type', 'counts'))
TYPES = {'first-time download': 'first_download', 'redownload': 'redownload',
         'manual update': 'update', 'auto-update': 'update', 'restore': 'restore'}


def _day(value):
    try:
        if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
            raise ValueError()
    except ValueError:
        raise Invalid('Invalid Apple report date') from None
    return value


def _unpack(segment, remaining):
    if not isinstance(segment, dict):
        raise Invalid('Invalid Apple report segment')
    raw, size, checksum = segment.get('data'), segment.get('size'), segment.get('checksum')
    if not isinstance(raw, bytes) or len(raw) > MAX_COMPRESSED or type(size) is not int or size != len(raw):
        raise Invalid('Invalid Apple report segment size')
    if not isinstance(checksum, str) or not re.fullmatch('[0-9a-fA-F]{32}', checksum):
        raise Invalid('Invalid Apple report checksum')
    if hashlib.md5(raw, usedforsecurity=False).hexdigest() != checksum.lower():
        raise Invalid('Apple report checksum mismatch')
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
            data = stream.read(remaining + 1)
    except (OSError, EOFError, ValueError, zlib.error):
        raise Invalid('Invalid compressed Apple report') from None
    if len(data) > remaining:
        raise Invalid('Apple report decompressed size exceeds the limit')
    return data


def _name(value):
    return ' '.join(value.replace('\ufeff', '').split()).casefold()


def _rows(data, app_id, budget):
    try:
        reader = csv.reader(io.StringIO(data.decode('utf-8-sig'), newline=''), delimiter='\t', strict=True)
        headers = next(reader)
        names = [_name(value) for value in headers]
        if len(set(names)) != len(names) or not REQUIRED.issubset(names):
            raise Invalid('Apple report columns are missing or duplicated')
        rows = []
        for values in reader:
            if len(values) != len(names) or len(rows) >= budget:
                raise Invalid('Apple report row shape or count exceeds its limit')
            row = dict(zip(names, values))
            if row['app apple identifier'] != app_id:
                raise Invalid('Apple report belongs to another app')
            day = _day(row['date'])
            count = row['counts']
            if not re.fullmatch(r'[0-9]{1,15}', count):
                raise Invalid('Invalid Apple report count')
            source_type = row['download type'].strip()
            if not source_type:
                raise Invalid('Missing Apple report download type')
            rows.append(dict(date=day, type=TYPES.get(source_type.casefold(), 'unknown'),
                             source_type=source_type, count=int(count),
                             dimensions={key: value for key, value in row.items() if key not in REQUIRED}))
        return rows
    except (UnicodeError, csv.Error, StopIteration):
        raise Invalid('Malformed Apple report CSV') from None


def _segment_identity(segment, identities):
    identity = segment.get('id') if isinstance(segment, dict) else None
    if not isinstance(identity, str) or not re.fullmatch(r'[A-Za-z0-9-]{1,200}', identity):
        raise Invalid('Invalid Apple report segment identity')
    if identity in identities:
        raise Invalid('Repeated Apple report segment identity')
    identities.add(identity)
    return identity


def parse_instance(app_id, processing_date, segments, complete):
    """Verify every enumerated segment before returning any app-scoped rows."""
    if not isinstance(app_id, str) or not re.fullmatch(r'[0-9]{1,30}', app_id):
        raise Invalid('Invalid Apple report app identity')
    _day(processing_date)
    if complete is not True or not isinstance(segments, list) or not 1 <= len(segments) <= MAX_SEGMENTS:
        raise Invalid('Apple report instance is incomplete')
    rows, size, identities, sources = [], 0, set(), []
    for segment in segments:
        identity = _segment_identity(segment, identities)
        data = _unpack(segment, MAX_DECOMPRESSED - size)
        sources.append(dict(id=identity, size=segment['size'], checksum=segment['checksum'].lower(),
                            sha256=hashlib.sha256(segment['data']).hexdigest()))
        size += len(data)
        for row in _rows(data, app_id, MAX_ROWS - len(rows)):
            row.update(segment_id=identity, processing_date=processing_date,
                       source_sha256=sources[-1]['sha256'])
            rows.append(row)
    if not rows:
        raise Invalid('Apple report instance contains no observations')
    return dict(app_id=app_id, processing_date=processing_date, rows=rows, sources=sources, complete=True)


def _accept_group(latest, day, processing, values):
    previous = latest.get(day)
    if previous is None or processing > previous[0]:
        latest[day] = (processing, values)
    elif processing == previous[0] and Counter(canonical(row) for row in values) != Counter(canonical(row) for row in previous[1]):
        raise Invalid('Conflicting Apple report instances for the same date')


def reconcile(instances):
    """Choose the newest complete processing date for each observed report date."""
    latest, app_id = {}, None
    for instance in instances:
        if not isinstance(instance, dict) or instance.get('complete') is not True or not isinstance(instance.get('rows'), list):
            raise Invalid('Incomplete Apple report instance')
        current_app = instance.get('app_id')
        if app_id is not None and current_app != app_id:
            raise Invalid('Cannot reconcile reports from different apps')
        app_id = current_app
        processing = _day(instance.get('processing_date'))
        grouped = {}
        for row in instance['rows']:
            grouped.setdefault(_day(row['date']), []).append(row)
        for day, values in grouped.items():
            _accept_group(latest, day, processing, values)
    return [row for day in sorted(latest) for row in latest[day][1]]
