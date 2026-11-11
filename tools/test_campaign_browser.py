"""Real browser owner journey, synthetic identity and provider only."""
from pathlib import Path
import json
import fitz
from unittest.mock import patch
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright,expect
from tests.test_campaign_access import CampaignGatewayTests
from tests.test_campaign_execution import FakePaidTransport
from mission_control.campaign_execution import CampaignExecutionService
from tests.test_verified_review import OWNER_TOKEN
def login(page,origin,token):
    page.goto(origin)
    page.locator('[data-view=activity]').click()
    page.get_by_role('button',name='Sign in for verified review',exact=True).click()
    page.get_by_label('GitHub identity token',exact=True).fill(token)
    page.get_by_role('button',name='Verify my identity',exact=True).click()
    expect(page.get_by_role('button',name='Sign out of review session')).to_be_visible()


def run(browser,width,out):
    fixture=CampaignGatewayTests('test_fresh_owner_and_exact_hash_are_required_to_issue_authority')
    fixture.setUp();fixture.wire=FakePaidTransport()
    credentials=patch.object(CampaignExecutionService,'_credentials',return_value=({},'synthetic-secret',{'access_token':'synthetic-user-token','page_token':'synthetic-page-token'}))
    credentials.start();fixture.addCleanup(credentials.stop)
    context=browser.new_context(viewport={'width':width,'height':900})
    page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    try:
        login(page,fixture.origin,OWNER_TOKEN)
        page.locator('#navigation > details > summary').click()
        page.locator('#navigation [data-view=connections]').click()
        page.get_by_role('button',name='Review campaign automation',exact=True).click()
        form=page.locator('#campaign-scope-form')
        form.locator('[name=connection_id]').select_option(fixture.connection)
        form.get_by_label('Approved post copy',exact=True).fill(fixture.message)
        form.get_by_label('Rights and claims evidence',exact=True).fill('Synthetic owned app claims and original copy for this isolated test.')
        form.locator('summary').click()
        form.get_by_label('Numeric ad-account ID',exact=True).fill('456')
        form.get_by_label('Currency',exact=True).fill('CAD')
        form.get_by_label('Maximum media budget in minor units',exact=True).fill('80')
        form.locator('[name=billing]').check();form.locator('[name=ordinary]').check()
        assert fixture.wire.posts==0
        form.get_by_role('button',name='Review exact automation scope').click()
        review=page.locator('#campaign-review')
        expect(review.get_by_role('heading',name='What you’re approving')).to_be_visible()
        for value in ('Synthetic Page · 123', '80 minor units CAD', 'Meta ad account', '456',
                      'Audience countries', 'CA', 'Permission expires', 'Maximum Meta requests',
                      'does not publish, schedule, or spend now', fixture.message):
            expect(review).to_contain_text(value)
        assert page.locator('#modal').evaluate('(modal) => modal.scrollTop === 0')
        page.screenshot(path=str(out/f'campaign-review-{width}.png'))
        (out/f'campaign-review-{width}.html').write_text(page.content(),encoding='utf-8')
        details=review.locator('details').filter(has_text='Exact authority and limits')
        assert details.get_attribute('open') is None
        details.locator('summary').focus()
        page.keyboard.press('Enter')
        expect(details.locator('pre')).to_be_visible()
        page.keyboard.press('Enter')
        assert details.get_attribute('open') is None
        assert fixture.wire.posts==0
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.get_by_role('button',name='Approve scope and enable automation',exact=True).focus()
        page.keyboard.press('Enter')
        expect(page.locator('#campaign-progress')).to_contain_text('ACTIVE')
        assert fixture.wire.posts==0
        page.get_by_role('button',name='Run approved workflow',exact=True).click()
        expect(page.locator('#campaign-progress')).to_contain_text('VERIFIED',timeout=15000)
        expect(page.locator('#campaign-progress')).to_contain_text('ACTIVE_campaign',timeout=15000)
        assert fixture.wire.posts==1 and len(fixture.wire.objects)==4
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        page.screenshot(path=str(out/f'campaign-progress-{width}.png'))
        (out/f'campaign-progress-{width}.html').write_text(page.content(),encoding='utf-8')
        with page.expect_popup() as opened:
            page.get_by_role('button',name='Campaign report / Save PDF',exact=True).click()
        report=opened.value;report.wait_for_load_state('load')
        pdf_path=out/f'campaign-report-{width}.pdf'
        report.pdf(path=str(pdf_path),format='A4')
        with fitz.open(pdf_path) as pdf:
            text='\n'.join(p.get_text() for p in pdf)
            assert 'Verified Page posts' in text and 'Campaign delivery' in text
            assert fixture.message not in text and OWNER_TOKEN not in text
        report.close()
        page.get_by_role('button',name='Turn off this scope',exact=True).click()
        expect(page.locator('#campaign-progress')).to_contain_text('REVOKED')
        expect(page.locator('#campaign-progress')).to_contain_text('PAUSED_campaign')
        page.get_by_role('button',name='Refresh saved receipts',exact=True).click()
        expect(page.locator('#campaign-progress')).to_contain_text('123_777')
        assert fixture.wire.posts==1
        assert not errors,errors
        return dict(width=width,owner_scope=True,keyboard_approval=True,no_effect_before_run=True,
                    verified_saved_receipt=True,paid_activation=True,verified_pause=True,pdf_privacy=True,off=True,requests=fixture.wire.posts,javascript_errors=errors,
                    provider='SYNTHETIC_ONLY',real_campaign_or_spend='NOT_RUN')
    finally:
        context.close();fixture.tearDown();fixture.doCleanups()


def main():
    out=ROOT/'.factory/licensing-automation';out.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch();results=[run(browser,width,out) for width in (1440,390)];browser.close()
    report=dict(status='PASS',observations=results)
    (out/'campaign-browser.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))


if __name__=='__main__':main()
