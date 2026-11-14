"""Browser proof for weekly review recovery with synthetic isolated identities."""

# ruff: noqa: E402
# Direct script execution imports repository fixtures after adding the repository root.

import gc
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import expect, sync_playwright

from mission_control.campaign_execution import SCHEMA as CAMPAIGN_SCHEMA
from mission_control.campaign_schedule import initialize as initialize_schedule
from mission_control.common import canonical, digest
from mission_control.db import connection
from tests.test_agent_review_http import ReviewHTTPTests
from tests.test_verified_review import CHECKER_TOKEN, OWNER, OWNER_TOKEN


def run(browser, width, out):
    fixture: Any = ReviewHTTPTests(methodName="test_exact_human_approval_and_agent_resume_use_separate_sessions")
    fixture.setUp()
    context = browser.new_context(viewport={"width": width, "height": 1000})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        prepared = fixture.prepare()
        before = prepared["checkpoint"]
        page.goto(fixture.origin)
        page.wait_for_function(
            "(context) => {const state=context.state;return (() => state.workspace?.app?.id === 'sample-one')(context.original);}",
            arg={"state": page.evaluate_handle("async () => (await import('/app.mjs')).state"), "original": None},
        )

        def login(token):
            page.evaluate(
                "async token => { const {api,refresh}=await import('/app.mjs'); await api('/api/identity/login', {token}); await refresh(); }",
                token,
            )

        def weekly():
            if not page.locator("#navigation details").evaluate("(node) => node.open"):
                page.get_by_text("Advanced tools", exact=True).click()
            page.locator('[data-view="weekly"]').click()
            page.get_by_role("button", name="Refresh review", exact=True).click()
            expect(page.locator('[data-action="weekly-recover"][data-resource="review-one"]')).to_have_count(1)

        initialize_schedule(fixture.store)
        stamp = datetime.now(timezone.utc)
        created = (stamp - timedelta(hours=2)).isoformat()
        expiry = (stamp - timedelta(hours=1)).isoformat()
        due = stamp - timedelta(minutes=90)
        owner = OWNER["principal"]
        scope = {"expires_at": expiry}
        body = {"item_id": "saved-item", "due_at": due.isoformat(), "request": {"request_id": "saved-request"}}
        batch = {
            "batch_id": "e873d2ea-0feb-4ca4-95a0-6b820d448a51",
            "app_id": "sample-one",
            "owner": owner,
            "scope_id": "old-scope",
            "scope_hash": digest(scope),
            "items": [body],
        }
        with connection(fixture.store.path) as db:
            db.executescript(CAMPAIGN_SCHEMA)
            db.execute(
                "INSERT INTO campaign_scopes VALUES(?,?,?,?,?,?,?,?,?,?)",
                ("sample-one", "old-scope", owner, 1, canonical(scope), digest(scope), "ACTIVE", 0, created, created),
            )
            db.execute(
                "INSERT INTO campaign_schedule_batches VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    "e873d2ea-0feb-4ca4-95a0-6b820d448a51",
                    "sample-one",
                    owner,
                    "old-scope",
                    canonical(batch),
                    digest(batch),
                    "ACTIVE",
                    1,
                    created,
                    created,
                ),
            )
            db.execute(
                "INSERT INTO campaign_schedule_items VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    "saved-item",
                    "e873d2ea-0feb-4ca4-95a0-6b820d448a51",
                    due.timestamp(),
                    canonical(body),
                    digest(body),
                    "READY",
                    None,
                    created,
                    created,
                ),
            )
        login(OWNER_TOKEN)
        weekly()
        expect(page.get_by_text("Your approval expired before all scheduled work finished.")).to_be_visible()
        with page.expect_request("**/api/apps/sample-one/campaigns/schedule-status") as request:
            page.get_by_role("button", name="Open schedule", exact=True).press("Enter")
        expect(page.get_by_role("dialog")).to_contain_text("Batch e873d2ea-0feb-4ca4-95a0-6b820d448a51")
        dialog = page.get_by_role("dialog")
        expect(dialog.get_by_role("heading", name="Approval expired")).to_be_visible()
        expect(dialog.get_by_role("status")).to_contain_text("Unfinished items cannot start")
        schedule_html = page.evaluate(
            r"""() => {
                const clone = document.documentElement.cloneNode(true);
                const styles = clone.querySelectorAll('link[rel="stylesheet"]');
                styles.forEach(node => node.remove());
                const css = [...document.styleSheets].map(
                    sheet => [...sheet.cssRules].map(rule => rule.cssText).join('\n')
                ).join('\n');
                const style = document.createElement('style');
                style.textContent = css;
                clone.querySelector('head').append(style);
                clone.querySelectorAll('script').forEach(node => node.remove());
                return '<!doctype html>' + clone.outerHTML;
            }"""
        )
        (out / f"schedule-{width}.html").write_text(schedule_html, encoding="utf-8")
        assert request.value.post_data_json == {"batch_id": "e873d2ea-0feb-4ca4-95a0-6b820d448a51"}
        with connection(fixture.store.path) as db:
            saved = db.execute("SELECT status,job_id FROM campaign_schedule_items WHERE id='saved-item'").fetchone()
            assert saved is not None
            assert tuple(saved) == ("READY", None)
        page.locator("#modal").evaluate("(node) => node.close()")
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
        page.wait_for_function(
            "(context) => {const state=context.state;return (() => !state.weeklyLoading)(context.original);}",
            arg={"state": page.evaluate_handle("async () => (await import('/app.mjs')).state"), "original": None},
        )
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
            "keyboard_opens_exact_schedule": True,
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
