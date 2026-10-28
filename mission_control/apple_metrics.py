"""Offline parsing and atomic reconciliation for supported Apple metrics.

This module does not fetch reports, resolve credentials, or authorize ingestion.
The production ``ingest`` entry point remains disabled until the durable worker
can fence app, connection, schedule, lease, attempt, and completion authority.
"""
from .apple_analytics_parser import parse_instance
from .apple_metrics_contract import PARTITION_FIELDS, complete_instance, partition
from .apple_metrics_store import (MAX_APP_BYTES, MAX_PARTITION_BYTES,
                                  MAX_PARTITIONS_PER_APP, _reconcile)
from .common import Invalid, canonical

IDENTITY_FIELDS = PARTITION_FIELDS - {'event_date'}


def parse_partitions(identity, processing_date, segments, complete):
    """Validate a full supported report and split it into dated app partitions.

    ``identity`` deliberately excludes event_date because one Apple instance
    may carry multiple observation dates. Rows and source identities remain
    intact; no downloads are aggregated and missing dates remain absent.
    """
    if type(identity) is not dict or set(identity) != IDENTITY_FIELDS:
        raise Invalid('Invalid Apple metrics report identity')
    # Reuse the closed-key validator for all shared identity constraints and
    # validate the processing date before passing it to the existing parser.
    partition(dict(identity, event_date=processing_date))
    parsed = parse_instance(identity['store_app_id'], processing_date,
                            segments, complete)
    grouped = {}
    for row in parsed['rows']:
        grouped.setdefault(row['date'], []).append(row)
    if not grouped or len(grouped) > MAX_PARTITIONS_PER_APP:
        raise Invalid('Apple metrics report date count exceeds local storage limit')

    result, total_bytes = [], 0
    for day in sorted(grouped):
        key = partition(dict(identity, event_date=day))
        instance = complete_instance(key, dict(parsed, rows=grouped[day]))
        size = len(canonical(instance).encode('utf-8'))
        if size > MAX_PARTITION_BYTES:
            raise Invalid('Apple metrics partition storage limit reached')
        total_bytes += size
        if total_bytes > MAX_APP_BYTES:
            raise Invalid('Apple metrics app storage limit reached')
        result.append(dict(partition=key, instance=instance))
    return result


def reconcile_offline_instance(db, identity, processing_date, segments, complete):
    """Atomically reconcile parsed partitions inside an existing SQLite tx.

    This local primitive has no production authority. It neither opens nor
    commits a transaction, and ``apple_metrics_store.ingest`` stays fail-closed.
    A savepoint makes multi-date writes all-or-nothing even if a caller catches
    a later SQL failure inside its surrounding transaction.
    """
    if not db.in_transaction:
        raise Invalid('Apple metrics reconciliation requires an owned transaction')
    partitions = parse_partitions(identity, processing_date, segments, complete)
    db.execute('SAVEPOINT apple_metrics_instance')
    try:
        statuses = [dict(partition=item['partition'], status=_reconcile(
            db, item['partition'], item['instance'])) for item in partitions]
        db.execute('RELEASE SAVEPOINT apple_metrics_instance')
        return statuses
    except BaseException:
        db.execute('ROLLBACK TO SAVEPOINT apple_metrics_instance')
        db.execute('RELEASE SAVEPOINT apple_metrics_instance')
        raise
