"""Actual preflight/reuse UI with synthetic retained bytes; no new render."""
from pathlib import Path
import json
import sys
import threading
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright,expect
from mission_control.server import Server
from mission_control.worker import jobs
from tests import test_hypit_preflight as fixture


def run(browser,width,out):
    source=fixture.HypitPreflightTests('test_plan_is_read_only_and_advisory');source.setUp()
    retained=source.retain();before=jobs(source.store,fixture.APP)
    server=Server(('127.0.0.1',0),source.store)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    context=browser.new_context(viewport={'width':width,'height':900});page=context.new_page();errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    try:
        page.goto('http://127.0.0.1:'+str(server.server_port))
        page.locator('#app-select').select_option(fixture.APP)
        page.wait_for_function('expected => state.workspace?.app?.id===expected && currentWorkspace()',arg=fixture.APP)
        page.locator('[data-view=research]').click()
        page.get_by_role('button',name='Render a video',exact=True).click()
        page.locator('#render-form [name=renderer]').select_option('HYPIT_LOCAL')
        page.locator('#render-form [name=brief_id]').select_option(source.request['brief_id'])
        page.locator('#render-form [name=shape]').select_option(source.request['shape'])
        page.locator('#render-form [type=submit]').click()
        try:expect(page.locator('#hypit-plan')).to_contain_text('This preflight starts no build.',timeout=10000)
        except Exception:
            print(json.dumps({'diagnostic_modal':page.locator('#modal-body').inner_text()[:1800],'javascript_errors':errors}))
            raise
        expect(page.locator('#hypit-plan')).to_contain_text('Text-density flags are advisory')
        expect(page.get_by_role('button',name='Queue a new Hypit render',exact=True)).to_be_disabled()
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=str(out/f'hypit-plan-{width}.png'))
        (out/f'hypit-plan-{width}.html').write_text(page.content(),encoding='utf-8')
        page.get_by_role('button',name='Reuse this verified artifact',exact=True).click()
        expect(page.locator('video.render-preview')).to_have_attribute('src',f'/api/apps/{fixture.APP}/hypit-renders/{retained}/preview')
        assert jobs(source.store,fixture.APP)==before
        assert not errors,errors
        return dict(width=width,preflight=True,missing_tools_block_new_build=True,explicit_reuse=True,
                    jobs_unchanged=True,javascript_errors=errors,artifact='SYNTHETIC_IDENTITY_BYTES_ONLY',visual_quality='NOT_ASSESSED')
    finally:
        context.close();server.shutdown();server.server_close();thread.join();source.doCleanups()


def main():
    out=ROOT/'.factory/licensing-automation';out.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch();result=dict(status='PASS',observations=[run(browser,w,out) for w in (1440,390)]);browser.close()
    (out/'hypit-browser.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))


if __name__=='__main__':main()
