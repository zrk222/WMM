"""Fixed operation dispatch reuses the authoritative existing WMM domain services."""
from .operation_catalog import request_data


def execute(service,envelope):
    """An authenticated gateway admits first; this internal dispatcher adds no authority."""
    from .agent_operations import discovery
    from .customer_workflow_store import CustomerWorkflows
    from .experiments import Experiments
    from .growth_review_store import GrowthReviews
    from .ledger import Ledger
    request_data(envelope)
    app=envelope['app_id'];body=envelope['input'];store=service.store
    resource=envelope.get('resource_id')
    routes={
        'workspace.read':lambda:service.workspace(app),
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
