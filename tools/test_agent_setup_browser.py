"""Owner setup review at desktop/mobile widths; synthetic identity, no provider effects."""

import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from playwright.sync_api import sync_playwright, expect
from mission_control import agent_setup
from mission_control.worker import jobs
from tests.test_campaign_access import CampaignGatewayTests
from tests.test_verified_review import OWNER_TOKEN


def run(browser, width, packaged, output):
    fixture = CampaignGatewayTests()
    fixture.setUp()
    context = browser.new_context(viewport=dict(width=width, height=900), accept_downloads=True)
    page = context.new_page()
    errors, requests = [], []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.on("request", lambda request: requests.append(request.url) if request.method == "POST" else None)
    original = agent_setup.report
    executable = ROOT / "Synthetic installed app" / ("WMM.exe" if sys.platform == "win32" else "WMM")

    def projection(origin, **kwargs):
        return original(origin, runtime_executable=str(executable) if packaged else None)

    kind = "packaged" if packaged else "source"
    try:
        with patch.object(agent_setup, "report", side_effect=projection):
            page.goto(fixture.origin)
            page.wait_for_function("() => state.workspace?.app?.id===state.app")
            page.locator("#navigation > [data-view=activity]").click()
            expect(page.get_by_role("button", name="Review agent setup", exact=True)).to_have_count(0)
            page.get_by_role("button", name="Sign in for verified review", exact=True).click()
            page.get_by_label("GitHub identity token", exact=True).fill(OWNER_TOKEN)
            page.get_by_role("button", name="Verify my identity", exact=True).click()
            expect(page.get_by_role("button", name="Review agent setup", exact=True)).to_be_visible()
            before = fixture.owner.request("POST", "/api/apps/sample-one/agent-grants/list", {})
            assert before["grants"] == []
            requests.clear()
            page.get_by_role("button", name="Review agent setup", exact=True).press("Enter")
            dialog = page.locator("#agent-control-dialog")
            download = dialog.get_by_role("button", name="Download reviewed setup JSON", exact=True)
            expect(download).to_be_visible()
            expect(dialog).to_contain_text("--use-grant")
            expect(dialog).to_contain_text("no separate Python" if packaged else "Source runtime")
            assert requests == [fixture.origin + "/api/apps/sample-one/agent-grants/setup"], requests
            with page.expect_download() as event:
                download.press("Enter")
            value = json.loads(Path(event.value.path()).read_text(encoding="utf-8"))
            expected = projection(fixture.origin)
            assert value == expected
            assert value["runtime_kind"] == ("PACKAGED_DESKTOP" if packaged else "SOURCE_PYTHON")
            assert value["mcp_config"]["mcpServers"]["wmm-local"]["args"][-1] == "--use-grant"
            assert OWNER_TOKEN not in json.dumps(value)
            assert not jobs(fixture.store, "sample-one") and fixture.wire.posts == 0
            assert fixture.owner.request("POST", "/api/apps/sample-one/agent-grants/list", {}) == before
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
            page.locator("#modal").screenshot(path=str(output / f"{kind}-{width}.png"))
            (output / f"{kind}-{width}.html").write_text(page.content(), encoding="utf-8")
            page.keyboard.press("Escape")
            expect(page.locator("#modal")).not_to_be_visible()
            expect(page.get_by_role("button", name="Review agent setup", exact=True)).to_be_focused()
            assert not errors, errors
            return dict(
                width=width,
                runtime=kind,
                exact_json_download=True,
                keyboard_open_download_close=True,
                no_grants_issued=True,
                provider_effects=0,
                javascript_errors=errors,
                execution_profile="Source server; real runtime projector; synthetic identity",
            )
    except BaseException:
        (output / f"first-failure-{kind}-{width}.html").write_text(page.content(), encoding="utf-8")
        page.screenshot(path=str(output / f"first-failure-{kind}-{width}.png"))
        raise
    finally:
        context.close()
        fixture.tearDown()
        fixture.doCleanups()


def main():
    output = ROOT / ".factory/packaged-agent-setup-browser"
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            observations = [
                run(browser, width, packaged, output) for packaged in (False, True) for width in (1440, 390)
            ]
        finally:
            browser.close()
    result = dict(
        status="PASS",
        observations=observations,
        frozen_executable_acceptance="Separate desktop package CI, not this source-server check",
    )
    (output / "browser.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
