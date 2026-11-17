"""Isolated real UI/server/PDF acceptance; synthetic source data, no provider calls."""

# ruff: noqa: E402  - direct script invocation adds the repository root first.
import json
import sys
import tempfile
import threading
from pathlib import Path
from typing import TypeAlias

import fitz

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import Locator, Page, expect, sync_playwright

from mission_control.growth_review_store import GrowthReviews
from mission_control.server import Server
from mission_control.store import Store
from tests.test_benchmark_ads import SEGMENT, saved_report
from tests.test_benchmark_context import records

JSONValue: TypeAlias = dict[str, object]


def seed(store: Store) -> None:
    for identity in ("sample-one", "sample-two"):
        store.save_app(
            identity,
            dict(
                name="Synthetic Café 東京 " + identity,
                release="build-1",
                locale="en-US",
                currency="USD",
                store_app_id="123",
            ),
        )
    saved_report(store)


def fill_listing(page: Page, platform: str = "iOS") -> None:
    page.get_by_label("Store platform", exact=True).select_option(platform)
    page.get_by_label("Change or test surface").select_option("MANUAL_METADATA")
    for name, value in dict(
        title="Café 東京 useful step",
        subtitle="Remember a useful next step",
        keywords="useful,progress",
        description="Original description. " * 160 + "DESCRIPTION_END_MARKER",
    ).items():
        page.locator("#growth-" + name).fill(value)
    page.locator("#growth-promotional_text").fill("Original optional promotional text")


def save_form(page: Page):
    with page.expect_response(
        lambda response: "/subscription-growth/entries" in response.url and response.request.method == "POST"
    ) as response:
        page.get_by_role("button", name="Save evidence", exact=True).click()
    assert response.value.status == 201, response.value.text()
    result = response.value.json()
    expect(page.locator("#modal")).not_to_be_visible()
    return result


def fill_reference(page: Page) -> None:
    reference, _ = records()
    reference.update(
        period_start="2026-10-01T00:00:00+00:00",
        period_end="2026-10-08T00:00:00+00:00",
        published_at="2026-10-10T00:00:00+00:00",
        retrieved_at="2026-10-22T00:00:00+00:00",
    )
    for name, value in reference.items():
        if name == "denominator":
            continue
        locator = page.locator("#growth-" + name)
        if name in ("metric", "platform", "coverage"):
            locator.select_option(str(value))
        else:
            locator.fill(str(value))


def compare(page: Page, reference_id: str):
    page.get_by_role("button", name="Compare saved report", exact=True).click()
    page.locator("#growth-reference_id").select_option(reference_id)
    page.locator("#growth-job_id").select_option("job-one")
    page.locator("#growth-metric").select_option("CPT_MINOR")
    for name, value in SEGMENT.items():
        page.locator("#growth-" + name).fill(value)
    return save_form(page)


def check_report(report: Locator, title: str) -> None:
    expect(report).to_be_visible()
    expect(report.get_by_role("heading", level=1)).to_have_text(title)
    expect(report.locator("input,textarea")).to_have_count(0)
    expect(report).not_to_contain_text("PRIVATE_SENTINEL")


def check_inline_report(page: Page, trigger: Locator, title: str) -> Locator:
    report = page.locator(".wmm-report-dialog[open]")
    check_report(report, title)
    expect(report.get_by_role("heading", level=1)).to_be_focused()
    page.evaluate("window.wmmTestPrint=window.print; window.print=()=>{window.wmmPrinted=true}")
    try:
        report.get_by_role("button", name="Print / Save as PDF", exact=True).focus()
        page.keyboard.press("Enter")
        assert page.evaluate("window.wmmPrinted===true")
    finally:
        page.evaluate("window.print=window.wmmTestPrint; delete window.wmmTestPrint; delete window.wmmPrinted")
    expect(trigger).not_to_be_focused()
    return report


def close_inline_report(page: Page, report: Locator, trigger: Locator) -> None:
    report.get_by_role("button", name="Close report", exact=True).focus()
    page.keyboard.press("Enter")
    expect(page.locator(".wmm-report-dialog")).to_have_count(0)
    expect(trigger).to_be_focused()


def export_pdf(page: Page, path: Path, title: str, *, inline: bool = False) -> int:
    trigger = page.locator('#modal [data-action="growth-report"]')
    trigger.focus()
    if inline:
        page.keyboard.press("Enter")
        surface = page
        report = check_inline_report(page, trigger, title)
    else:
        with page.expect_popup() as waiting:
            page.keyboard.press("Enter")
        surface = waiting.value
        surface.wait_for_load_state("load")
        assert surface.evaluate("window.opener===null")
        report = surface.locator("body")
        check_report(report, title)
    try:
        css = (ROOT / "mission_control/static/page-reporting.css").read_text(encoding="utf-8")
        snapshot = (
            '<!doctype html><html lang="en"><head><meta charset="utf-8"><style>'
            + css
            + '</style></head><body class="wmm-print-report">'
            + report.inner_html()
            + "</body></html>"
            if inline
            else surface.content().replace("</head>", "<style>" + css + "</style></head>")
        )
        path.with_suffix(".html").write_text(snapshot, encoding="utf-8")
        surface.pdf(path=str(path), format="A4", print_background=True)
    finally:
        if inline:
            close_inline_report(page, report, trigger)
        else:
            surface.close()
    with fitz.open(path) as document:
        text = "\n".join(str(item.get_text()) for item in document)
        assert "Café" in text and "東京" in text
        assert "DESCRIPTION_END_MARKER" in text
        assert "PRIVATE_SENTINEL" not in text
        assert "limit 30" in text and "Source hash" in text
        assert len(document) >= 2
        pages = len(document)
    return pages


def exercise(page: Page, origin: str, store: Store, width: int, out: Path) -> JSONValue:
    page.goto(origin)
    page.locator('[data-view="results"]').click()
    expect(page.locator("#growth-review-title")).to_be_visible()
    kpi = page.get_by_role("region", name="KPI gaps")
    metric = page.get_by_role("cell", name="ROAS_D30", exact=True)
    roas = kpi.get_by_role("row").filter(has=metric)
    missing = roas.locator(".status.missing")
    expect(metric).to_be_visible()
    expect(metric).to_have_css("white-space", "nowrap")
    expect(missing).to_have_text("MISSING")
    expect(missing).to_have_css("white-space", "nowrap")
    expect(missing).to_have_css("background-color", "rgb(249, 235, 206)")
    expect(missing).to_have_css("color", "rgb(101, 70, 9)")
    kpi.screenshot(path=str(out / f"kpi-gaps-{width}.png"))
    page.locator('#growth-review-panel [data-action="growth-listing"]').focus()
    page.keyboard.press("Enter")
    fill_listing(page)
    page.screenshot(path=str(out / f"listing-form-{width}.png"))
    # A real server error leaves all original input values available for correction/retry.
    page.route(
        "**/subscription-growth/entries",
        lambda route: route.fulfill(
            status=400, content_type="application/json", body=json.dumps({"error": "Synthetic recoverable rejection"})
        ),
    )
    page.get_by_role("button", name="Save evidence", exact=True).click()
    expect(page.locator("#growth-form-error")).to_contain_text("Inputs are preserved")
    expect(page.locator("#growth-title")).to_have_value("Café 東京 useful step")
    page.unroute("**/subscription-growth/entries")
    listing = save_form(page)
    current = next(row for row in GrowthReviews(store).list("sample-one")["history"] if row["id"] == listing["id"])
    assert current["readout"]["analysis"]["status"] == "READY_FOR_REVIEW"
    page.locator(f'[data-action="growth-detail"][data-id="{listing["id"]}"]').click()
    expect(page.locator("#modal-body")).to_contain_text("limit 30")
    page.evaluate(
        "async () => {const {state}=await import('/app.mjs');state.privateDraft='PRIVATE_SENTINEL'; state.workspace.credentials='PRIVATE_SENTINEL';}"
    )
    title = "Saved growth review: " + listing["id"]
    # This listing has no sections: it attempts a popup, then falls back when blocked.
    page.evaluate("window.wmmTestOpen=window.open; window.open=()=>null")
    try:
        inline_pages = export_pdf(page, out / f"listing-inline-{width}.pdf", title, inline=True)
        expect(page.locator("#modal")).to_be_visible()
    finally:
        page.evaluate("window.open=window.wmmTestOpen; delete window.wmmTestOpen")
    pdf_pages = export_pdf(page, out / f"listing-{width}.pdf", title)
    page.locator('#modal [data-action="growth-note"]').click()
    page.locator("#growth-decision").select_option("REVISE")
    page.locator("#growth-rationale").fill("Keep the source and test a shorter title. Local reasoning only.")
    note = save_form(page)
    assert note["data"]["target_hash"] == listing["hash"]
    page.locator('[data-action="growth-reference"]').click()
    fill_reference(page)
    reference = save_form(page)
    comparison = compare(page, reference["id"])
    current = next(row for row in GrowthReviews(store).list("sample-one")["history"] if row["id"] == comparison["id"])
    assert current["readout"]["analysis"]["difference"] == 100
    page.locator(f'[data-action="growth-detail"][data-id="{comparison["id"]}"]').click()
    expect(page.locator("#modal-body")).to_contain_text("Numerator 3000.00; denominator 10 TAPS")
    expect(page.locator("#modal-body")).to_contain_text("advisory difference 100")
    page.locator("#close-modal").click()
    page.reload()
    page.locator('[data-view="results"]').click()
    expect(page.locator(f'[data-action="growth-detail"][data-id="{listing["id"]}"]')).to_be_visible()
    # A server-side manifest change during editing cannot save into the changed setup.
    page.locator('[data-action="growth-listing"]').click()
    fill_listing(page, "Android")
    before = len(GrowthReviews(store).list("sample-one")["history"])
    app = store.app("sample-one")
    store.save_app("sample-one", dict(app["data"], job="Changed during the form"), app["version"])
    page.get_by_role("button", name="Save evidence", exact=True).click()
    expect(page.locator("#growth-form-error")).to_contain_text("Inputs are preserved")
    assert len(GrowthReviews(store).list("sample-one")["history"]) == before
    expect(page.locator("#growth-title")).to_have_value("Café 東京 useful step")
    page.locator("#close-modal").click()
    page.reload()
    page.locator('[data-view="results"]').click()
    # Verify the second platform can actually save under a newly current app version.
    page.locator('[data-action="growth-listing"]').click()
    fill_listing(page, "Android")
    android = save_form(page)
    assert android["data"]["listing"]["platform"] == "Android"
    assert "keywords" not in android["data"]["listing"]["fields"]
    page.screenshot(path=str(out / f"results-{width}.png"), full_page=True)
    page.screenshot(path=str(out / f"results-viewport-{width}.png"))
    css = (ROOT / "mission_control/static/style.css").read_text(encoding="utf-8") + (
        ROOT / "mission_control/static/page-reporting.css"
    ).read_text(encoding="utf-8")
    (out / f"results-{width}.html").write_text(
        page.content().replace("</head>", "<style>" + css + "</style></head>"), encoding="utf-8"
    )
    assert page.evaluate("document.documentElement.scrollWidth<=window.innerWidth"), "Horizontal overflow"
    page.locator("#app-select").select_option("sample-two")
    expect(page.locator("#growth-review-panel")).to_contain_text("No saved entries yet")
    assert page.locator(f'[data-action="growth-detail"][data-id="{listing["id"]}"]').count() == 0
    return dict(
        width=width,
        saved_entries=5,
        pdf_pages=pdf_pages,
        inline_pdf_pages=inline_pages,
        durable_readback=True,
        manifest_rejection=True,
        keyboard=True,
        privacy=True,
        app_switch=True,
        horizontal_overflow=False,
    )


def main() -> None:
    out = ROOT / ".factory/growth-review-ui"
    out.mkdir(parents=True, exist_ok=True)
    observations = []
    with tempfile.TemporaryDirectory(prefix="wmm-growth-ui-") as folder, sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            for width in (1440, 390):
                store = Store(Path(folder) / f"ui-{width}.sqlite", seed=False)
                seed(store)
                server = Server(("127.0.0.1", 0), store)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                page = browser.new_page(viewport={"width": width, "height": 900 if width == 1440 else 844})
                errors: list[str] = []
                page.on("pageerror", lambda error, errors=errors: errors.append(str(error)))
                try:
                    observations.append(exercise(page, f"http://127.0.0.1:{server.server_port}", store, width, out))
                    assert not errors, errors
                except Exception:
                    (out / f"failure-{width}.html").write_text(page.content(), encoding="utf-8")
                    page.screenshot(path=str(out / f"failure-{width}.png"), full_page=True)
                    print(page.locator("#toast").text_content(), flush=True)
                    raise
                finally:
                    page.close()
                    server.shutdown()
                    server.server_close()
                    thread.join()
            (out / "browser.json").write_text(
                json.dumps(dict(status="PASS", browser=browser.version, observations=observations), indent=2),
                encoding="utf-8",
            )
            print(json.dumps(observations))
        finally:
            browser.close()


if __name__ == "__main__":
    main()
