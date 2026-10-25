"""Typed app-sales funnel inputs; supplied plans and counts never prove outcomes."""
from copy import deepcopy
from .common import Invalid, required, identifier, iso_time, safe_data
from .pmf_contract import exact, count, hashed, one

STAGE_TYPES = {'VIDEO_VIEW', 'CTA_CLICK', 'STORE_VISIT', 'INSTALL', 'SIGNUP',
               'ONBOARDING_COMPLETE', 'ACTIVATION', 'PAYWALL_EXPOSURE', 'TRIAL_START',
               'PURCHASE', 'RENEWAL', 'CANCEL_REQUEST', 'REFUND', 'RESOURCE_REQUEST', 'RESOURCE_DELIVERED'}
UNITS = {'EVENTS', 'UNIQUE_SUBJECTS', 'SESSIONS', 'VIEWS'}
ROUTES = {'APP_DOWNLOAD', 'RESOURCE', 'APP_DEMO'}


def rows(value, maximum, name, minimum=0):
    """Keep all nested evidence collections finite and explicitly sized."""
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise Invalid(name + ': use between ' + str(minimum) + ' and ' + str(maximum) + ' rows')
    return value


def source_ref(value):
    """Reference existing source identity and digest, never a filesystem path."""
    exact(value, {'kind', 'id', 'version', 'sha256'})
    one(value['kind'], {'CREATIVE_BRIEF', 'CUSTOMER_WORKFLOW'}, 'Source kind')
    from .ledger import opaque
    opaque(value['id'], 'Source identity');hashed(value['sha256'])
    count(value['version'], 1, 2147483647)
    return deepcopy(value)


def unique(values, field, name):
    """Reject duplicate identities rather than silently collapse source observations."""
    keys = [row[field] for row in values]
    if len(set(keys)) != len(keys):
        raise Invalid(name + ': identities must be unique')


def stages(value):
    """Require a topologically ordered app-sales graph with explicit parent edges."""
    result=[];seen=set()
    for row in rows(value, 32, 'Funnel stages', 1):
        exact(row, {'id', 'type', 'label', 'parents', 'unit', 'denominator_definition'})
        identity=identifier(row['id']);one(row['type'], STAGE_TYPES, 'Stage type')
        one(row['unit'], UNITS, 'Stage unit')
        for key in ('label', 'denominator_definition'):required(row[key], key, 500)
        parents=rows(row['parents'], 32, 'Stage parents')
        if any(not isinstance(p,str) or p not in seen for p in parents) or len(set(parents)) != len(parents):
            raise Invalid('Stage parents must be distinct earlier stages; cycles and unknown parents are rejected')
        if identity in seen:raise Invalid('Stage identities must be unique')
        seen.add(identity);result.append(deepcopy(row))
    return result


def window(value):
    """Freeze declared attribution timing and identity basis without assuming tracking."""
    exact(value, {'method', 'identity_scope', 'starts_at', 'ends_at', 'conversion_window_seconds'})
    required(value['method'], 'Attribution method', 500)
    required(value['identity_scope'], 'Identity scope', 200)
    start,end=iso_time(value['starts_at']),iso_time(value['ends_at'])
    if start>=end:raise Invalid('Funnel observation start must precede its end')
    count(value['conversion_window_seconds'], 1, 31536000)
    return dict(value,starts_at=start.isoformat(),ends_at=end.isoformat())


def outcome(value):
    """Store the operator's target as a hypothesis with source-linked audience pain."""
    exact(value, {'audience', 'pain', 'research_refs', 'milestone', 'metric', 'target', 'due_at'})
    for key in ('audience', 'pain', 'milestone', 'metric'):required(value[key], key, 1000)
    count(value['target'], 0, 1000000000000)
    refs=[source_ref(row) for row in rows(value['research_refs'], 20, 'Pain evidence')]
    unique(refs,'id','Pain evidence')
    return dict(value,research_refs=refs,due_at=iso_time(value['due_at']).isoformat())


def offer_boundary(value):
    """Describe actual free and paid app capabilities without preset coaching prices."""
    exact(value, {'free_deliverables', 'paid_deliverables'})
    return {key:[required(text,key,500) for text in rows(value[key],20,key)] for key in value}


def definition(value):
    """Normalize an app-sales plan; current domain binding is the store's responsibility."""
    safe_data(value)
    exact(value, {'release','locale','currency','cohort_id','outcome','creative_refs','hook','cta',
                  'destination','route','stages','attribution','offer_boundary'})
    for key in ('release','locale','hook','cta'):required(value[key],key,1000)
    from .ledger import currency,opaque
    from .aeo_transport import public_url
    currency(value['currency']);opaque(value['cohort_id'],'cohort_id')
    one(value['route'],ROUTES,'App-sales route')
    refs=[source_ref(row)for row in rows(value['creative_refs'],20,'Creative sources',1)]
    unique(refs,'id','Creative sources')
    return dict(deepcopy(value),outcome=outcome(value['outcome']),creative_refs=refs,
                destination=public_url(value['destination']),stages=stages(value['stages']),
                attribution=window(value['attribution']),offer_boundary=offer_boundary(value['offer_boundary']))


def observation(value, plan, observed_at):
    """Retain comparable supplied aggregates, distinguishing zero from unavailable data."""
    safe_data(value)
    fields={'event_id','stage_id','source_ref','source_sha256','cohort_id','starts_at','ends_at',
            'observed_at','coverage','count','unit','denominator_definition','identity_scope'}
    exact(value,fields);identifier(value['event_id'])
    known={row['id']:row for row in plan['stages']}
    if not isinstance(value['stage_id'],str) or value['stage_id'] not in known:
        raise Invalid('Observation stage is not in this funnel definition')
    stage=known[value['stage_id']]
    required(value['source_ref'],'Observation source',500);hashed(value['source_sha256'])
    one(value['coverage'],{'OBSERVED','PARTIAL','UNKNOWN'},'Observation coverage')
    if value['coverage']=='UNKNOWN':
        if value['count'] is not None:raise Invalid('Unknown coverage requires an unknown count')
    else:count(value['count'],0,1000000000000)
    if value['cohort_id']!=plan['cohort_id']:raise Invalid('Observation cohort differs from the funnel')
    for key in ('unit','denominator_definition'):
        if value[key]!=stage[key]:raise Invalid('Observation population or unit differs from the declared stage')
    if value['identity_scope']!=plan['attribution']['identity_scope']:
        raise Invalid('Observation identity scope differs from the declared attribution')
    return observation_window(value,plan,observed_at)


def observation_window(value,plan,observed_at):
    """Require completed evidence timing inside the exact declared acquisition window."""
    start,end,at=[iso_time(value[key])for key in ('starts_at','ends_at','observed_at')]
    lower,upper=[iso_time(plan['attribution'][key])for key in ('starts_at','ends_at')]
    if not lower<=start<end<=upper or not end<=at<=observed_at:
        raise Invalid('Observation window is outside the funnel or its evidence timestamp')
    return dict(value,starts_at=start.isoformat(),ends_at=end.isoformat(),observed_at=at.isoformat())


def agent_contract():
    """Describe the implemented nested inputs so generic agents need not guess fields."""
    return dict(schema='growth.app-sales-funnel-input.v1',
        definition_fields=['release','locale','currency','cohort_id','outcome','creative_refs','hook','cta','destination','route','stages','attribution','offer_boundary'],
        outcome_fields=['audience','pain','research_refs','milestone','metric','target','due_at'],
        source_fields=['kind','id','version','sha256'],source_kinds=['CREATIVE_BRIEF','CUSTOMER_WORKFLOW'],
        source_selection='Read workspace.read: briefs current id/version/hash; subscription_growth.customer_workflows.history id/hash uses immutable version1; ledger cohort identities.',
        stage_fields=['id','type','label','parents','unit','denominator_definition'],
        stage_types=sorted(STAGE_TYPES),stage_units=sorted(UNITS),routes=sorted(ROUTES),
        attribution_fields=['method','identity_scope','starts_at','ends_at','conversion_window_seconds'],
        offer_boundary_fields=['free_deliverables','paid_deliverables'],
        observation_fields=['event_id','stage_id','source_ref','source_sha256','cohort_id','starts_at','ends_at','observed_at','coverage','count','unit','denominator_definition','identity_scope'],
        coverage=['OBSERVED','PARTIAL','UNKNOWN'],unknown_count='UNKNOWN requires null; observed zero remains0.',
        bounds=dict(stages=32,creative_refs=20,research_refs=20,import_rows=500,definitions_per_app=1000,observations_per_definition=10000),
        binding='Use exact current app version, latest source hashes and an existing matching release/locale/currency/cohort acquisition window. Save responses return the immutable funnel hash for imports.',
        graph='Parents must be distinct earlier stage IDs. No cycles, guessed identities or hidden fields.',
        observation_scope='Counts require declared units, population and identity scope; evidence timestamps follow their completed observation window and cannot be future.',
        report='Aggregate ratios do not prove person transitions or growth. Payments and refunds come from the existing ledger. Inspect findings and unknowns.',
        authority='Input descriptions grant no execution or approval authority. Use owner-issued scope and required human checkpoints. No automatic retry after uncertain writes.')
