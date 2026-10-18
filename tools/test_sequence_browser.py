"""Optional developer browser proof using installed Playwright and isolated fixtures.

Run with an existing Playwright/Chromium environment. This is not a runtime
dependency and never reads operational app databases or calls real providers.
"""
from pathlib import Path
from unittest.mock import patch
import json,sys,threading
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright,expect
from tests.test_sequence_runtime import SequenceRuntimeTests
from tests.test_aeo_workflows import CountingReader,ROOT as SITE
from mission_control.server import Server
from mission_control.sequence_store import Sequences
from mission_control.worker import run_once,jobs

# Scenario labels identify exercised UI paths, not measured line/branch coverage.
UI_PATHS=['sequencePanel','sequenceRecent','sequenceTarget','sequenceChoices','sequenceReview',
          'sequenceHistory','sequenceProgress','sequenceNextItem','sequenceRun','sequenceError',
          'sequenceVisible','sequenceUpdate','sequencePoll','sequenceAction','sequenceSubmit','sequenceSelectedId']


def prepare():
    fixture=SequenceRuntimeTests('test_worker_advances_independent_steps_and_resumes_saved_checkpoint');fixture.setUp()
    fixture.connected();app=fixture.store.app('sample-one')
    fixture.store.save_app('sample-one',{**app['data'],'website':SITE+'/page'},app['version'])
    server=Server(('127.0.0.1',0),fixture.store)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    return fixture,server,thread


def click_review(page):
    page.locator('[data-view="pipeline"]').first.click()
    page.locator('[data-action="automatic-sequence-review"]').last.click()
    expect(page.locator('#sequence-form')).to_be_visible()


def approve_collect_only(page,fixture):
    proposal=fixture.server_proposal if hasattr(fixture,'server_proposal') else Sequences(fixture.store).proposal('sample-one')[1]
    target=next(s['id'] for s in proposal['steps'] if s['tool']=='collect_sources')
    for checkbox in page.locator('#sequence-form input[name="step"]').all():
        checkbox.uncheck()
    page.locator('#sequence-form button[type="submit"]').click()
    expect(page.locator('#sequence-error')).to_contain_text('at least one')
    assert Sequences(fixture.store).history('sample-one')==[]
    page.locator(f'#sequence-form input[value="{target}"]').check()
    page.locator('#sequence-form button[type="submit"]').click()
    expect(page.locator('#sequence-status')).to_be_visible()
    run=Sequences(fixture.store).history('sample-one')[0]
    assert len(run['steps'])==1 and run['steps'][0]['tool']=='collect_sources'
    return run


def check_modal_isolation(page,run):
    page.locator('[data-action="automatic-sequence-review"]').last.click()
    page.locator('#sequence-form input[name="step"]').first.focus()
    page.wait_for_timeout(1200)
    expect(page.locator('#sequence-form')).to_be_visible()
    assert page.evaluate('document.activeElement.name')=='step'
    page.keyboard.press('Escape')
    page.locator(f'[data-action="automatic-sequence-run"][data-id="{run["id"]}"]').first.click()
    expect(page.locator('#sequence-status')).to_be_visible()


def stop_owned_work(page,fixture):
    assert run_once(fixture.store)
    page.locator('[data-action="automatic-sequence-refresh"]').click()
    expect(page.locator('#sequence-status')).to_contain_text('WAITING')
    page.locator('[data-action="automatic-sequence-cancel"]').click()
    expect(page.locator('#sequence-status')).to_contain_text('CANCELLED')
    expect(page.locator('[data-action="automatic-sequence-cancel"]')).to_have_count(0)
    sources=[j for j in jobs(fixture.store,'sample-one') if j['action']=='sync']
    assert len(sources)==3 and all(j['status']=='CANCELLED' for j in sources)


def complete_new_plan(page,fixture):
    page.locator('[data-action="automatic-sequence-review"]').last.click()
    page.locator('#sequence-form button[type="submit"]').click()
    expect(page.locator('#sequence-status')).to_be_visible()
    with patch('mission_control.worker.sync',return_value={'fixture':True}) as a, \
         patch('mission_control.worker.read_report',return_value={'fixture':True}) as b, \
         patch('mission_control.aeo_workflows.PublicReader',CountingReader):
        fixture.pump()
        assert a.call_count+b.call_count==3
    page.locator('[data-action="automatic-sequence-refresh"]').click()
    expect(page.locator('#sequence-status')).to_contain_text('EVIDENCE REVIEW REQUIRED')
    assert page.locator('#sequence-status').get_attribute('aria-live')=='polite'
    assert 'Evidence still needs review' in page.locator('#sequence-dialog').inner_text()
    row=Sequences(fixture.store).history('sample-one')[0]
    assert row['checkpoint']==2 and not row['automatically_verified']
    return row


def retained_evidence_and_access(page,run):
    page.locator('[data-action="automatic-resolution-run"]').first.click()
    expect(page.locator('#resolution-live-status')).to_be_visible()
    page.wait_for_timeout(1200)
    expect(page.locator('#resolution-live-status')).to_be_visible()
    page.keyboard.press('Escape')
    page.locator('[data-action="automatic-sequence-history"]').click()
    expect(page.locator(f'#modal [data-action="automatic-sequence-run"][data-id="{run["id"]}"]')).to_be_visible()
    page.keyboard.press('Escape')
    page.reload();page.locator('#main h1').wait_for()
    page.locator('#app-select').select_option('sample-two')
    page.locator('[data-view="pipeline"]').first.click()
    page.locator('[data-action="automatic-sequence-review"]').last.click()
    expect(page.locator('#sequence-form button[type="submit"]')).to_have_count(0)
    page.locator('#modal [data-action="measurement-connections"]').click()
    expect(page.locator('#main h1')).to_have_text('Connect with clarity')


def main():
    folder=ROOT/'.factory';folder.mkdir(exist_ok=True);observations=[]
    with sync_playwright() as tool:
        browser=tool.chromium.launch()
        for width,height in [(1440,900),(390,844)]:
            fixture,server,thread=prepare()
            try:
                page=browser.new_page(viewport={'width':width,'height':height});errors=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{server.server_port}');page.locator('#main h1').wait_for()
                click_review(page);run=approve_collect_only(page,fixture)
                check_modal_isolation(page,run);stop_owned_work(page,fixture)
                complete=complete_new_plan(page,fixture)
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                page.screenshot(path=str(folder/f'sequence-{width}.png'),full_page=True)
                rendered=page.content().replace('<link rel="stylesheet" href="/style.css">',
                    '<style>'+(ROOT/'mission_control/static/style.css').read_text(encoding='utf-8')+'</style>')
                (folder/f'sequence-rendered-{width}.html').write_text(rendered,encoding='utf-8')
                retained_evidence_and_access(page,complete)
                assert not errors,errors
                observations.append(dict(viewport=[width,height],approval_edit=True,zero_selection_rejected=True,
                    cancellation_owned_only=True,completed_actions=2,native_evidence=True,reload=True,
                    no_access_recovery=True,poll_modal_isolation=True,keyboard_focus_retained=True,
                    horizontal_overflow=False,js_errors=errors,ui_paths=UI_PATHS))
                page.close()
            finally:
                server.shutdown();server.server_close();thread.join();fixture.doCleanups()
        browser.close()
    result=dict(status='PASS',scope='Isolated synthetic UI and mocked read responses; no live provider or campaign proof',observations=observations)
    (folder/'sequence-browser-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':main()
