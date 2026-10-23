"""Project saved Apple Ads observations; never fetch, bid, infer revenue or spend."""
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, localcontext
import json
import re
from .common import Invalid, digest, identifier, iso_time, required, safe_data
from .pmf_contract import exact, hashed
from .benchmark_context import METRICS, observed_record
from .currency_units import minor_units, SOURCE_SHA256
from .ledger import currency
from .provider_reports import campaign_ids, campaign_row
from .ads_reports import row_identity


def source_connection(db, app, job, report):
    """Use this app's current exact connection and actual promoted-store identity."""
    data = job["data"]
    row = db.execute("SELECT * FROM records WHERE app_id=? AND id=? AND kind='connection'", (app["id"], data.get("connection_id"))).fetchone()
    if not row or type(data.get("connection_version")) is not int or row["version"] != data["connection_version"]:
        raise Invalid("Saved Ads report connection changed; refresh the source")
    binding = json.loads(row["data"])
    if binding.get("provider") != "apple_ads" or binding.get("auth_mode") == "disconnected":
        raise Invalid("Saved report needs a current Apple Ads connection")
    expected = str(app["data"].get("store_app_id") or "")
    if not expected or str(binding.get("store_app_id")) != expected or str(report.get("store_app_id")) != expected:
        raise Invalid("Saved Ads report does not match the configured app identity")
    return row, binding


def source_report(db, app_id, job_id, source_hash, as_of):
    """Freeze successful app-owned source, request and connection without credentials."""
    identifier(job_id)
    hashed(source_hash)
    app = db.execute("SELECT * FROM apps WHERE id=?", (app_id,)).fetchone()
    job = db.execute("SELECT * FROM jobs WHERE app_id=? AND id=? AND action='sync' AND status='SUCCEEDED'", (app_id, job_id)).fetchone()
    if not app or not job:
        raise Invalid("Choose this app's successful saved Apple Ads read")
    app = dict(dict(app), data=json.loads(app["data"]))
    job = dict(dict(job), data=json.loads(job["data"]))
    report = json.loads(job["result"])
    report_identity(report, job, app_id, source_hash, as_of)
    record, binding = source_connection(db, app, job, report)
    options = job["data"].get("options")
    exact(options, {"operation", "start", "end", "campaign_ids"})
    campaign_ids(options["campaign_ids"])
    if options != report.get("request") or options["operation"] not in ("campaign_report", "keyword_report"):
        raise Invalid("Use an exact saved campaign or keyword report; account-local search-term windows need timezone support")
    if report.get("operation") != options["operation"] or report.get("external_writes") is not False:
        raise Invalid("Saved report operation or read-only boundary is invalid")
    frozen = dict(job_id=job_id, report_hash=source_hash, result_hash=digest(report), connection_id=record["id"],
                  connection_version=record["version"], connection_hash=record["hash"], request_hash=digest(options))
    return report, binding, options, frozen


def report_identity(report, job, app_id, source_hash, as_of):
    """Validate report ownership and chronological integrity before source projection."""
    if not isinstance(report, dict) or report.get("provider") != "apple_ads" or report.get("app_id") != app_id:
        raise Invalid("Saved report provider or app scope is invalid")
    if report.get("source_hash") != source_hash or iso_time(report.get("observed_at")) > iso_time(as_of):
        raise Invalid("Saved report source changed or has a future observation date")
    if not iso_time(job["created"]) <= iso_time(report["observed_at"]) <= iso_time(job["updated"]) <= iso_time(as_of):
        raise Invalid("Saved report job dates contradict its observation history")


def report_rows(report, binding, options):
    """Reject duplicate or out-of-scope entities before aggregating any provider totals."""
    rows = report.get("rows")
    if not isinstance(rows, list) or len(rows) > 300:
        raise Invalid("Saved Ads report row coverage is malformed")
    total = report.get("declared_rows")
    if type(total) is not int or total < len(rows):
        raise Invalid("Saved Ads report declared row coverage is malformed")
    if report.get("coverage") == "COMPLETE" and total != len(rows):
        raise Invalid("Saved Ads report completeness contradicts its row count")
    seen = set()
    for row in rows:
        if options["operation"] == "campaign_report":
            campaign_row(row, binding, options["campaign_ids"])
            identity = str(row["metadata"]["id"])
        else:
            identity = digest(row_identity(row, binding, options))
        if identity in seen:
            raise Invalid("Saved Ads report repeats an entity; no totals were combined")
        seen.add(identity)
    return rows


def report_window(options):
    """Map inclusive UTC report dates to an explicit exclusive end timestamp."""
    try:
        start, end = [date.fromisoformat(options[key]) for key in ("start", "end")]
    except (ValueError, TypeError) as exc:
        raise Invalid("Saved Ads report needs ISO calendar dates") from exc
    if start > end:
        raise Invalid("Saved Ads report dates are reversed")
    return (datetime.combine(start, time.min, timezone.utc).isoformat(),
            datetime.combine(end + timedelta(days=1), time.min, timezone.utc).isoformat())


def count_value(value):
    """Retain missing provider metrics as unavailable, never substitute zero."""
    if type(value) is int and value >= 0:
        return value
    if isinstance(value, str) and re.fullmatch(r"[0-9]{1,30}", value):
        return int(value)
    raise Invalid("Required provider count is missing or malformed")


def report_currency(rows):
    """A billing currency must be returned by every row; never infer it from a reference."""
    codes = set()
    for row in rows:
        money = row["totalMetrics"].get("localSpend")
        if not isinstance(money, dict):
            raise Invalid("Provider billing currency is unavailable")
        codes.add(currency(money.get("currency")))
    if len(codes) != 1:
        raise Invalid("Provider currencies are mixed or unavailable")
    return next(iter(codes))


def spend_minor(value, code):
    """Preserve decimal precision before descriptive conversion; no cash rounding or FX."""
    if not isinstance(value, dict) or value.get("currency") != code:
        raise Invalid("Provider spend currency changed")
    raw = value.get("amount")
    if type(raw) not in (str, int) or not re.fullmatch(r"[0-9]{1,30}(?:\.[0-9]{1,30})?", str(raw)):
        raise Invalid("Provider spend amount is missing or malformed")
    with localcontext() as context:
        context.prec = 96
        return Decimal(str(raw)) * (Decimal(10) ** minor_units(code))


def aggregate_metric(rows, metric, code):
    """Use only the selected metric's actual counts and exact provider spend values."""
    if metric in ("CPT_MINOR", "CPI_MINOR"):
        with localcontext() as context:
            context.prec = 96
            numerator = sum((spend_minor(row["totalMetrics"].get("localSpend"), code) for row in rows), Decimal(0))
        field = "taps" if metric == "CPT_MINOR" else "totalInstalls"
    else:
        numerator = sum(count_value(row["totalMetrics"].get("totalInstalls" if metric == "CR" else "taps")) for row in rows)
        field = "taps" if metric == "CR" else "impressions"
    denominator = sum(count_value(row["totalMetrics"].get(field)) for row in rows)
    return numerator, denominator


def project_saved_ads(db, app_id, job_id, source_hash, metric, segment, as_of):
    """Derive app-owned observations and keep operator classification visibly separate."""
    if not isinstance(metric, str) or metric not in METRICS:
        raise Invalid("Choose CPT, CPI, conversion rate or tap-through rate")
    exact(segment, {"category", "territory", "placement", "campaign_type"})
    safe_data(segment)
    segment = {key: required(value, key, 300) for key, value in segment.items()}
    report, binding, options, frozen = source_report(db, app_id, job_id, source_hash, as_of)
    rows = report_rows(report, binding, options)
    start, end = report_window(options)
    if options["operation"] == "keyword_report" and report.get("reporting_timezone") != "UTC":
        raise Invalid("Saved keyword report timezone is not verified as UTC")
    if report.get("reporting_timezone", "UTC") != "UTC":
        raise Invalid("Saved report timezone is not UTC")
    reasons, observed, numerator_exact = [], None, None
    try:
        code = report_currency(rows)
        numerator, denominator = aggregate_metric(rows, metric, code)
        numerator_exact = str(numerator)
        numerator = int(numerator) if numerator == int(numerator) else float(numerator)
        value = dict(segment, metric=metric, denominator=METRICS[metric], platform="iOS", currency=code,
                     period_start=start, period_end=end, numerator=numerator, denominator_count=denominator,
                     source_sha256=frozen["result_hash"], coverage=report.get("coverage", "UNKNOWN"))
        observed = observed_record(value)
        observed.pop("value")
    except Invalid as exc:
        reasons.append(str(exc))
    return dict(status="SOURCE_METRICS_UNAVAILABLE" if reasons else "SAVED_ACCOUNT_OBSERVATION", observed=observed, numerator_exact=numerator_exact,
                reasons=reasons, binding=frozen, row_count=len(rows), unit_source_sha256=SOURCE_SHA256,
                classification_provenance="OPERATOR_DECLARED", classification_provider_verified=False,
                provider_observed_at=report["observed_at"], external_writes=False, spend_authority=False,
                scope="Metrics come from a saved app-owned report. Category, territory, placement and campaign type are operator classification, not provider verification. Provider-declared rows may restate; no post-install revenue, causal lift, bids or scale authority.")
