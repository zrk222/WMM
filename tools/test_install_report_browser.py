"""Owner MMP upload and install report through the real loopback UI."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright, expect
from tests.test_install_import_http import InstallImportHTTPTests, CAMPAIGN
from datetime import datetime, timedelta, timezone


def main():
    checks = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for width in (390, 1440):
            fx = InstallImportHTTPTests()
            fx.setUp()
            try:
                context = browser.new_context(viewport={"width": width, "height": 900})
                context.add_cookies(
                    [dict(name=c.name, value=c.value, url=fx.fx.origin, sameSite="Lax") for c in fx.fx.owner.cookies]
                )
                page = context.new_page()
                page.goto(fx.fx.origin)
                page.locator('[data-view="results"]').click()
                page.get_by_label("Install attribution").get_by_role(
                    "button", name="Import install export", exact=True
                ).click()
                end = datetime.now(timezone.utc) - timedelta(days=1)
                start = end - timedelta(days=7)
                data = (
                    "id,event,time,unused\r\ninstall_example,converted," + start.isoformat() + ",example\r\n"
                ).encode("utf-8-sig")
                page.locator("#install-export-file").set_input_files(
                    {"name": "synthetic.csv", "mimeType": "text/csv", "buffer": data}
                )
                for field, value in {
                    "campaign": CAMPAIGN,
                    "observed": end.isoformat(),
                    "window-start": start.isoformat(),
                    "window-end": end.isoformat(),
                    "col-id": "id",
                    "col-state": "event",
                    "col-time": "time",
                    "state-values": '{"converted":"ATTRIBUTED"}',
                    "count": "1",
                }.items():
                    page.locator("#install-" + field).fill(value)
                page.locator('[name="coverage_complete"]').check()
                page.get_by_role("button", name="Preview import", exact=True).click()
                expect(page.get_by_text("1 rows read", exact=False)).to_be_visible()
                button = page.get_by_role("button", name="Confirm import", exact=True)
                button.focus()
                page.keyboard.press("Enter")
                page.get_by_role("button", name="Open install report", exact=True).click()
                expect(page.get_by_text("ATTRIBUTED 1", exact=True)).to_be_visible()
                page.get_by_role("button", name="Day 7", exact=True).click()
                expect(page.get_by_role("heading", name="Day 7", exact=True)).to_be_visible()
                page.get_by_text("Export receipts and observation dates", exact=True).click()
                expect(page.get_by_text("Source SHA-256", exact=False)).to_be_visible()
                assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                context.close()
                checks.append(
                    dict(width=width, mapped_provider_state=True, source_receipt=True, day7=True, keyboard_confirm=True)
                )
            finally:
                fx.doCleanups()
        browser.close()
    print(json.dumps(checks))


if __name__ == "__main__":
    main()
