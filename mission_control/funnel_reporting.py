"""Source-bound funnel counts and cautious comparable rates; no inferred people or lift."""
from .common import digest,iso_time


def selected_snapshot(stage,observations,attribution,as_of):
    """Choose a full-window snapshot per source, never sum overlapping exports."""
    matching=[v for v in observations if v['stage_id']==stage['id'] and iso_time(v['observed_at'])<=as_of]
    complete=[v for v in matching if all(iso_time(v[k])==iso_time(attribution[k])for k in ('starts_at','ends_at'))]
    if not matching:return dict(count=None,status='MISSING',source_refs=[],evidence_hash=None)
    if not complete:return dict(count=None,status='PARTIAL_WINDOW',source_refs=sorted({v['source_ref']for v in matching}),evidence_hash=digest(matching))
    sources={v['source_ref']for v in complete}
    if len(sources)!=1:return dict(count=None,status='AMBIGUOUS_SOURCES',source_refs=sorted(sources),evidence_hash=digest(complete))
    latest=max(iso_time(v['observed_at'])for v in complete)
    latest_rows=[v for v in complete if iso_time(v['observed_at'])==latest]
    counts={(v['coverage'],v['count'])for v in latest_rows}
    if len(counts)!=1:return dict(count=None,status='CONFLICTING_SNAPSHOTS',source_refs=sorted(sources),evidence_hash=digest(latest_rows))
    coverage,value=next(iter(counts))
    return dict(count=value,status=coverage,source_refs=sorted(sources),evidence_hash=digest(latest_rows))


def edge_rate(parent,child):
    """An aggregate ratio requires declared matching units/population and complete counts."""
    reason=None
    if parent['status']!='OBSERVED' or child['status']!='OBSERVED':reason='INCOMPLETE_OBSERVATION'
    elif parent['unit']!=child['unit'] or parent['denominator_definition']!=child['denominator_definition']:reason='POPULATION_OR_UNIT_MISMATCH'
    elif parent['count']==0:reason='ZERO_DENOMINATOR'
    elif child['count']>parent['count']:reason='NUMERATOR_EXCEEDS_DENOMINATOR'
    value=None if reason else child['count']/parent['count']
    return dict(from_stage=parent['id'],to_stage=child['id'],rate=value,
                drop_off_count=None if reason else parent['count']-child['count'],
                numerator=child['count'],denominator=parent['count'],status=reason or 'SUPPLIED_AGGREGATE_RATIO',
                subject_transition_verified=False,causal_lift=False)


def calculate(saved,observations,ledger,as_of,source_status='CURRENT'):
    """Keep upstream aggregates and the authoritative downstream ledger distinct."""
    frozen=saved['data'];plan=frozen['definition'];as_of=iso_time(as_of)
    inputs=[r['data']['observation']for r in observations]
    stages=[dict(row,**selected_snapshot(row,inputs,plan['attribution'],as_of))for row in plan['stages']]
    by_id={row['id']:row for row in stages}
    edges=[edge_rate(by_id[parent],row)for row in stages for parent in row['parents']]
    findings=[dict(stage_id=row['id'],code=row['status'],next_action='Collect or reconcile this exact stage and declared observation window.')for row in stages if row['status']!='OBSERVED']
    findings.extend(dict(stage_id=r['to_stage'],code=r['status'],next_action='Review the declared population, unit and eligible denominator before interpreting this edge.')for r in edges if r['rate'] is None)
    if source_status!='CURRENT':findings.insert(0,dict(stage_id=None,code='SOURCE_REVIEW_NEEDED',next_action='Review current app and source evidence; historical observations are retained.'))
    if ledger is None:findings.append(dict(stage_id=None,code='LEDGER_UNAVAILABLE',next_action='Inspect the selected cohort ledger; no payment values are inferred.'))
    result=dict(schema='growth.app-sales-funnel-report.v1',funnel_id=saved['id'],definition_hash=saved['hash'],
                app_id=saved['app_id'],as_of=as_of.isoformat(),currency=plan['currency'],cohort_id=plan['cohort_id'],
                source_status=source_status,stages=stages,edges=edges,findings=findings,
                subscription_ledger=ledger,conversion_timing='NOT_ESTABLISHED_FROM_AGGREGATE_COUNTS',
                production_cost_coverage='NOT_ESTABLISHED_BY_THIS_FUNNEL',execution_authority=False,
                scope='Supplied aggregate observations; ratios do not prove individual transitions or causal growth. Subscription payments, refunds and contribution come only from the referenced ledger.')
    return dict(result,source_hash=digest(result))
