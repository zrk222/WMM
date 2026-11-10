"""Fixed operation dispatch reuses the authoritative existing WMM domain services."""
from .operation_catalog import request_data


def execute(service,envelope,*,caller='SCOPED_AGENT'):
    """An authenticated gateway admits first; this internal dispatcher adds no authority."""
    from .common import Invalid
    if caller not in ('LOCAL_SESSION','SCOPED_AGENT'):
        raise Invalid('Unknown operation caller')
    from .agent_operations import discovery
    from .customer_workflow_store import CustomerWorkflows
    from .experiments import Experiments
    from .growth_review_store import GrowthReviews
    from .ledger import Ledger
    from .ios_reports import read as report_read
    from .worker import jobs
    from .hypit_jobs import HypitRenders
    from .creative_rendering import Renders
    from .video_edit_projects import Projects
    from .managed_media_store import Media
    from .funnel_store import Funnels
    from .funnel_founder_review import review as funnel_review
    from .activity_timeline import read as activity_read
    from .video_edit_jobs import EditRenders
    request_data(envelope)
    if envelope['operation'].startswith('observational-campaign.'):
        from .observational_campaign import ObservationalCampaign
        from .operation_authority import protected
        action = envelope['operation'].split('.')[1]
        with protected(service.store, envelope):
            return ObservationalCampaign(service.store).dispatch(
                envelope['app_id'], action, envelope['input'],
            )
    if envelope['operation']=='evidence.save' and envelope['input']['kind']=='asset':
        data=envelope['input']['data']
        if isinstance(data,dict) and (data.get('authentic') is True or data.get('rights_cleared') is True):
            from .operation_authority import REQUEST,protected
            context=REQUEST.get()
            owner=caller=='LOCAL_SESSION' and context and context.get('principal') and 'grant_id' not in context
            reviewed=caller=='SCOPED_AGENT' and context and context.get('grant_id') and context.get('review')
            if not owner and not reviewed:raise PermissionError('Asset authenticity and rights require a current owner or independently reviewed request')
            with protected(service.store,envelope):return save_evidence(service,envelope['app_id'],envelope['input'])
    if envelope['operation'] in ('creative.source.save','creative.analysis.save','creative.profile.save',
                                 'creative.requirement.save','creative.brief.save'):
        from .operation_authority import REQUEST,protected
        from .creative_library import Library
        from .creative_analysis import Analyses
        from .production_feasibility import Capabilities
        from .creative_briefs import Briefs
        context=REQUEST.get()
        owner=caller=='LOCAL_SESSION' and context and context.get('principal') and 'grant_id' not in context
        reviewed=caller=='SCOPED_AGENT' and context and context.get('grant_id') and context.get('review')
        if not owner and not reviewed:
            raise PermissionError('Creative source, inspection and rights assertions require a current owner or independently reviewed request')
        app=envelope['app_id'];body=envelope['input'];store=service.store
        if ('id' in body)!=('version' in body):raise Invalid('Supply both resource ID and exact version for a correction')
        routes={'creative.source.save':lambda:Library(store).save(app,body),
                'creative.analysis.save':lambda:Analyses(store).save(app,body),
                'creative.profile.save':lambda:Capabilities(store).save(app,'profile',body),
                'creative.requirement.save':lambda:Capabilities(store).save(app,'requirement',body),
                'creative.brief.save':lambda:Briefs(store).save(app,body)}
        with protected(store,envelope):return routes[envelope['operation']]()
    if envelope['operation'].startswith('creative.batch.'):
        from .operation_authority import protected
        from .creative_batches import Batch
        batch=Batch(service.store);action=envelope['operation'].removeprefix('creative.batch.')
        with protected(service.store,envelope):
            if action=='plan':return batch.plan(envelope['app_id'],envelope['input'])
            if action=='create':return batch.create(envelope['app_id'],envelope['input'])
            if action=='list':return batch.list(envelope['app_id'])
            if action=='cancel':return batch.cancel(envelope['app_id'],envelope['input']['batch_id'])
            raise Invalid('Unknown creative batch operation')
    if envelope['operation'] in ('handoff.create','handoff.resume'):
        from .operation_authority import protected
        from .agent_handoffs import Handoffs
        if caller!='SCOPED_AGENT':raise PermissionError('A scoped agent admission is required')
        with protected(service.store,envelope):
            handoffs=Handoffs(service.store)
            if envelope['operation']=='handoff.create':return handoffs.create(envelope['app_id'],None,envelope['input'])
            return handoffs.resume(envelope['app_id'],dict(envelope['input'],id=envelope['resource_id']))
    if envelope['operation'] in ('experiment.schedule','experiment.schedule-run'):
        from .operation_authority import REQUEST,protected
        from .experiment_schedules import Schedules
        context=REQUEST.get()
        if caller!='LOCAL_SESSION' or not context or not context.get('principal') or 'grant_id' in context:
            raise PermissionError('Experiment monitoring requires a verified owner')
        with protected(service.store,envelope):
            if envelope['operation']=='experiment.schedule-run':
                return Schedules(service.store).run_foreground(envelope['app_id'],envelope['resource_id'],owner=context['principal'])
            return Schedules(service.store).save(envelope['app_id'],envelope['resource_id'],envelope['input'],owner=context['principal'])
    if envelope['operation'].startswith('campaign.'):
        from .campaign_access import dispatch
        from .operation_authority import protected
        with protected(service.store,envelope):
            return dispatch(service.store,envelope['app_id'],envelope['operation'].split('.')[1],envelope['input'])
    if envelope['operation'].startswith('publication.'):
        from .agent_dispatch import dispatch as publication_dispatch
        return publication_dispatch(service,envelope,caller=caller)
    if envelope['operation'].startswith('studio.'):
        return service.studio.dispatch(envelope)
    if envelope['operation'].startswith('packaging.'):
        from .packaging_access import dispatch
        action=envelope['operation'].split('.')[1]
        if action=='editor-prepare':
            from .operation_authority import protected
            with protected(service.store,envelope):
                return dispatch(service.store,envelope['app_id'],action,envelope['input'])
        return dispatch(service.store,envelope['app_id'],action,envelope['input'])
    if envelope['operation'].startswith('organic-video.'):
        from .operation_authority import protected
        from .organic_video_collector import claim, submit
        if caller != 'SCOPED_AGENT':
            raise PermissionError('Video gateway operations require a scoped agent')
        with protected(service.store, envelope) as actor:
            if envelope['operation'] in ('organic-video.claim','organic-video.submit'):
                action = {'organic-video.claim': claim, 'organic-video.submit': submit}[envelope['operation']]
                return action(service.store, envelope['app_id'], actor, envelope['input'])
            from .organic_video_access import dispatch
            return dispatch(service.store,envelope['app_id'],envelope['operation'].split('.')[1],envelope['input'])
    if envelope['operation'].startswith('discovery.'):
        from .discovery_access import dispatch
        return dispatch(service.store,envelope['app_id'],envelope['operation'].split('.')[1],envelope['input'])
    app=envelope['app_id'];body=envelope['input'];store=service.store
    resource=envelope.get('resource_id')
    routes={
        'report.read':lambda:report_read(store,app),
        'workspace.read':lambda:service.workspace(app),
        'evidence.save':lambda:save_evidence(service,app,body),
        'pipeline.prepare':lambda:service.queue(app,body),
        'jobs.read':lambda:jobs(store,app),
        'hypit.read':lambda:HypitRenders(store).list(app),
        'hypit.plan':lambda:HypitRenders(store).plan(app,body),
        'hypit.reuse':lambda:HypitRenders(store).reuse(app,body),
        'hypit.queue':lambda:HypitRenders(store).queue(app,body),
        'native.read':lambda:Renders(store).list(app),
        'native.queue':lambda:Renders(store).queue(app,body),
        'funnel.list':lambda:Funnels(store).list(app,body.get('offset',0)),
        'funnel.review':lambda:funnel_review(store,app,body.get('offset',0)),
        'funnel.read':lambda:Funnels(store).read(app,resource),
        'funnel.save':lambda:Funnels(store).save(app,body),
        'funnel.observations':lambda:Funnels(store).observations(app,resource,body.get('offset',0)),
        'funnel.import':lambda:Funnels(store).ingest(app,dict(body,funnel_id=resource)),
        'funnel.report':lambda:Funnels(store).report(app,resource),
        'media.sources':lambda:Media(store).sources(app),
        'editor.list':lambda:Projects(store,caller).list(app),
        'editor.renders':lambda:EditRenders(store).list(app),
        'editor.queue':lambda:EditRenders(store).queue(app,body),
        'editor.read':lambda:Projects(store,caller).read(app,resource),
        'editor.save':lambda:Projects(store,caller).save(app,body),
        'editor.edit':lambda:Projects(store,caller).edit(app,resource,body),
        'editor.history':lambda:Projects(store,caller).history(app,resource,body),
        'editor.diff':lambda:Projects(store,caller).diff(app,resource,body),
        'job.cancel':lambda:service.cancel(app,resource),
        'operations.read':lambda:discovery(store.app(app),body.get('profile')),
        'activity.history':lambda:activity_read(store,app,kind=body.get('kind'),status=body.get('status'),
                                                cursor=body.get('cursor'),limit=body.get('limit',20)),
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
