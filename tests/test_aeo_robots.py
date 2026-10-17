"""Crawler groups, precedence, wildcard bounds and honest unknown states."""
import unittest
from mission_control.aeo_robots import policy, matches, normalized_path, rule_pattern, parse_rules, matching_rules, agent_group, apply_directive


def robots(raw="", status=200, media="text/plain"):
    return {"status":status, "headers":{"content-type":[media]}, "body":raw.encode()}


class Robots(unittest.TestCase):
    def test_empty_directive_separates_groups(self):
        r = robots("User-agent: Googlebot\nDisallow:\nUser-agent: OAI-SearchBot\nDisallow: /\n")
        self.assertEqual(policy(r, "https://example.com/", "Googlebot")["state"], "ALLOW")
        self.assertEqual(policy(r, "https://example.com/", "OAI-SearchBot")["state"], "DISALLOW")

    def test_rule_components_and_longest_agent(self):
        self.assertEqual(normalized_path("/caf%C3%a9/%7e"), "/caf%C3%A9/~")
        self.assertEqual(rule_pattern("/path*$"), "/path*$")
        groups, maps = parse_rules("User-agent: Google\nDisallow: /\nUser-agent: Googlebot\nAllow: /page\n")
        self.assertEqual(matching_rules(groups, "Googlebot"), [("allow", "/page")]); self.assertEqual(maps, [])
        state = {"groups":[], "agents":[], "rules":[], "maps":[], "count":0, "has_directives":False}
        agent_group(state, "Googlebot"); apply_directive(state, "disallow", "")
        agent_group(state, "OAI-SearchBot"); apply_directive(state, "disallow", "/")
        self.assertEqual(state["groups"], [(["googlebot"], [])]); self.assertEqual(state["rules"], [("disallow", "/")])

    def test_specific_agent_merged_and_generic_excluded(self):
        r = robots("User-agent: *\nDisallow: /\nUser-agent: Googlebot\nAllow: /page\nUser-agent: Googlebot\nDisallow: /page/private\n")
        self.assertEqual(policy(r, "https://example.com/page", "Googlebot")["state"], "ALLOW")
        self.assertEqual(policy(r, "https://example.com/page/private", "Googlebot")["state"], "DISALLOW")
        self.assertEqual(policy(r, "https://example.com/page", "OAI-SearchBot")["state"], "DISALLOW")

    def test_longest_rule_and_allow_on_tie(self):
        r = robots("User-agent: *\nDisallow: /\nAllow: /public\nDisallow: /public/private\nAllow: /public/private\n")
        self.assertEqual(policy(r, "https://example.com/public/private", "Agent")["state"], "ALLOW")
        self.assertEqual(policy(r, "https://example.com/Public", "Agent")["state"], "DISALLOW")

    def test_utf8_percent_and_unreserved_paths(self):
        r = robots("User-agent: *\nDisallow: /café\nDisallow: /~private\nDisallow: /a%2Fb\n")
        for path in ("/caf%C3%A9", "/%7eprivate", "/a%2fb"):
            self.assertEqual(policy(r, "https://example.com"+path, "Agent")["state"], "DISALLOW")
        self.assertEqual(policy(r, "https://example.com/a/b", "Agent")["state"], "ALLOW")

    def test_wildcards_and_terminal_anchor(self):
        for pattern, path, expected in [("/a*b$c", "/ab$c", True), ("/a*b$", "/axxb", True), ("/a*b$", "/axxbc", False), ("/a*b", "/axxbc", True), ("/a*b*c$", "/axbyc", True), ("/a*b*b$", "/ab", False), ("/*$", "/anything", True)]:
            with self.subTest(pattern=pattern, path=path):
                self.assertEqual(matches(pattern, path), expected)

    def test_absent_vs_unavailable_and_malformed(self):
        for status in (404, 410):
            self.assertEqual(policy(robots(status=status), "https://example.com/", "Agent")["state"], "ALLOW")
        for r in (robots(status=500), robots(status=403), robots("not a policy"), robots("<html>SPA</html>", media="text/html"), robots("<html>hello:there</html>"), robots("User-agent: *\nDisallow: /a$b\n"), robots("User-agent: G*\nDisallow: /\n")):
            self.assertEqual(policy(r, "https://example.com/", "Agent")["state"], "UNKNOWN")

    def test_rule_and_wildcard_caps_unknown(self):
        self.assertEqual(policy(robots("Sitemap: https://example.com/"+"x"*2048), "https://example.com/", "Agent")["state"], "UNKNOWN")
        for r in (robots("User-agent: *\n"+"Disallow: /path\n"*1025), robots("User-agent: *\nDisallow: /"+"*a"*17), robots("User-agent: *\nDisallow: /"+"x"*2048)):
            self.assertEqual(policy(r, "https://example.com/", "Agent")["state"], "UNKNOWN")

    def test_comments_and_declared_sitemaps(self):
        r = robots("# header\nUser-agent: *\nDisallow: # blank\nSitemap: https://example.com/sitemap.xml\nCrawl-delay: 2\n")
        p = policy(r, "https://example.com/", "Agent")
        self.assertEqual(p["state"], "ALLOW"); self.assertEqual(p["sitemaps"], ["https://example.com/sitemap.xml"])


if __name__ == "__main__":
    unittest.main()
