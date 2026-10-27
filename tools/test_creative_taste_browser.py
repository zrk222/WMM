"""Owner direction authoring and recovery in isolated local Chromium, no providers."""
from pathlib import Path
import csv,io,json,sys
import fitz
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tests import test_agent_grants as grants
from tests.test_creative_library import reference
from mission_control.creative_library import Library
from playwright.sync_api import sync_playwright,expect

OUT=ROOT/'.factory/content-packaging-taste-ui'


def button(page,label):return page.locator('#modal').get_by_role('button',name=label,exact=True)


def exports(page,width):
    with page.expect_download() as pending:button(page,'Download plan JSON').click()
    path=OUT/f'direction-{width}.json';pending.value.save_as(str(path));saved=json.loads(path.read_bytes())
    assert saved['version']==2 and saved['data']['definition']['examples'][0]['interpretation']=='Observe the opening contrast.'
    with page.expect_download() as pending:button(page,'Download plan CSV').click()
    path=OUT/f'direction-{width}.csv';pending.value.save_as(str(path))
    rows=list(csv.DictReader(io.StringIO(path.read_text(encoding='utf-8'))))
    assert any('VOICE_END' in row['Value'] for row in rows)
    with page.expect_popup() as pending:
        button(page,'Report / Save PDF').focus();page.keyboard.press('Enter')
    popup=pending.value;popup.wait_for_load_state('load')
    assert popup.evaluate('window.opener===null')
    path=OUT/f'direction-{width}.pdf';popup.pdf(path=str(path),format='A4',print_background=True)
    with fitz.open(path) as document:
        text=' '.join(p.get_text() for p in document)
        assert 'VOICE_END' in text and 'Observe the opening contrast.' in text
        assert 'UNRELATED_PRIVATE_SENTINEL' not in text
        pages=len(document)
    popup.close();return saved,pages


def exercise(browser,width):
    fixture=grants.GrantTests('test_owner_issues_once_hash_only_persistence_and_snapshot_no_authority')
    fixture.setUp();context=None
    try:
        Library(fixture.store).save('sample-one',dict(data=reference()))
        source=Library(fixture.store).list('sample-one')[0]
        context=browser.new_context(viewport=dict(width=width,height=900 if width==1440 else 844),accept_downloads=True)
        context.add_cookies([dict(name=c.name,value=c.value,url=fixture.origin,sameSite='Lax')for c in fixture.owner.cookies])
        page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(fixture.origin);page.locator('[data-view="research"]').click()
        page.get_by_role('button',name='Open creative packaging',exact=True).click()
        button(page,'Review video direction').click();button(page,'Create video direction').click()
        expect(page.locator('#packaging-voice')).to_be_visible()
        assert page.locator('#packaging-example_11').count()==1
        page.locator('#packaging-lens').select_option('product')
        page.locator('#packaging-voice').fill('Plain words. '+('Synthetic reviewed voice rule. '*100)+'VOICE_END')
        page.locator('#packaging-visual').fill('Show actual product controls with readable labels.')
        page.locator('#packaging-exclusions').fill('No fabricated proof.\nNo flashing transitions.')
        page.locator('#packaging-example_11').locator('xpath=ancestor::details').locator('summary').click()
        page.locator('#packaging-example_11').select_option('SOURCE:'+source['id'])
        page.locator('#packaging-interpretation_11').fill('Observe the opening contrast.')
        with page.expect_response(lambda r:r.url.endswith('/taste-review') and r.request.method=='POST') as pending:
            button(page,'Save owner-reviewed direction').click()
        assert pending.value.status==200,pending.value.text()
        expect(page.locator('#modal-body')).to_contain_text('CURRENT_OWNER_REVIEW')
        page.evaluate("state.workspace.privateDraft='UNRELATED_PRIVATE_SENTINEL'")
        button(page,'Revise video direction').click()
        page.locator('#packaging-visual').fill('Show real controls and one clear ending.')
        calls=[]
        def lost(route):
            response=route.fetch();assert response.status==200
            calls.append('server-committed');route.fulfill(status=503,content_type='application/json',body='{"error":"Synthetic response lost after commit"}')
        page.route('**/packaging/taste-review',lost)
        button(page,'Save owner-reviewed direction').click()
        expect(page.locator('#packaging-recovery')).to_contain_text('Save result unconfirmed')
        assert len(calls)==1
        page.unroute('**/packaging/taste-review',lost)
        button(page,'Inspect saved revision').click()
        expect(page.locator('#modal-body')).to_contain_text('Revision 2 is saved')
        assert len(calls)==1
        saved,pages=exports(page,width)
        button(page,'Revise video direction').click()
        assert page.locator('#packaging-voice').input_value().endswith('VOICE_END')
        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth')
        workspace=page.locator('.packaging-workspace');workspace.focus();page.keyboard.press('Tab')
        assert page.evaluate("document.activeElement.matches('input,textarea,select,button,summary')")
        page.locator('#modal-body').evaluate('(n)=>n.scrollTop=0')
        page.screenshot(path=str(OUT/f'actual-{width}.png'))
        css='\n'.join((ROOT/'mission_control/static'/name).read_text(encoding='utf-8')for name in ['style.css','packaging.css'])
        html=page.locator('#modal').evaluate('(n)=>n.outerHTML')
        if width==1440:
            (OUT/'rendered-modal.html').write_bytes(('<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Your video direction</title><style>'+css+'</style></head><body>'+html+'</body></html>').encode('utf-8'))
        page.locator('#app-select').select_option('sample-two')
        expect(page.locator('#modal')).not_to_be_visible()
        assert not errors,errors
        return dict(width=width,exact_review=saved['hash'],revision=2,example_slot12=True,complete_voice=True,uncertain_write_observed_once=True,json_csv_pdf=True,pdf_pages=pages,keyboard=True,app_switch=True,no_overflow=True,no_page_errors=True)
    finally:
        if context:context.close()
        fixture.tearDown()


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        try:
            values=[exercise(browser,width) for width in [1440,390]]
            (OUT/'browser-observations.json').write_bytes((json.dumps(dict(status='PASS',browser=browser.version,observations=values,limits=['Synthetic local owner and source data','Chromium viewport emulation, not native iOS','No video execution or measured outcomes']),indent=2)+'\n').encode('utf-8'))
            print(json.dumps(values))
        finally:browser.close()


if __name__=='__main__':main()
