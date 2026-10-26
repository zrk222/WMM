"""Fixed local upgrade operations shared by CLI and MCP protocol adapters."""
import copy
import re
from .common import Invalid,digest


def descriptor(method,suffix,effect,required=(),optional=(),resource=False):
    """Describe a closed envelope; nested domain validation remains server authoritative."""
    return dict(method=method,suffix=suffix,effect=effect,required=list(required),optional=list(optional),resource=resource)


OPERATIONS={
    'discovery.history':descriptor('POST','/discovery/history','READ_PRIVATE_LOCAL_DATA',('kind',),('offset',)),
    'discovery.read':descriptor('POST','/discovery/read','READ_PRIVATE_LOCAL_DATA',('id','kind'),('version',)),
    'discovery.review':descriptor('POST','/discovery/review','WRITE_LOCAL_EVIDENCE',('id','version','manifest_version','reference_id','source_hash','data')),
    'discovery.collect':descriptor('POST','/discovery/collect','WRITE_LOCAL_EVIDENCE',('id','version','manifest_version','query','attempted_sources','failed_sources')),
    'discovery.watch':descriptor('POST','/discovery/watch','WRITE_LOCAL_EVIDENCE',('id','version','manifest_version','data')),
    'discovery.attempt':descriptor('POST','/discovery/attempt','WRITE_LOCAL_EVIDENCE',('id','manifest_version','watch_id','watch_hash','collection_id','collection_hash','source_results')),
    'discovery.handoff':descriptor('POST','/discovery/handoff','READ_PRIVATE_LOCAL_DATA',('manifest_version','collection_id','collection_hash','reference_id','review_hash')),
    'workspace.read':descriptor('GET','','READ_PRIVATE_LOCAL_DATA'),
    'evidence.save':descriptor('POST','/workflow-evidence','WRITE_LOCAL_EVIDENCE',('id','manifest_version','kind','title','source','data'),('version',)),
    'pipeline.prepare':descriptor('POST','/jobs','QUEUE_LOCAL_PREPARATION',('action','data','request_key')),
    'jobs.read':descriptor('GET','/jobs','READ_PRIVATE_LOCAL_DATA'),
    'hypit.read':descriptor('GET','/hypit-renders','READ_PRIVATE_LOCAL_DATA'),
    'hypit.queue':descriptor('POST','/production/hypit-renders','QUEUE_LOCAL_PREPARATION',('data','request_key')),
    'studio.plan':descriptor('POST','/studio/plan','READ_PRIVATE_EXECUTION_PLAN',('source_job_id','manifest_version')),
    'studio.start':descriptor('POST','/studio/start','START_OWNED_LOCAL_NATIVE_SESSION',('source_job_id','manifest_version','summary_hash','request_key')),
    'studio.sessions':descriptor('POST','/studio/sessions','READ_PRIVATE_LOCAL_DATA'),
    'studio.read':descriptor('POST','/studio/{resource_id}/read','READ_PRIVATE_LOCAL_DATA',(),(),True),
    'studio.edit':descriptor('POST','/studio/{resource_id}/edit','WRITE_PRIVATE_NATIVE_SOURCE',('request_key','base_version','base_hash','parameter'),(),True),
    'studio.inspect':descriptor('POST','/studio/{resource_id}/inspect','READ_PRIVATE_LOCAL_DATA',(),(),True),
    'studio.close':descriptor('POST','/studio/{resource_id}/close','STOP_OWNED_LOCAL_NATIVE_SESSION',(),(),True),
    'native.read':descriptor('GET','/native-renders','READ_PRIVATE_LOCAL_DATA'),
    'native.queue':descriptor('POST','/production/renders','QUEUE_LOCAL_PREPARATION',('data','request_key')),
    'funnel.list':descriptor('GET','/funnels','READ_PRIVATE_LOCAL_DATA',(),('offset',)),
    'funnel.review':descriptor('GET','/funnels/_review','READ_PRIVATE_LOCAL_DATA',(),('offset',)),
    'funnel.read':descriptor('GET','/funnels/{resource_id}','READ_PRIVATE_LOCAL_DATA',(),(),True),
    'funnel.save':descriptor('POST','/funnels','WRITE_LOCAL_EVIDENCE',('id','manifest_version','data')),
    'funnel.observations':descriptor('GET','/funnels/{resource_id}/observations','READ_PRIVATE_LOCAL_DATA',(),('offset',),True),
    'funnel.import':descriptor('POST','/funnels/{resource_id}/observations','WRITE_LOCAL_EVIDENCE',('funnel_hash','manifest_version','observations'),(),True),
    'funnel.report':descriptor('GET','/funnels/{resource_id}/report','READ_PRIVATE_LOCAL_DATA',(),(),True),
    'media.sources':descriptor('GET','/media/sources','READ_PRIVATE_LOCAL_DATA'),
    'editor.list':descriptor('GET','/video-projects','READ_PRIVATE_LOCAL_DATA'),
    'editor.renders':descriptor('GET','/video-edit-renders','READ_PRIVATE_LOCAL_DATA'),
    'editor.queue':descriptor('POST','/video-edit-renders','QUEUE_LOCAL_PREPARATION',('data','request_key')),
    'editor.read':descriptor('GET','/video-projects/{resource_id}','READ_PRIVATE_LOCAL_DATA',(),(),True),
    'editor.save':descriptor('POST','/video-projects','WRITE_LOCAL_PLAN',('id','revision','manifest_version','data','request_key')),
    'editor.edit':descriptor('POST','/video-projects/{resource_id}/edits','WRITE_LOCAL_PLAN',('revision','manifest_version','command','request_key'),(),True),
    'editor.history':descriptor('POST','/video-projects/{resource_id}/history','WRITE_LOCAL_PLAN',('revision','manifest_version','operation','request_key'),('target_revision',),True),
    'editor.diff':descriptor('POST','/video-projects/{resource_id}/diff','READ_PRIVATE_LOCAL_DATA',('from_revision','to_revision'),(),True),
    'job.cancel':descriptor('POST','/jobs/{resource_id}/cancel','CANCEL_LOCAL_JOB',(),(),True),
    'operations.read':descriptor('GET','/agent-operations','READ_LOCAL_POLICY'),
    'growth.read':descriptor('GET','/subscription-growth','READ_PRIVATE_LOCAL_DATA'),
    'growth.history':descriptor('GET','/subscription-growth/history','READ_PRIVATE_LOCAL_DATA'),
    'growth.save':descriptor('POST','/subscription-growth/entries','WRITE_LOCAL_EVIDENCE',('id','manifest_version','kind','data')),
    'customer.history':descriptor('GET','/customer-workflows','READ_PRIVATE_LOCAL_DATA'),
    'customer.save':descriptor('POST','/customer-workflows','WRITE_LOCAL_EVIDENCE',('id','manifest_version','data')),
    'measurement.read':descriptor('GET','/measurement','READ_PRIVATE_LOCAL_DATA'),
    'snapshot.export':descriptor('GET','/export','READ_PRIVATE_LOCAL_DATA'),
    'cohort.define':descriptor('POST','/cohorts','WRITE_LOCAL_EVIDENCE',('cohort_id','release','platform','locale','currency','starts_at','ends_at','matures_at','attribution_method','observability','source')),
    'events.import':descriptor('POST','/events','WRITE_LOCAL_EVIDENCE',('cohort_id','events')),
    'billing.save':descriptor('POST','/records','WRITE_LOCAL_EVIDENCE',('id','manifest_version','kind','title','source','data')),
    'experiment.register':descriptor('POST','/experiments','WRITE_LOCAL_PLAN',('manifest_version','name','hypothesis','owner','primary_metric','baseline_rate','minimum_detectable_effect','treatment_allocation','analysis_at','assignment_method','assignment_source','guardrails','stop_rule','rollback_plan','control','treatment')),
    'experiment.evaluate':descriptor('POST','/experiments/{resource_id}/evaluate','WRITE_LOCAL_ASSESSMENT',(),(),True),
    'experiment.action':descriptor('POST','/experiments/{resource_id}/actions','WRITE_LOCAL_DECISION',('operation','version'),('source','observed_at','decision','reason','assessment_hash','target'),True)
}


def catalog():
    """Return inspectable transport capabilities without granting agent or human authority."""
    value=dict(schema='growth.operation-catalog.v1',operations=copy.deepcopy(OPERATIONS),
        envelope=dict(required=['app_id','operation','input'],optional=['resource_id']),
        input_validation='Exact top-level fields here; authoritative nested domain checks run on the existing server.',
        transport='EXACT_LOOPBACK_HTTP_WITH_SCOPED_BEARER_OR_TRUSTED_LOCAL_SESSION',
        authority='Scoped bearer grants enforce current app, owner role, operations, expiry, revocation and call limits. Trusted local browser sessions are separate; neither grants human approval.',
        review=dict(prepare='/api/agent-operations/reviews/prepare',status='/api/agent-operations/reviews/status',resume='/api/agent-operations/reviews/resume',
            approval='SEPARATE_FRESH_HUMAN_IDENTITY_DISTINCT_CHECKER',policy='OWNER_SELECTED_WRITE_OPERATIONS',input='IMMUTABLE_EXACT_ENVELOPE_AND_GRANT',replay='DENIED_AFTER_CLAIM'),
        workflow=dict(sequence=['workspace.read','evidence.save','pipeline.prepare','jobs.read'],
            job_submission='QUEUED_IS_NOT_COMPLETED',job_result='Read the saved job status and result; pipeline preparation never publishes or spends.',
            cancellation='Stops future local work where supported; running effects and receipts require inspection.'),
        denied=['human_approval','identity_login','credentials','provider_mutation','publish','spend','arbitrary_http','shell_execution'],
        full_agent_operation=False,remaining=['Full-domain operation coverage','Full-domain CLI/MCP conformance','Provider-specific authorized effect adapters'])
    from .funnel_contract import agent_contract
    from .discovery_contract import agent_contract as discovery_contract
    value['domain_contracts']={'app_sales_funnel':agent_contract(),'discovery_research':discovery_contract()}
    return dict(value,catalog_sha256=digest(value))


def path_segment(value):
    """Do not permit query, encoded slash, traversal, host or arbitrary path injection."""
    if not isinstance(value,str) or not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,199}',value):
        raise Invalid('Use a lowercase app or resource identifier containing letters, digits and hyphens')
    return value


def exact_keys(value,required,optional=()):
    """Close protocol boundaries before any transport or bootstrap side effect."""
    if not isinstance(value,dict) or set(required)-set(value) or set(value)-set(required)-set(optional):
        raise Invalid('Operation fields must match the declared required and optional names')


def local_constraints(operation,body):
    """Limit existing general record/action routes to the intended local evidence domain."""
    if operation in ('funnel.list','funnel.observations','funnel.review') and 'offset' in body:
        from .pmf_contract import count
        count(body['offset'],0,10000)
    if operation=='billing.save' and body['kind']!='billing':
        raise Invalid('billing.save accepts billing evidence only')
    if operation=='experiment.action' and body['operation'] not in ('observe','decide','cancel','rollback'):
        raise Invalid('Use only the existing local experiment lifecycle actions')
    if operation=='evidence.save':
        path_segment(body['id'])
        from .catalog import FIELDS
        if not isinstance(body['kind'],str) or body['kind'] not in FIELDS or body['kind']=='connection':
            raise Invalid('Use a known local evidence type; connection credentials require separate human setup')
    if operation=='pipeline.prepare':
        pipeline_input(body)


def pipeline_input(body):
    """Close the generic job route to local stage preparation before transport."""
    if body['action']!='pipeline':raise Invalid('pipeline.prepare permits local pipeline preparation only')
    exact_keys(body['data'],('stage',))
    stage=body['data']['stage']
    if type(stage) is not int or not 0<=stage<=12:raise Invalid('Choose local pipeline stage 0 through 12')
    if not isinstance(body['request_key'],str) or not body['request_key'].strip() or len(body['request_key'])>120:
        raise Invalid('Use a pipeline request key containing 1 through 120 characters')


def request_data(envelope):
    """Validate a catalog call and resolve only its fixed app-owned route."""
    exact_keys(envelope,('app_id','operation','input'),('resource_id',))
    app_id=path_segment(envelope['app_id'])
    name=envelope['operation']
    if not isinstance(name,str) or name not in OPERATIONS:
        raise Invalid('Unknown or unauthorized operation; inspect the fixed catalog')
    rule=OPERATIONS[name]
    exact_keys(envelope['input'],rule['required'],rule['optional'])
    suffix=rule['suffix']
    if rule['resource']:
        suffix=suffix.replace('{resource_id}',path_segment(envelope.get('resource_id')))
    elif 'resource_id' in envelope:
        raise Invalid('This operation has no resource identifier')
    local_constraints(name,envelope['input'])
    if rule['method']=='GET' and 'offset' in envelope['input']:
        suffix+='?offset='+str(envelope['input']['offset'])
    return dict(method=rule['method'],path='/api/apps/'+app_id+suffix,body=envelope['input'] if rule['method']=='POST' else None)
