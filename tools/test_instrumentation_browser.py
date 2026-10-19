"""Actual browser IndexedDB and download UI; synthetic provider only, no live campaign."""
from pathlib import Path
from io import BytesIO
import hashlib,json,sys,zipfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright,expect
from test_tracking_browser import prepare,review

CONFIG=dict(schema='growth.browser-instrumentation.v1',app_id='sample-one',release='build-1',locale='en-US',
 experiment_id='c7952e67-b1d5-4934-a220-cf32c8c48cf5',experiment_hash='a'*64,
 flag_key='wmm-c7952e67-b1d5-4934-a220-cf32c8c48cf5',starts_at='2026-01-01T00:00:00Z',ends_at='2027-01-01T00:00:00Z',origin='https://example.com')
HTML='''<html><body><div id="variant">Synthetic control</div><script type="module">
import {createTracker} from '/client.mjs';
window.events=[];window.controls={consent:true,arm:'control',enabled:true,identity:'synthetic-user'};
const callbacks=new Set();
const client={config:{person_profiles:'always'},get_distinct_id:()=>controls.identity,has_opted_out_capturing:()=>false,
 onFeatureFlags:fn=>{callbacks.add(fn);return()=>callbacks.delete(fn);},setPersonPropertiesForFlags:()=>{},
 reloadFeatureFlags:()=>queueMicrotask(()=>{for(const fn of [...callbacks])fn([],{},{});}),
 getFeatureFlagResult:()=>({enabled:controls.enabled,variant:controls.arm}),
 capture:(event,properties,options)=>{events.push({event,properties,options});return {};}};
window.tracker=createTracker(CONFIG,client,{consent:()=>controls.consent,
 context:()=>({app_id:'sample-one',release:'build-1',locale:'en-US',identified:true,id:controls.identity})});
window.ready=true;
</script></body></html>'''.replace('CONFIG',json.dumps(CONFIG))


def storage_journey(browser):
    context=browser.new_context();source=(ROOT/'mission_control/sdk/experiment-client.mjs').read_text(encoding='utf-8')
    context.route('https://example.com/**',lambda route:route.fulfill(status=200,
        content_type='text/javascript' if route.request.url.endswith('client.mjs') else 'text/html',
        body=source if route.request.url.endswith('client.mjs') else HTML))
    pages=[context.new_page(),context.new_page()]
    for page in pages:page.goto('https://example.com/');page.wait_for_function('window.ready===true')
    # Launch both tabs before awaiting either; real IndexedDB transactions arbitrate.
    for page in pages:page.evaluate('window.pending=tracker.assign().then(v=>{window.result=v;}); true')
    for page in pages:page.wait_for_function('window.result!==undefined')
    events=sum([page.evaluate('events') for page in pages],[])
    assert len({event['options']['uuid'] for event in events})==1
    page=pages[0];page.bring_to_front()
    assert page.evaluate('tracker.expose(document.querySelector("#variant"),"control")')['status']=='QUEUED_NOT_DELIVERED'
    exposure=page.evaluate('events.filter(e=>e.event.endsWith("exposure"))');assert len(exposure)==1
    page.reload();page.wait_for_function('window.ready===true')
    assert page.evaluate('tracker.assign()')['status']=='ALREADY_QUEUED_NOT_DELIVERED'
    assert page.evaluate('tracker.expose(document.querySelector("#variant"),"control")')['status']=='ALREADY_QUEUED_NOT_DELIVERED'
    assert page.evaluate('events.length')==0
    for expression,expected in [('controls.enabled=false','FLAG_UNAVAILABLE'),('controls.enabled=true;controls.arm="treatment"','ASSIGNMENT_CHANGED'),
                                ('controls.arm="control";controls.consent=false','CONSENT_REQUIRED')]:
        page.evaluate(expression)
        assert page.evaluate('tracker.assign().then(()=>"unexpected",e=>e.code)')==expected
    context.close()
    return dict(real_indexeddb=True,two_tab_stable_uuid=True,reload_deduplication=True,kill_switch=True,consent_denial=True)


def ui_journey(browser,width,height):
    fixture,server,thread=prepare()
    try:
        app=fixture.store.app('sample-one');fixture.store.save_app('sample-one',{**app['data'],'website':'https://example.com'},app['version'])
        page=browser.new_page(viewport=dict(width=width,height=height),accept_downloads=True);errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(f'http://127.0.0.1:{server.server_port}');page.locator('#main h1').wait_for()
        page.locator('[data-view="pipeline"]').first.click();review(page)
        button=page.locator('[data-action="automatic-tracking-package"]');expect(button).to_be_visible()
        expect(page.locator('#tracking-dialog')).to_contain_text('does not install code')
        with page.expect_download() as download:button.click()
        received=download.value;assert received.failure() is None
        raw=Path(received.path()).read_bytes()
        with zipfile.ZipFile(BytesIO(raw)) as zipped:
            manifest=json.loads(zipped.read('manifest.json'))
            for row in manifest['files']:assert hashlib.sha256(zipped.read(row['name'])).hexdigest()==row['sha256']
            assert json.loads(zipped.read('config.json'))['experiment_id']==fixture.experiment['id']
        # A changed source after review produces an inline recovery error, no fake download success.
        app=fixture.store.app('sample-one');fixture.store.save_app('sample-one',{**app['data'],'release':'changed'},app['version'])
        button.click();expect(page.locator('#tracking-error')).not_to_be_empty()
        assert not errors and page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        page.screenshot(path=str(ROOT/f'.factory/instrumentation-ui-{width}.png'))
        html=page.content().replace('<link rel="stylesheet" href="/style.css">','<style>'+(ROOT/'mission_control/static/style.css').read_text(encoding='utf-8')+'</style>')
        (ROOT/f'.factory/instrumentation-ui-{width}.html').write_text(html,encoding='utf-8')
        result=dict(viewport=[width,height],startup_build_id=server.service.build_id,download_verified=True,
                    stale_source_recovery=True,horizontal_overflow=False,js_errors=errors)
        page.close();return result
    finally:server.shutdown();server.server_close();thread.join();fixture.doCleanups()


def main():
    with sync_playwright() as runtime:
        browser=runtime.chromium.launch();storage=storage_journey(browser)
        ui=[ui_journey(browser,w,h) for w,h in ((1440,900),(390,844))];browser.close()
    result=dict(status='PASS',scope='Actual browser storage and isolated UI with mocked provider; not installation or delivery proof',storage=storage,observations=ui)
    (ROOT/'.factory/instrumentation-browser.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))


if __name__=='__main__':main()
