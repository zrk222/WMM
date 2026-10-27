"""Pure, bounded Apple downloads envelopes; validation grants no source authority.

Rows retain multiplicity. An explicit zero is an observation; an absent date or
empty instance is never interpreted as zero. Hash linkage checks consistency of
supplied provenance, not authenticity of a provider or the supplied bytes.
"""
from collections import Counter
import base64
import binascii
from copy import deepcopy
from datetime import date
import hashlib
import json
import re

from .common import Invalid
from .apple_analytics_parser import MAX_ROWS, MAX_SEGMENTS, MAX_COMPRESSED, MAX_DECOMPRESSED, TYPES

STANDARD_DIMENSIONS = frozenset(('app name', 'app version', 'device',
    'platform version', 'source type', 'page type', 'pre-order', 'territory'))
MAX_DIMENSIONS = len(STANDARD_DIMENSIONS)
MAX_DIMENSION_TEXT = 200
# Local persistence budgets, derived from the existing parser's decompressed
# input budget; these are deliberately not represented as Apple provider limits.
MAX_SOURCE_BYTES = MAX_DECOMPRESSED
MAX_ENVELOPE_BYTES = MAX_DECOMPRESSED
PARTITION_FIELDS = frozenset(('app_id', 'store_app_id', 'connection_id',
    'connection_version', 'report_id', 'report_family', 'granularity', 'event_date'))
SENSITIVE = re.compile(r'://|\bwww\.|\bbearer(?:\s+|:\s*)\S+|\bbasic:\s*\S+|'
    r'\b(?:password|credential|secret|token|authorization|cookie|signature)\s*[:=]|'
    r'-----BEGIN .*PRIVATE KEY-----', re.I)


def _basic_credentials(value):
    # "Basic Calculator" is an ordinary label. HTTP Basic credentials encode
    # a user:password pair; only that syntactic form triggers this guard.
    for match in re.finditer(r'\bbasic\s+([A-Za-z0-9+/]+={0,2})(?!\S)', value, re.I):
        try:
            if b':' in base64.b64decode(match.group(1), validate=True):
                return True
        except (ValueError, binascii.Error):
            pass
    return False


def _exact(value, fields):
    if type(value) is not dict or set(value) != set(fields):
        raise Invalid('Invalid Apple metrics fields')


def _text(value, maximum=200):
    # Closed standard columns exclude detailed referrer/campaign payloads. This
    # lexical guard rejects URL and common credential syntax, not every possible
    # secret: trusted ingestion and source verification remain caller duties.
    if (type(value) is not str or not 1 <= len(value) <= maximum
            or value != value.strip()
            or not value.isprintable()
            or SENSITIVE.search(value) or _basic_credentials(value)):
        raise Invalid('Invalid Apple metrics label')
    return value


def _id(value):
    if type(value) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', value):
        raise Invalid('Invalid Apple metrics identity')
    return value


def _day(value):
    try:
        if type(value) is not str or date.fromisoformat(value).isoformat() != value:
            raise ValueError()
    except (ValueError, TypeError):
        raise Invalid('Invalid Apple metrics date') from None
    return value


def _integer(value, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise Invalid('Invalid Apple metrics integer')
    return value


def _hash(value, length):
    if type(value) is not str or not re.fullmatch('[0-9a-f]{%d}' % length, value):
        raise Invalid('Invalid Apple metrics source hash')
    return value


def partition(value):
    """Validate a closed local-app, Apple-app, source, report and event key."""
    _exact(value, PARTITION_FIELDS)
    for field in ('app_id', 'connection_id', 'report_id'):
        _id(value[field])
    if type(value['store_app_id']) is not str or not re.fullmatch(r'[0-9]{1,30}', value['store_app_id']):
        raise Invalid('Invalid Apple store app identity')
    _integer(value['connection_version'], 1, 2147483647)
    if value['report_family'] != 'App Downloads Standard' or value['granularity'] != 'DAILY':
        raise Invalid('Unsupported Apple metrics report or granularity')
    _day(value['event_date'])
    return deepcopy(value)


def _sources(values):
    if type(values) is not list or not 1 <= len(values) <= MAX_SEGMENTS:
        raise Invalid('Invalid Apple metrics source count')
    result, total = {}, 0
    for source in values:
        _exact(source, ('id', 'size', 'checksum', 'sha256'))
        identity = _id(source['id'])
        if identity in result:
            raise Invalid('Duplicate Apple metrics source identity')
        _integer(source['size'], 1, MAX_COMPRESSED)
        total += source['size']
        if total > MAX_SOURCE_BYTES:
            raise Invalid('Apple metrics aggregate source size exceeds local limit')
        _hash(source['checksum'], 32)
        result[identity] = _hash(source['sha256'], 64)
    return result


def _row(row, key, processing_date, sources):
    _exact(row, ('date', 'type', 'source_type', 'count', 'dimensions',
                 'segment_id', 'processing_date', 'source_sha256'))
    if _day(row['date']) != key['event_date'] or _day(row['processing_date']) != processing_date:
        raise Invalid('Apple metrics row belongs to another date')
    source_type = _text(row['source_type'])
    expected = TYPES.get(source_type.casefold(), 'unknown')
    if row['type'] != expected:
        raise Invalid('Apple metrics download type contradicts source label')
    _integer(row['count'], 0, 999999999999999)
    dimensions = row['dimensions']
    if (type(dimensions) is not dict or len(dimensions) > MAX_DIMENSIONS
            or not set(dimensions).issubset(STANDARD_DIMENSIONS)):
        raise Invalid('Invalid Apple metrics dimensions')
    for name, value in dimensions.items():
        _text(name, 100)
        # Empty dimension cells are legitimate source values.
        if value != '':
            _text(value, MAX_DIMENSION_TEXT)
    segment = _id(row['segment_id'])
    if segment not in sources or _hash(row['source_sha256'], 64) != sources[segment]:
        raise Invalid('Apple metrics row source does not match provenance')


def complete_instance(key, instance):
    """Validate one nonempty date partition from an already parsed full instance.

    The caller groups rows by event date, retaining the original sources. This
    function cannot prove segment enumeration, fetched bytes or write authority;
    those are obligations of the parser and fenced ingestion transaction.
    """
    key = partition(key)
    _exact(instance, ('app_id', 'processing_date', 'rows', 'sources', 'complete'))
    if instance['complete'] is not True or instance['app_id'] != key['store_app_id']:
        raise Invalid('Incomplete or foreign Apple metrics instance')
    processing = _day(instance['processing_date'])
    if processing < key['event_date']:
        raise Invalid('Apple metrics processing date predates observations')
    sources = _sources(instance['sources'])
    rows = instance['rows']
    if type(rows) is not list or not 1 <= len(rows) <= MAX_ROWS:
        raise Invalid('Apple metrics instance contains no observations or too many rows')
    for row in rows:
        _row(row, key, processing, sources)
    _serialized_budget(instance)
    return deepcopy(instance)


def _serialized_budget(value):
    """Count canonical UTF-8 bytes incrementally before any defensive copy."""
    total = 0
    encoder = json.JSONEncoder(sort_keys=True, separators=(',', ':'),
                               ensure_ascii=True, allow_nan=False)
    for chunk in encoder.iterencode(value):
        total += len(chunk.encode('utf-8'))
        if total > MAX_ENVELOPE_BYTES:
            raise Invalid('Apple metrics serialized envelope exceeds local limit')


def observation_fingerprint(rows):
    """Hash validated observation multisets, preserving duplicate multiplicity."""
    # Call only after complete_instance; no caller payload is made authoritative.
    if type(rows) is not list or not 1 <= len(rows) <= MAX_ROWS:
        raise Invalid('Invalid Apple metrics observation count')
    try:
        _serialized_budget(rows)
        counts = Counter(json.dumps(row, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=True, allow_nan=False) for row in rows)
        payload = json.dumps(sorted(counts.items()), separators=(',', ':'))
    except (TypeError, ValueError):
        raise Invalid('Invalid Apple metrics observations') from None
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()
