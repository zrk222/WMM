"""Actual human UI through loopback API; provider identity is synthetic only."""
from pathlib import Path
import json
import hashlib
import sys
from unittest.mock import patch
import fitz
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright,expect
from mission_control.operator_client import OperatorClient
from tests.test_agent_review_http import ReviewHTTPTests
from tests import test_verified_review as identities


def login(page,origin,token):
    page.goto(origin)
    page.locator('[data-view=activity]').click()
    page.get_by_role('button',name='Sign in for verified review',exact=True).click()
    page.get_by_label('GitHub identity token',exact=True).fill(token)
    page.get_by_role('button',name='Verify my identity',exact=True).click()
    expect(page.get_by_role('button',name='Sign out of review session')).to_be_visible()


def click(page,action):
    page.locator('[data-action=control-'+action+']').first.click()


def report(page,out,name,private):
    page.locator('[data-action=control-report]').focus()
    with page.expect_popup() as wait:page.keyboard.press('Enter')
    popup=wait.value;popup.wait_for_load_state('load')
    assert popup.evaluate('window.opener===null')
    assert not popup.locator('input,textarea').count()
    path=out/(name+'.pdf');popup.pdf(path=str(path),format='A4',print_background=True)
    with fitz.open(path) as pdf:
        text='\n'.join(p.get_text() for p in pdf)
        assert 'Agent controls:' in text and 'sample-one' in text
        assert private not in text and 'PRIVATE_SENTINEL' not in text
        assert 'Evidence boundaries' in text
    popup.close()


def capture(page,out,name):
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(out/(name+'.png')),full_page=True)
    html=page.content().replace('</head>','<style>'+(ROOT/'mission_control/static/style.css').read_text(encoding='utf-8')+'</style></head>')
    (out/(name+'.html')).write_text(html,encoding='utf-8')


def races(page):
    """Hold actual HTTP requests to exercise duplicate and late-response handling."""
    page.locator('#close-modal').click();click(page,'grants');click(page,'new')
    page.get_by_label('Agent identifier',exact=True).fill('late-response-agent')
    page.locator('input[name=operations][value="growth.read"]').check()
    # A changed loaded version is rejected locally before issuing credentials.
    page.evaluate('state.workspace.app.version++')
    page.get_by_role('button',name='Issue scoped grant',exact=True).click()
    expect(page.locator('#control-form-error')).to_contain_text('App setup or review identity changed')
    page.evaluate('state.workspace.app.version--')
    pending=[]
    page.route('**/agent-grants/issue',lambda route:pending.append(route))
    page.get_by_role('button',name='Issue scoped grant',exact=True).click()
    page.wait_for_function('document.querySelector("#control-grant-form").dataset.pending==="true"')
    page.evaluate('document.querySelector("#control-grant-form").requestSubmit()')
    assert len(pending)==1
    page.locator('#app-select').select_option('sample-two')
    pending[0].continue_();page.unroute('**/agent-grants/issue')
    expect(page.locator('#toast')).to_contain_text('Grant was issued')
    assert not page.locator('[data-grant-secret]').count()
    page.locator('#app-select').select_option('sample-one')
    expect(page.locator('[data-action=control-grants]')).to_be_visible()
    # A replaced dialog must not be resurrected by an older queue response.
    pending=[]
    page.route('**/agent-reviews/list',lambda route:pending.append(route))
    click(page,'queue');page.wait_for_function('document.querySelector("#agent-control-dialog").textContent.includes("Loading saved")')
    page.locator('#close-modal').click();click(page,'grants')
    expect(page.locator('#agent-control-dialog')).to_contain_text('saved grants')
    pending[0].continue_();page.unroute('**/agent-reviews/list')
    expect(page.locator('#agent-control-dialog')).to_contain_text('saved grants')
    assert not page.locator('[data-action=control-inspect]').count()


def viewport(browser,width,out):
    fixture=ReviewHTTPTests('test_exact_human_approval_and_agent_resume_use_separate_sessions');fixture.setUp()
    context=browser.new_context(viewport=dict(width=width,height=900 if width==1440 else 844))
    checker_context=browser.new_context(viewport=dict(width=width,height=900 if width==1440 else 844))
    page=context.new_page();checker=checker_context.new_page();errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)));checker.on('pageerror',lambda e:errors.append(str(e)))
    try:
        login(page,fixture.origin,identities.OWNER_TOKEN)
        click(page,'grants');expect(page.locator('#agent-control-dialog')).to_contain_text('saved grants')
        report(page,out,f'grants-{width}',fixture.token)
        click(page,'new')
        page.get_by_label('Agent identifier',exact=True).fill('browser-agent')
        page.get_by_label('Maximum admitted attempts',exact=True).fill('300')
        page.locator('input[name=operations][value="growth.read"]').check()
        page.locator('input[name=operations][value="growth.save"]').check()
        capture(page,out,f'grant-form-{width}')
        page.get_by_role('button',name='Issue scoped grant',exact=True).click()
        token=page.get_by_label('Once-only agent bearer token').input_value()
        assert token.startswith('wmmg_')
        assert page.locator('#grant-secret').get_attribute('value') is None
        assert token not in page.content()
        assert token not in page.evaluate('JSON.stringify(localStorage)')
        token_handle=page.locator('#grant-secret').element_handle()
        page.get_by_role('button',name='Show or hide token').click()
        assert page.locator('#grant-secret').get_attribute('type')=='text'
        page.locator('#close-modal').click();expect(page.locator('#modal')).not_to_be_visible()
        page.wait_for_function('(node)=>node.value===\'\'',arg=token_handle)
        agent=OperatorClient(fixture.origin,grant_token=token)
        envelope=fixture.input
        envelope['input']['data']['listing']['fields']['description']='PRIVATE_SENTINEL '+('Synthetic long description. '*100)
        prepared=agent.review('prepare',dict(id='a-browser-request',envelope=envelope))
        click(page,'queue');click(page,'inspect')
        expect(page.locator('#agent-control-dialog')).to_contain_text('PRIVATE_SENTINEL')
        expect(page.locator('[data-action=control-approve]')).to_have_count(0)
        page.locator('#close-modal').click()
        login(checker,fixture.origin,identities.CHECKER_TOKEN)
        expect(checker.locator('[data-action=control-grants]')).to_have_count(0)
        click(checker,'queue');click(checker,'inspect')
        expect(checker.locator('[data-action=control-approve]')).to_be_visible()
        capture(checker,out,f'exact-review-{width}')
        report(checker,out,f'exact-review-{width}',token)
        checker.evaluate('window.savedOpen=window.open;window.open=()=>null')
        click(checker,'report');expect(checker.locator('#control-error')).to_contain_text('Allow a report window')
        checker.evaluate('window.open=window.savedOpen')
        click(checker,'approve');expect(checker.locator('#agent-control-dialog')).to_contain_text('APPROVED')
        approved=agent.review('status',dict(app_id='sample-one',id='a-browser-request'))['checkpoint']
        done=agent.review('resume',dict(app_id='sample-one',id='a-browser-request',revision=approved['revision'],packet_hash=approved['hash']))
        assert done['checkpoint']['state']=='SUCCEEDED'
        click(checker,'inspect');expect(checker.locator('#agent-control-dialog')).to_contain_text('SUCCEEDED')
        report(checker,out,f'result-{width}',token)
        checker.locator('#close-modal').click()
        envelope['input']['id']='second-browser-listing'
        agent.review('prepare',dict(id='b-browser-request',envelope=envelope))
        click(page,'queue');page.locator('[data-action=control-inspect][data-id=b-browser-request]').click()
        click(page,'cancel');expect(page.locator('#agent-control-dialog')).to_contain_text('CANCELLED')
        page.locator('#close-modal').click()
        envelope['input']['id']='unknown-browser-listing'
        pending=agent.review('prepare',dict(id='c-browser-request',envelope=envelope))
        approved=fixture.approve(pending)
        with patch('mission_control.agent_review_dispatch.execute',side_effect=RuntimeError('PRIVATE_SENTINEL')):
            unknown=agent.review('resume',dict(app_id='sample-one',id='c-browser-request',revision=approved['revision'],packet_hash=approved['hash']))
        assert unknown['checkpoint']['state']=='UNKNOWN'
        click(checker,'queue');checker.locator('[data-action=control-inspect][data-id=c-browser-request]').click()
        click(checker,'reconcile-open')
        checker.get_by_label('Verified outcome').select_option('FAILED')
        checker.get_by_label('Evidence SHA256').fill('a'*64)
        checker.get_by_role('button',name='Record outcome without retry').click()
        expect(checker.locator('#agent-control-dialog')).to_contain_text('FAILED')
        checker.locator('#close-modal').click()
        for n in range(101):agent.review('prepare',dict(id=f'paging-{n:03d}',envelope=envelope))
        click(checker,'queue');expect(checker.locator('#agent-control-dialog')).to_contain_text('100 requests displayed')
        checker.get_by_role('button',name='Next requests').click()
        expect(checker.locator('#agent-control-dialog')).to_contain_text('4 requests displayed')
        report(checker,out,f'queue-{width}',token)
        checker.locator('#app-select').select_option('sample-two')
        expect(checker.locator('#modal')).not_to_be_visible()
        expect(checker.locator('#main')).not_to_contain_text('a-browser-request')
        click(page,'grants');click(page,'new')
        page.get_by_label('Agent identifier',exact=True).fill('preserved-input')
        page.locator('input[name=operations][value="growth.read"]').check()
        page.route('**/agent-grants/issue',lambda route:route.fulfill(status=400,content_type='application/json',body=json.dumps(dict(error='Synthetic save failure'))))
        page.get_by_role('button',name='Issue scoped grant',exact=True).click()
        expect(page.locator('#control-form-error')).to_contain_text('Synthetic save failure')
        assert page.get_by_label('Agent identifier',exact=True).input_value()=='preserved-input'
        page.unroute('**/agent-grants/issue')
        races(page)
        # Revoke the browser-issued grant through the actual owner UI.
        row=page.locator('#agent-control-dialog section').filter(has=page.get_by_role('heading',name='browser-agent',exact=True))
        row.get_by_role('button',name='Review revocation').click();click(page,'revoke')
        expect(page.locator('#agent-control-dialog')).to_contain_text('REVOKED')
        assert not errors,errors
        return dict(width=width,grant_issue_revoke=True,secret_cleared=True,independent_review=True,actual_resume='SUCCEEDED',cancel=True,reconcile=True,paging=dict(total=104,last_page=4),error_retention=True,duplicate_suppression=True,late_response_discard=True,stale_version_rejected=True,pdf_privacy=True,keyboard=True,app_switch=True,javascript_errors=errors)
    finally:
        context.close();checker_context.close();fixture.tearDown()


def main():
    out=ROOT/'.factory/agent-control-ui';out.mkdir(parents=True,exist_ok=True)
    paths=['mission_control/static/agent-control.js','mission_control/static/app.js','mission_control/static/index.html','mission_control/server.py','mission_control/agent_operations.py','tools/test_agent_control_browser.py']
    source_hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in paths}
    with sync_playwright() as p:
        browser=p.chromium.launch();observations=[viewport(browser,w,out) for w in (1440,390)]
        assert all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==value for name,value in source_hashes.items())
        result=dict(status='PASS',browser=browser.version,observations=observations,identity='SYNTHETIC_PROVIDER_FIXTURE_ONLY',external_writes=False,source_hashes=source_hashes,source_unchanged=True)
        browser.close()
    (out/'browser.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))


if __name__=='__main__':main()
