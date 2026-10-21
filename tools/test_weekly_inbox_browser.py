"""Real browser review and recovery with isolated synthetic app evidence."""
from pathlib import Path
import json,sys,tempfile,threading
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mission_control.server import Server
from mission_control.store import Store
from playwright.sync_api import sync_playwright,expect

def main():
    rows=[]
    with tempfile.TemporaryDirectory() as folder:
        store=Store(Path(folder)/'test.sqlite',seed=False)
        for app,name in [('sample-one','First synthetic app'),('sample-two','Second synthetic app')]:
            store.save_app(app,dict(name=name,job='Synthetic task',audience='Test',activation='Saved step',release='build-1',locale='en-US'))
        server=Server(('127.0.0.1',0),store);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with sync_playwright() as runtime:
                browser=runtime.chromium.launch()
                for width,height in ((1440,900),(390,844)):
                    page=browser.new_page(viewport=dict(width=width,height=height));errors=[]
                    page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto(f'http://127.0.0.1:{server.server_port}/');page.locator('#main h1').wait_for()
                    page.locator('[data-view="weekly"]').click()
                    page.get_by_role('button',name='Review apps',exact=True).click()
                    expect(page.locator('#main')).to_contain_text('8 exceptions on this page')
                    expect(page.locator('#main')).to_contain_text('Second synthetic app')
                    out=ROOT/'.factory';out.mkdir(exist_ok=True)
                    page.screenshot(path=str(out/f'weekly-inbox-review-{width}.png'),full_page=True)
                    css=(ROOT/'mission_control/static/style.css').read_text(encoding='utf-8')
                    html=page.content().replace('</head>','<style>'+css+'</style></head>')
                    (out/f'weekly-inbox-review-{width}.html').write_text(html,encoding='utf-8')
                    page.locator('[data-action="weekly-recover"][data-app="sample-two"][data-tool="retention"]').focus()
                    page.keyboard.press('Enter')
                    expect(page.locator('#modal')).to_be_visible()
                    assert page.evaluate('state.app')=='sample-two'
                    page.keyboard.press('Escape')
                    page.locator('[data-view="weekly"]').click()
                    # A late response must not reopen the review after navigation away.
                    page.route('**/api/weekly-review?offset=0',lambda route:route.fulfill(status=200,content_type='application/json',body='{}'))
                    page.evaluate("state.view='weekly';window.delayed=new Promise(resolve=>window.resolveDelayed=resolve);window.savedApi=api;api=()=>delayed;window.pendingWeekly=weeklyAction({dataset:{action:'weekly-refresh'}});state.view='overview';state.weeklyGeneration++;resolveDelayed({exceptions:[],apps:[],coverage:{}})")
                    page.evaluate('window.pendingWeekly')
                    assert page.evaluate('state.view')=='overview'
                    page.evaluate('api=window.savedApi;state.weeklyLoading=false;state.view="weekly";render()')
                    page.unroute('**/api/weekly-review?offset=0')
                    page.route('**/api/weekly-review?offset=0',lambda route:route.fulfill(status=500,content_type='application/json',body='{"error":"Synthetic outage"}'))
                    page.get_by_role('button',name='Refresh review',exact=True).click()
                    expect(page.locator('#main')).to_contain_text('Synthetic outage')
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                    assert not errors,errors
                    out=ROOT/'.factory';out.mkdir(exist_ok=True)
                    page.screenshot(path=str(out/f'weekly-inbox-{width}.png'),full_page=True)
                    (out/f'weekly-inbox-{width}.html').write_text(page.content(),encoding='utf-8')
                    rows.append(dict(viewport=[width,height],cross_app_recovery=True,keyboard=True,error_visible=True,horizontal_overflow=False,js_errors=errors))
                    page.close()
                browser.close()
        finally:server.shutdown();server.server_close();thread.join()
    result=dict(status='PASS',scope='Isolated browser; no campaign or measured founder time savings',observations=rows)
    (ROOT/'.factory/weekly-inbox-browser.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))

if __name__=='__main__':main()
