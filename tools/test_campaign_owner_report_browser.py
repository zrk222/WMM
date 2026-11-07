"""Protected report capture and scheduled local snapshots at two widths."""
from pathlib import Path
from datetime import datetime, timedelta
import json
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright, expect
from mission_control.db import connection
from tests.test_campaign_owner_reports import CampaignOwnerReportsTests
OUT=ROOT/".factory/paid-pause-readback"

def run(browser,width):
    f=CampaignOwnerReportsTests()
    f.setUp()
    context=browser.new_context(viewport={"width":width,"height":1000})
    page=context.new_page(); errors=[]
    page.on("pageerror",lambda error:errors.append(str(error)))
    try:
        with connection(f.store.path) as db:
            db.execute("UPDATE campaign_monitors SET status='OFF'")
        intent=f.fixture.intent
        f.fixture.wire.objects[intent['ids']['campaign']]['effective_status']='ACTIVE'
        paused=f.fixture.fixture.service.run_pause('sample','owner',f.fixture.scope['scope_id'],intent['id'])
        pause_hash=paused['pause_readback']['sha256']
        page.goto(f.fixture.client.origin)
        page.wait_for_function("() => state.workspace?.app?.id===state.app")
        page.locator("#app-select").select_option("sample")
        page.wait_for_function("() => state.app==='sample' && state.workspace?.app?.id==='sample'")
        page.locator("#navigation > [data-view=activity]").click()
        page.get_by_role("button",name="Sign in for verified review",exact=True).click()
        page.get_by_label("GitHub identity token",exact=True).fill("synthetic_owner_identity_token")
        page.get_by_role("button",name="Verify my identity",exact=True).click()
        expect(page.get_by_role("button",name="Sign out of review session")).to_be_visible()
        page.locator("#navigation > [data-view=overview]").click()
        page.locator("#goal-advanced > summary").click()
        page.get_by_role("button",name="Review private campaign outcomes",exact=True).click()
        form=page.locator("#owner-report-form")
        form.locator("[name=monitor_id]").select_option(f.monitor["id"])
        form.locator("[name=starts_at]").fill("2026-10-01T00:00")
        form.locator("[name=ends_at]").fill("2026-11-01T00:00")
        form.get_by_role("button",name="Continue with exact sources",exact=True).click()
        result=page.locator("#owner-report-result")
        expect(result).to_contain_text("Source dates stay separate")
        expect(result).to_contain_text("unknown")
        result.get_by_text("Exact receipts, source window and integrity",exact=True).click()
        expect(result).to_contain_text("configured PAUSED · effective ACTIVE")
        expect(result).to_contain_text(pause_hash)
        page.screenshot(path=str(OUT/f"owner-report-{width}.png"),full_page=True)
        css=page.evaluate("""() => Array.from(document.styleSheets).flatMap(sheet=>{
            try{return Array.from(sheet.cssRules).map(rule=>rule.cssText)}catch{return []}
            }).join('\\n')""")
        html=result.evaluate('(node)=>node.outerHTML')
        (OUT/f"owner-report-{width}.html").write_text(
            '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" '
            'content="width=device-width,initial-scale=1"><title>Private campaign outcome review</title>'
            '<style>'+css+'</style><main><h1>Your private campaign outcome review</h1>'+html+'</main></html>',
            encoding="utf-8")
        with page.expect_popup() as popup:
            result.get_by_role("button",name="Private report / Save PDF",exact=True).click()
        report=popup.value
        expect(report.locator("body")).to_contain_text("Private campaign outcome review")
        expect(report.locator("body")).to_contain_text("configured PAUSED · effective ACTIVE")
        expect(report.locator("body")).to_contain_text(pause_hash)
        assert "synthetic-secret" not in report.locator("body").inner_text()
        assert "synthetic-token" not in report.locator("body").inner_text()
        report.close()
        result.get_by_role("button",name="Return to saved reports",exact=True).click()
        form=page.locator("#owner-report-form")
        form.locator("[name=scope_id]").select_option(f.fixture.scope["scope_id"])
        form.locator("[name=starts_at]").fill("2026-10-01T00:00")
        form.locator("[name=ends_at]").fill("2026-11-01T00:00")
        form.get_by_role("button",name="Continue with exact sources",exact=True).press("Enter")
        expect(result).to_contain_text("No monitor selected. Monitoring results are unavailable.")
        result.get_by_text("Exact receipts, source window and integrity",exact=True).click()
        expect(result).to_contain_text(pause_hash)
        page.screenshot(path=str(OUT/f"owner-report-without-monitor-{width}.png"))
        result.get_by_role("button",name="Return to saved reports",exact=True).click()
        form=page.locator("#owner-report-form")
        form.locator("[name=monitor_id]").select_option(f.monitor["id"])
        form.locator("[name=starts_at]").fill("2026-10-01T00:00")
        form.locator("[name=ends_at]").fill("2026-11-01T00:00")
        form.locator("[name=mode]").select_option("schedule")
        form.locator("details summary").click()
        form.locator("[name=expires_at]").fill((datetime.now()+timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"))
        form.get_by_role("button",name="Continue with exact sources",exact=True).click()
        review=page.locator("#owner-report-review")
        expect(review).to_contain_text("No provider reads")
        review.get_by_role("button",name="Approve exact report plan",exact=True).click()
        expect(page.locator("#owner-report-plan")).to_contain_text("ACTIVE")
        assert f.fixture.server.runner.poll()
        with connection(f.store.path) as db:
            assert db.execute("SELECT count(*) FROM campaign_owner_reports").fetchone()[0]==3
        page.get_by_role("button",name="Turn report plan OFF",exact=True).click()
        expect(page.locator("#owner-report-plan")).to_contain_text("OFF")
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
        assert not errors,errors
        return dict(width=width,status="PASS",capture=True,capture_without_monitor=True,finite_plan=True,actual_local_worker=True,pdf_privacy=True,pause_readback_retained=True,effective_state_distinct=True,source_windows_explicit=True,off=True,javascript_errors=errors)
    except Exception:
        print(json.dumps({"errors":errors,"body":page.locator("body").inner_text()[-5000:]}))
        raise
    finally:
        context.close();f.doCleanups()

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch()
        try:result={"status":"PASS","observations":[run(browser,w) for w in (1440,390)]}
        finally:browser.close()
    (OUT/"owner-report-browser.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
    print(json.dumps(result))

if __name__=="__main__":main()
