"""Actual desktop/mobile owner setup and scheduled batch review; synthetic providers."""
from pathlib import Path
import json,sys
from datetime import datetime,timedelta
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright,expect
from tests.test_campaign_access import CampaignGatewayTests
from tests.test_verified_review import OWNER_TOKEN
from mission_control.worker import jobs

def run(browser,width,out):
 f=CampaignGatewayTests();f.setUp()
 context=browser.new_context(viewport={"width":width,"height":900});page=context.new_page();errors=[]
 page.on("pageerror",lambda e:errors.append(str(e)))
 try:
  page.goto(f.origin);page.wait_for_function("() => state.workspace?.app?.id===state.app")
  page.locator("#navigation > [data-view=activity]").click()
  page.get_by_role("button",name="Sign in for verified review",exact=True).click()
  page.get_by_label("GitHub identity token",exact=True).fill(OWNER_TOKEN)
  page.get_by_role("button",name="Verify my identity",exact=True).click()
  expect(page.get_by_role("button",name="Sign out of review session")).to_be_visible()
  page.locator("#navigation > [data-view=overview]").click()
  page.get_by_role("button",name="Run an approved campaign",exact=True).click()
  page.get_by_role("button",name="Check connections for this goal",exact=True).click()
  form=page.locator("#goal-readiness-form");form.get_by_label("Agent identifier",exact=True).fill("grok-bot")
  form.locator("[name=social_connection_ids]").check()
  form.get_by_role("button",name="Check selected connections",exact=True).click()
  expect(page.locator("#modal-body")).to_contain_text("EXACT_OWNER_CAMPAIGN_SCOPE_REQUIRED")
  expect(page.locator("#modal-body")).to_contain_text("No approval, grant, job or campaign")
  assert f.wire.posts==0;assert not jobs(f.store,"sample-one")
  page.screenshot(path=str(out/f"readiness-{width}.png"));(out/f"readiness-{width}.html").write_text(page.content(),encoding="utf-8")
  page.get_by_role("button",name="Review campaign scope",exact=True).click()
  form=page.locator("#campaign-scope-form");form.locator("[name=connection_id]").select_option(f.connection)
  form.get_by_label("Approved post copy",exact=True).fill(f.message)
  form.get_by_label("Rights and claims evidence",exact=True).fill("Original synthetic app claim evidence")
  form.get_by_role("button",name="Review exact automation scope",exact=True).click()
  page.get_by_role("button",name="Approve scope and enable automation",exact=True).click()
  expect(page.locator("#campaign-progress")).to_contain_text("ACTIVE")
  page.get_by_role("button",name="Schedule approved posts",exact=True).click()
  form=page.locator("#campaign-schedule-form")
  form.locator("[name=due_0]").fill((datetime.now()+timedelta(minutes=2)).strftime("%Y-%m-%dT%H:%M"))
  form.get_by_role("button",name="Review exact scheduled batch",exact=True).click()
  expect(page.locator("#campaign-schedule-review")).to_contain_text(f.message)
  assert f.wire.posts==0;assert not jobs(f.store,"sample-one")
  page.get_by_role("button",name="Approve exact batch and schedule",exact=True).click()
  expect(page.locator("#campaign-schedule-progress")).to_contain_text("ACTIVE")
  page.screenshot(path=str(out/f"schedule-{width}.png"));(out/f"schedule-{width}.html").write_text(page.content(),encoding="utf-8")
  with page.expect_popup() as report_info:page.get_by_role("button",name="Report / Save PDF",exact=True).click()
  report=report_info.value;expect(report.locator("body")).to_contain_text("Scheduled campaign batch")
  assert f.message not in report.locator("body").inner_text();assert OWNER_TOKEN not in report.locator("body").inner_text();report.close()
  page.get_by_role("button",name="Turn scheduled batch OFF",exact=True).click()
  expect(page.locator("#campaign-schedule-progress")).to_contain_text("CANCELLED")
  page.locator("#close-modal").click();page.reload();page.wait_for_function("() => state.workspace?.app?.id===state.app")
  page.locator("#navigation > details > summary").click();page.locator("#navigation [data-view=connections]").click()
  page.get_by_role("button",name="Review campaign automation",exact=True).click()
  page.get_by_role("button",name="Inspect scheduled batch",exact=True).click()
  expect(page.locator("#campaign-schedule-progress")).to_contain_text("OFF")
  assert f.wire.posts==0;assert not jobs(f.store,"sample-one");assert not errors,errors
  assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
  return dict(width=width,owner_readiness=True,blockers_preserved=True,exact_schedule_review=True,no_effect_before_due=True,off=True,durable_reload=True,report_privacy=True,javascript_errors=errors,provider="SYNTHETIC_ONLY")
 finally:
  context.close();f.tearDown();f.doCleanups()

def main():
 out=ROOT/".factory/goal-first-automation"
 with sync_playwright() as p,patch("mission_control.campaign_transport.MetaTransport.request",side_effect=AssertionError("Real provider forbidden")):
  browser=p.chromium.launch();result={"status":"PASS","observations":[run(browser,w,out) for w in (1440,390)]};browser.close()
 (out/"automation-browser.json").write_text(json.dumps(result,indent=2),encoding="utf-8");print(json.dumps(result))
if __name__=="__main__":main()
