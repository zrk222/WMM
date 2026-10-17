"""Dependency-aware stage checks. Operator evidence is not provider verification."""
from datetime import datetime, timezone
from .common import Invalid, iso_time
from .catalog import stages
from .packets import stage_packet
from .journey_readiness import complete as readiness_complete

PASS_KINDS={"readiness","measurement","claim","route","billing","learning","evaluation"}
RELEASE_KINDS={"readiness","measurement","claim","asset","store","route","billing"}
LOCALE_KINDS={"readiness","claim","asset","store"}


def current(record, app):
    """Check release identity, freshness and kind-specific acceptance of evidence."""
    data=record["data"]
    if record["kind"] in RELEASE_KINDS and data.get("release")!=app["data"].get("release"):
        return False
    if record["kind"] in LOCALE_KINDS:
        if not app["data"].get("locale") or data.get("locale")!=app["data"].get("locale"):
            return False
    if record["kind"] in PASS_KINDS and data.get("result")!="PASS":
        return False
    if data.get("checked_at"):
        age=(datetime.now(timezone.utc)-iso_time(data["checked_at"])).total_seconds()
        if not 0<=age<=30*86400:
            return False
    return checks_by_kind(record["kind"],data)


def checks_by_kind(kind,data):
    """Apply the acceptance predicates for a single typed evidence record."""
    checks={"readiness":lambda: readiness_complete(data),
            "measurement":lambda: data.get("consent_review") is True and data.get("refund_reconciliation") is True,
            "asset":lambda: data.get("authentic") is True and data.get("rights_cleared") is True and bool(data.get("file_id")),
            "store":lambda: data.get("availability")=="AVAILABLE",
            "cohort":lambda: data.get("mature") is True,
            "route":lambda: all(data.get(k) is True for k in ("installed","fresh_install","signed_out")),
            "billing":lambda: data.get("restore_tested") is True and data.get("trial_eligibility_tested") is True,
            "retention":lambda: data.get("mature") is True}
    return checks.get(kind,lambda: True)()


def missing_manifest(app):
    """Identify the app facts required before a stage can use the manifest."""
    return [f"Add {field} to app setup" for field in ("job","audience","activation","release","locale") if not app["data"].get(field)]


def scoped_candidates(kind,app,records):
    """Keep the latest evidence inside the required local release and locale."""
    candidates=[row for row in records if row['kind']==kind]
    for field,kinds in (('release',RELEASE_KINDS),('locale',LOCALE_KINDS)):
        if kind in kinds:
            accepted=(app['data'].get(field),None,'') if kind=='readiness' and field=='locale' else (app['data'].get(field),)
            candidates=[row for row in candidates if row['data'].get(field) in accepted]
    return sorted(candidates,key=lambda row:row['updated'],reverse=True)


def kind_needs(kind,app,records,reports):
    """Resolve one input kind without losing the latest-failure precedence rule."""
    if kind=='manifest':
        return missing_manifest(app)
    ledger=ledger_for_release(app,reports) if kind=='cohort' else None
    if ledger:
        return [] if ledger['status']=='SUPPLIED_RECONCILED' else ['Reconcile the latest event cohort for this release: maturity, observation coverage, costs or adjustments remain unresolved']
    rows=scoped_candidates(kind,app,records)
    if not rows or not current(rows[0],app):
        return [f'Add current {kind} evidence that meets its acceptance checks; the latest result controls readiness']
    return []


def provider_needs(context,verified,label):
    """Unavailable source prerequisites cannot become local readiness passes."""
    if context is None or context.get('state')=='NOT_APPLICABLE' or context.get(verified):
        return []
    return [label+context['reason']]


def missing_evidence(stage, app, records,ledger_reports=(), catalog=None, release=None):
    """Explain local input gaps and the relevant current provider prerequisite."""
    missing=[message for kind in stage['inputs'] for message in kind_needs(kind,app,records,ledger_reports)]
    if stage['id']==9:
        missing.extend(provider_needs(catalog,'catalog_verified','Verify App Store subscription catalog: '))
    if stage['id']==5:
        missing.extend(provider_needs(release,'inventory_verified','Verify selected App Store release: '))
    return missing


def ledger_for_release(app,reports):
    """Use the latest acquisition window for the current build, never an older success."""
    candidates=[r for r in reports if r["cohort"]["release"]==app["data"].get("release")]
    return max(candidates,key=lambda r:iso_time(r["cohort"]["ends_at"])) if candidates else None


def critical_findings(records):
    """Return confirmed P0 complaints that should block affected promotion."""
    return [r["title"] for r in records if r["kind"]=="review" and r["data"].get("confirmed") is True and r["data"].get("severity")=="P0"]


def evaluate(app, records,ledger_reports=(), catalog=None, release=None):
    """Evaluate twelve ordered stages and propagate dependency and critical blockers."""
    if catalog is not None and catalog.get('app_id')!=app['id']:
        raise Invalid('Subscription catalog belongs to another app')
    if release is not None and release.get('app_id')!=app['id']:
        raise Invalid('Release inventory belongs to another app')
    result=[]
    for stage in stages():
        missing=missing_evidence(stage,app,records,ledger_reports,catalog,release)
        for dep in stage["dependencies"]:
            if result[dep-1]["status"]!="READY":
                missing.append(f"Finish stage {dep}: {result[dep-1]['title']}")
        if stage["id"] in (5,6,7,11):
            missing.extend("Resolve critical finding: "+f for f in critical_findings(records))
        result.append(dict(stage,status="BLOCKED" if missing else "READY",missing=missing,
                           evidence_scope="operator-reported"))
    return result


def execute(app, records, stage_id,ledger_reports=(), catalog=None, release=None):
    """Prepare selected stage packets without publishing, spending or inventing outcomes."""
    checklist=evaluate(app,records,ledger_reports,catalog,release)
    selected=checklist if stage_id==0 else [s for s in checklist if s["id"]==stage_id]
    if not selected:
        raise Invalid("Choose a stage from 1 through 12, or run the full pipeline")
    outputs=[]
    for stage in selected:
        packet=stage_packet(stage,app,records,checklist,ledger_reports)
        outputs.append({"stage":stage["id"],"status":"PREPARED" if stage["status"]=="READY" else "BLOCKED",
                        "missing":stage["missing"],"packet":packet})
    return {"outputs":outputs,"external_execution":"NOT_RUN","spend_minor":0}
