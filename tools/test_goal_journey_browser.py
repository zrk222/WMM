"""Actual goal-first home, synthetic apps, no provider or campaign execution."""
from pathlib import Path
import json,sys,threading
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright,expect
from mission_control.server import Server
from mission_control.worker import jobs
from tests.test_guided_workflow import GuidedWorkflowTests

def run(browser,width,out):
 fixture=GuidedWorkflowTests();fixture.setUp()
 fixture.store.save_app("sample-two",dict(name="Second synthetic app",release="test",job="Another app goal",audience="Synthetic audience",activation="Synthetic value",locale="en-US"))
 server=Server(("127.0.0.1",0),fixture.store);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 context=browser.new_context(viewport={"width":width,"height":900});page=context.new_page();errors=[];writes=[]
 page.on("pageerror",lambda error:errors.append(str(error)))
 page.on("request",lambda request:writes.append(request.url) if request.method=="POST" else None)
 try:
  page.goto("http://127.0.0.1:"+str(server.server_port))
  page.wait_for_function("() => state.workspace?.app?.id===state.app")
  expect(page.get_by_role("heading",name="Set your goal",exact=True)).to_be_visible()
  nav=page.locator("#navigation");expect(nav.get_by_role("button",name="Watch the work",exact=True)).to_be_visible()
  nav.locator("summary").focus();nav.locator("summary").press("Enter")
  expect(nav.get_by_role("button",name="Guided workflow",exact=True)).to_be_visible()
  nav.locator("summary").press("Enter")
  page.get_by_role("button",name="Run an approved campaign",exact=True).click()
  expect(page.locator("#goal-message")).to_contain_text("No work has started")
  expect(page.get_by_role("button",name="Review campaign setup",exact=True)).to_be_focused()
  expect(page.get_by_role("region",name="Your selected goal")).to_contain_text("No Facebook Page connection")
  assert not writes,writes
  page.screenshot(path=str(out/f"goal-home-{width}.png"),full_page=True)
  (out/f"goal-home-{width}.html").write_text(page.content(),encoding="utf-8")
  page.locator("#app-select").select_option("sample-two");page.wait_for_function("expected => state.workspace?.app?.id===expected",arg="sample-two")
  expect(page.get_by_role("region",name="Your selected goal")).to_have_count(0)
  page.get_by_role("button",name="Understand app results",exact=True).click()
  page.locator("#app-select").select_option("sample-one");page.wait_for_function("expected => state.workspace?.app?.id===expected",arg="sample-one")
  expect(page.get_by_role("heading",name="Run an approved campaign",exact=True)).to_be_visible()
  page.reload();page.wait_for_function("expected => state.workspace?.app?.id===expected",arg="sample-one")
  expect(page.get_by_role("heading",name="Run an approved campaign",exact=True)).to_be_visible()
  page.locator("#goal-advanced > summary").click()
  with page.expect_popup() as popup_info: page.get_by_role("button",name="Report / Save PDF",exact=True).click()
  popup=popup_info.value;expect(popup.get_by_role("heading",name="Overview — WMM report",exact=True)).to_have_count(0)
  expect(popup.locator("body")).to_contain_text("No publication, spend or approval authority")
  popup.close()
  nav.get_by_role("button",name="Watch the work",exact=True).click();expect(page.locator("#main .page-heading")).to_be_visible()
  nav.get_by_role("button",name="Review results",exact=True).click();expect(page.locator("#main .page-heading")).to_be_visible()
  assert not jobs(fixture.store,"sample-one");assert not writes,writes
  assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
  assert not errors,errors
  return dict(width=width,keyboard_navigation=True,app_isolation=True,reload_retains_choice=True,pdf_preview=True,no_mutations=True,javascript_errors=errors)
 finally:
  context.close();server.shutdown();server.server_close();thread.join();fixture.doCleanups()

def main():
 out=ROOT/".factory/goal-first-automation";out.mkdir(parents=True,exist_ok=True)
 with sync_playwright() as p:
  browser=p.chromium.launch();result={"status":"PASS","observations":[run(browser,width,out) for width in (1440,390)]};browser.close()
 (out/"browser.json").write_text(json.dumps(result,indent=2),encoding="utf-8");print(json.dumps(result))
if __name__=="__main__":main()
