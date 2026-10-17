"""Raw-source diagnostics only; no rendered, schema or indexing guarantees."""
from html.parser import HTMLParser
import json
import re
import xml.etree.ElementTree as ET
from urllib.parse import urljoin
from .aeo_transport import ReadError, public_url, text


def limited(value):
    """Keep metadata bounded even when the document uses hostile attributes."""
    return " ".join(value.split())[:300]


def declared_children(row, depth, types):
    """Return bounded traversal inputs and collect only string type labels."""
    if isinstance(row, dict):
        candidates = row.get("@type", [])
        candidates = [candidates] if isinstance(candidates, str) else candidates
        if isinstance(candidates, list):
            types.update(limited(t) for t in candidates if isinstance(t, str))
        return [(v, depth+1) for v in row.values() if isinstance(v, (dict, list))]
    if isinstance(row, list):
        return [(v, depth+1) for v in row]
    return []


def json_types(raw):
    """Report declared types, never schema correctness or semantic eligibility."""
    if len(raw.encode()) > 65536:
        return [], "UNSUPPORTED"
    try:
        value = json.loads(raw, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, RecursionError):
        return [], "INVALID_JSON"
    pending = [(value, 0)]; types = set(); count = 0
    while pending:
        row, depth = pending.pop(); count += 1
        if depth > 16 or count > 1024:
            return [], "UNSUPPORTED"
        pending.extend(declared_children(row, depth, types))
        if len(types) > 64:
            return [], "UNSUPPORTED"
    return sorted(types), "DECLARED_NOT_VALIDATED"


class Page(HTMLParser):
    """Extract bounded source facts without executing remote scripts."""
    def __init__(self):
        """Initialize an isolated parser without shared document state."""
        super().__init__(convert_charrefs=True)
        self.title = []; self.titles = 0; self.lang = []; self.canonical = []; self.hreflang = []
        self.robots = []; self.h1 = 0; self.words = 0; self.blocked = []; self.in_title = False
        self.ld = None; self.ld_types = set(); self.ld_status = []; self.ld_count = 0

    def handle_starttag(self, tag, attrs):
        """Advance visibility and JSON-LD capture independently of metadata."""
        a = {key: value or "" for key, value in attrs}
        self.metadata_tag(tag, a)
        if tag in ("head", "script", "style", "template", "noscript"):
            self.blocked.append(tag)
        if tag == "script" and a.get("type", "").lower() == "application/ld+json":
            self.ld = []; self.ld_count += 1

    def metadata_tag(self, tag, a):
        """Separate metadata declarations from parser visibility state."""
        if tag == "html" and a.get("lang"):
            self.lang.append(limited(a["lang"]))
        if tag == "title":
            self.in_title = True; self.titles += 1
        if tag == "h1":
            self.h1 += 1
        if tag == "link":
            self.link(a)
        if tag == "meta" and a.get("name", "").lower() in ("robots", "googlebot", "oai-searchbot"):
            content = a.get("content", "")
            self.robots.append((a["name"].lower(), content if len(content) <= 2048 else "unsupported-directives"))

    def link(self, attrs):
        """Keep raw declarations; canonical URL validation is a separate finding."""
        rel = attrs.get("rel", "").lower().split(); href = attrs.get("href", "")
        if "canonical" in rel:
            self.canonical.append(href[:2400])
        if "alternate" in rel and attrs.get("hreflang"):
            self.hreflang.append({"lang": limited(attrs["hreflang"]), "url": href[:2400]})

    def handle_endtag(self, tag):
        """Close source capture even when HTML has mismatched nesting."""
        if tag == "title":
            self.in_title = False
        if tag == "script" and self.ld is not None:
            types, state = json_types("".join(self.ld))
            self.ld_types.update(types); self.ld_status.append(state); self.ld = None
        if tag in self.blocked:
            index = len(self.blocked)-1-self.blocked[::-1].index(tag)
            self.blocked = self.blocked[:index]

    def handle_data(self, data):
        """Count static text without treating scripts or head content as visible."""
        if self.in_title and sum(map(len, self.title)) < 600:
            self.title.append(data[:600])
        if self.ld is not None and self.ld_count <= 8:
            self.ld.append(data)
        if not self.blocked:
            self.words += len(data.split())


def scoped_directives(value, agent):
    """Retain scope across comma-separated directives in one HTTP field."""
    selected = []; scope = "*"
    for part in value.lower().strip().split(","):
        part = part.strip(); scoped = re.match(r"^([a-z][a-z0-9_-]*):\s*(.*)$", part)
        if scoped and scoped[1] not in ("max-snippet", "max-image-preview", "max-video-preview", "unavailable_after"):
            scope = scoped[1]; part = scoped[2]
        if scope in ("*", agent.lower()):
            selected.append(part)
    return selected


def known_directive(value):
    """Malformed/unknown controls cannot become an unrestricted assertion."""
    known = {"index", "noindex", "follow", "nofollow", "none", "all", "nosnippet", "noarchive", "nocache", "noimageindex", "notranslate", "indexifembedded"}
    return value in known or bool(re.fullmatch(r"max-(?:snippet|video-preview):\s*(?:-1|[0-9]+)|max-image-preview:\s*(?:none|standard|large)", value))


def directives(values, agent):
    """Apply generic and exact product-scoped restrictions independently."""
    restrictions = [p for v in values for p in scoped_directives(v, agent)]
    unknown = any(not known_directive(p) for p in restrictions)
    blocked = any(p in ("noindex", "none") for p in restrictions)
    no_snippet = any(p in ("nosnippet", "none") or re.fullmatch(r"max-snippet:\s*0", p) for p in restrictions)
    return {"indexing": "RESTRICTED" if blocked else "UNKNOWN" if unknown else "NO_OBSERVED_RESTRICTION",
            "snippets": "RESTRICTED" if no_snippet else "UNKNOWN" if unknown else "NO_OBSERVED_RESTRICTION"}


def page_metadata(resource):
    """Summarize original HTTP/HTML facts without a synthetic success score."""
    types = resource["headers"].get("content-type", [])
    if not types or any(t.split(";", 1)[0].strip().lower() not in ("text/html", "application/xhtml+xml") for t in types):
        raise ReadError("HTML_TYPE_UNSUPPORTED")
    page = Page(); page.feed(text(resource)); page.close()
    if page.ld is not None:
        page.ld_status.append("UNTERMINATED")
    if page.ld_count > 8:
        page.ld_status.append("UNSUPPORTED")
    controls = {}
    for agent in ("Googlebot", "OAI-SearchBot"):
        values = list(resource["headers"].get("x-robots-tag", []))
        values.extend(v for name, v in page.robots if name in ("robots", agent.lower()))
        controls[agent] = directives(values, agent)
    return {"title": limited(" ".join(page.title)), "title_count": page.titles, "languages": page.lang[:32],
            "canonicals": page.canonical[:32], "hreflang": page.hreflang[:64], "h1_count": page.h1,
            "static_text_words": page.words, "controls": controls, "jsonld_types": sorted(page.ld_types)[:64],
            "jsonld_status": page.ld_status[:9], "visibility": "RAW_HTML_NOT_RENDERED"}


def sitemap_membership(resource, target, complete=True):
    """Exact membership in one map; incomplete coverage never proves absence."""
    if resource.get("status") != 200:
        return {"state": "UNKNOWN", "reason": "SITEMAP_UNAVAILABLE"}
    try:
        raw = text(resource)
        if re.search(r"<!\s*(?:DOCTYPE|ENTITY)", raw, re.I):
            raise ValueError
        root = ET.fromstring(raw)
    except (ReadError, ValueError, ET.ParseError):
        return {"state": "UNKNOWN", "reason": "SITEMAP_UNSUPPORTED"}
    if root.tag != "{http://www.sitemaps.org/schemas/sitemap/0.9}urlset":
        return {"state": "UNKNOWN", "reason": "SITEMAP_INDEX_OR_UNSUPPORTED"}
    matches = [n.text for n in root.findall("{http://www.sitemaps.org/schemas/sitemap/0.9}url/{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]
    if target in matches:
        return {"state": "YES", "reason": "EXACT_URL_OBSERVED"}
    return {"state": "NOT_LISTED_IN_CHECKED_MAP" if complete else "UNKNOWN", "reason": "ONE_MAP_CHECKED"}
