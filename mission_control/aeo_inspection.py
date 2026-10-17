"""Robots-first read-only diagnostics; durable app binding is a separate layer."""
from urllib.parse import urljoin
from .aeo_transport import AGENT, PublicReader, ReadError, evidence, origin, public_url
from .aeo_robots import policy
from .aeo_parse import page_metadata, sitemap_membership

VERSION = "aeo.raw-source.v1"


def fetch(reader, url, cap, permit=None):
    """Retain only closed error codes when a public read fails."""
    try:
        return reader.read(url, cap, permit=permit)
    except ReadError as exc:
        return {"url": url, "status": None, "error": exc.code}


def safe_evidence(resource):
    """Never persist the inspected body or raw transport error details."""
    return {k: resource[k] for k in ("url", "status", "error") if k in resource} if "error" in resource else evidence(resource)


def sitemap_check(reader, robots, target, maps):
    """Inspect one same-origin map, respecting the diagnostic crawler policy."""
    candidate = maps[0] if maps else origin(target)+"/sitemap.xml"
    try:
        candidate = public_url(candidate)
        if origin(candidate) != origin(target):
            raise ReadError("SITEMAP_ORIGIN")
    except ReadError:
        return {"state": "UNKNOWN", "reason": "SITEMAP_ORIGIN_OR_URL"}, None
    if policy(robots, candidate, AGENT)["state"] != "ALLOW":
        return {"state": "UNKNOWN", "reason": "SITEMAP_ROBOTS_BLOCKED"}, None
    resource = fetch(reader, candidate, 1048576, permit=lambda url: policy(robots, url, AGENT)["state"] == "ALLOW")
    return sitemap_membership(resource, target, complete=len(maps) <= 1), safe_evidence(resource)


def inspect_page(value, reader=None):
    """Read public evidence once; never convert observations into placement proof."""
    target = public_url(value); reader = reader or PublicReader()
    robots = fetch(reader, origin(target)+"/robots.txt", 512000)
    policies = {a: policy(robots, target, a) for a in (AGENT, "Googlebot", "OAI-SearchBot")}
    result = {"parser_version": VERSION, "target": target, "robots": safe_evidence(robots), "policies": policies,
              "page": None, "metadata": None, "sitemap": None, "membership": {"state": "UNKNOWN", "reason": "NOT_READ"},
              "indexing": "NOT_VERIFIED", "citations": "NOT_MEASURED", "growth": "NOT_MEASURED"}
    if policies[AGENT]["state"] != "ALLOW":
        result["state"] = "BLOCKED_ROBOTS"
        return result
    page = fetch(reader, target, 1048576, permit=lambda url: policy(robots, url, AGENT)["state"] == "ALLOW"); result["page"] = safe_evidence(page)
    if page.get("status") != 200:
        result["state"] = "PAGE_UNAVAILABLE"
        return result
    try:
        result["metadata"] = page_metadata(page)
    except ReadError as exc:
        result["state"] = exc.code
        return result
    result["policies"] = {a: policy(robots, page["url"], a) for a in policies}
    result["membership"], result["sitemap"] = sitemap_check(reader, robots, page["url"], policies[AGENT]["sitemaps"])
    result["state"] = "OBSERVED"
    return result
