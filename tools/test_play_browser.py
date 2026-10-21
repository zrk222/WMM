"""Synthetic localhost UI journey; external consent and provider reads are mocked explicitly."""
from pathlib import Path
import json,sys,threading
from unittest.mock import patch
from urllib.parse import parse_qs,urlsplit,urlencode
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from mission_control.server import Server
from mission_control.worker import run_once
from mission_control import play_auth
from tests.test_play_worker import PlayFixture
from tests.test_play_connections import CONFIG,GRANT
from playwright.sync_api import sync_playwright,expect


def review(page,base,fixture,width,height):
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(base);page.locator('#main h1').wait_for()
    page.locator('#app-select').select_option('sample-one')
    page.locator('[data-view="connections"]').click()
    panel=page.locator('#google-play-connector');expect(panel).to_contain_text('com.example.synthetic')
    panel.get_by_role('button',name='Reconnect',exact=True).focus();page.keyboard.press('Enter')
    expect(page.locator('#modal-title')).to_have_text('Connect this Android app')
    page.locator('#play-metadata-file').set_input_files(dict(name='app.json',mimeType='application/json',buffer=b'{"expo":{"android":{"package":"com.example.synthetic"}}}'))
    expect(page.locator('#play-discovery')).to_contain_text('Package found')
    page.locator('[name="client_file"]').set_input_files(dict(name='client.json',mimeType='application/json',buffer=json.dumps({'installed':CONFIG}).encode()))
    page.locator('[name="confirm_read"]').check()
    page.get_by_role('button',name='Prepare Google consent',exact=True).click()
    expect(page.locator('#modal-title')).to_have_text('Continue with Google')
    url=page.locator('#modal-body a').get_attribute('href')
    assert urlsplit(url).netloc=='accounts.google.com'
    query=parse_qs(urlsplit(url).query);assert query['redirect_uri']==[base]
    assert page.locator('[name="client_file"]').count()==0
    out=ROOT/'.factory/android-platform';out.mkdir(parents=True,exist_ok=True)
    page.locator('#modal').screenshot(path=str(out/f'play-consent-{width}.png'))
    callback=page.context.new_page()
    callback.goto(base+'/?'+urlencode(dict(state=query['state'][0],code='synthetic-browser-code')))
    expect(callback.locator('#connection-title')).to_have_text('Google Play read access verified')
    callback.screenshot(path=str(out/f'play-callback-{width}.png'))
    assert '?' not in callback.url
    assert callback.evaluate("localStorage.getItem('growth-app')")=='sample-one'
    callback.close();page.locator('#close-modal').click();page.reload()
    page.locator('[data-view="connections"]').click()
    panel=page.locator('#google-play-connector');expect(panel).to_contain_text('Last verified')
    panel.get_by_role('button',name='Read releases',exact=True).click()
    expect(page.locator('#modal-title')).to_have_text('Google Play read')
    run_once(fixture.store)
    expect(page.locator('#modal-body')).to_contain_text('No non-obsolete releases',timeout=15000)
    page.get_by_role('button',name='Review and retry',exact=True).click()
    expect(page.locator('#modal-title')).to_have_text('Review the current Android target')
    page.get_by_role('button',name='Read current target',exact=True).click()
    expect(page.locator('#modal-title')).to_have_text('Google Play read')
    fixture.network.side_effect=ValueError('Synthetic Google read outage')
    run_once(fixture.store);fixture.network.side_effect=None
    expect(page.locator('#modal-body')).to_contain_text('did not produce a verified observation',timeout=15000)
    page.get_by_role('button',name='Review and retry',exact=True).click()
    expect(page.locator('#modal-title')).to_have_text('Review the current Android target')
    page.locator('#close-modal').click()
    # A delayed setup response cannot reopen a dialog the user closed.
    page.locator('#google-play-connector').get_by_role('button',name='Reconnect',exact=True).click()
    page.evaluate("window.originalPlayApi=api;window.pendingPlay=new Promise(resolve=>window.resolvePlay=resolve);api=()=>pendingPlay;window.submission=playSubmit(document.querySelector('#play-setup-form'));document.querySelector('#modal').close()")
    page.evaluate("resolvePlay({authorization_url:'https://accounts.google.com/o/oauth2/v2/auth',flow_id:'synthetic-delayed',package_name:'com.example.synthetic',track:'production'})")
    page.evaluate('window.submission');assert not page.locator('#modal').evaluate('(element)=>element.open')
    page.evaluate('()=>{api=window.originalPlayApi;}')
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    assert not errors,errors
    out=ROOT/'.factory/android-platform';out.mkdir(parents=True,exist_ok=True)
    page.screenshot(path=str(out/f'play-connections-{width}.png'),full_page=True)
    css=(ROOT/'mission_control/static/style.css').read_text(encoding='utf-8')
    html=page.content().replace('</head>','<style>'+css+'</style></head>')
    (out/f'play-connections-{width}.html').write_text(html,encoding='utf-8')
    return dict(viewport=[width,height],keyboard=True,discovery=True,callback_query_cleared=True,typed_read=True,
                retry_current_target=True,error_recovery=True,late_response_did_not_reopen=True,horizontal_overflow=False,js_errors=errors)


def main():
    fixture=PlayFixture();fixture.setUp()
    server=Server(('127.0.0.1',0),fixture.store)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with patch('mission_control.connection_setup.Vault',return_value=fixture.vault),patch('mission_control.play_connections.Vault',return_value=fixture.vault),patch.object(play_auth,'exchange',return_value=GRANT),sync_playwright() as runtime:
            browser=runtime.chromium.launch();rows=[]
            for width,height in ((1440,900),(390,844)):
                context=browser.new_context(viewport=dict(width=width,height=height))
                rows.append(review(context.new_page(),f'http://127.0.0.1:{server.server_port}',fixture,width,height));context.close()
            browser.close()
        result=dict(status='PASS',scope='Isolated localhost; synthetic Google consent and responses. No live provider or account verified.',observations=rows)
        (ROOT/'.factory/android-platform/play-browser.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
    finally:server.shutdown();server.server_close();thread.join();fixture.doCleanups()


if __name__=='__main__':main()
