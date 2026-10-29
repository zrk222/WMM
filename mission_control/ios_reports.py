"""Allowlisted native analytics projection; no raw account, subject or connection data."""
from .common import Invalid, digest

COHORT_FIELDS = ('activation_rate','paid_conversion','paid_cac_minor','contribution_minor',
                 'contribution_after_acquisition_minor')
COUNT_FIELDS = ('installs','activated','paid','acquisition_cost_minor','net_proceeds_minor',
                'delivery_cost_minor','refunds_minor')
LEDGER_FIELDS = ('installs','activated','paid','retained','activation_rate','paid_conversion',
                 'retention_rate','net_proceeds_minor','refunds_minor','acquisition_cost_minor',
                 'delivery_cost_minor','paid_cac_minor','contribution_after_acquisition_minor')


def projection(app, records, ledger_reports, observed_at, insight_reports=(), apple_partitions=()):
    from .metrics import summarize
    metrics = summarize(records, app['id'], ledger_reports)
    source_hash = digest({'app':app,'records':records,'ledger':ledger_reports,'insights':insight_reports,'apple':apple_partitions})
    rows = []
    def add(label, value, evidence):
        if len(rows) >= 1000: raise Invalid('Native report exceeds 1000 rows; narrow the source evidence before exporting')
        rows.append(dict(metric=label,observed=None if value is None else str(value),evidence=evidence))
    add('Report scope','Supplied observations; no causal lift established',source_hash)
    add('Units','Rates are fractions from 0 to 1; money fields marked minor use the stated currency minor unit.',source_hash)
    if not any(metrics[key] for key in ('cohorts','retention','event_ledger','acquisition')):
        add('App performance',None,'No app-scoped cohort, retention, acquisition or event observations are saved.')
    for index, cohort in enumerate(metrics['cohorts'],1):
        evidence = 'Supplied cohort; '+cohort.get('scope',cohort.get('reason',''))
        evidence += '; currency='+str(cohort.get('currency') or 'unknown')+'; horizon='+str(cohort.get('horizon') or 'unknown')
        add(f'Cohort {index}: status',cohort['status'],evidence)
        for field in COHORT_FIELDS: add(f'Cohort {index}: {field}',cohort.get(field),evidence)
        for field in COUNT_FIELDS: add(f'Cohort {index}: {field}',cohort.get('counts',{}).get(field),evidence)
    for index, retention in enumerate(metrics['retention'],1):
        evidence='Supplied retention; window='+str(retention['window'])+'; mature='+str(retention['mature'])
        for field in ('eligible','retained','rate'): add(f'Retention {index}: {field}',retention[field],evidence)
    for index, ledger in enumerate(ledger_reports,1):
        cohort=ledger['cohort']
        evidence='Imported events; source='+ledger['source_hash']+'; as_of='+ledger['as_of']
        evidence+='; currency='+cohort['currency']+'; starts='+cohort['starts_at']+'; ends='+cohort['ends_at']
        evidence+='; matures='+cohort['matures_at']+'; status='+ledger['status']+'; observability='+ledger['observability']
        add(f'Event cohort {index}: scope',ledger['scope'],evidence)
        for field in LEDGER_FIELDS: add(f'Event cohort {index}: {field}',ledger.get(field),evidence)
        journey = ledger['subscription_journey']
        for group_index, group in enumerate(journey['groups'],1):
            binding = group['binding']
            proof = evidence+'; subscription binding='+digest(binding)+'; coverage='+journey['coverage']
            proof += '; trial_days='+str(binding['trial_days'])+'; billing_period_days='+str(binding['billing_period_days'])
            prefix = f'Event cohort {index}, offer {group_index}'
            add(prefix+': rate status',group['rate_status'],proof)
            for field in ('trial_to_paid_rate','first_renewal_rate','mature_trial_subjects','mature_paid_subjects',
                          'trial_to_paid_subjects','renewed_subjects','median_seconds_to_first_payment'):
                add(prefix+': '+field,group.get(field),proof)
            for field, count in sorted(group['counts'].items()): add(prefix+': '+field,count,proof)
    # Detailed ASA/AEO worksheets retain their own typed result contract. Do not
    # flatten public attention counts into installs or revenue.
    if metrics['acquisition']:
        add('Acquisition worksheets',len(metrics['acquisition']),
            'App-scoped ASA/AEO worksheets are saved; detailed worksheet export is not included in this projection.')
    # Export the latest observation per source separately from transaction totals.
    # Public projections omit project/account identifiers and protected bindings.
    seen = set()
    for item in insight_reports:
        if item['app_id'] != app['id']:raise Invalid('Analytics report belongs to another app')
        if item['source_id'] in seen:continue
        seen.add(item['source_id'])
        data = item['data']
        proof = ('Provider aggregate; provider='+item['provider']+'; observed='+data['observed_at']+
                 '; source='+item['hash']+'; not transaction evidence or causal attribution')
        add('Provider '+item['provider']+': coverage',data['coverage'],proof)
        for metric in data['rows']:
            label='Provider '+item['provider']+': '+metric['id']
            if item['provider']=='clarity':
                for field,value in metric['values'].items():
                    add(label+': row '+str(metric['row'])+': '+field,value,
                        proof+'; period='+metric['period']+'; provider numeric aggregate')
            else:
                add(label,metric['value'],proof+'; period='+metric['period']+'; unit='+metric['unit'])
    for index,item in enumerate(apple_partitions,1):
        key=item['partition'];instance=item['instance']
        if key['app_id']!=app['id'] or key['store_app_id']!=app['data'].get('store_app_id'):
            raise Invalid('Apple metrics partition belongs to another selected app')
        proof='Apple download events; source='+digest(item)+'; event_date='+key['event_date']
        proof+='; processing_date='+instance['processing_date']+'; finality=UNKNOWN; not installs, sales, revenue or causal lift'
        for offset,metric in enumerate(instance['rows'],1):
            add(f'Apple partition {index}, observation {offset}: download_events',metric['count'],
                proof+'; type='+metric['type']+'; source_type='+metric['source_type']+'; dimensions='+digest(metric['dimensions']))
    if any(len(row['metric'])>200 or len(row['evidence'])>4000 or len(row['observed'] or '')>4000 for row in rows):
        raise Invalid('Native report field exceeds the reviewed export bounds')
    return dict(appID=app['id'],appName=app['data']['name'],sourceHash=source_hash,observedAt=observed_at,rows=rows)
