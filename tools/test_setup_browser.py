"""Actual localhost UI, synthetic public website; no external account or product proof."""
from pathlib import Path
import json
import sys
import threading
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mission_control.server import Server
from tests.test_setup_discovery import SetupFixture
from tests.test_aeo_inspection import Reader, ROOT as SITE
from playwright.sync_api import sync_playwright, expect

OUT = ROOT / '.factory/setup-browser'


def journey(page, base, fixture, width, height):
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(base)
    page.locator('#main h1').wait_for()
    page.locator('#app-select').select_option('sample-one')
    page.locator('#edit-app').click()
    page.get_by_role('button', name='Discover app details', exact=True).focus()
    page.keyboard.press('Enter')
    expect(page.locator('#setup-home')).to_be_visible()
    before = fixture.store.app('sample-one')
    page.get_by_role('button', name='Read saved website', exact=True).click()
    expect(page.locator('#setup-review')).to_be_visible()
    assert fixture.store.app('sample-one') == before
    expect(page.locator('#setup-review')).to_contain_text('Conflicting Name suggestions')
    assert not page.locator('#setup-review input[type=checkbox]:checked').count()
    page.get_by_role('button', name='Approve selected changes', exact=True).click()
    expect(page.locator('#setup-review .field-error')).to_contain_text('Select at least one field')
    page.locator('#setup-name-candidate').select_option('0')
    page.locator('#setup-name').fill('Reviewed synthetic app')
    page.locator('[name="select-name"]').check()
    page.locator('#setup-android_package-candidate').select_option('0')
    page.locator('[name="select-android_package"]').check()
    page.locator('[name="select-android_track"]').check()
    assert not page.locator('#setup-review').evaluate('(node)=>node.scrollWidth>node.clientWidth+1')
    page.locator('#modal').screenshot(path=str(OUT / f'review-{width}.png'))
    css = (ROOT / 'mission_control/static/style.css').read_text(encoding='utf-8')
    (OUT / f'review-{width}.html').write_text(page.content().replace('</head>', '<style>'+css+'</style></head>'), encoding='utf-8')
    page.get_by_role('button', name='Approve selected changes', exact=True).click()
    expect(page.locator('#setup-home')).to_be_visible()
    saved = fixture.store.app('sample-one')
    assert saved['data']['name'] == 'Reviewed synthetic app'
    assert saved['data']['android_package'] == 'com.example.synthetic'
    assert saved['data']['android_track'] == 'production'
    assert saved['data']['store_app_id'] == '123'
    page.locator('#close-modal').click()
    page.reload()
    page.locator('#main h1').wait_for()
    page.locator('#edit-app').click()
    expect(page.locator('#field-name')).to_have_value('Reviewed synthetic app')
    page.get_by_role('button', name='Discover app details', exact=True).click()
    page.get_by_role('button', name='Review draft', exact=True).first.click()
    expect(page.locator('#setup-review')).to_contain_text('APPLIED')
    page.get_by_role('button', name='Remove this local draft', exact=True).click()
    page.get_by_role('button', name='Keep draft', exact=True).click()
    expect(page.locator('#setup-review')).to_be_visible()
    page.get_by_role('button', name='Remove this local draft', exact=True).click()
    page.get_by_role('button', name='Remove draft', exact=True).click()
    expect(page.locator('#setup-home')).to_contain_text('No drafts yet')
    assert fixture.store.app('sample-one') == saved
    # A completed read cannot reclaim a dialog after the user closes it.
    page.evaluate("window.savedSetupApi=api;window.setupWait=new Promise(resolve=>window.finishSetupWait=resolve);api=()=>setupWait;window.setupSubmission=setupRead(document.querySelector('[data-action=setup-read]'));document.querySelector('#modal').close()")
    page.evaluate("finishSetupWait({});")
    page.evaluate('window.setupSubmission')
    assert not page.locator('#modal').evaluate('(node)=>node.open')
    page.evaluate('()=>{api=window.savedSetupApi;}')
    # Render a real approved agent job result and follow its draft link.
    from mission_control.resolutions import Resolutions
    from mission_control.worker import run_once
    import uuid
    resolver=Resolutions(fixture.store)
    _,plan=resolver.proposal('sample-one')
    issue=plan['issues'][0]
    option=next(item for item in issue['options'] if item['tool']=='discover_setup')
    job=resolver.start('sample-one',dict(issue_id=issue['id'],option_id=option['id'],source_hash=issue['source_hash'],target_url=None,request_key=str(uuid.uuid4())))
    assert run_once(fixture.store)
    page.evaluate('async()=>{await refresh();}')
    page.evaluate('(id)=>{openResolutionRun(id);}',job['id'])
    page.get_by_role('button',name='Review collected app details',exact=True).click()
    expect(page.locator('#setup-review')).to_contain_text('PENDING')
    expect(page.get_by_role('link',name='Open inspected public page')).to_have_attribute('href',SITE+'/page')
    page.locator('#close-modal').click()
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
    assert not errors, errors
    return dict(viewport=[width,height], keyboard=True, selected_edits=True, reload_persistence=True,
                separate_apple_android=True, delete_preserves_app=True, late_response_did_not_reopen=True,
                agent_result_review_link=True,horizontal_overflow=False, js_errors=errors)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    observations = []
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        for width, height in ((1440,900),(390,844)):
            fixture = SetupFixture(); fixture.setUp()
            reader = Reader(page='<html lang="en"><meta name="application-name" content="Source app"><meta property="og:site_name" content="Alternate app"><a href="https://play.google.com/store/apps/details?id=com.example.synthetic">Android</a></html>')
            server = Server(('127.0.0.1',0), fixture.store)
            thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
            try:
                with patch('mission_control.setup_discovery.PublicReader', return_value=reader):
                    context = browser.new_context(viewport=dict(width=width,height=height))
                    observations.append(journey(context.new_page(),f'http://127.0.0.1:{server.server_port}',fixture,width,height))
                    context.close()
            finally:
                server.shutdown(); server.server_close(); thread.join(); fixture.doCleanups()
        browser.close()
    result = dict(status='PASS', scope='Synthetic website and isolated localhost UI only; no live provider or readiness proof.', observations=observations)
    (OUT / 'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
