"""Real Chromium owner-policy taste controls; disposable synthetic WMM only."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import hashlib
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright, expect
from mission_control.db import connection
from tests import test_organic_video_policy_http as fixtures
from tests import test_organic_video_policy as policy

OUT = ROOT / ".factory/taste-agent-review/browser"
RULES = "Actual product controls stay readable. Show an honest useful result and one usable next action."


def exercise(browser, width):
    fixture = fixtures.PolicyHTTPTests()
    fixture.setUp()
    context = None
    try:
        issued = fixture.owner.request(
            "POST",
            "/api/apps/" + policy.APP + "/agent-grants/issue",
            dict(
                agent_id="synthetic-taste-reviewer",
                manifest_version=fixture.store.app(policy.APP)["version"],
                operations=["organic-video.policy-admit"],
                expires=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
                max_calls=20,
            ),
        )
        context = browser.new_context(
            viewport=dict(width=width, height=900 if width == 1440 else 844), accept_downloads=True
        )
        context.add_cookies(
            [dict(name=c.name, value=c.value, url=fixture.origin, sameSite="Lax") for c in fixture.owner.cookies]
        )
        context.add_init_script("localStorage.setItem('growth-app'," + json.dumps(policy.APP) + ")")
        page = context.new_page()
        errors, external = [], []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def restrict(route):
            if route.request.url.startswith(fixture.origin + "/"):
                route.continue_()
            else:
                external.append(route.request.url)
                route.abort()

        context.route("**/*", restrict)
        page.goto(fixture.origin)
        nav = page.locator('[data-view="research"]')
        if not nav.is_visible():
            page.locator("details").filter(has=nav).locator("summary").first.click()
        nav.click()
        page.locator('[data-action="opolicy-open"]').click()
        page.locator('[data-action="opolicy-new"]').click()
        form = page.locator("#opolicy-form")
        expect(form).to_be_visible()
        toggle = form.locator('[name="auto_taste"]')
        expect(toggle).not_to_be_checked()
        form.locator("#opolicy-page").select_option(index=1)
        form.locator("#opolicy-mode").select_option("STANDING_GENERATED")
        for name in ("sources", "claims"):
            form.locator('[name="' + name + '"]').first.check()
        form.locator('[name^="template-"]').first.check()
        form.locator('[name^="caption-"]').fill("See the synthetic app demonstrate a useful result.")
        toggle.focus()
        page.keyboard.press("Space")
        expect(toggle).to_be_checked()
        form.locator('button[type="submit"]').press("Enter")
        expect(page.locator("#opolicy-error")).to_contain_text("Choose a current scoped taste reviewer")
        reviewer = form.locator('[name="taste_agent"]')
        reviewer.focus()
        page.keyboard.press("ArrowDown")
        page.keyboard.press("Tab")
        expect(reviewer).to_have_value(issued["grant"]["id"])
        form.locator('button[type="submit"]').press("Enter")
        expect(page.locator("#opolicy-error")).to_contain_text("Owner acceptance rules")
        rules = form.locator('[name="taste_rules"]')
        rules.focus()
        page.keyboard.insert_text(RULES)
        form.locator('button[type="submit"]').press("Enter")
        modal = page.locator("#modal")
        expect(modal).to_contain_text(RULES)
        expect(modal).to_contain_text("not mechanical visual certification")
        expect(modal).to_contain_text(issued["grant"]["id"])
        expect(page.locator('[data-action="opolicy-confirm"]')).to_be_visible()
        assert fixture.request("policy-history", dict(offset=0, request_id=None))["items"] == []
        page.locator('[data-action="opolicy-confirm"]').press("Enter")
        page.locator('[data-action="opolicy-read"]').click()
        expect(modal).to_contain_text("current policy revalidated")
        expected_rules = hashlib.sha256(json.dumps(RULES, separators=(",", ":")).encode()).hexdigest()
        expect(modal).to_contain_text(expected_rules)
        with page.expect_download() as download:
            page.locator('[data-action="opolicy-json"]').click()
        report = json.loads(Path(download.value.path()).read_text(encoding="utf-8"))
        snapshot = report["policy_snapshot"]
        assert snapshot["policy"]["taste_auto_review"]["reviewer_grant_id"] == issued["grant"]["id"]
        assert snapshot["taste_reviewer"]["rules_sha256"] == expected_rules
        assert snapshot["policy"]["max_model_minor"] == 0
        with connection(fixture.store.path) as db:
            assert db.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0
            assert db.execute("SELECT count(*) FROM organic_video_admissions").fetchone()[0] == 0
        assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
        assert not modal.locator(".organic-policy-workspace").evaluate("(n)=>n.scrollWidth>n.clientWidth")
        assert not errors, errors
        assert not external, external
        return dict(
            width=width,
            default_off=True,
            keyboard_toggle_selection_rules=True,
            missing_reviewer_and_rules_rejected=True,
            summary_and_export_hash_bound=True,
            saved_policies=1,
            render_jobs=0,
            admitted_outputs=0,
            page_errors=errors,
            external_requests=external,
            no_overflow=True,
        )
    finally:
        if context:
            context.close()
        fixture.doCleanups()


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            result = dict(
                status="PASS",
                browser=browser.version,
                observed_at=datetime.now(timezone.utc).isoformat(),
                script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                observations=[exercise(browser, width) for width in (1440, 390)],
                limits="Synthetic local owner workflow only. No provider calls, video watching, taste judgment or publication proved.",
            )
            (OUT / "browser.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(result))
        finally:
            browser.close()
