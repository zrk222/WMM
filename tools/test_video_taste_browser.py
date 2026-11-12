"""Actual shared-editor recipe review/apply/save in disposable Chromium workspaces."""

from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright, expect
from mission_control.creative_rendering import Renders
from mission_control.db import connection
from mission_control.video_edit_projects import Projects
from mission_control.worker import run_once
from tests import test_agent_grants as grants
from tests.test_creative_rendering import prepared_render
from tests.test_video_edit_projects import project_data

OUT = ROOT / ".factory/hypit-taste-footage"


def exercise(browser, width):
    fixture = grants.GrantTests()
    fixture.setUp()
    context = None
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
        Renders(fixture.store).queue("sample-one", dict(data=request, request_key="taste-source"))
        assert run_once(fixture.store)
        with connection(fixture.store.path) as db:
            jobs_before = db.execute("SELECT count(*) FROM jobs").fetchone()[0]
        native = Renders(fixture.store).list("sample-one")["items"][0]
        data = project_data(native["id"], native["data"]["artifact"]["sha256"])
        data["clips"][0].update(out_frame=120, speed_percent=150)
        data["clips"][0]["transform"]["fit"] = "COVER"
        version = fixture.store.app("sample-one")["version"]
        projects = Projects(fixture.store)
        projects.save(
            "sample-one",
            dict(id="taste-browser", revision=0, manifest_version=version, data=data, request_key="taste-create"),
        )
        context = browser.new_context(viewport=dict(width=width, height=900 if width == 1440 else 844))
        context.add_cookies(
            [dict(name=c.name, value=c.value, url=fixture.origin, sameSite="Lax") for c in fixture.owner.cookies]
        )
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(fixture.origin)
        page.locator("#navigation summary").click()
        page.locator('[data-view="research"]').click()
        page.get_by_role("button", name="Open video projects", exact=True).click()
        modal = page.locator("#modal")
        modal.get_by_role("button", name="Edit project", exact=True).click()
        review = modal.locator(".video-taste-recipe summary")
        review.focus()
        page.keyboard.press("Enter")
        expect(modal).to_contain_text("current 150%")
        modal.get_by_role("button", name="Apply proposal to draft fields", exact=True).focus()
        page.keyboard.press("Enter")
        expect(modal.locator('[name="c0.fit"]')).to_have_value("CONTAIN")
        expect(modal.locator('[name="c0.speed_percent"]')).to_have_value("100")
        assert projects.read("sample-one", "taste-browser")["revision"] == 1
        modal.get_by_role("button", name="Render saved revision", exact=True).click()
        expect(modal.locator("#editor-error")).to_contain_text("Save your current field edits first")
        modal.get_by_role("button", name="Save edits", exact=True).focus()
        page.keyboard.press("Enter")
        expect(modal).to_contain_text("Current revision 2")
        current = projects.read("sample-one", "taste-browser")
        clip = current["data"]["definition"]["clips"][0]
        assert clip["source"] == data["clips"][0]["source"]
        assert (clip["in_frame"], clip["out_frame"]) == (0, 120)
        with connection(fixture.store.path) as db:
            assert db.execute("SELECT count(*) FROM jobs WHERE action='edit_render'").fetchone()[0] == 0
            assert db.execute("SELECT count(*) FROM jobs").fetchone()[0] == jobs_before
        assert not page.evaluate("document.documentElement.scrollWidth > innerWidth")
        assert not errors, errors
        modal.locator(".video-taste-recipe summary").click()
        modal.locator("#modal-body").evaluate("(n) => n.scrollTop = 0")
        page.screenshot(path=str(OUT / f"editor-{width}.png"))
        if width == 1440:
            css = "\n".join(
                (ROOT / "mission_control/static" / n).read_text(encoding="utf-8")
                for n in ("style.css", "video-editor.css")
            )
            html = modal.evaluate("(n) => n.outerHTML")
            page_heading = page.locator("h1").first.evaluate("(n) => n.outerHTML")
            (OUT / "editor-modal.html").write_text(
                '<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width,initial-scale=1">'
                "<title>Review your video edit</title><style>"
                + css
                + "</style></head><body>"
                + page_heading
                + html
                + "</body></html>",
                encoding="utf-8",
            )
        return dict(
            width=width,
            keyboard_review_apply_save=True,
            draft_only=True,
            explicit_revision=2,
            source_and_trim_preserved=True,
            unsaved_render_rejected=True,
            render_jobs_created=0,
            no_overflow=True,
            page_errors=errors,
        )
    finally:
        if context:
            context.close()
        fixture.tearDown()


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            result = dict(
                status="PASS",
                browser=browser.version,
                observations=[exercise(browser, width) for width in (1440, 390)],
                scope="Synthetic owner/local media; no provider or native-device acceptance",
            )
            (OUT / "browser.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(result))
        finally:
            browser.close()
