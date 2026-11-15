"""Capture actual WMM controls in an isolated synthetic owner workspace."""

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, cast

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from playwright._impl._api_structures import SetCookieParam  # noqa: E402
from playwright.sync_api import expect, sync_playwright  # noqa: E402 - repository bootstrap

from mission_control.creative_rendering import Renders  # noqa: E402
from mission_control.db import connection  # noqa: E402
from mission_control.video_edit_projects import Projects  # noqa: E402
from mission_control.worker import run_once  # noqa: E402
from tests import test_agent_grants as grants  # noqa: E402
from tests.test_creative_rendering import prepared_render  # noqa: E402
from tests.test_video_edit_projects import project_data  # noqa: E402

OUT = ROOT / ".factory/preview10-polish-audit/ui-capture"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    fixture = grants.GrantTests()
    fixture.setUp()
    captures = []
    try:
        app = fixture.store.app("sample-one")
        fixture.store.save_app(
            "sample-one",
            dict(
                app["data"],
                job="Synthetic editing task",
                audience="Synthetic reviewers",
                activation="Review the fictional step",
            ),
            app["version"],
        )
        _, request = prepared_render(fixture.store, "sample-one")
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            cookies: list[SetCookieParam] = []
            for cookie in fixture.owner.cookies:
                assert cookie.value is not None
                cookies.append({"name": cookie.name, "value": cookie.value, "url": fixture.origin, "sameSite": "Lax"})
            context.add_cookies(cookies)
            context.route(
                "**/*",
                lambda route: route.continue_() if route.request.url.startswith(fixture.origin) else route.abort(),
            )
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))

            def capture(name, caption):
                assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
                path = OUT / (name + ".png")
                page.screenshot(path=str(path))
                captures.append(
                    dict(file=path.name, caption=caption, sha256=hashlib.sha256(path.read_bytes()).hexdigest())
                )

            page.goto(fixture.origin)
            page.locator("#app-select").select_option("sample-one")
            nav = page.locator('[data-view="research"]')
            if not nav.is_visible():
                page.locator("#navigation summary").click()
            nav.click()
            expect(page.get_by_role("button", name="Render a video", exact=True)).to_be_visible()
            capture("01-workspace", "Open your app's creative workspace")
            page.get_by_role("button", name="Render a video", exact=True).click()
            page.locator('#render-form [name="renderer"]').select_option("NATIVE_FFMPEG")
            page.locator('#render-form [name="brief_id"]').select_option(request["brief_id"])
            page.locator('#render-form [name="shape"]').select_option("PORTRAIT")
            capture("02-render-options", "Choose the approved brief, renderer and video format")
            page.get_by_role("button", name="Queue local render", exact=True).click()
            expect(page.locator("#modal")).not_to_be_visible()
            assert run_once(fixture.store)
            rendered = cast(dict[str, Any], cast(dict[str, Any], Renders(fixture.store).list("sample-one"))["items"][0])
            data = cast(dict[str, Any], project_data(rendered["id"], rendered["data"]["artifact"]["sha256"]))
            data["clips"][0].update(out_frame=120, speed_percent=150)
            data["clips"][0]["transform"]["fit"] = "COVER"
            Projects(fixture.store).save(
                "sample-one",
                dict(
                    id="preview-demo",
                    revision=0,
                    manifest_version=fixture.store.app("sample-one")["version"],
                    data=data,
                    request_key="preview-demo-create",
                ),
            )
            page.reload()
            if not page.locator('[data-view="research"]').is_visible():
                page.locator("#navigation summary").click()
            page.locator('[data-view="research"]').click()
            page.get_by_role("button", name="Open video projects", exact=True).click()
            page.locator("#modal").get_by_role("button", name="Edit project", exact=True).click()
            capture("03-edit", "Revise the real timeline, captions and crop controls")
            modal = page.locator("#modal")
            modal.locator(".video-taste-recipe summary").click()
            expect(modal).to_contain_text("current 150%")
            capture("04-taste", "Inspect the guided taste proposal before applying it")
            modal.get_by_role("button", name="Apply proposal to draft fields", exact=True).click()
            expect(modal.locator('[name="c0.speed_percent"]')).to_have_value("100")
            modal.get_by_role("button", name="Save edits", exact=True).click()
            expect(modal).to_contain_text("Current revision 2")
            capture("05-save", "Save a new revision; review before rendering or publication")
            with connection(fixture.store.path) as db:
                assert db.execute("SELECT count(*) FROM jobs WHERE action='edit_render'").fetchone()[0] == 0
            assert not errors, errors
            context.close()
            browser.close()
        manifest = dict(
            schema="wmm.actual-ui-capture.v1",
            classification="ACTUAL_WMM_UI_SYNTHETIC_WORKSPACE",
            width=1440,
            height=900,
            captures=captures,
            external_requests="BLOCKED",
            social_publication="NOT_RUN",
            edited_render="NOT_RUN",
            source={
                name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                for name in [
                    "mission_control/static/creative-rendering.mjs",
                    "mission_control/static/video-editor.js",
                    "mission_control/static/style.css",
                ]
            },
        )
        (OUT / "captures.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        print(json.dumps(dict(status="PASS", captures=len(captures), publication="NOT_RUN")))
    finally:
        fixture.tearDown()


if __name__ == "__main__":
    main()
