"""Fixed app-owned setup actions inside the existing session/CSRF boundary."""
from .common import Invalid
from .setup_discovery import SetupDiscovery
from .setup_approval import apply


def post(store, app_id, parts, body):
    """No arbitrary destination, credential, command or caller result is accepted."""
    store.app(app_id)
    if len(parts) != 1:
        raise Invalid('Use one exact setup discovery action')
    service = SetupDiscovery(store)
    actions = {'discover': lambda: service.get(app_id, service.start(app_id, body)['id']),
               'apply': lambda: apply(store, app_id, body),
               'delete': lambda: service.delete(app_id, body)}
    if parts[0] not in actions:
        raise Invalid('Choose discovery, selected-field approval or local draft deletion')
    return actions[parts[0]]()


def get(store, app_id, parts):
    """GET loads one local proposal and never reads a website or approves changes."""
    if len(parts) != 1:
        raise Invalid('Choose one app-owned saved setup proposal')
    return SetupDiscovery(store).get(app_id, parts[0])
