"""Real local owner bootstrap continuation; no actual GitHub or provider requests."""

from pathlib import Path
import json, sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests import test_agent_grants as grants
from tests import test_verified_review as identities
from mission_control.review_access import Access
from playwright.sync_api import sync_playwright, expect


def exercise(browser, width, out):
    fixture = grants.GrantTests("test_owner_issues_once_hash_only_persistence_and_snapshot_no_authority")
    fixture.setUp()
    try:
        page = browser.new_page(viewport=dict(width=width, height=900 if width == 1440 else 844))
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(fixture.origin)
        page.locator("#app-select").select_option("sample-two")
        page.locator('[data-view="activity"]').click()
        panel = page.get_by_role("region", name="Agent permissions and checkpoints")
        trigger = panel.get_by_role("button", name="Set up app owner", exact=True)
        expect(trigger).to_be_visible()
        (out / f"owner-repair-{width}.html").write_text(page.content(), encoding="utf-8")
        trigger.focus()
        page.keyboard.press("Enter")
        expect(page.locator("#identity-form")).to_be_visible()
        assert page.evaluate("document.querySelector('#modal').contains(document.activeElement)")
        for _ in range(12):
            page.keyboard.press("Tab")
            assert page.evaluate("document.querySelector('#modal').contains(document.activeElement)")
        page.keyboard.press("Escape")
        assert not page.locator("#modal").evaluate("node=>node.open")
        assert page.evaluate(
            "document.activeElement && document.activeElement.textContent.includes('Set up app owner')"
        )
        assert not Access(fixture.store).list("sample-two")["configured"]
        trigger.press("Enter")
        expect(page.locator("#identity-form")).to_be_visible()
        page.evaluate("""() => new Promise(resolve => {
            const dialog = document.querySelector('#modal');
            dialog.addEventListener('close', resolve, {once:true});
            dialog.close();
            document.querySelector('#navigation > [data-view="activity"]').focus();
        })""")
        expect(page.locator('#navigation > [data-view="activity"]')).to_be_focused()
        trigger.focus()
        page.keyboard.press("Enter")
        expect(page.locator("#identity-form")).to_be_visible()
        page.get_by_label("GitHub identity token", exact=True).fill(identities.OWNER_TOKEN)
        page.get_by_role("button", name="Verify my identity", exact=True).focus()
        page.keyboard.press("Enter")
        expect(page.locator("#access-bootstrap-form")).to_be_visible()
        expect(page.locator("#access-bootstrap-form")).to_have_attribute(
            "data-principal", identities.OWNER["principal"]
        )
        expect(page.locator("#access-bootstrap-form")).to_have_attribute("data-app-version", "1")
        assert not Access(fixture.store).list("sample-two")["configured"]
        assert not page.locator('[name="confirm_owner"]').is_checked()
        page.locator('[name="confirm_owner"]').check()
        page.get_by_role("button", name="Establish verified owner", exact=True).click()
        expect(page.get_by_role("button", name="Assign a reviewer", exact=True)).to_be_visible()
        access = Access(fixture.store).list("sample-two")
        assert len(access["members"]) == 1 and access["members"][0]["principal"] == identities.OWNER["principal"]
        assert access["members"][0]["role"] == "OWNER"
        assert not page.evaluate("document.documentElement.scrollWidth>innerWidth")
        assert not errors, errors
        page.close()
        return dict(
            width=width,
            login_continues=True,
            explicit_confirmation=True,
            no_automatic_owner=True,
            owner_saved=True,
            keyboard=True,
            keyboard_trap=True,
            focus_returned=True,
            late_close_keeps_new_focus=True,
            escape_no_submit=True,
            no_overflow=True,
            no_page_errors=True,
        )
    finally:
        fixture.tearDown()


def main():
    folder = ROOT / ".factory/owner-onboarding"
    folder.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            rows = [exercise(browser, width, folder) for width in [1440, 390]]
            data = dict(
                status="PASS",
                browser=browser.version,
                observations=rows,
                limits=["Synthetic identity; no external provider access", "Chromium emulation, not native iOS"],
            )
            (folder / "browser.json").write_bytes((json.dumps(data, indent=2) + "\n").encode("utf-8"))
            print(json.dumps(rows))
        finally:
            browser.close()


if __name__ == "__main__":
    main()
