"""Actual static preview interactions; synthetic data and zero external requests."""

import json
import re
import threading
from functools import partial
from hashlib import sha256
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / ".factory/organic-video-automation/hypit/preview-browser"


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def exercise(browser, origin, width):
    context = browser.new_context(viewport=dict(width=width, height=1050), accept_downloads=True)
    page = context.new_page()
    errors, external = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: external.append(request.url) if not request.url.startswith(origin) else None)
    try:
        page.goto(origin + "/demo.html")
        expect(page.get_by_role("heading", name="Your next campaign, made clear.")).to_be_visible()
        process = page.locator("#video-process")
        expect(process).to_be_visible()
        expect(process.locator(".video-steps li")).to_have_count(6)
        expect(process).to_contain_text("100,000 views AND 10×")
        expect(process).to_contain_text("does not grant reuse permission")
        video = process.locator("#video-production")
        expect(video).to_be_visible()
        expect(video).to_have_attribute("controls", "")
        expect(video).to_have_attribute("playsinline", "")
        expect(video).to_have_attribute("preload", "none")
        expect(video).to_have_attribute("poster", "media/video-production.webp")
        expect(video).not_to_have_attribute("autoplay", "")
        expect(video.locator("source")).to_have_attribute("src", "media/video-production.mp4")
        expect(video.locator('track[kind="captions"]')).to_have_attribute("src", "media/video-production.vtt")
        video.evaluate("async video => { video.muted = true; await video.play(); }")
        page.wait_for_function("document.querySelector('#video-production').currentTime > 0")
        assert 14 <= video.evaluate("video => video.duration") <= 16
        video.evaluate("video => video.pause()")
        details = process.locator("#video-job-details")
        details.locator("summary").click()
        expect(details.get_by_text("Illustrative plan only", exact=False)).to_be_visible()
        details.locator("summary").click()
        expect(details).not_to_have_attribute("open", "")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Process overflow"
        channels = {
            "facebook": "Facebook Page",
            "instagram": "Instagram Reels",
            "tiktok": "TikTok",
            "youtube": "YouTube Shorts",
            "linkedin": "LinkedIn",
        }
        expect(page.locator(".sample-channel-key .channel-logo")).to_have_count(5)
        expect(page.locator('[name="channels"]')).to_have_count(5)
        page.locator("#channels-clear").click()
        page.locator("#prepare").click()
        expect(page.locator("#notice")).to_contain_text("Choose at least one")
        for key, name in channels.items():
            page.locator('[name="channels"][value="' + key + '"]').check()
            expect(page.locator("#scope-channel")).to_contain_text(name)
        page.locator("#channels-clear").click()
        page.locator('[name="channels"][value="facebook"]').check()
        next_step = page.locator("#next")
        expect(next_step).to_be_disabled()
        page.locator("#app-name").fill("")
        page.locator("#prepare").click()
        expect(page.locator("#consent")).to_be_disabled()
        page.locator("#app-name").fill("Trail Timer")
        page.locator("#prepare").press("Enter")
        expect(page.locator("#consent")).to_be_disabled()
        for approval in page.locator("[data-approve-channel]").all():
            approval.check()
        expect(page.locator("#consent")).to_be_enabled()
        next_step.dispatch_event("click")
        expect(page.locator("#receipts li")).to_have_count(0)
        page.locator("#consent").check()
        next_step.click()
        expect(page.locator("#receipts li")).to_have_count(1)
        page.locator("#stop").click()
        expect(next_step).to_be_disabled()
        expect(page.locator("#receipts li")).to_have_count(1)
        page.locator("#consent").check()
        next_step.click()
        expect(page.locator("#receipts li")).to_have_count(2)
        page.locator("#goal").select_option("creative")
        expect(page.locator("#consent")).not_to_be_checked()
        expect(page.locator("#consent")).to_be_disabled()
        expect(next_step).to_be_disabled()
        expect(page.locator("#report")).to_be_hidden()
        page.locator("#channels-all").click()
        for name in channels.values():
            expect(page.locator("#scope-channel")).to_contain_text(name)
        # Editable content stays text, including HTML-shaped names.
        page.locator("#app-name").fill("<img src=x onerror=alert(1)>")
        page.locator("#prepare").click()
        expect(page.locator("#output")).to_contain_text("<img src=x onerror=alert(1)>")
        expect(page.locator("#output img")).to_have_count(0)
        page.locator("#app-name").fill("Trail Timer")
        page.locator("#prepare").click()
        expect(page.locator("#consent")).to_be_disabled()
        for approval in page.locator("[data-approve-channel]").all():
            approval.check()
        expect(page.locator("#consent")).to_be_enabled()
        # Once loaded, the entire workflow and exports work offline.
        context.set_offline(True)
        page.locator("#consent").focus()
        page.keyboard.press("Space")
        expect(page.locator("#consent")).to_be_checked()
        for number in range(1, 5):
            next_step.click()
            expect(page.locator("#receipts li")).to_have_count(number)
        expect(page.locator("#report")).to_be_visible()
        expect(page.locator("#report-title")).to_be_focused()
        expect(page.locator("#report")).to_contain_text("0 pp")
        expect(next_step).to_be_disabled()
        with page.expect_download() as downloaded:
            page.locator("#export").click()
        value = json.loads(Path(downloaded.value.path()).read_text(encoding="utf-8"))
        assert value["classification"] == "SYNTHETIC_EXAMPLE_NOT_OPERATIONAL_EVIDENCE"
        assert value["plan"]["channels"] == list(channels)
        assert len(value["destinations"]) == 5
        assert all(row["sample_approved"] and row["delivery"] == "NOT_SENT_SAMPLE" for row in value["destinations"])
        assert value["delivery"] == "NOT_SENT_SAMPLE" and value["external_effects"] == 0
        assert value["metrics"]["causal_lift"] is None and value["metrics"]["revenue"] is None
        assert value["plan_sha256"] == sha256(encoded(value["plan"])).hexdigest()
        assert len(value["receipts"]) == 4
        for receipt in value["receipts"]:
            payload = {key: val for key, val in receipt.items() if key not in ("sha256", "recorded_at")}
            assert receipt["sha256"] == sha256(encoded(payload)).hexdigest()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Mobile overflow"
        page.screenshot(path=str(OUT / f"sample-{width}.png"), full_page=True)
        if width == 1440:
            page.screenshot(path=str(ROOT / "docs/images/sample-workflow.png"), full_page=True)
            page.pdf(path=str(OUT / "sample-report.pdf"), print_background=True)
            assert (OUT / "sample-report.pdf").read_bytes().startswith(b"%PDF")
        context.set_offline(False)
        page.goto(origin + "/index.html")
        expect(
            page.get_by_role("heading", level=1, name="Give your personal agent a marketing workspace.")
        ).to_be_visible()
        expect(page.locator("#channels .channel-logo")).to_have_count(5)
        for name in channels.values():
            expect(page.locator("#channels").get_by_role("heading", name=name, exact=True)).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), "Overview overflow"
        studio = page.get_by_role("region", name="Turn a promising idea into a video you can test.")
        expect(studio.get_by_text("What it does:")).to_be_visible()
        expect(studio.get_by_text("What you get:")).to_be_visible()
        studio.get_by_role("link", name="Watch the Studio workflow").click()
        expect(page).to_have_url(origin + "/demo.html#video-process")
        expect(page.locator("#video-process")).to_be_visible()
        page.go_back()
        page.get_by_text("See the pipeline and analytics screens", exact=True).click()
        for image in page.locator("img").all():
            image.scroll_into_view_if_needed()
            expect(image).to_be_visible()
            assert image.evaluate("el => el.complete && el.naturalWidth > 0"), "Broken preview image"
        page.locator(".cta").click()
        expect(page.get_by_role("heading", name="Your next campaign, made clear.")).to_be_visible()
        assert not errors, errors
        assert not external, external
        return dict(
            width=width,
            flow="PASS",
            consent_and_revocation="PASS",
            real_export_hashes="PASS",
            offline="PASS",
            video_process="PASS",
            studio_overview_to_demo="PASS",
            captioned_video_controls="PASS",
            overflow=False,
            javascript_errors=errors,
            external_requests=external,
        )
    finally:
        context.close()


def local_links():
    for name in ("index.html", "demo.html"):
        text = (ROOT / "docs" / name).read_text(encoding="utf-8")
        ids = set(re.findall(r'\bid="([^"]+)"', text))
        for target in re.findall(r'(?:href|src)="([^"]+)"', text):
            if target.startswith(("https:", "http:", "data:")):
                continue
            if target.startswith("#"):
                assert target[1:] in ids, target
            else:
                assert (ROOT / "docs" / target.split("#")[0]).is_file(), target


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(ROOT / "docs")))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as runtime:
            browser = runtime.chromium.launch()
            try:
                rows = [
                    exercise(browser, "http://127.0.0.1:" + str(server.server_port), width) for width in (1440, 390)
                ]
            finally:
                browser.close()
        local_links()
        receipt = dict(state="PASS", profiles=rows, local_links="PASS", screenshots="ACTUAL_SYNTHETIC_SAMPLE_UI")
        (OUT / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print(json.dumps(receipt))
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == "__main__":
    main()
