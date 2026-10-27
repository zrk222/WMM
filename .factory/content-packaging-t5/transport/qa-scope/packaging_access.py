def dispatch(store, app_id, action, body):
    """Existing owner/grant gateways provide exact authority for domain calls."""
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
