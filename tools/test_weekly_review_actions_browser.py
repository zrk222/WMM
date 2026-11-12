"""Browser proof for weekly review recovery with synthetic isolated identities."""

import gc
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright, expect
from tests.test_agent_review_http import ReviewHTTPTests
from tests.test_verified_review import OWNER_TOKEN, CHECKER_TOKEN


def run(browser, width, out):
    fixture = ReviewHTTPTests(methodName="test_exact_human_approval_and_agent_resume_use_separate_sessions")
    fixture.setUp()
    context = browser.new_context(viewport={"width": width, "height": 1000})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        prepared = fixture.prepare()
        before = prepared["checkpoint"]
        page.goto(fixture.origin)
        page.wait_for_function("() => state.workspace?.app?.id === 'sample-one'")

        def login(token):
            page.evaluate("async token => { await api('/api/identity/login', {token}); await refresh(); }", token)

        def weekly():
            if not page.locator("#navigation details").evaluate("(node) => node.open"):
                page.get_by_text("Advanced tools", exact=True).click()
            page.locator('[data-view="weekly"]').click()
            page.get_by_role("button", name="Refresh review", exact=True).click()
            expect(page.locator('[data-action="weekly-recover"][data-resource="review-one"]')).to_have_count(1)

        login(OWNER_TOKEN)
        weekly()
        card = page.locator('[data-action="weekly-recover"][data-resource="review-one"]')
        card.press("Enter")
        dialog = page.get_by_role("dialog")
        expect(dialog).to_contain_text("Exact frozen operation input")
        expect(dialog).to_contain_text("grant-listing")
        expect(dialog.get_by_role("button", name="Approve this exact request")).to_have_count(0)
        assert fixture.agent.review("status", dict(app_id="sample-one", id="review-one"))["checkpoint"] == before
        assert fixture.owner.call(fixture.envelope())["history"] == []
        page.screenshot(path=str(out / f"owner-{width}.png"), full_page=True)
        css = page.evaluate(
            "() => [...document.styleSheets].map(s => [...s.cssRules].map(r => r.cssText).join(String.fromCharCode(10))).join(String.fromCharCode(10))"
        )
        assert css.strip()
        (out / f"owner-{width}.html").write_text(
            page.content().replace("</head>", '<style data-audit="actual-loaded-styles">' + css + "</style></head>"),
            encoding="utf-8",
        )
        page.locator("#modal").evaluate("(node) => node.close()")
        login(CHECKER_TOKEN)
        weekly()
        page.locator('[data-action="weekly-recover"][data-resource="review-one"]').press("Enter")
        expect(dialog).to_contain_text("grant-listing")
        expect(dialog.get_by_role("button", name="Approve this exact request")).to_have_count(1)
        assert fixture.agent.review("status", dict(app_id="sample-one", id="review-one"))["checkpoint"] == before
        with page.expect_popup() as opened:
            dialog.get_by_role("button", name="Report / Save PDF", exact=True).click()
        report = opened.value
        expect(report.locator("body")).to_contain_text("review-one")
        pdf = report.pdf(path=str(out / f"request-{width}.pdf"))
        assert pdf.startswith(b"%PDF")
        report.close()
        page.locator("#modal").evaluate("(node) => node.close()")
        cancelled = fixture.human("cancel", dict(id="review-one", revision=before["revision"]), fixture.owner)
        assert cancelled["state"] == "CANCELLED"
        page.get_by_role("button", name="Refresh review", exact=True).click()
        page.wait_for_function("() => !state.weeklyLoading")
        expect(page.locator('[data-action="weekly-recover"][data-resource="review-one"]')).to_have_count(0)
        assert fixture.owner.call(fixture.envelope())["history"] == []
        page.locator('[data-view="evidence"]').click()
        with page.expect_download() as downloaded:
            page.get_by_role("button", name="Export workspace", exact=True).click()
        exported = json.loads(Path(downloaded.value.path()).read_text(encoding="utf-8"))
        assert isinstance(exported, dict) and "payload" in exported
        assert not errors, errors
        return {
            "width": width,
            "browser": browser.version,
            "owner_maker_cannot_approve": True,
            "checker_inspected": True,
            "checkpoint_unchanged_on_open": True,
            "cancel_removed_after_refresh": True,
            "json_export": True,
            "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
            "data": "SYNTHETIC_TEMPORARY_WORKSPACE",
        }
    finally:
        context.close()
        gc.collect()
        fixture.tearDown()


def main():
    out = ROOT / ".factory/weekly-review-actions"
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            result = {"status": "PASS", "observations": [run(browser, width, out) for width in (1440, 390)]}
        finally:
            browser.close()
    (out / "browser.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
