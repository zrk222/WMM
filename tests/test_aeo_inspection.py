"""Robots-first execution, source semantics and no fabricated placement outcomes."""
import hashlib
import json
import time
import unittest
from mission_control.aeo_inspection import inspect_page, safe_evidence, sitemap_check
from mission_control.aeo_parse import Page, page_metadata, sitemap_membership, directives, json_types, declared_children, scoped_directives, known_directive
from mission_control.aeo_transport import ReadError

ROOT = "https://example.com"
NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


def resource(url, body, media="text/html", status=200, extra=None):
    raw = body.encode() if isinstance(body, str) else body
    return {"url":url, "status":status, "headers":dict({"content-type":[media]}, **(extra or {})),
            "body":raw, "bytes":len(raw), "sha256":hashlib.sha256(raw).hexdigest()}


def html(body="<h1>Useful decision</h1><p>Evidence and next action.</p>"):
    return '<html lang="en"><head><title>Real app</title><link rel="canonical" href="https://example.com/page"><meta name="robots" content="index,follow"><script type="application/ld+json">{"@type":"WebPage"}</script></head><body>'+body+'</body></html>'


class Reader:
    def __init__(self, robots="User-agent: *\nAllow: /\n", page=None, maps=None):
        self.calls = []
        self.resources = {ROOT+"/robots.txt": resource(ROOT+"/robots.txt", robots, "text/plain"),
                          ROOT+"/page": resource(ROOT+"/page", page or html()),
                          ROOT+"/sitemap.xml": resource(ROOT+"/sitemap.xml", maps or '<urlset xmlns="'+NS+'"><url><loc>'+ROOT+'/page</loc></url></urlset>', "application/xml")}

    def read(self, url, cap, permit=None):
        self.calls.append((url, cap))
        if permit is not None and not permit(url):
            raise ReadError("ROBOTS_TARGET_BLOCKED")
        value = self.resources[url]
        if isinstance(value, Exception):
            raise value
        return value


class Parse(unittest.TestCase):
    def test_parser_callbacks_preserve_scope_and_capture(self):
        page = Page(); page.handle_starttag("head", []); page.metadata_tag("html", {"lang":"fr"})
        page.handle_starttag("title", []); page.handle_data("Example title"); page.handle_endtag("title")
        page.handle_endtag("head"); page.handle_starttag("h1", []); page.handle_data("Visible words")
        self.assertEqual(page.title, ["Example title"]); self.assertEqual(page.lang, ["fr"]); self.assertEqual(page.words, 2)
        self.assertEqual(page.h1, 1); self.assertEqual(page.blocked, [])
        types = set(); self.assertEqual(declared_children({"@type":"WebPage", "nested":{"x":1}}, 1, types), [({"x":1}, 2)])
        self.assertEqual(types, {"WebPage"})
        self.assertEqual(scoped_directives("Googlebot: noindex, nosnippet", "OAI-SearchBot"), [])
        self.assertEqual(scoped_directives("Googlebot: noindex, nosnippet", "Googlebot"), ["noindex", "nosnippet"])
        self.assertTrue(known_directive("max-snippet: -1")); self.assertFalse(known_directive("max-snippet: -5"))

    def test_metadata_and_declared_schema_are_not_validation(self):
        page = page_metadata(resource(ROOT+"/page", html()))
        self.assertEqual(page["title"], "Real app"); self.assertEqual(page["languages"], ["en"])
        self.assertEqual(page["h1_count"], 1); self.assertEqual(page["static_text_words"], 6)
        self.assertEqual(page["canonicals"], [ROOT+"/page"])
        self.assertEqual(page["jsonld_types"], ["WebPage"]); self.assertEqual(page["jsonld_status"], ["DECLARED_NOT_VALIDATED"])
        self.assertEqual(page["visibility"], "RAW_HTML_NOT_RENDERED")

    def test_headers_and_meta_scope_are_separate(self):
        page = resource(ROOT+"/page", html().replace('content="index,follow"', 'content="index,follow"')+'<meta name="oai-searchbot" content="noindex">', extra={"x-robots-tag":["Googlebot: nosnippet, max-snippet: 0"]})
        controls = page_metadata(page)["controls"]
        self.assertEqual(controls["Googlebot"]["snippets"], "RESTRICTED")
        self.assertEqual(controls["Googlebot"]["indexing"], "NO_OBSERVED_RESTRICTION")
        self.assertEqual(controls["OAI-SearchBot"]["indexing"], "RESTRICTED")
        self.assertEqual(controls["OAI-SearchBot"]["snippets"], "NO_OBSERVED_RESTRICTION")

    def test_malformed_and_oversize_directives_are_unknown(self):
        for value in ("max-snippet: banana", "unsupported-directives", "noindex nofollow"):
            self.assertEqual(directives([value], "Googlebot")["indexing"], "UNKNOWN")
        doc = '<meta name="robots" content="'+"index,"*400+'noindex">'
        self.assertEqual(page_metadata(resource(ROOT, doc))["controls"]["Googlebot"]["indexing"], "UNKNOWN")
        self.assertEqual(directives(["none"], "Googlebot")["indexing"], "RESTRICTED")

    def test_schema_bounds_and_invalid_json_are_visible(self):
        for raw in ('{"@type":', '{"@type":NaN}', '['*40+'{}'+']'*40, 'x'*65537):
            types, status = json_types(raw)
            self.assertEqual(types, []); self.assertNotEqual(status, "DECLARED_NOT_VALIDATED")
        self.assertEqual(json_types('{"@graph":[{"@type":["Product","SoftwareApplication"]}]}')[0], ["Product", "SoftwareApplication"])

    def test_script_style_and_head_are_not_static_body_text(self):
        doc = html('<script>private secret example</script><style>hidden words</style><p>One two</p>')
        self.assertEqual(page_metadata(resource(ROOT, doc))["static_text_words"], 2)

    def test_unsupported_content_types_and_charsets_fail(self):
        for media in ("application/json", "text/html; charset=latin-1"):
            with self.assertRaises(ReadError):
                page_metadata(resource(ROOT, html(), media))

    def test_sitemap_exact_membership_and_incomplete_coverage(self):
        r = resource(ROOT, '<urlset xmlns="'+NS+'"><url><loc>'+ROOT+'/page-other</loc></url></urlset>', "application/xml")
        self.assertEqual(sitemap_membership(r, ROOT+"/page")["state"], "NOT_LISTED_IN_CHECKED_MAP")
        self.assertEqual(sitemap_membership(r, ROOT+"/page", complete=False)["state"], "UNKNOWN")
        self.assertEqual(sitemap_membership(r, ROOT+"/page-other")["state"], "YES")

    def test_xml_entities_index_and_invalid_are_unknown(self):
        for raw in ('<!DOCTYPE foo [<!ENTITY x SYSTEM "file:///private">]><urlset/>', '<sitemapindex xmlns="'+NS+'"/>', 'not XML'):
            self.assertEqual(sitemap_membership(resource(ROOT, raw, "application/xml"), ROOT)["state"], "UNKNOWN")

    def test_maximum_source_parsing_is_bounded(self):
        body = html("<p>word word word </p>"*40000)
        self.assertLess(len(body.encode()), 1048576)
        start = time.monotonic(); page = page_metadata(resource(ROOT, body))
        self.assertEqual(page["static_text_words"], 120000); self.assertLess(time.monotonic()-start, 5)


class Inspection(unittest.TestCase):
    def test_safe_evidence_and_direct_sitemap_failure(self):
        row = resource(ROOT, "private page contents", extra={"set-cookie":["secret"]})
        clean = safe_evidence(row)
        self.assertNotIn("body", clean); self.assertNotIn("set-cookie", clean["headers"])
        self.assertEqual(clean["headers"], {"content-type":["text/html"]})
        reader = Reader(); reader.resources[ROOT+"/sitemap.xml"] = ReadError("DEADLINE")
        finding, source = sitemap_check(reader, reader.resources[ROOT+"/robots.txt"], ROOT+"/page", [])
        self.assertEqual(finding["state"], "UNKNOWN"); self.assertEqual(source["error"], "DEADLINE")

    def test_complete_three_request_flow_and_body_redaction(self):
        reader = Reader(); report = inspect_page(ROOT+"/page", reader)
        self.assertEqual(report["state"], "OBSERVED"); self.assertEqual(report["membership"]["state"], "YES")
        self.assertEqual(len(reader.calls), 3); self.assertEqual(reader.calls[0], (ROOT+"/robots.txt", 512000))
        self.assertEqual(report["indexing"], "NOT_VERIFIED"); self.assertEqual(report["citations"], "NOT_MEASURED")
        self.assertEqual(report["growth"], "NOT_MEASURED"); self.assertNotIn('"body"', json.dumps(report))
        self.assertEqual(report["page"]["sha256"], hashlib.sha256(reader.resources[ROOT+"/page"]["body"]).hexdigest())

    def test_denied_and_unknown_diagnostic_policy_stop_reads(self):
        for raw in ("User-agent: *\nDisallow: /", "malformed policy"):
            reader = Reader(robots=raw); report = inspect_page(ROOT+"/page", reader)
            self.assertEqual(report["state"], "BLOCKED_ROBOTS"); self.assertEqual(len(reader.calls), 1)
            self.assertIsNone(report["page"])

    def test_crawlers_evaluated_independently(self):
        reader = Reader(robots="User-agent: *\nAllow: /\nUser-agent: Googlebot\nDisallow: /\nUser-agent: OAI-SearchBot\nAllow: /page\n")
        report = inspect_page(ROOT+"/page", reader)
        self.assertEqual(report["policies"]["Googlebot"]["state"], "DISALLOW")
        self.assertEqual(report["policies"]["OAI-SearchBot"]["state"], "ALLOW")
        self.assertEqual(report["state"], "OBSERVED")

    def test_network_failure_is_visible_not_fake_empty(self):
        reader = Reader(); reader.resources[ROOT+"/robots.txt"] = ReadError("TLS_FAILED")
        report = inspect_page(ROOT+"/page", reader)
        self.assertEqual(report["robots"]["error"], "TLS_FAILED"); self.assertEqual(report["state"], "BLOCKED_ROBOTS")
        reader = Reader(); reader.resources[ROOT+"/page"] = ReadError("NETWORK_FAILED")
        report = inspect_page(ROOT+"/page", reader)
        self.assertEqual(report["state"], "PAGE_UNAVAILABLE"); self.assertEqual(report["page"]["error"], "NETWORK_FAILED")

    def test_foreign_and_disallowed_sitemaps_not_fetched(self):
        for rules in ("Sitemap: https://elsewhere.example/map.xml", "Disallow: /sitemap.xml"):
            reader = Reader(robots="User-agent: *\nAllow: /\n"+rules)
            report = inspect_page(ROOT+"/page", reader)
            self.assertEqual(report["membership"]["state"], "UNKNOWN"); self.assertEqual(len(reader.calls), 2)

    def test_multiple_declared_maps_never_prove_absence(self):
        reader = Reader(robots="User-agent: *\nAllow: /\nSitemap: "+ROOT+"/sitemap.xml\nSitemap: "+ROOT+"/other.xml", maps='<urlset xmlns="'+NS+'"/>')
        self.assertEqual(inspect_page(ROOT+"/page", reader)["membership"]["state"], "UNKNOWN")

    def test_absent_robots_is_observed_as_absent(self):
        reader = Reader(); reader.resources[ROOT+"/robots.txt"]["status"] = 404
        report = inspect_page(ROOT+"/page", reader)
        self.assertEqual(report["state"], "OBSERVED"); self.assertEqual(report["policies"]["Googlebot"]["reason"], "ROBOTS_ABSENT")


if __name__ == "__main__":
    unittest.main()
