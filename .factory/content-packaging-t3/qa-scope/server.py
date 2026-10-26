def get_history(self,app_id,kind):
    """Export only registered app-scoped histories through exact addresses."""
    from .aeo_portable import export_aeo
    from .attribution_portable import export_attribution
    exporters={'aeo':export_aeo,'attribution':export_attribution}
    store=self.server.service.store
    store.app(app_id)
    if urlparse(self.path).query:
        raise Invalid('Use the exact app '+kind+' history address')
    with connection(store.path) as db:
        value=exporters[kind](db,app_id)
    return self.send(200,value,filename=app_id+'-'+kind+'-history.json')


def post(self,path):
    """Parse finite object requests or process a bounded image upload."""
    service=self.server.service
    parts=path.strip("/").split("/")
    if len(parts)==4 and parts[:2]==["api","apps"] and parts[3]=="files":
        return self.send(201,service.upload(parts[2],unquote(self.headers.get("X-Filename","image.png")),self.body(8388608)))
    domain=owner_domain_post(parts)
    if domain is not None:return domain(self,parts)
    data=self.post_data(path,parts)
    if path=='/api/social/callback':
        from .social_callbacks import callback
        return self.send(200,callback(service.store,data,self.server.server_port))
    if parts[:2]==["api","identity"]:return self.post_identity(parts,data)
    ordinary={'/api/worker/retry':lambda:self.retry_worker(data),
              '/api/play/callback':lambda:self.play_callback(data),
              '/api/apps':lambda:self.send(201,service.store.save_app(data.get('id'),data.get('data',{}),data.get('version'))),
              '/api/restore':lambda:self.send(201,service.store.restore(data))}
    if path in ordinary:
        return ordinary[path]()
    if len(parts)<4 or parts[:2]!=["api","apps"]:
        raise KeyError(path)
    return self.post_app(parts,data)


def retry_worker(self,data):
    """Bind explicit shared-worker recovery to a current workspace session."""
    if urlparse(self.path).query or set(data)!={"app_id","manifest_version"} or type(data["manifest_version"]) is not int or not isinstance(data["app_id"],str):
        raise Invalid("Reload the current workspace before retrying automation")
    with connection(self.server.service.store.path) as db:
        db.execute("BEGIN IMMEDIATE")
        row=db.execute("SELECT version FROM apps WHERE id=?",(data["app_id"],)).fetchone()
        if row is None or row["version"]!=data["manifest_version"]:
            raise Invalid("App setup changed; refresh saved work before retrying automation")
        result=self.server.runner.retry_failed()
    return self.send(200,result)


def owner_domain_post(parts):
    """Resolve only fixed private domain modules, retaining lazy imports."""
    if len(parts)<4 or parts[:2]!=['api','apps']:return None
    module={'drive':'drive_http','media':'managed_media_http','funnels':'funnel_http',
            'discovery':'discovery_http','packaging':'packaging_http'}.get(parts[3])
    if module is None:return None
    from importlib import import_module
    return import_module('.'+module,__package__).post
