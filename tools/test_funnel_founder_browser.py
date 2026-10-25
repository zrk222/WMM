"""Owner founder-review acceptance with real local HTTP, isolated sources and exports."""
from pathlib import Path
import csv,io,json,sys
import fitz
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tests.test_funnel_clients import FunnelClientsTests
from tests.test_funnel_contract import observed
from mission_control.funnel_store import Funnels
from mission_control.db import connection
from playwright.sync_api import sync_playwright,expect

OUT=ROOT/'.factory/funnel-founder'


def button(page,name):return page.locator('#modal').get_by_role('button',name=name,exact=True)


def seed(t):
    plan=json.loads(json.dumps(t.plan));stage=plan['stages'][1]
    plan['stages'].append(dict(stage,id='activation',type='ACTIVATION',label='Useful activation',parents=['install']))
    flow=Funnels(t.store)
    for i in range(7):flow.save('sample-one',dict(t.payload(),id='founder-plan-'+str(i),data=plan))
    saved=flow.read('sample-one','founder-plan-0');zero=observed(plan)
    unknown=dict(zero,event_id='unknown-install',stage_id='install',coverage='UNKNOWN',count=None,unit=stage['unit'],denominator_definition=stage['denominator_definition'])
    partial=dict(unknown,event_id='partial-value',stage_id='activation',coverage='PARTIAL',count=7)
    flow.ingest('sample-one',dict(funnel_id=saved['id'],funnel_hash=saved['hash'],manifest_version=t.version,observations=[zero,unknown,partial]))
    with connection(t.store.path)as db:db.execute("UPDATE growth_funnels SET hash=? WHERE id='founder-plan-1'",('0'*64,))


def open_review(page):
    page.locator('[data-view="results"]').click()
    page.locator('#growth-review-panel [data-action="funnel-review"]').click()
    expect(page.locator('.funnel-workspace')).to_contain_text('5 of 7 saved funnels')


def exports(page,width):
    with page.expect_download()as waiting:button(page,'Download review JSON').click()
    path=OUT/f'founder-{width}.json';waiting.value.save_as(str(path));value=json.loads(path.read_text())
    assert value['coverage']['evaluated']==5 and value['coverage']['total']==7
    assert value['funnels'][0]['stage_coverage']==dict(OBSERVED=1,UNKNOWN=1,PARTIAL=1)
    assert value['funnels'][1]['state']=='UNAVAILABLE'
    assert value['funnels'][1]['stages']is None
    with page.expect_download()as waiting:button(page,'Download review CSV').click()
    path=OUT/f'founder-{width}.csv';waiting.value.save_as(str(path));rows=list(csv.DictReader(io.StringIO(path.read_text())))
    stage_rows=[r for r in rows if r['kind']=='stage' and r['funnel_id']=='founder-plan-0']
    assert [r['count']for r in stage_rows]==['0','','7']
    assert any(r['kind']=='unavailable'and r['funnel_id']=='founder-plan-1'for r in rows)
    assert all(r['review_hash']==value['source_hash']for r in rows)
    with page.expect_popup()as waiting:
        button(page,'Report / Save PDF').focus();page.keyboard.press('Enter')
    popup=waiting.value;popup.wait_for_load_state('load')
    expect(popup.get_by_role('button',name='Print / Save as PDF',exact=True)).to_be_visible()
    assert popup.evaluate('window.opener===null')
    pdf=OUT/f'founder-{width}.pdf';popup.pdf(path=str(pdf),format='A4',print_background=True)
    with fitz.open(pdf)as document:text=' '.join(p.get_text()for p in document)
    for expected in ['App-sales founder review','founder-plan-0','unknown','partial','founder-plan-1','unavailable']:
        assert expected.lower()in text.lower(),expected
    popup.close();return value['source_hash']


def exercise(browser,width):
    t=FunnelClientsTests('test_current_grant_foreign_scope_unknown_inputs_and_stale_manifest_are_denied');t.setUp();context=None
    try:
        seed(t);context=browser.new_context(viewport=dict(width=width,height=900 if width==1440 else 844),accept_downloads=True)
        context.add_cookies([dict(name=c.name,value=c.value,url=t.origin,sameSite='Lax')for c in t.owner.cookies])
        page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(t.origin);open_review(page)
        expect(page.locator('.funnel-workspace')).to_contain_text('1 unknown stages')
        expect(page.locator('.funnel-workspace')).to_contain_text('1 partial stages')
        expect(page.locator('.funnel-workspace')).to_contain_text('Stage counts unavailable')
        expect(page.locator('.funnel-workspace section.panel h3').first).to_have_text('founder-plan-1')
        assert page.locator('.funnel-workspace').evaluate('(n)=>n===document.activeElement')
        # A corrupt source has a concrete way back; it must never look like zero.
        page.locator('[data-action="funnel-detail"][data-id="founder-plan-1"]').click()
        expect(page.locator('#funnel-error')).not_to_be_empty()
        button(page,'Reload founder review').click()
        expect(page.locator('.funnel-workspace')).to_contain_text('5 of 7 saved funnels')
        button(page,'Next review page').click()
        expect(page.locator('.funnel-workspace')).to_contain_text('2 of 7 saved funnels from offset 5')
        page.locator('[data-action="funnel-detail"][data-id="founder-plan-6"]').click()
        expect(page.locator('.funnel-workspace')).to_contain_text('cohort-one')
        button(page,'Back to founder review').click()
        expect(page.locator('.funnel-workspace')).to_contain_text('2 of 7 saved funnels from offset 5')
        button(page,'Previous review page').click()
        page.locator('[data-action="funnel-detail"][data-id="founder-plan-0"]').click()
        expect(page.locator('#modal td').filter(has_text='Unknown').first).to_be_visible()
        button(page,'Back to founder review').click()
        report_hash=exports(page,width)
        button(page,'Reload founder review').click()
        expect(page.locator('.funnel-workspace')).to_contain_text('5 of 7 saved funnels')
        assert page.locator('#modal-body').evaluate('(n)=>n.scrollTop')==0
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert page.locator('#modal').evaluate('(n)=>n.scrollWidth<=n.clientWidth')
        css=''.join((ROOT/'mission_control/static'/name).read_text(encoding='utf-8')for name in ['style.css','page-reporting.css','video-editor.css'])
        page.screenshot(path=str(OUT/f'founder-{width}.png'))
        (OUT/f'founder-{width}.html').write_text(page.content().replace('</head>','<style>'+css+'</style></head>'),encoding='utf-8')
        button(page,'Return to subscription review').click();expect(page.locator('#modal')).not_to_be_visible()
        page.locator('#app-select').select_option('sample-two');expect(page.locator('#growth-review-panel')).to_be_visible()
        page.locator('#growth-review-panel [data-action="funnel-review"]').click()
        expect(page.locator('#funnel-error')).to_contain_text('owner')
        expect(page.locator('#modal')).not_to_contain_text('founder-plan-0')
        assert not errors,errors
        return dict(width=width,review_hash=report_hash,coverage='5 of7 then2 of7',corrupt_source_visible=True,exact_links_and_page_return=True,zero_partial_unknown=True,pdf_json_csv_match=True,owner_denial=True,no_overflow=True,no_page_errors=True)
    except Exception:
        if context:
            page.screenshot(path=str(OUT/f'failure-{width}.png'))
            (OUT/f'failure-{width}.html').write_text(page.content(),encoding='utf-8')
        raise
    finally:
        if context:context.close()
        t.tearDown()


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    with sync_playwright()as playwright:
        browser=playwright.chromium.launch(headless=True)
        try:
            values=[exercise(browser,width)for width in (1440,390)]
            (OUT/'browser.json').write_bytes((json.dumps(dict(status='PASS',browser=browser.version,observations=values),indent=2)+'\n').encode())
            print(json.dumps(values))
        finally:browser.close()


if __name__=='__main__':main()
