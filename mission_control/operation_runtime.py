"""Fixed operation dispatch reuses the authoritative existing WMM domain services."""
from .operation_catalog import request_data


def execute(service,envelope):
    """An authenticated gateway admits first; this internal dispatcher adds no authority."""
    from .agent_operations import discovery
    from .customer_workflow_store import CustomerWorkflows
    from .experiments import Experiments
    from .growth_review_store import GrowthReviews
    from .ledger import Ledger
    from .worker import jobs
    from .hypit_jobs import HypitRenders
    from .creative_rendering import Renders
    from .video_edit_projects import Projects
    from .managed_media_store import Media
    from .video_edit_jobs import EditRenders
    request_data(envelope)
    if envelope['operation'].startswith('studio.'):
        return service.studio.dispatch(envelope)
    app=envelope['app_id'];body=envelope['input'];store=service.store
    resource=envelope.get('resource_id')
    routes={
        'workspace.read':lambda:service.workspace(app),
        'evidence.save':lambda:save_evidence(service,app,body),
        'pipeline.prepare':lambda:service.queue(app,body),
        'jobs.read':lambda:jobs(store,app),
        'hypit.read':lambda:HypitRenders(store).list(app),
        'hypit.queue':lambda:HypitRenders(store).queue(app,body),
        'native.read':lambda:Renders(store).list(app),
        'native.queue':lambda:Renders(store).queue(app,body),
        'media.sources':lambda:Media(store).sources(app),
        'editor.list':lambda:Projects(store,'SCOPED_AGENT').list(app),
        'editor.renders':lambda:EditRenders(store).list(app),
        'editor.queue':lambda:EditRenders(store).queue(app,body),
        'editor.read':lambda:Projects(store,'SCOPED_AGENT').read(app,resource),
        'editor.save':lambda:Projects(store,'SCOPED_AGENT').save(app,body),
        'editor.edit':lambda:Projects(store,'SCOPED_AGENT').edit(app,resource,body),
        'editor.history':lambda:Projects(store,'SCOPED_AGENT').history(app,resource,body),
        'editor.diff':lambda:Projects(store,'SCOPED_AGENT').diff(app,resource,body),
        'job.cancel':lambda:service.cancel(app,resource),
        'operations.read':lambda:discovery(store.app(app)),
        'growth.read':lambda:service.subscription_review(app),
        'growth.history':lambda:GrowthReviews(store).list(app),
        'growth.save':lambda:GrowthReviews(store).save(app,body),
        'customer.history':lambda:CustomerWorkflows(store).list(app),
        'customer.save':lambda:CustomerWorkflows(store).save(app,body),
        'measurement.read':lambda:Ledger(store.path).reports(app),
        'snapshot.export':lambda:store.export(app),
        'cohort.define':lambda:service.cohort(app,body),
        'events.import':lambda:service.events(app,body),
        'billing.save':lambda:service.evidence(app,body),
        'experiment.register':lambda:Experiments(store).create(app,body),
        'experiment.evaluate':lambda:Experiments(store).evaluate(app,resource),
        'experiment.action':lambda:Experiments(store).act(app,resource,body)}
    return routes[envelope['operation']]()


def save_evidence(service,app,body):
    """Preserve record kind and current version before the store's atomic write check."""
    from .common import Invalid
    request_data(dict(app_id=app,operation='evidence.save',input=body))
    old=next((r for r in service.store.records(app) if r['id']==body['id']),None)
    expected=old['version'] if old else None
    if expected is not None and type(body.get('version')) is not int:raise Invalid('Use the exact integer evidence revision')
    if body.get('version')!=expected:raise Invalid('Evidence revision changed; reload before saving')
    if old and (old['kind']=='connection' or old['kind']!=body['kind']):
        raise Invalid('Workflow evidence cannot replace a connection or change record kind')
    # Concurrent creation/update changes the version; Store.save_record rejects it.
    return service.evidence(app,body)
