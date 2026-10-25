"""Real owner UI/HTTP and exported PDF/JSON/CSV on isolated synthetic workspaces."""
from pathlib import Path
import json
import sys
import csv
import io
import fitz
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tests.test_funnel_clients import FunnelClientsTests
from tests.test_customer_workflow import proposal
from mission_control.customer_workflow_store import CustomerWorkflows
from mission_control.funnel_store import Funnels
from playwright.sync_api import sync_playwright,expect

OUT=ROOT/'.factory/funnel-ui'

def button(page,name):return page.locator('#modal').get_by_role('button',name=name,exact=True)
def fill(page,values):
    for name,value in values.items():page.locator('#modal [name="'+name+'"]').fill(str(value))

def open_results(page):
    page.locator('[data-view="results"]').click()
    page.locator('[data-action="funnel-open"]').click()
    expect(button(page,'Create app-sales funnel')).to_be_visible()

def create(page,t):
    button(page,'Create app-sales funnel').click()
    expect(page.locator('#funnel-plan-form')).to_be_visible()
    fill(page,dict(audience='Synthetic app users',pain='Tasks lack a next action',milestone='Save the next useful task',metric='Activated users',target='100',due_at='2026-11-01T00:00:00Z',hook='Choose your next useful action',cta='Try the app',destination='https://example.com/app',method='Synthetic source export',identity_scope='source-app-cohort',conversion_window_seconds='86400',free_deliverables='One saved action',paid_deliverables='Additional app workflows'))
    page.locator('[name="creative"]').select_option(index=0)
    page.locator('[name="research"]').select_option('customer-ui-source')
    # Exercise a complete optional stage and keyboard controls, then remove it.
    button(page,'Add stage').click()
    expect(page.locator('[name="stage-8-id"]')).to_be_visible()
    button(page,'Remove stage').last.click()
    expect(page.locator('[data-funnel-stage]')).to_have_count(8)
    first=page.locator('[data-funnel-stage]').first;first.locator('summary').click()
    page.locator('[name="stage-0-label"]').fill('=Views <img onerror=alert(1)>')
    first.locator('summary').click()
    posts=[]
    def lost(route):
        if route.request.method!='POST':return route.continue_()
        response=route.fetch();assert response.status==201,response.text()
        posts.append(route.request.post_data)
        route.fulfill(status=201,content_type='application/json',body='UNREADABLE_SUCCESS')
    page.route('**/api/apps/sample-one/funnels',lost)
    button(page,'Save app-sales plan').click()
    expect(page.locator('#funnel-error')).to_contain_text('could not be read')
    assert len(posts)==1
    assert len(Funnels(t.store).list('sample-one')['items'])==1
    button(page,'Reconcile saved evidence').click()
    expect(button(page,'Record stage observation')).to_be_visible()
    page.unroute('**/api/apps/sample-one/funnels',lost)
    assert len(posts)==1,'Reconciliation must never resend a plan'
    saved=Funnels(t.store).read('sample-one',Funnels(t.store).list('sample-one')['items'][0]['id'])
    assert saved['data']['definition']['outcome']['research_refs'][0]['id']=='customer-ui-source'
    return saved

def single(page,coverage,count,event,stage):
    button(page,'Record stage observation').click()
    page.locator('[name="stage_id"]').select_option(stage)
    page.locator('[name="coverage"]').select_option(coverage)
    fill(page,dict(event_id=event,source_ref='synthetic-export',source_sha256='b'*64,observed_at='2026-10-03T00:00:00Z'))
    if coverage!='UNKNOWN':fill(page,dict(count=count))
    else:expect(page.locator('[name="count"]')).to_be_disabled()
    button(page,'Save stage observation').click()
    expect(button(page,'Record stage observation')).to_be_visible()

def batch(page,t,saved):
    definition=saved['data']['definition'];attr=definition['attribution'];stage=definition['stages'][0]
    rows=[dict(event_id='page-'+str(i).zfill(3),stage_id=stage['id'],source_ref='synthetic-export',source_sha256='b'*64,cohort_id=definition['cohort_id'],starts_at=attr['starts_at'],ends_at=attr['ends_at'],observed_at='2026-10-03T00:00:00Z',coverage='OBSERVED',count=0,unit=stage['unit'],denominator_definition=stage['denominator_definition'],identity_scope=attr['identity_scope'])for i in range(101)]
    rows[-1].update(count=42,observed_at='2026-10-04T00:00:00Z')
    button(page,'Import JSON observations').click()
    # Actual server duplicate-key rejection preserves the original file draft.
    bad='[{"event_id":"one","event_id":"two"}]'
    fill(page,dict(observations=bad))
    button(page,'Import observation batch').click()
    expect(page.locator('#funnel-error')).not_to_be_empty()
    expect(page.locator('[name="observations"]')).to_have_value(bad)
    assert len(Funnels(t.store).observations('sample-one',saved['id'])['items'])==3
    file=OUT/'batch-input.json';file.write_text(json.dumps(rows),encoding='utf-8')
    page.locator('#funnel-batch-file').set_input_files(str(file))
    expect(page.locator('[name="observations"]')).to_have_value(json.dumps(rows))
    path='**/api/apps/sample-one/funnels/'+saved['id']+'/observations';posts=[]
    def lost(route):
        if route.request.method!='POST':return route.continue_()
        response=route.fetch();assert response.status==200,response.text();posts.append(route.request.post_data)
        if len(posts)==1:route.fulfill(status=200,content_type='application/json',body='UNREADABLE_IMPORT')
        else:route.fulfill(response=response)
    page.route(path,lost)
    button(page,'Import observation batch').click()
    expect(page.locator('#funnel-error')).to_contain_text('could not be read')
    assert len(posts)==1
    button(page,'Retry exact retained request').click()
    expect(button(page,'Record stage observation')).to_be_visible()
    page.unroute(path,lost)
    assert len(posts)==2 and posts[0]==posts[1]
    assert Funnels(t.store).observations('sample-one',saved['id'])['total']==104
    report=Funnels(t.store).report('sample-one',saved['id'])
    assert report['stages'][0]['count']==42
    assert report['stages'][1]['status']=='PARTIAL' and report['stages'][2]['status']=='UNKNOWN'
    button(page,'Inspect saved observations').click()
    expect(page.locator('.funnel-workspace')).to_contain_text('100 of 104')
    button(page,'Next observations').click()
    expect(page.locator('.funnel-workspace')).to_contain_text('4 of 104')
    button(page,'Back to stage results').click()
    expect(button(page,'Download report JSON')).to_be_visible()

def exports(page,width):
    with page.expect_download() as waiting:button(page,'Download report JSON').click()
    path=OUT/f'funnel-{width}.json';waiting.value.save_as(str(path));data=json.loads(path.read_text())
    assert data['report']['stages'][0]['count']==42
    assert data['report']['stages'][2]['count'] is None
    with page.expect_download() as waiting:button(page,'Download stage CSV').click()
    path=OUT/f'funnel-{width}.csv';waiting.value.save_as(str(path));rows=list(csv.DictReader(io.StringIO(path.read_text())))
    assert rows[0]['count_or_numerator']=='42' and rows[2]['count_or_numerator']==''
    with page.expect_popup() as waiting:
        button(page,'Report / Save PDF').focus();page.keyboard.press('Enter')
    popup=waiting.value;popup.wait_for_load_state('load')
    expect(popup.get_by_role('button',name='Print / Save as PDF',exact=True)).to_be_visible()
    assert popup.evaluate('window.opener===null')
    pdf=OUT/f'funnel-{width}.pdf';popup.pdf(path=str(pdf),format='A4',print_background=True)
    with fitz.open(pdf) as document:text=' '.join(p.get_text()for p in document)
    for expected in ['App-sales funnel','42','partial','unknown','cohort-one']:assert expected.lower()in text.lower(),expected
    popup.close();return data['report']['source_hash']

def exercise(browser,width):
    t=FunnelClientsTests('test_current_grant_foreign_scope_unknown_inputs_and_stale_manifest_are_denied');t.setUp()
    context=None
    try:
        data=proposal()
        for key in ('release','locale','currency'):data[key]=t.store.app('sample-one')['data'][key]
        CustomerWorkflows(t.store).save('sample-one',dict(id='customer-ui-source',manifest_version=t.version,data=data))
        context=browser.new_context(viewport=dict(width=width,height=900 if width==1440 else 844),accept_downloads=True)
        context.add_cookies([dict(name=c.name,value=c.value,url=t.origin,sameSite='Lax')for c in t.owner.cookies])
        page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(t.origin);expect(page.locator('[data-view="results"]')).to_be_visible();open_results(page)
        saved=create(page,t)
        single(page,'OBSERVED','0','single-zero','video-view')
        single(page,'PARTIAL','5','single-partial','store-visit')
        single(page,'UNKNOWN',None,'single-unknown','install')
        batch(page,t,saved)
        assert page.locator('#modal-body').evaluate('(n)=>n.scrollTop')==0
        page.screenshot(path=str(OUT/f'funnel-results-top-{width}.png'))
        report_hash=exports(page,width)
        assert page.locator('.funnel-workspace img').count()==0
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert page.locator('#modal').evaluate('(n)=>n.scrollWidth<=n.clientWidth')
        css=''.join((ROOT/'mission_control/static'/name).read_text(encoding='utf-8')for name in ['style.css','page-reporting.css','video-editor.css'])
        page.screenshot(path=str(OUT/f'funnel-{width}.png'),full_page=True)
        page.screenshot(path=str(OUT/f'funnel-viewport-{width}.png'))
        (OUT/f'funnel-{width}.html').write_text(page.content().replace('</head>','<style>'+css+'</style></head>'),encoding='utf-8')
        assert not errors,errors
        # A stale manifest is a real rejected HTTP write; the entered draft stays.
        button(page,'Record stage observation').click()
        fill(page,dict(event_id='stale-draft',source_ref='synthetic-export',source_sha256='b'*64,observed_at='2026-10-03T00:00:00Z',count='1'))
        app=t.store.app('sample-one');t.store.save_app('sample-one',dict(app['data'],job='Changed synthetic app context'),app['version'])
        button(page,'Save stage observation').click()
        expect(page.locator('#funnel-error')).not_to_be_empty()
        expect(page.locator('[name="event_id"]')).to_have_value('stale-draft')
        assert Funnels(t.store).observations('sample-one',saved['id'])['total']==104
        page.reload();open_results(page);button(page,'Inspect stages and results').click()
        expect(page.locator('.funnel-workspace')).to_contain_text('source review needed')
        # A second app must never retain this app's modal or report.
        page.locator('#close-modal').click();page.locator('#app-select').select_option('sample-two')
        expect(page.locator('#funnel-panel')).to_be_visible();page.locator('[data-action="funnel-open"]').click()
        expect(page.locator('#funnel-error')).to_contain_text('owner')
        expect(page.locator('#modal')).not_to_contain_text(saved['id'])
        return dict(width=width,source_hash=report_hash,observations=104,plan_count=1,uncertain_plan_reconciled=True,identical_batch_retry=True,unknown_partial_zero=True,pdf_json_csv=True,stale_manifest_draft_preserved=True,cross_app_denied=True,no_page_errors=True)
    except Exception:
        if context:
            page.screenshot(path=str(OUT/f'failure-{width}.png'),full_page=True)
            (OUT/f'failure-{width}.html').write_text(page.content(),encoding='utf-8')
        raise
    finally:
        if context:context.close()
        t.tearDown()

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True)
        try:
            rows=[exercise(browser,width)for width in (1440,390)]
            (OUT/'browser.json').write_text(json.dumps(dict(status='PASS',browser=browser.version,observations=rows),indent=2)+'\n',encoding='utf-8')
            print(json.dumps(rows))
        finally:browser.close()

if __name__=='__main__':main()
