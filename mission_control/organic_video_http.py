"""Fresh-owner admission for bounded external-agent video research tasks."""
import secrets

from .common import Invalid, identifier
from .discovery_http import json_body
from .managed_media_http import singleton
from .operation_authority import bound_owner, protected
from .organic_video_collector import prepare

POLICY_ACTIONS = {'policy-create': 'create', 'policy-read': 'read', 'policy-revoke': 'revoke',
                  'policy-reserve': 'reserve', 'policy-admit': 'admit'}
INTENT_ACTIONS = {'intent-create', 'intent-read', 'intent-execute', 'intent-reconcile'}
SCHEDULE_ACTIONS = {'schedule-prepare', 'schedule-activate', 'schedule-status', 'schedule-revoke'}


def post(handler, parts):
    """Preparing research is owner-only; recipient agents use the scoped gateway."""
    if (len(parts) != 5 or parts[:2] != ['api', 'apps']
            or parts[3] != 'organic-video' or parts[4] not in {'prepare', 'task-read', 'intake', *POLICY_ACTIONS, *INTENT_ACTIONS, *SCHEDULE_ACTIONS}):
        raise Invalid('Use the exact video research preparation address')
    identifier(parts[2])
    if handler.command != 'POST' or handler.path != '/' + '/'.join(parts):
        raise Invalid('Use an exact video research POST without query')
    origin = 'http://127.0.0.1:' + str(handler.server.server_port)
    if handler.headers.get_all('Host') != [origin[7:]]:
        raise PermissionError('Use the exact local video research host')
    if handler.headers.get_all('Origin') != [origin]:
        raise PermissionError('Use the exact local video research origin')
    if handler.headers.get_all('Authorization') is not None:
        raise PermissionError('Video research preparation requires an owner session only')
    session = handler.session()
    user = handler.server.identities.fresh(session)
    if not secrets.compare_digest(singleton(handler, 'X-CSRF-Token'), session):
        raise PermissionError('Reload the current video research session')
    body = json_body(handler, 'Video research')
    store = handler.server.service.store
    action = parts[4]
    envelope = dict(app_id=parts[2], operation='organic-video.' + action, input=body)
    with bound_owner(store, envelope, handler.server.identities, session, user):
        with protected(store, envelope) as actor:
            if action == 'prepare':
                result = prepare(store, parts[2], actor, body)
            elif action in SCHEDULE_ACTIONS:
                result = schedule(store, parts[2], action, body)
            elif action == 'intake':
                from .organic_video_intake import adopt
                result = adopt(store, parts[2], actor, body)
            elif action == 'task-read':
                from .organic_video_discovery import exact
                from .organic_video_collector import _row, _view
                from .db import connection
                import json
                exact(body, ('task_id',))
                with connection(store.path) as db:
                    row = _row(db, parts[2], body['task_id'])
                    if row['owner'] != actor:
                        raise PermissionError('Video research belongs to another owner')
                    result = dict(_view(row), submission=json.loads(row['submission']) if row['submission'] else None,
                                  result_hash=row['result_hash'])
            elif action in INTENT_ACTIONS:
                from . import campaign_video_execution as video
                from .campaign_contract import exact
                if action == 'intent-create':
                    result = video.create_intent(store, parts[2], actor, body)
                else:
                    exact(body, ('intent_id',))
                    if action == 'intent-read':
                        from .db import connection
                        from .organic_video_policy import _saved
                        import json
                        with connection(store.path) as db:
                            row = video._row(db, parts[2], body['intent_id'])
                            request = json.loads(row['data'])['request']
                            policy = _saved(db.execute('SELECT * FROM organic_video_policies WHERE app_id=? AND id=?',
                                                       (parts[2], request['policy_id'])).fetchone())
                            if policy['data']['owner'] != actor:
                                raise PermissionError('Reel intent belongs to another owner')
                            result = video._view(row)
                    else:
                        run = video.execute if action == 'intent-execute' else video.reconcile
                        result = run(store, parts[2], actor, body['intent_id'], None)
            else:
                from .organic_video_policy import Policies
                result = getattr(Policies(store), POLICY_ACTIONS[action])(parts[2], body)
            return handler.send(200, result)


def schedule(store, app_id, action, body):
    from .campaign_contract import exact
    from .organic_video_schedule import VideoSchedules
    service = VideoSchedules(store)
    if action == 'schedule-prepare':
        return service.prepare(app_id, body)
    if action == 'schedule-activate':
        return service.activate(app_id, body)
    if action == 'schedule-status':
        exact(body, ('batch_id',))
        return service.status(app_id, body['batch_id'])
    exact(body, ('batch_id', 'version'))
    from .campaign_schedule import CampaignSchedules
    return CampaignSchedules(store).revoke(app_id, body['batch_id'], body['version'])
