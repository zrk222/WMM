"""Closed Google Play UI actions; every read uses the ordinary source-bound queue."""
from .common import Invalid
from .play_contract import operation, package_candidates
from .play_connections import PlayConnections
from .service import Service


def exact(body, keys):
    """No setup request may carry an extra provider operation or authority field."""
    if not isinstance(body, dict) or set(body) != set(keys):
        raise Invalid('Use only the displayed Google Play setup fields')


def discover(body):
    """Return explicit package candidates without saving or executing source text."""
    exact(body, ('kind', 'text'))
    return package_candidates(body['kind'], body['text'])


def cancel(service, app, body):
    """Cancel only the selected app's saved consent flow."""
    exact(body, ('flow_id',))
    return service.stop(app, body['flow_id'])


def cleanup(service, app, body):
    """An explicit cleanup retries recorded native retirements only."""
    exact(body, ())
    return service.cleanup(app)


def queue_read(store, app, body):
    """Keep target and source validation identical for manual and agent-driven reads."""
    exact(body, ('connection_id', 'connection_version', 'manifest_version', 'operation', 'request_key'))
    operation(body['operation'])
    data = {k: body[k] for k in ('connection_id', 'connection_version', 'manifest_version')}
    data['options'] = {'operation': body['operation']}
    return Service(store).queue(app, dict(action='sync', data=data, request_key=body['request_key']))


def post(store, app, parts, body, port):
    """Dispatch exact app-owned Google Play setup and queued-read actions."""
    store.app(app)
    if len(parts) != 1:raise KeyError('Google Play action not found')
    service = PlayConnections(store, port)
    handlers = {'discover': lambda: discover(body), 'start': lambda: service.start(app, body),
                'cancel': lambda: cancel(service, app, body), 'cleanup': lambda: cleanup(service, app, body),
                'read': lambda: queue_read(store, app, body)}
    if parts[0] not in handlers:raise KeyError('Google Play action not found')
    return handlers[parts[0]]()


def finish(store, body, port):
    """Complete one protected Google consent callback using the actual listener port."""
    return PlayConnections(store, port).finish(body)
