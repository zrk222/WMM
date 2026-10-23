"""Actual local authoring/revision/recovery/PDF behavior with synthetic public research."""
from pathlib import Path
import json
import sys
import tempfile
import threading
import fitz
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mission_control.server import Server
from mission_control.store import Store
from mission_control.customer_workflow_store import CustomerWorkflows
from playwright.sync_api import sync_playwright, expect


def seed(store):
    for identity in ('sample-one','sample-two'):
        store.save_app(identity,dict(name='Synthetic Café 東京 '+identity,release='build-1',locale='en-US',currency='USD'))


def fill(page,name,value):
    page.locator('[name="'+name+'"]').fill(value)


def source(page,index,letter):
    prefix=f'sources.{index}.'
    values=dict(url='https://synthetic.example/'+letter,content_sha256=letter*64,observed_at='2026-10-01T00:00:00+00:00',expires_at='2026-12-01T00:00:00+00:00',excerpt='Café 東京 '+('Public observation words. '*15)+'END_'+letter,frequency='Synthetic weekly recurrence',impact='Synthetic task cost remains unmeasured')
    for key,value in values.items():
        fill(page,prefix+key,value)


def save(page):
    with page.expect_response(lambda response: '/customer-workflows' in response.url and response.request.method=='POST') as waiting:
        page.get_by_role('button',name='Save customer workflow',exact=True).click()
    response=waiting.value
    assert response.status==201,response.text()
    result=response.json()
    expect(page.locator('#modal')).not_to_be_visible()
    return result


def export(page,path,expected):
    page.locator('#modal [data-action="customer-report"]').focus()
    with page.expect_popup() as waiting:
        page.keyboard.press('Enter')
    popup=waiting.value
    popup.wait_for_load_state('load')
    assert popup.evaluate('window.opener===null')
    assert popup.locator('input,textarea').count()==0
    css=(ROOT/'mission_control/static/page-reporting.css').read_text(encoding='utf-8')
    path.with_suffix('.html').write_text(popup.content().replace('</head>','<style>'+css+'</style></head>'),encoding='utf-8')
    popup.pdf(path=str(path),format='A4',print_background=True)
    with fitz.open(path) as document:
        text='\n'.join(item.get_text() for item in document)
        for value in expected:
            assert ''.join(value.split()) in ''.join(text.split()),(value,text)
        assert 'PRIVATE_SENTINEL' not in text
        assert 'Demand verified: false' in text and 'Paid behavior verified: false' in text
        assert len(document)>=2
        pages=len(document)
    popup.close()
    return pages


def exercise(page,origin,store,width,out):
    page.goto(origin)
    page.locator('[data-view="results"]').click()
    expect(page.locator('#customer-workflow-title')).to_be_visible()
    page.locator('[data-action="customer-create"]').focus()
    page.keyboard.press('Enter')
    for key,value in dict(buyer='Synthetic independent founder',micro_behavior='Reconcile the first renewal',desired_outcome='Find the missing billing step',prototype_test='Observe whether a consented tester finds the missing step; demand and payment remain untested.').items():
        fill(page,key,value)
    source(page,0,'a')
    fill(page,'features.0.description','Show a first-renewal report')
    fill(page,'features.0.validation','Observe a tester finding the missing step, or record failure')
    fill(page,'excluded_features.0.feature','CRM')
    fill(page,'excluded_features.0.reason','The observation describes renewal reconciliation')
    page.locator('[data-action="customer-add-source"]').click()
    expect(page.locator('[name="buyer"]')).to_have_value('Synthetic independent founder')
    expect(page.locator('[name="sources.0.url"]')).to_have_value('https://synthetic.example/a')
    source(page,1,'b')
    page.locator('[data-action="customer-add-feature"]').click()
    fill(page,'features.1.description','Second proposed feature for row editing')
    fill(page,'features.1.validation','Record task completion')
    options=page.locator('[name="features.1.source_ids"] option').evaluate_all('(items)=>items.map(item=>item.value)')
    page.locator('[name="features.1.source_ids"]').select_option(options)
    page.locator('[data-action="customer-add-exclusion"]').click()
    fill(page,'excluded_features.1.feature','Social dashboard')
    fill(page,'excluded_features.1.reason','Outside the observed task')
    page.get_by_role('button',name='Remove observation 1',exact=True).click()
    expect(page.locator('[name="sources.0.url"]')).to_have_value('https://synthetic.example/b')
    assert page.locator('[name="features.0.source_ids"]').evaluate('(item)=>item.selectedOptions.length')==0
    assert not page.locator('#customer-workflow-form').evaluate('(form)=>form.checkValidity()')
    retained=page.locator('[name="features.0.source_ids"] option').get_attribute('value')
    page.locator('[name="features.0.source_ids"]').select_option(retained)
    page.get_by_role('button',name='Remove feature 2',exact=True).click()
    page.get_by_role('button',name='Remove exclusion 2',exact=True).click()
    page.locator('[data-action="customer-add-source"]').click()
    source(page,1,'c')
    source_ids=page.locator('[name="features.0.source_ids"] option').evaluate_all('(items)=>items.map(item=>item.value)')
    page.locator('[name="features.0.source_ids"]').select_option(source_ids)
    # Actual backend validation must reject contact information without losing the draft.
    fill(page,'sources.0.excerpt','Remove private contact person@example.test')
    page.get_by_role('button',name='Save customer workflow',exact=True).click()
    expect(page.locator('#customer-form-error')).to_contain_text('Remove personal contact information')
    expect(page.locator('[name="buyer"]')).to_have_value('Synthetic independent founder')
    assert CustomerWorkflows(store).list('sample-one')['history']==[]
    source(page,0,'b')
    page.screenshot(path=str(out/f'form-{width}.png'))
    original=save(page)
    assert len(original['data']['sources'])==2
    assert original['data']['features'][0]['source_ids']==source_ids
    assert original['data']['excluded_features']==[dict(feature='CRM',reason='The observation describes renewal reconciliation')]
    page.locator(f'[data-action="customer-detail"][data-id="{original["id"]}"]').click()
    expect(page.locator('#modal-body')).to_contain_text('Excluded: CRM')
    page.evaluate("state.privateDraft='PRIVATE_SENTINEL';state.workspace.privateCredential='PRIVATE_SENTINEL'")
    pages=export(page,out/f'workflow-{width}.pdf',['Café','東京','END_b','END_c','Supporting observations','Excluded: CRM','Prototype test',original['hash']])
    page.locator('[data-action="customer-revise"]').click()
    expect(page.locator('[name="sources.0.url"]')).to_have_value('https://synthetic.example/b')
    fill(page,'buyer','Revised synthetic founder')
    page.locator('[name="sources.1.availability"]').select_option('REMOVED')
    revision=save(page)
    assert revision['id']!=original['id']
    rows=CustomerWorkflows(store).list('sample-one')['history']
    first=next(row for row in rows if row['id']==original['id'])
    second=next(row for row in rows if row['id']==revision['id'])
    assert first['hash']==original['hash'] and first['data']['buyer']=='Synthetic independent founder'
    assert second['readout']['status']=='SOURCE_REVIEW_NEEDED'
    assert second['readout']['features'][0]['state']=='SOURCE_REVIEW_NEEDED'
    page.reload()
    page.locator('[data-view="results"]').click()
    expect(page.locator(f'[data-action="customer-detail"][data-id="{revision["id"]}"]')).to_contain_text('source review needed')
    page.locator(f'[data-action="customer-detail"][data-id="{revision["id"]}"]').click()
    page.locator('[data-action="customer-revise"]').click()
    app=store.app('sample-one')
    store.save_app('sample-one',dict(app['data'],locale='fr-CA'),app['version'])
    page.get_by_role('button',name='Save customer workflow',exact=True).click()
    expect(page.locator('#customer-form-error')).to_contain_text('Inputs are preserved')
    expect(page.locator('[name="buyer"]')).to_have_value('Revised synthetic founder')
    assert len(CustomerWorkflows(store).list('sample-one')['history'])==2
    page.locator('#close-modal').click()
    page.reload()
    page.locator('[data-view="results"]').click()
    expect(page.locator('#customer-workflow-panel')).to_contain_text('stale app scope')
    page.locator('#customer-workflow-panel').scroll_into_view_if_needed()
    page.screenshot(path=str(out/f'customer-{width}.png'),full_page=True)
    css=(ROOT/'mission_control/static/style.css').read_text(encoding='utf-8')+(ROOT/'mission_control/static/page-reporting.css').read_text(encoding='utf-8')
    (out/f'customer-{width}.html').write_text(page.content().replace('</head>','<style>'+css+'</style></head>'),encoding='utf-8')
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
    page.locator('#app-select').select_option('sample-two')
    expect(page.locator('#customer-workflow-panel')).to_contain_text('No workflows saved yet')
    assert page.locator(f'[data-action="customer-detail"][data-id="{original["id"]}"]').count()==0
    return dict(width=width,saved_versions=2,linked_sources=2,pdf_pages=pages,row_link_repair=True,contact_rejection=True,immutable_revision=True,source_freshness=True,manifest_rejection=True,app_switch=True,keyboard=True,privacy=True,horizontal_overflow=False)


def main():
    out=ROOT/'.factory/customer-workflow-ui'
    out.mkdir(exist_ok=True,parents=True)
    observations=[]
    with tempfile.TemporaryDirectory(prefix='wmm-customer-ui-') as folder,sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True)
        try:
            for width in (1440,390):
                store=Store(Path(folder)/f'ui-{width}.sqlite',seed=False)
                seed(store)
                server=Server(('127.0.0.1',0),store)
                thread=threading.Thread(target=server.serve_forever,daemon=True)
                thread.start()
                page=browser.new_page(viewport={'width':width,'height':900 if width==1440 else 844})
                try:
                    observations.append(exercise(page,f'http://127.0.0.1:{server.server_port}',store,width,out))
                except Exception:
                    (out/f'failure-{width}.html').write_text(page.content(),encoding='utf-8')
                    page.screenshot(path=str(out/f'failure-{width}.png'),full_page=True)
                    print(page.locator('#toast').text_content(),flush=True)
                    raise
                finally:
                    page.close();server.shutdown();server.server_close();thread.join()
            (out/'browser.json').write_text(json.dumps(dict(status='PASS',browser=browser.version,observations=observations),indent=2),encoding='utf-8')
            print(json.dumps(observations))
        finally:
            browser.close()


if __name__=='__main__':
    main()
