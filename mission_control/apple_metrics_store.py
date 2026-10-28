"""Bounded local partition persistence; production ingestion remains disabled.

Validation is not authority. The private reconciliation primitive belongs inside
a future lease/attempt/app/connection/schedule/authority-fenced transaction. It is
not routed to a worker, HTTP handler, operation, import, or snapshot restore.
"""
from datetime import datetime, timedelta
import json

from .apple_metrics_contract import complete_instance, observation_fingerprint, partition
from .common import Invalid, canonical, digest, now
from .db import connection

MAX_PARTITIONS_PER_APP = 1000
MAX_PARTITION_BYTES = 4194304
MAX_APP_BYTES = 16777216
KEY_FIELDS = ('app_id', 'store_app_id', 'connection_id', 'connection_version',
              'report_id', 'report_family', 'granularity', 'event_date')
_WHERE = ' AND '.join(field + '=?' for field in KEY_FIELDS)


def ingest(*args, **kwargs):
    """Fail closed until atomic scheduler and job-completion fencing is shipped.

    No credential lookup, database connection or input-controlled validation is
    attempted. A caller-supplied callback, lease flag or synthetic marker cannot
    enable this boundary.
    """
    raise Invalid('APPLE_METRICS_INGESTION_DISABLED')


def read_partition(path, key):
    """Read one exact local partition; this grants no API access authority."""
    key = partition(key)
    with connection(path) as db:
        row = db.execute('SELECT data,ingested_at,processing_date,fingerprint,source_hash,byte_count '
                         'FROM apple_metric_partitions WHERE ' +
                         _WHERE, tuple(key[field] for field in KEY_FIELDS)).fetchone()
        if row is None:
            return None
        try:
            size = len(row['data'].encode('utf-8'))
            if size > MAX_PARTITION_BYTES or size != row['byte_count']:
                raise ValueError()
            instance = complete_instance(key, json.loads(row['data']))
            timestamp = datetime.fromisoformat(row['ingested_at'])
            if (timestamp.utcoffset() != timedelta(0)
                    or timestamp.isoformat() != row['ingested_at']
                    or instance['processing_date'] != row['processing_date']
                    or observation_fingerprint(instance['rows']) != row['fingerprint']
                    or _source_hash(instance) != row['source_hash']):
                raise ValueError()
        except (Invalid, ValueError, TypeError, AttributeError, OverflowError):
            raise Invalid('Stored Apple metrics partition failed integrity validation') from None
        return dict(partition=key,
            instance=instance, ingested_at=row['ingested_at'],
            transport_completeness='SUPPLIED_COMPLETE', event_data_finality='UNKNOWN')


def _reconcile(db, key, instance):
    """Internal transaction primitive, exercised only by trusted offline tests.

    Never opens or commits a transaction. Callers must hold BEGIN IMMEDIATE;
    eventual production callers must additionally fence all authority and commit
    job completion in that same transaction. An active transaction alone is not
    production authorization. Retain only the latest complete version, preserving
    duplicate observations and exact supplied provenance without aggregation.
    """
    if not db.in_transaction:
        raise Invalid('Apple metrics reconciliation requires an owned transaction')
    key = partition(key)
    instance = complete_instance(key, instance)
    data = canonical(instance)
    size = len(data.encode('utf-8'))
    if size > MAX_PARTITION_BYTES:
        raise Invalid('Apple metrics partition storage limit reached')
    values = tuple(key[field] for field in KEY_FIELDS)
    current = db.execute('SELECT processing_date,fingerprint,source_hash,byte_count '
                         'FROM apple_metric_partitions WHERE ' + _WHERE, values).fetchone()
    fingerprint = observation_fingerprint(instance['rows'])
    source_hash = _source_hash(instance)
    processing = instance['processing_date']
    if current is not None:
        if processing < current['processing_date']:
            return 'STALE'
        if processing == current['processing_date']:
            if (fingerprint != current['fingerprint'] or source_hash != current['source_hash']):
                raise Invalid('Conflicting Apple metrics processing version')
            return 'UNCHANGED'
    usage = db.execute('SELECT COUNT(*),COALESCE(SUM(byte_count),0) '
                       'FROM apple_metric_partitions WHERE app_id=?', (key['app_id'],)).fetchone()
    if ((current is None and usage[0] >= MAX_PARTITIONS_PER_APP)
            or usage[1] - (current['byte_count'] if current else 0) + size > MAX_APP_BYTES):
        raise Invalid('Apple metrics app storage limit reached')
    db.execute('INSERT INTO apple_metric_partitions (' + ','.join(KEY_FIELDS) +
               ',processing_date,fingerprint,source_hash,data,byte_count,ingested_at) '
               'VALUES (' + ','.join('?' for _ in range(len(KEY_FIELDS) + 6)) + ') '
               'ON CONFLICT (' + ','.join(KEY_FIELDS) + ') DO UPDATE SET '
               'processing_date=excluded.processing_date,fingerprint=excluded.fingerprint,'
               'source_hash=excluded.source_hash,data=excluded.data,'
               'byte_count=excluded.byte_count,ingested_at=excluded.ingested_at',
               values + (processing, fingerprint, source_hash, data, size, now()))
    return 'REPLACED' if current else 'INSERTED'


def _source_hash(instance):
    return digest(sorted(instance['sources'], key=lambda source: source['id']))
