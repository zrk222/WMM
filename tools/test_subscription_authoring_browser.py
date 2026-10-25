"""Real local forms and typed registration; isolated synthetic observations only."""
from pathlib import Path
from datetime import datetime,timedelta,timezone
import json
import sys
import tempfile
import threading
import fitz
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mission_control.server import Server
from mission_control.store import Store
from mission_control.service import Service
from mission_control.experiments import Experiments
from tests.test_ledger import cohort
from playwright.sync_api import sync_playwright,expect


def dates():
    today=datetime.now(timezone.utc).replace(microsecond=0)
    return {key:(today+timedelta(days=offset)).isoformat() for key,offset in [('checked',-1),('expires',90),('starts',3),('ends',10),('matures',45),('analysis',46)]}


def seed(store,stamp):
    for identity in ('sample-one','sample-two'):
        store.save_app(identity,dict(name='Synthetic Café 東京 '+identity,release='build-1',locale='en-US',currency='USD'))
    service=Service(store)
    for arm in ('control','treatment'):
        service.cohort('sample-one',cohort(cohort_id=arm,starts_at=stamp['starts'],ends_at=stamp['ends'],matures_at=stamp['matures']))


def fill(page,values):
    for name,value in values.items():
        page.locator('[name="'+name+'"]').fill(str(value))


def billing(page,stamp,arm,kind='PAYWALL'):
    page.locator('[data-action="subscription-plan-billing"]').click()
    fill(page,dict(title='Synthetic '+arm,source='Synthetic device test receipt',product_id='synthetic.monthly',offer_id='STANDARD',storefront='US',variant_id=arm,price_minor=1000,renewal_price_minor=1000,trial_days=0,intro_days=0,billing_period_days=14,renewal_terms='Synthetic USD10 each 14 days; cancel before renewal',checked_at=stamp['checked'],expires_at=stamp['expires']))
    if kind=='OFFER':
        fill(page,dict(offer_id='synthetic-'+arm,price_minor=1000 if arm=='control' else 800,title='Synthetic offer '+arm))
    for name,value in dict(experiment_type=kind,access_method='HARD' if arm=='control' or kind=='OFFER' else 'SOFT',placement='AFTER_ONBOARDING',platform='iOS',result='PASS',eligibility_status='ELIGIBLE').items():
        page.locator('[name="'+name+'"]').select_option(value)
    page.locator('[name="restore_tested"]').check()
    page.locator('[name="trial_eligibility_tested"]').check()
    with page.expect_response(lambda response:response.request.method=='POST' and response.url.endswith('/records')) as waiting:
        page.get_by_role('button',name='Save billing observations',exact=True).click()
    assert waiting.value.status==201,waiting.value.text()
    result=waiting.value.json()
    expect(page.locator('#modal')).not_to_be_visible()
    return result


def exercise(page,origin,store,stamp,width,out):
    page.goto(origin)
    page.locator('[data-view="results"]').click()
    expect(page.locator('#subscription-plan-panel')).to_be_visible()
    control=billing(page,stamp,'control')
    treatment=billing(page,stamp,'treatment')
    page.locator(f'[data-action="subscription-plan-detail"][data-id="{control["id"]}"]').click()
    expect(page.locator('#modal-body')).to_contain_text('price_minor: 1000')
    page.evaluate("state.workspace.privateDraft='PRIVATE_SENTINEL'")
    with page.expect_popup() as waiting:
        page.locator('[data-action="subscription-plan-report"]').focus()
        page.keyboard.press('Enter')
    popup=waiting.value
    popup.wait_for_load_state('load')
    path=out/f'billing-{width}.pdf'
    popup.pdf(path=str(path),format='A4',print_background=True)
    with fitz.open(path) as document:
        text='\n'.join(item.get_text() for item in document)
        assert 'synthetic.monthly' in text and 'renewal_price_minor: 1000' in text
        assert 'PRIVATE_SENTINEL' not in text and 'No authenticated provider acceptance' in ' '.join(text.split())
    css=(ROOT/'mission_control/static/page-reporting.css').read_text(encoding='utf-8')
    (out/f'billing-{width}.html').write_text(popup.content().replace('</head>','<style>'+css+'</style></head>'),encoding='utf-8')
    popup.close()
    page.locator('#close-modal').click()
    page.locator('[data-action="subscription-plan-experiment"]').focus()
    page.keyboard.press('Enter')
    fill(page,dict(name='Synthetic bounded paywall test',owner='Synthetic operator',hypothesis='Test access method after onboarding',analysis_at=stamp['analysis'],assignment_source='Synthetic disjoint assignment receipt',stop_rule='Stop for a blocking billing error',rollback_plan='Return to prior tested terms',baseline_rate=.1,minimum_detectable_effect=.1,treatment_allocation=.5,min_retention_rate=.2,max_refund_fraction=.1,min_contribution_minor=0,max_acquisition_minor=5000))
    for name,value in dict(primary_metric='paid_conversion',assignment_method='OBSERVATIONAL',control_cohort='control',treatment_cohort='treatment',control_source=control['id'],treatment_source=control['id']).items():
        page.locator('[name="'+name+'"]').select_option(value)
    page.get_by_role('button',name='Register subscription experiment',exact=True).click()
    expect(page.locator('#subscription-plan-error')).to_contain_text('different identities')
    expect(page.locator('[name="hypothesis"]')).to_have_value('Test access method after onboarding')
    assert Experiments(store).list('sample-one')==[]
    page.locator('[name="treatment_source"]').select_option(treatment['id'])
    page.screenshot(path=str(out/f'form-{width}.png'))
    with page.expect_response(lambda response:response.request.method=='POST' and response.url.endswith('/experiments')) as waiting:
        page.get_by_role('button',name='Register subscription experiment',exact=True).click()
    assert waiting.value.status==201,waiting.value.text()
    saved=waiting.value.json()
    expect(page.locator('#modal')).not_to_be_visible()
    assert saved['data']['control']['variant_type']=='SUBSCRIPTION'
    assert saved['data']['control']['source_hash']==control['hash']
    assert saved['data']['treatment']['configuration']['access_method']=='SOFT'
    assert 'asset_id' not in saved['data']['control']
    page.reload()
    page.locator('[data-view="results"]').click()
    expect(page.locator('#growth-review-panel')).to_contain_text('Synthetic bounded paywall test')
    assert len(Experiments(store).list('sample-one'))==1
    offer_control=billing(page,stamp,'control','OFFER')
    offer_treatment=billing(page,stamp,'treatment','OFFER')
    page.locator('[data-action="subscription-plan-experiment"]').click()
    fill(page,dict(name='Synthetic bounded offer test',owner='Synthetic operator',hypothesis='Compare the supplied offers',analysis_at=stamp['analysis'],assignment_source='Synthetic disjoint assignment receipt',stop_rule='Stop for billing errors',rollback_plan='Return to the prior offer',baseline_rate=.1,minimum_detectable_effect=.1,treatment_allocation=.5,min_retention_rate=.2,max_refund_fraction=.1,min_contribution_minor=0,max_acquisition_minor=5000))
    for name,value in dict(primary_metric='paid_conversion',assignment_method='OBSERVATIONAL',control_cohort='control',treatment_cohort='treatment',control_source=offer_control['id'],treatment_source=offer_treatment['id']).items():
        page.locator('[name="'+name+'"]').select_option(value)
    with page.expect_response(lambda response:response.request.method=='POST' and response.url.endswith('/experiments')) as waiting:
        page.get_by_role('button',name='Register subscription experiment',exact=True).click()
    assert waiting.value.status==201,waiting.value.text()
    offer=waiting.value.json()
    expect(page.locator('#modal')).not_to_be_visible()
    assert offer['data']['treatment']['configuration']['experiment_type']=='OFFER'
    assert offer['data']['treatment']['configuration']['price_minor']==800
    assert len(Experiments(store).list('sample-one'))==2
    page.locator('[data-action="subscription-plan-billing"]').click()
    fill(page,dict(title='Retained draft'))
    page.locator('#close-modal').click()
    page.locator('#subscription-plan-panel').scroll_into_view_if_needed()
    page.screenshot(path=str(out/f'subscription-{width}.png'),full_page=True)
    css=(ROOT/'mission_control/static/style.css').read_text(encoding='utf-8')+(ROOT/'mission_control/static/page-reporting.css').read_text(encoding='utf-8')
    (out/f'subscription-{width}.html').write_text(page.content().replace('</head>','<style>'+css+'</style></head>'),encoding='utf-8')
    assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
    page.locator('#app-select').select_option('sample-two')
    expect(page.locator('#subscription-plan-panel')).to_contain_text('0 saved configuration records')
    return dict(width=width,billing_records=4,typed_experiments=2,paywall_and_offer=True,source_hash_readback=True,identical_arms_rejected=True,inputs_retained=True,pdf_verified=True,keyboard=True,app_switch=True,overflow=False)


def main():
    out=ROOT/'.factory/subscription-authoring-ui';out.mkdir(exist_ok=True,parents=True)
    observations=[]
    with tempfile.TemporaryDirectory(prefix='wmm-sub-ui-') as folder,sync_playwright() as playwright:
        browser=playwright.chromium.launch(headless=True)
        try:
            for width in (1440,390):
                stamp=dates();store=Store(Path(folder)/f'{width}.sqlite',seed=False);seed(store,stamp)
                server=Server(('127.0.0.1',0),store);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
                page=browser.new_page(viewport={'width':width,'height':900 if width==1440 else 844})
                try:
                    observations.append(exercise(page,f'http://127.0.0.1:{server.server_port}',store,stamp,width,out))
                except Exception:
                    (out/f'failure-{width}.html').write_text(page.content(),encoding='utf-8');page.screenshot(path=str(out/f'failure-{width}.png'),full_page=True);raise
                finally:
                    page.close();server.shutdown();server.server_close();thread.join()
            (out/'browser.json').write_text(json.dumps(dict(status='PASS',browser=browser.version,observations=observations),indent=2),encoding='utf-8');print(json.dumps(observations))
        finally:
            browser.close()

if __name__=='__main__':main()
