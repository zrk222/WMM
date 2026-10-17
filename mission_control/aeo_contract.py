"""Closed raw-source report contracts and reproducible repair findings."""
import re
from .common import Invalid
from .aeo_transport import AGENT, public_url, origin
from .aeo_inspection import VERSION

AGENTS = (AGENT, "Googlebot", "OAI-SearchBot")
HEADERS = {"content-type", "content-encoding", "content-length", "x-robots-tag"}
ERRORS = set("ADDRESS_BLOCKED BODY_INCOMPLETE BODY_TOO_LARGE CHARSET_UNSUPPORTED DEADLINE DNS_BUSY DNS_FAILED DNS_INVALID ENCODING_UNSUPPORTED HEADERS_TOO_LARGE LIMIT_INVALID NETWORK_FAILED REDIRECT_LIMIT REDIRECT_ORIGIN REQUEST_LIMIT ROBOTS_TARGET_BLOCKED TLS_FAILED URL_INVALID UTF8_INVALID HTML_TYPE_UNSUPPORTED".split())


def require(condition, message="Invalid AEO evidence"):
    """Reject malformed assertions rather than promoting them to usable facts."""
    if not condition:
        raise Invalid(message)


def fields(value, names):
    """Require an exact dictionary shape with no hidden authority fields."""
    require(isinstance(value, dict) and set(value) == set(names.split()))
    return value


def string(value, limit=2400):
    """Retain bounded text without silently coercing non-string values."""
    require(isinstance(value, str) and len(value) <= limit)
    return value


def number(value, maximum):
    """Booleans are not counts."""
    require(type(value) is int and 0 <= value <= maximum)
    return value


def sha(value):
    """Validate a full lowercase SHA-256 digest."""
    require(isinstance(value, str) and bool(re.fullmatch("[a-f0-9]{64}", value)))
    return value


def strings(value, count, length):
    """Validate finite source declaration arrays."""
    require(isinstance(value, list) and len(value) <= count)
    for item in value:
        string(item, length)


def url(value):
    """Only already normalized public URLs are accepted as evidence addresses."""
    require(public_url(value) == value)
    return value


def resource(value, target, cap):
    """Retain safe source hashes and selected headers, never raw documents."""
    if value is None:
        return
    url(value.get("url") if isinstance(value, dict) else None)
    require(origin(value["url"]) == origin(target))
    if "error" in value:
        fields(value, "url status error")
        require(value["status"] is None and value["error"] in ERRORS)
        return
    fields(value, "url status bytes sha256 headers")
    require(type(value["status"]) is int and 100 <= value["status"] <= 599)
    number(value["bytes"], cap); sha(value["sha256"])
    require(isinstance(value["headers"], dict) and set(value["headers"]) <= HEADERS)
    for values in value["headers"].values():
        strings(values, 64, 16384)


def policies(value):
    """Diagnostic and search-agent permissions remain independent."""
    fields(value, " ".join(AGENTS))
    for policy in value.values():
        fields(policy, "state reason sitemaps")
        require(policy["state"] in ("ALLOW", "DISALLOW", "UNKNOWN"))
        require(policy["reason"] in ("ROBOTS_ABSENT", "ROBOTS_UNAVAILABLE", "ROBOTS_OBSERVED", "ROBOTS_UNSUPPORTED"))
        strings(policy["sitemaps"], 32, 2048)


def metadata(value):
    """Validate raw-source facts without interpreting psychological or ranking meaning."""
    fields(value, "title title_count languages canonicals hreflang h1_count static_text_words controls jsonld_types jsonld_status visibility")
    string(value["title"], 300)
    for key in ("title_count", "h1_count", "static_text_words"):
        number(value[key], 1048576)
    for key, count, length in (("languages",32,300),("canonicals",32,2400),("jsonld_types",64,300),("jsonld_status",9,40)):
        strings(value[key], count, length)
    require(all(v in ("DECLARED_NOT_VALIDATED","INVALID_JSON","UNSUPPORTED","UNTERMINATED") for v in value["jsonld_status"]))
    require(value["visibility"] == "RAW_HTML_NOT_RENDERED")
    require(isinstance(value["hreflang"], list) and len(value["hreflang"]) <= 64)
    for item in value["hreflang"]:
        fields(item, "lang url"); string(item["lang"],300); string(item["url"],2400)
    fields(value["controls"], "Googlebot OAI-SearchBot")
    for controls in value["controls"].values():
        fields(controls, "indexing snippets")
        require(all(v in ("RESTRICTED","UNKNOWN","NO_OBSERVED_RESTRICTION") for v in controls.values()))


def report(value):
    """Reject impossible success states and unexpected report data."""
    fields(value, "parser_version target robots policies page metadata sitemap membership indexing citations growth state")
    require(value["parser_version"] == VERSION)
    target = url(value["target"])
    require((value["indexing"],value["citations"],value["growth"]) == ("NOT_VERIFIED","NOT_MEASURED","NOT_MEASURED"))
    resource(value["robots"],target,512000); require(value["robots"] is not None)
    resource(value["page"],target,1048576); resource(value["sitemap"],target,1048576)
    policies(value["policies"])
    fields(value["membership"], "state reason")
    require(value["membership"]["state"] in ("YES","NOT_LISTED_IN_CHECKED_MAP","UNKNOWN"))
    require(value["membership"]["reason"] in ("NOT_READ","EXACT_URL_OBSERVED","ONE_MAP_CHECKED","SITEMAP_UNAVAILABLE","SITEMAP_UNSUPPORTED","SITEMAP_INDEX_OR_UNSUPPORTED","SITEMAP_ORIGIN_OR_URL","SITEMAP_ROBOTS_BLOCKED"))
    state = value["state"]
    require(state in ERRORS | {"OBSERVED","BLOCKED_ROBOTS","PAGE_UNAVAILABLE"})
    report_state(value)
    return value


def report_state(value):
    """A blocked or unavailable source cannot carry invented page facts."""
    state=value["state"]; page=value["page"]
    if state == "OBSERVED":
        observed_state(value)
    else:
        require(value["metadata"] is None and value["sitemap"] is None)
        require(value["membership"] == {"state":"UNKNOWN","reason":"NOT_READ"})
        if state == "BLOCKED_ROBOTS":
            require(page is None and value["policies"][AGENT]["state"] != "ALLOW")
        elif state == "PAGE_UNAVAILABLE":
            require(page is not None and page["status"] != 200)
        else:
            require(page is not None and page["status"] == 200)
    if value["membership"]["state"] == "YES":
        require(value["sitemap"] is not None and value["sitemap"]["status"] == 200)
        require(value["membership"]["reason"] == "EXACT_URL_OBSERVED")


def observed_state(value):
    """Successful parsing requires actual HTTP success and explicit crawl permission."""
    page=value["page"]
    require(page is not None and page["status"] == 200 and "error" not in page)
    require(value["policies"][AGENT]["state"] == "ALLOW")
    metadata(value["metadata"])


def repairs(value):
    """Derive actionable checks, not a synthetic AEO score or visibility claim."""
    result=[]
    def add(code, instruction):
        result.append({"code":code,"instruction":instruction})
    if value["state"] != "OBSERVED":
        add(value["state"], "Inspect the source failure and robots policy. Correct access or encoding, then run a new check.")
    for agent, policy in value["policies"].items():
        if policy["state"] != "ALLOW":
            add("ROBOTS_"+agent, "Review robots.txt for "+agent+": "+policy["state"]+". Unknown permission requires investigation.")
    source=value["metadata"]
    if source:
        metadata_repairs(source, add)
    if value["membership"]["state"] != "YES":
        add("SITEMAP", "Check the exact final page URL in a same-origin sitemap. One map or unsupported map does not prove site-wide absence.")
    return result


def metadata_repairs(source, add):
    """Describe source-specific repairs while preserving raw HTML limitations."""
    if not source["title"] or source["title_count"] != 1:
        add("TITLE", "Provide one descriptive, nonempty HTML title.")
    if len(source["canonicals"]) != 1:
        add("CANONICAL", "Declare one canonical HTTPS URL and verify its intended destination.")
    elif source["canonicals"]:
        try:
            public_url(source["canonicals"][0])
        except Invalid:
            add("CANONICAL", "Use an absolute public HTTPS canonical URL.")
    if not source["h1_count"]:
        add("H1", "Provide a meaningful heading in the raw source; rendered visibility was not checked.")
    control_repairs(source, add)


def control_repairs(source, add):
    """Keep crawler restrictions separate from structured-data parse failures."""
    for agent, controls in source["controls"].items():
        for key, state in controls.items():
            if state != "NO_OBSERVED_RESTRICTION":
                add(agent+"_"+key, "Inspect HTTP and HTML "+key+" controls for "+agent+": "+state+".")
    if any(v != "DECLARED_NOT_VALIDATED" for v in source["jsonld_status"]):
        add("JSON_LD", "Repair malformed or unsupported JSON-LD. Declared types do not establish schema validity.")
