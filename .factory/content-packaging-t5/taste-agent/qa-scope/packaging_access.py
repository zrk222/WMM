def dispatch(store, app_id, action, body):
    """Existing owner/grant gateways provide exact authority for domain calls."""
    if action in {'taste-review','taste-read','taste-reconcile','taste-history'}:
        from .creative_taste_store import dispatch as taste
        return taste(store,app_id,action,body)
    service=Packaging(store)
    if action=='checklist':
        from .packaging_handoff import preview
        return preview(store,app_id,body)
    if action=='save':return service.save(app_id,body)
    if action=='reconcile':return reconcile(store,app_id,body)
    if action=='read':
        exact_keys(body,{'id','kind'},{'version'})
        return service.read(app_id,body['id'],body['kind'],body.get('version'))
    if action=='history':
        return history(store,app_id,body)
    raise Invalid('Unknown packaging operation')
