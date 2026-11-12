"""Real owner UI consent, extension and revocation on isolated SQLite/HTTP."""

from pathlib import Path
from datetime import datetime, timedelta, timezone
import json
import os
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright, expect
from mission_control.db import connection
from mission_control.operator_client import OperatorClient
from tests import test_agent_grants as fixtures


def date_value(page, days):
    return page.evaluate(
        "days => { const value=new Date(Date.now()+days*86400000); return new Date(value-value.getTimezoneOffset()*60000).toISOString().slice(0,16); }",
        days,
    )


def exercise(browser, width, output):
    fixture = fixtures.GrantTests("test_owner_issues_once_hash_only_persistence_and_snapshot_no_authority")
    fixture.setUp()
    context = browser.new_context(viewport=dict(width=width, height=950))
    try:
        issued = fixture.issue(["operations.read"])
        agent = OperatorClient(fixture.origin, issued["token"])
        agent.call(dict(operation="operations.read", app_id="sample-one", input={}))
        with connection(fixture.store.path) as db:
            before = dict(db.execute("SELECT * FROM agent_grants WHERE id=?", (issued["grant"]["id"],)).fetchone())
        context.add_cookies(
            [
                dict(name=item.name, value=item.value, url=fixture.origin, httpOnly=True)
                for item in fixture.owner.cookies
            ]
        )
        page = context.new_page()
        page.set_default_timeout(10000)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(fixture.origin)
        page.locator("#app-select").select_option("sample-one")
        page.locator('[data-view="activity"]').click()
        page.get_by_role("button", name="Manage agent grants", exact=True).click()
        page.locator('[data-action="control-extend"]').click()
        form = page.locator("#authority-expiry-form")
        form.locator('[name="expires_at"]').fill(date_value(page, 3))
        form.locator("[data-expiry-preview]").click()
        expect(form.locator("#authority-expiry-error")).to_contain_text("consent")
        with connection(fixture.store.path) as db:
            assert db.execute("SELECT count(*) FROM authority_expiry_consents").fetchone()[0] == 0
        form.locator('[name="extended_expiry_consent"]').check()
        form.locator("[data-expiry-preview]").click()
        expect(page.locator("[data-expiry-confirm]")).to_be_visible()
        page.locator('[name="expires_at"]').fill(date_value(page, 5))
        expect(page.locator("[data-expiry-confirm]")).to_be_disabled()
        page.locator('[name="extended_expiry_consent"]').check()
        page.locator("[data-expiry-preview]").click()
        expect(page.locator("[data-expiry-confirm]")).to_be_enabled()
        page.screenshot(path=str(output / f"review-{width}.png"), full_page=True)
        page.locator("[data-expiry-confirm]").focus()
        page.keyboard.press("Enter")
        expect(page.locator("[data-expiry-done]")).to_be_visible()
        with connection(fixture.store.path) as db:
            after = dict(db.execute("SELECT * FROM agent_grants WHERE id=?", (issued["grant"]["id"],)).fetchone())
            assert before == after, "Extending permission must not mutate original grant or usage"
        rows = fixture.owner.request("POST", "/api/apps/sample-one/agent-grants/list", {})["grants"]
        assert rows[0]["consent_revision"] == 1 and rows[0]["used"] == 1
        assert datetime.fromisoformat(rows[0]["expires"]) > datetime.now(timezone.utc) + timedelta(days=4)
        report = agent.call(dict(operation="operations.read", app_id="sample-one", input={}))
        assert report["agent_authority"]["consent_revision"] == 1
        assert report["agent_authority"]["used"] == 2
        page.locator("[data-expiry-done]").click()
        page.get_by_role("button", name="Issue an agent grant", exact=True).click()
        page.locator("#grant-agent").fill("long-owner-approved")
        page.locator('#control-grant-form [name="expires_at"]').fill(date_value(page, 4))
        page.locator('#control-grant-form [name="extended_expiry_consent"]').check()
        page.locator("#control-grant-form [data-task-advanced] summary").click()
        page.locator('#control-grant-form [name="operations"][value="operations.read"]').check()
        page.get_by_role("button", name="Issue scoped grant", exact=True).focus()
        page.keyboard.press("Enter")
        expect(page.locator("#grant-secret")).to_be_visible()
        page.get_by_role("button", name="Return to grant list", exact=True).click()
        page.locator('[data-action="control-revoke-open"]').first.click()
        page.get_by_role("button", name="Revoke this grant", exact=True).click()
        expect(page.get_by_text("REVOKED", exact=False).first).to_be_visible()
        assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
        assert not errors, errors
        return dict(
            width=width,
            explicit_consent=True,
            stale_date_rejected=True,
            extension=True,
            original_grant_and_usage_unchanged=True,
            same_token=True,
            issuance=True,
            revocation=True,
            keyboard=True,
            errors=errors,
        )
    finally:
        context.close()
        fixture.tearDown()


def main():
    with patch.dict(os.environ, {"WMM_BROWSER_TEST_PROFILE": "1"}):
        suite = unittest.defaultTestLoader.loadTestsFromName("tests.test_automation_profiles_browser")
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        if not result.wasSuccessful() or result.testsRun == 0 or result.skipped:
            raise SystemExit("The owner automation browser journeys must run and pass")

    output = ROOT / ".factory/authority-expiry-extension/browser"
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            rows = [exercise(browser, width, output) for width in (1440, 390)]
            receipt = dict(
                status="PASS",
                chromium=browser.version,
                observations=rows,
                limits=[
                    "Synthetic owner identity and temporary databases",
                    "No provider mutation or native-device proof",
                ],
            )
            (output / "receipt.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
            print(json.dumps(receipt))
        finally:
            browser.close()


if __name__ == "__main__":
    main()
