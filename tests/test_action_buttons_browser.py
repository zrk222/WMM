"""Actual loopback app action states using a disposable synthetic store."""

from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Browser, Locator

from mission_control.server import Server
from mission_control.store import Store

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".factory/action-button-depth"


def contrast(first: tuple[int, int, int], second: tuple[int, int, int]) -> float:
    def luminance(color: tuple[int, int, int]) -> float:
        channels = [channel / 255 for channel in color]
        values = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
        return sum(value * weight for value, weight in zip(values, (0.2126, 0.7152, 0.0722), strict=True))

    light, dark = sorted((luminance(first), luminance(second)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def styles(control: Locator) -> dict:
    return control.evaluate("""node => {
      const s = getComputedStyle(node);
      return Object.fromEntries(['backgroundImage','boxShadow','transform','outlineColor',
        'outlineWidth','opacity','cursor','color','transitionDuration'].map(k => [k,s[k]]));
    }""")


def exercise(browser: Browser, origin: str, width: int) -> dict:
    from playwright.sync_api import expect

    page = browser.new_page(viewport={"width": width, "height": 900})
    errors: list[str] = []
    external: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.route(
        "**/*",
        lambda route: route.continue_()
        if route.request.url.startswith(origin + "/")
        else (external.append(route.request.url), route.abort()),
    )
    try:
        page.goto(origin)
        expect(page.locator("#app-name")).to_contain_text("Synthetic action review")
        primary = page.locator("main .button").first
        expect(primary).to_be_visible()
        primary.hover()
        rest = styles(primary)
        assert "linear-gradient" in rest["backgroundImage"]
        assert rest["boxShadow"] != "none"
        box = primary.bounding_box()
        assert box is not None
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.down()
        expect(primary).to_have_css("transform", "matrix(1, 0, 0, 1, 0, 2)")
        assert styles(primary)["boxShadow"] != rest["boxShadow"]
        page.screenshot(path=str(OUT / f"pressed-{width}.png"))
        page.mouse.move(0, 0)
        page.mouse.up()
        page.emulate_media(reduced_motion="reduce")
        primary.hover()
        page.mouse.down()
        expect(primary).to_have_css("transform", "none")
        assert "inset" in styles(primary)["boxShadow"]
        page.mouse.move(0, 0)
        page.mouse.up()
        page.emulate_media(reduced_motion="no-preference")
        setup = page.locator("#edit-app")
        page.keyboard.press("Tab")
        setup.focus()
        expect(setup).to_have_css("outline-width", "3px")
        assert styles(setup)["outlineColor"] == "rgb(36, 90, 155)"
        assert contrast((36, 90, 155), (251, 252, 248)) >= 3
        setup.press("Enter")
        expect(page.locator("#modal")).to_be_visible()
        close = page.locator("#close-modal")
        expect(close).to_have_css("color", "rgb(39, 79, 134)")
        expect(close.locator("svg")).to_have_css("color", "rgb(39, 79, 134)")
        assert contrast((39, 79, 134), (232, 239, 248)) >= 4.5
        save = page.get_by_role("button", name="Save app setup", exact=True)
        expect(save).to_have_css("color", "rgb(255, 255, 255)")
        assert "rgb(40, 104, 95)" in styles(save)["backgroundImage"]
        assert contrast((255, 255, 255), (40, 104, 95)) >= 4.5
        assert contrast((217, 238, 162), (17, 45, 54)) >= 3
        close.focus()
        page.screenshot(path=str(OUT / f"dialog-{width}.png"))
        page.keyboard.press("Escape")
        expect(page.locator("#modal")).not_to_be_visible()
        page.locator('[data-view="activity"]').click()
        disabled = page.get_by_role("button", name="Inspect agent review queue", exact=True)
        expect(disabled).to_be_disabled()
        disabled.hover(force=True)
        expect(disabled).to_have_css("box-shadow", "none")
        expect(disabled).to_have_css("transform", "none")
        expect(disabled).to_have_css("cursor", "not-allowed")
        assert float(styles(disabled)["opacity"]) == 0.6
        page.screenshot(path=str(OUT / f"activity-{width}.png"), full_page=True)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        assert not errors, errors
        assert not external, external
        (OUT / f"rendered-{width}.html").write_text(page.content(), encoding="utf-8")
        return {
            "width": width,
            "pressed": True,
            "reduced_motion": True,
            "keyboard_dialog": True,
            "disabled": True,
            "icon_inheritance": True,
            "no_overflow": True,
            "no_page_errors": True,
            "external_requests": 0,
        }
    finally:
        page.close()


def main() -> None:
    from playwright.sync_api import sync_playwright

    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="wmm-buttons-") as folder, sync_playwright() as playwright:
        store = Store(Path(folder) / "synthetic.sqlite", seed=False)
        store.save_app("synthetic-app", {"name": "Synthetic action review", "release": "test-1", "locale": "en-US"})
        server = Server(("127.0.0.1", 0), store)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        browser = playwright.chromium.launch(headless=True)
        try:
            observations = [
                exercise(browser, f"http://127.0.0.1:{server.server_port}", width) for width in (1440, 768, 390)
            ]
            result = {
                "status": "PASS",
                "browser": browser.version,
                "observations": observations,
                "limits": [
                    "Synthetic local app only",
                    "No dark theme exists",
                    "No native device acceptance",
                    "No prior screenshot baseline; visual regression comparison is inconclusive",
                ],
            }
            (OUT / "browser.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(json.dumps(result))
        finally:
            browser.close()
            server.shutdown()
            server.server_close()
            thread.join()


@unittest.skipUnless(os.environ.get("WMM_BROWSER_TEST_PROFILE") == "1", "Requires the Chromium browser profile")
class ActionButtonsBrowserTests(unittest.TestCase):
    def test_actual_app_action_states(self) -> None:
        main()


if __name__ == "__main__":
    unittest.main()
