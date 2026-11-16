"""Native Apple keyword observations, without campaign mutation or ROI inference."""

import re

from .common import Invalid, digest

REPORT_PATHS = {"keyword_report": "keywords", "search_term_report": "searchterms"}


def numeric(value):
    """Accept provider integer/string identities, never booleans or floats."""
    if type(value) not in (str, int) or not re.fullmatch(r"\d{1,30}", str(value)):
        raise Invalid("Report identity must be numeric")
    return str(value)


def text(value):
    """Keep provider text as untrusted observations with a finite size."""
    if not isinstance(value, str) or not value.strip() or len(value) > 4096:
        raise Invalid("Report text is missing or exceeds its limit")
    return value


def keyword_identity(keyword, campaign, account, group):
    """Require a supplied keyword to agree with its outer row scope."""
    if not isinstance(keyword, dict):
        raise Invalid("Keyword metadata is malformed")
    identity = tuple(numeric(keyword.get(k)) for k in ("campaignId", "adAccountId", "adGroupId"))
    if identity != (campaign, account, group):
        raise Invalid("Nested keyword belongs to another campaign, account or ad group")
    if keyword.get("matchType") not in ("EXACT", "BROAD"):
        raise Invalid("Keyword match type is unsupported")
    text(keyword.get("text"))
    return numeric(keyword.get("id"))


def row_identity(row, binding, options):
    """Validate ownership before accepting any keyword or search-term metric."""
    if not isinstance(row, dict) or not isinstance(row.get("metadata"), dict):
        raise Invalid("Keyword report metadata is missing")
    m = row["metadata"]
    campaign, account, group = (numeric(m.get(k)) for k in ("campaignId", "adAccountId", "adGroupId"))
    if campaign not in options["campaign_ids"] or account != binding["account_id"]:
        raise Invalid("Keyword report contains another campaign or account")
    if not isinstance(row.get("totalMetrics"), dict):
        raise Invalid("Keyword report metrics are missing")
    if "granularMetrics" in row and not isinstance(row["granularMetrics"], list):
        raise Invalid("Granular report metrics are malformed")
    if options["operation"] == "keyword_report":
        return (campaign, group, keyword_identity(m, campaign, account, group))
    if "searchTermText" not in m:
        raise Invalid("Search term identity is missing")
    # Apple may aggregate low-volume queries into an unnamed row. Preserve the
    # row for paid reporting without inventing a candidate or weakening scope.
    term = None if m["searchTermText"] is None else text(m["searchTermText"])
    source = text(m.get("searchTermSource"))
    keyword = m.get("keyword")
    kid = None if keyword is None else keyword_identity(keyword, campaign, account, group)
    return (campaign, group, term, source, kid)


def report_page(payload, binding, options, offset, previous_total, page_check, seen):
    """Reject contradictory pages and duplicate entities instead of double counting."""
    result = payload.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("rows"), list):
        raise Invalid("Keyword report rows are missing")
    rows = result["rows"]
    total = page_check(payload, offset, rows)
    if len(rows) > payload["pagination"]["pageSize"]:
        raise Invalid("Keyword report rows exceed the declared page size")
    if previous_total is not None and total != previous_total:
        raise Invalid("Report changed during pagination; rerun a narrower window")
    for row in rows:
        key = digest(row_identity(row, binding, options))
        if key in seen:
            raise Invalid("Repeated keyword report entity; no duplicate metrics accepted")
        seen.add(key)
    return rows, total


def read_keywords(reader, binding, options, query, page_check):
    """Read at most three pages after campaign ownership has been verified."""
    path = REPORT_PATHS[options["operation"]]
    rows, seen = [], set()
    total, offset, pages = None, 0, 0
    for _ in range(3):
        payload = reader.read("https://api.ads.apple.com/v1/reports/apps/" + path + "/query", query(options, offset))
        page, total = report_page(payload, binding, options, offset, total, page_check, seen)
        rows.extend(page)
        offset += len(page)
        pages += 1
        if offset >= total:
            break
    search = options["operation"] == "search_term_report"
    term_coverage = {}
    if search:
        suppressed = sum(row["metadata"]["searchTermText"] is None for row in rows)
        term_coverage = {
            "visible_search_term_rows": len(rows) - suppressed,
            "suppressed_search_term_rows": suppressed,
        }
    return {
        "operation": options["operation"],
        "api_version": "PLATFORM_V1",
        "rows": rows,
        "pages": pages,
        "declared_rows": total,
        "coverage": "COMPLETE" if offset >= total else "PARTIAL",
        "reporting_timezone": "ORTZ" if search else "UTC",
        "privacy_suppression_possible": search,
        "coverage_scope": "PROVIDER_DECLARED_ROWS_ONLY",
        "interpretation": (
            "Account reporting timezone (ORTZ). Visible queries are paid observations. "
            "Low-volume terms may be suppressed; unnamed rows do not support keyword recommendations. "
            "Fetched rows are not total demand or organic rank. "
            if search
            else "UTC report window. "
        )
        + "Page cap may limit coverage. Missing metrics remain unavailable; attributed installs do not prove paid customers or ROI.",
        **term_coverage,
    }
