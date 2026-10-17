"""Expert evidence goals and closed tool choices; source text never grants authority."""
import re

GOALS = {
    'app':'Confirm this app identity, audience, job, release and owned destination',
    'readiness':'Prove the complete advertised journey on the named release and devices',
    'measurement':'Verify consent, event meaning, attribution and reconciliation',
    'cohort':'Obtain mature, source-backed cohort denominators and actual costs',
    'claim':'Bind each promise to verified current app behavior',
    'asset':'Obtain authentic release screens with confirmed usage rights',
    'store':'Verify localized metadata, media, review state and public destination',
    'experiment':'Preregister an app-specific test with measurement and stopping rules',
    'distribution':'Verify the channel, intent, destination and exact approved limits',
    'route':'Prove entry routes preserve context through the first useful outcome',
    'billing':'Verify displayed terms, actual purchase, restore and resulting access',
    'retention':'Observe useful repeat value in a mature eligible cohort',
    'evaluation':'Evaluate the declared experiment with mature outcomes and guardrails',
    'learning':'Validate a proposed improvement on a holdout with rollback',
    'review':'Investigate the reported failure and verify the repair'
}

PRIORITY = {
    'app':('collect_sources','inspect_site'),
    'readiness':('inspect_site','collect_sources'),
    'measurement':('refresh_analytics','collect_sources','inspect_site'),
    'cohort':('refresh_analytics','evaluate_experiment','collect_sources'),
    'asset':('collect_sources','inspect_site'),
    'store':('collect_sources','inspect_site'),
    'experiment':('refresh_analytics','evaluate_experiment','inspect_site'),
    'distribution':('inspect_site','collect_sources','refresh_analytics'),
    'billing':('collect_sources','refresh_analytics','inspect_site'),
    'retention':('refresh_analytics','evaluate_experiment'),
    'evaluation':('evaluate_experiment','refresh_analytics'),
    'learning':('evaluate_experiment','refresh_analytics'),
}

TOOL_COPY = {
    'reuse_observation':dict(title='Reuse the current saved public-site observation',
        access='This app exact native observation; no network or credential access',
        artifact='The existing source-hashed observation and its public repair codes',
        verifies='Observation integrity, app/target identity and24-hour freshness',
        limits='Does not rerun the website check or verify native/authenticated journeys or business outcomes',
        fallback='Approve a fresh public inspection if the source changed or the saved observation expired'),
    'collect_sources':dict(title='Have the agent collect connected provider facts',
        access='Existing app-owned read-only provider connections',
        artifact='Saved identity, review, subscription and selected-release source receipts',
        verifies='Provider identity, observed configuration and returned coverage',
        limits='Does not prove app behavior, ownership rights, purchases, retention or campaign success',
        fallback='Review source access, reconnect the exact app, or inspect its public destination'),
    'inspect_site':dict(title='Have the agent inspect the public destination',
        access='Credential-free HTTPS on this app website origin only',
        artifact='Source-linked page, robots and indexability inspection with repair findings',
        verifies='What the public page returned and the checks actually observed',
        limits='Does not prove authenticated journeys, native screens, payments, indexing or citations',
        fallback='Edit the same-origin target, resolve the reported transport issue, or collect provider facts'),
    'refresh_analytics':dict(title='Have the agent refresh connected measurement',
        access='Existing consented, app-dedicated analytics source',
        artifact='Saved provider report with source configuration and coverage',
        verifies='Returned aggregates and current source access',
        limits='Aggregates alone do not verify event semantics, randomization, costs or mature cohort outcomes',
        fallback='Review analytics permissions or connect an app-dedicated source'),
    'evaluate_experiment':dict(title='Have the agent evaluate the registered experiment',
        access='This app immutable experiment and its existing permitted observations',
        artifact='Source-bound assessment or an explicit maturity/coverage gap',
        verifies='Declared sample, maturity, quality and guardrail checks on supplied evidence',
        limits='Imported comparisons remain descriptive; no automatic winner, rollout or spending',
        fallback='Collect the missing eligible outcomes, wait for the declared maturity, or repair tracking'),
}


def issue_kind(message,primary):
    """Closed kind recognition; unexpected source text becomes an investigation."""
    match=re.match(r'^Add current ([a-z_]+) evidence',message)
    if match and match[1] in GOALS:return match[1]
    if message.startswith('Verify selected App Store release:'):return 'store'
    if message.startswith('Verify App Store subscription catalog:'):return 'billing'
    if message.startswith('Reconcile '):return 'cohort'
    return primary if primary in GOALS else 'review'


def ordered_tools(kind):
    """Prefer a task-relevant action while keeping an alternative source path."""
    first=PRIORITY.get(kind,('inspect_site','collect_sources'))
    return (*first,*(t for t in TOOL_COPY if t not in first))
