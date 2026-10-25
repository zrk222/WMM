"""Explicit cohort arithmetic and app-scoped ASA/AEO worksheet integration."""
from .common import Invalid, amount


def ratio(numerator, denominator):
    """Preserve an unavailable denominator as null rather than zero conversion."""
    return numerator/denominator if denominator else None


def cohort_metrics(data):
    """Calculate supplied mature cohort costs and contribution with explicit scope."""
    names=("installs","activated","paid","acquisition_cost_minor","net_proceeds_minor","delivery_cost_minor","refunds_minor")
    values={name:amount(data.get(name),name) for name in names}
    if values["activated"]>values["installs"] or values["paid"]>values["installs"]:
        raise Invalid("Activated and paid counts cannot exceed eligible installs")
    if data.get("mature") is not True:
        return {"status":"INCONCLUSIVE","reason":"Cohort follow-up is not mature"}
    # Net proceeds already reflect refunds; retain refunds separately for analysis.
    contribution=values["net_proceeds_minor"]-values["delivery_cost_minor"]
    return {"status":"MEASURED","cohort_id":data.get("cohort_id"),"currency":data.get("currency"),
            "horizon":data.get("horizon"),"counts":values,
            "activation_rate":ratio(values["activated"],values["installs"]),
            "paid_conversion":ratio(values["paid"],values["installs"]),
            "paid_cac_minor":ratio(values["acquisition_cost_minor"],values["paid"]),
            "contribution_minor":contribution,
            "contribution_after_acquisition_minor":contribution-values["acquisition_cost_minor"],
            "scope":"Supplied cohort evidence; not independently verified or causal"}


def retention_metrics(data):
    """Calculate retained value only when the declared follow-up window is mature."""
    eligible=amount(data.get("eligible"),"eligible")
    retained=amount(data.get("retained"),"retained")
    if retained>eligible:
        raise Invalid("Retained count exceeds eligible cohort")
    return {"window":data.get("window"),"eligible":eligible,"retained":retained,
            "rate":ratio(retained,eligible) if data.get("mature") is True else None,
            "mature":data.get("mature") is True}


def acquisition_metrics(data, app_id):
    """Apply the offline ASA/AEO worksheet only to the selected app."""
    from package.acquisition_analysis import analyze
    if data.get("app_id") != app_id:
        raise Invalid("Worksheet belongs to another app")
    return analyze(data)


def summarize(records, app_id,ledger_reports=()):
    """Keep economics, retention and acquisition evidence in separate app-scoped views."""
    cohorts=[cohort_metrics(r["data"]) for r in records if r["kind"]=="cohort"]
    retention=[retention_metrics(r["data"]) for r in records if r["kind"]=="retention"]
    acquisition=[acquisition_metrics(r["data"]["analysis"],app_id) for r in records if r["kind"]=="acquisition"]
    return {"cohorts":cohorts,"retention":retention,"acquisition":acquisition,"event_ledger":list(ledger_reports),
            "status":"MEASURED" if cohorts else "UNAVAILABLE","generated_from":"app-scoped supplied evidence"}
