def report_destination(url,body):
    """Verify method-specific fixed destinations before creating an authenticated request."""
    parsed=urlsplit(url)
    if parsed.scheme!="https" or parsed.netloc!=parsed.hostname or parsed.fragment:
        raise Invalid("Unapproved provider report destination")
    query_paths=("/v1/campaigns/query","/v1/reports/apps/campaigns/query","/v1/reports/apps/keywords/query","/v1/reports/apps/searchterms/query")
    allowed=False
    if parsed.hostname=="api.appstoreconnect.apple.com":
        apple_paths = r'/v1/(?:apps/\d+(?:/customerReviews|/subscriptionGroups|/analyticsReportRequests)?|subscriptionGroups/\d+/subscriptions|appStoreVersions/[A-Za-z0-9-]{1,80}(?:/appStoreVersionLocalizations)?|appStoreVersionLocalizations/[A-Za-z0-9-]{1,80}/appScreenshotSets|appScreenshotSets/[A-Za-z0-9-]{1,80}/appScreenshots|analyticsReportRequests/[A-Za-z0-9-]{1,200}/reports|analyticsReports/[A-Za-z0-9-]{1,200}/instances)'
        allowed=body is None and re.fullmatch(apple_paths,parsed.path)
    if parsed.hostname=="api.ads.apple.com":
        allowed=parsed.path in query_paths and body is not None and not parsed.query
    if not allowed:
        raise Invalid("Unapproved provider report destination")

def report_options(provider,options):
    """Validate supported read operations and report dates before queue or network."""
    if not isinstance(options,dict):
        raise Invalid("Choose a report operation")
    operation=options.get("operation")
    if provider=='google_play':
        return google_options(options)
    if operation == 'release_inventory':
        return release_options(provider, options)
    if operation in ("reviews", "subscription_catalog", "analytics_reports") and provider=="app_store" and set(options)=={"operation"}:
        return options
    if operation not in ("campaign_report", *REPORT_PATHS) or provider!="apple_ads" or set(options)!={"operation","start","end","campaign_ids"}:
        raise Invalid("Choose customer reviews or a dated Apple Ads campaign, keyword or search-term report")
    report_dates(options)
    campaign_ids(options["campaign_ids"])
    return options

def read_report(binding,app_id,options):
    """Dispatch a validated app-scoped read; results never authorize external writes."""
    report_options(binding.get("provider"),options)
    if binding.get('provider')=='google_play':
        return google_report(binding,app_id,options)
    store_id=numeric_scope(binding,"store_app_id")
    headers={"Authorization":"Bearer "+credential(binding,app_id)}
    if binding["provider"]=="apple_ads":
        headers["X-AP-Context"]="adAccountId="+numeric_scope(binding,"account_id")
    reader=Reader(headers)
    if options["operation"]=="reviews":
        report=reviews(reader,store_id)
    elif options["operation"]=="subscription_catalog":
        report=read_catalog(reader,store_id)
    elif options["operation"]=="release_inventory":
        report=read_inventory(reader,store_id,options['version_id'])
    elif options["operation"]=="analytics_reports":
        report=read_analytics(reader,store_id)
    elif options["operation"]=="campaign_report":
        report=campaigns(reader,binding,options)
    else:
        verify_campaigns(reader,binding,options["campaign_ids"])
        report=read_keywords(reader,binding,options,query_body,report_pagination)
    return dict(report,provider=binding["provider"],app_id=app_id,store_app_id=store_id,
                observed_at=now(),source_hash=digest(reader.hashes),page_source_hashes=reader.hashes,
                request=options,external_writes=False,scope=("Catalog observation only; approval, prices, purchase and restore require separate verification" if options['operation']=='subscription_catalog' else "Provider observation only; installs do not prove paid or retained customers"))
