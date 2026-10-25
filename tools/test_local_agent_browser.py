"""Actual setup, consent, worker inference and reports for a synthetic local server."""
from pathlib import Path
import hashlib
import json
import sys
import threading
import fitz
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright,expect
from mission_control.server import Server
from tests.test_local_agent_access import LocalAccessTests
from tests.test_agent_access import answer,connection_test_fixture
from mission_control.common import canonical


def snapshot(page,out,name):
    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(out/(name+'.png')),full_page=True)
    html=page.content().replace('</head>','<style>'+(ROOT/'mission_control/static/style.css').read_text(encoding='utf-8')+'</style></head>')
    (out/(name+'.html')).write_text(html,encoding='utf-8')


def run_viewport(browser,width,out):
    fixture=LocalAccessTests('test_real_worker_capability_test_then_routed_draft');fixture.setUp()
    server=Server(('127.0.0.1',0),fixture.store);server.runner.start()
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    context=browser.new_context(viewport=dict(width=width,height=900 if width==1440 else 844));page=context.new_page();errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    try:
        page.goto('http://127.0.0.1:'+str(server.server_port));page.locator('[data-view=agents]').click()
        page.locator('[data-action=agent-setup][data-id=local_api]').click()
        form=page.locator('#agent-setup-form')
        form.get_by_label('Connection name',exact=True).fill('Local browser model')
        form.get_by_label('Model',exact=True).fill('synthetic-model')
        form.get_by_label('Local HTTP API base URL',exact=True).fill(fixture.model.url)
        assert not form.get_by_label('Local server bearer key (optional)',exact=True).get_attribute('required')
        snapshot(page,out,f'local-setup-{width}')
        form.locator('[name=charges]').check();form.get_by_role('button',name='Save protected connection').click()
        expect(page.locator('#main')).to_contain_text('Local browser model')
        assert fixture.model.calls==[]
        fixture.model.value['choices'][0]['message']['content']=canonical(connection_test_fixture())
        page.get_by_role('button',name='Test connection',exact=True).click()
        expect(page.locator('#agent-approve-form')).to_contain_text(fixture.model.url)
        assert fixture.model.calls==[]
        page.get_by_role('button',name='Approve and run once',exact=True).click()
        expect(page.locator('#agent-job-status')).to_contain_text('SUCCEEDED',timeout=15000)
        assert len(fixture.model.calls)==1
        page.locator('#close-modal').click()
        page.get_by_role('button',name='Choose task routes',exact=True).click()
        page.get_by_label('Access mode',exact=True).select_option('local')
        for select in page.locator('#agent-routes-form select:not([name=mode])').all():
            select.select_option(label='Local browser model')
        page.get_by_role('button',name='Save task routes',exact=True).click()
        expect(page.locator('#modal')).not_to_be_visible()
        fixture.model.value['choices'][0]['message']['content']=canonical(answer())
        page.get_by_role('button',name='Prepare agent work',exact=True).click()
        page.get_by_label('Focus (optional)',exact=True).fill('A reviewed synthetic local request')
        page.get_by_role('button',name='Review proposed work',exact=True).click()
        expect(page.locator('#agent-approve-form')).to_contain_text('A reviewed synthetic local request')
        assert len(fixture.model.calls)==1
        snapshot(page,out,f'local-review-{width}')
        page.get_by_role('button',name='Approve and run once',exact=True).click()
        expect(page.locator('#agent-job-status')).to_contain_text('SUCCEEDED',timeout=15000)
        expect(page.locator('#agent-run')).to_contain_text('Try a bounded test')
        assert len(fixture.model.calls)==2
        page.locator('#close-modal').click()
        page.get_by_role('button',name='Report / Save PDF',exact=True).focus()
        with page.expect_popup() as wait:page.keyboard.press('Enter')
        popup=wait.value;popup.wait_for_load_state('load');pdfpath=out/f'local-report-{width}.pdf'
        popup.pdf(path=str(pdfpath),format='A4',print_background=True)
        with fitz.open(pdfpath) as pdf:
            text='\n'.join(p.get_text() for p in pdf)
            assert 'Your agents' in text and 'Configured model profiles' in text and 'Evidence boundaries' in text
            assert 'A reviewed synthetic local request' not in text
        popup.close()
        page.reload();page.locator('[data-view=agents]').click()
        expect(page.locator('#main')).to_contain_text('Local browser model')
        page.get_by_role('button',name='Choose task routes',exact=True).click()
        expect(page.get_by_label('Access mode',exact=True)).to_have_value('local')
        page.locator('#close-modal').click()
        fixture.model.status=500
        page.get_by_role('button',name='Test connection',exact=True).click()
        page.get_by_role('button',name='Approve and run once',exact=True).click()
        expect(page.locator('#agent-job-status')).to_contain_text('BLOCKED',timeout=15000)
        assert len(fixture.model.calls)==3
        assert not errors,errors
        return dict(width=width,keyless_setup=True,explicit_consent=True,capability_test=True,local_routing_persisted=True,approved_draft=True,requests_before_approval=0,request_count=3,provider_error_retained=True,pdf_privacy=True,keyboard=True,javascript_errors=errors)
    finally:
        context.close();server.runner.stop();server.shutdown();server.server_close();thread.join();fixture.doCleanups()


def main():
    out=ROOT/'.factory/local-agent-api';out.mkdir(parents=True,exist_ok=True)
    paths=['mission_control/local_agent_api.py','mission_control/agent_contract.py','mission_control/agent_access.py','mission_control/agent_api.py','mission_control/agent_registry.py','mission_control/static/agent-access.js','tools/test_local_agent_browser.py']
    hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}
    with sync_playwright() as p:
        browser=p.chromium.launch();observations=[run_viewport(browser,w,out) for w in (1440,390)]
        result=dict(status='PASS',browser=browser.version,observations=observations,source_hashes=hashes,source_unchanged=all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==v for p,v in hashes.items()),model='SYNTHETIC_HTTP_FIXTURE_ONLY',actual_model_acceptance='NOT_RUN',external_writes=False)
        browser.close()
    assert result['source_unchanged'];(out/'browser.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))


if __name__=='__main__':main()
