"""Optional actual browser checks with isolated stores and fixed mocked PostHog responses."""
from pathlib import Path
from unittest.mock import patch
import json,sys,threading
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright,expect
from tests.test_experiment_tracking import ExperimentTrackingTests
from tests.test_tracking_contract import payload
from tests.test_experiments import prepared,REGISTER
from mission_control.experiments import Experiments
from mission_control.experiment_tracking import Tracking
from mission_control.insights_transport import ProviderFailure
from mission_control.server import Server
from mission_control.worker import run_once

# Paths identify exercised functions, not measured browser line or branch coverage.
PATHS=['trackingPanel','trackingAccess','trackingReview','trackingForm','trackingSubmit','trackingCounts',
       'trackingProgress','trackingRun','trackingVisible','trackingUpdate','trackingPoll','trackingHistory','trackingAction','trackingReviewVisible','trackingRecovery']


def prepare():
    fixture=ExperimentTrackingTests('test_execute_adopts_only_guarded_result_once_without_keys_in_receipts');fixture.setUp()
    definition=prepared(fixture.store,app_id='sample-two')
    with patch('mission_control.experiments.now',return_value=REGISTER):Experiments(fixture.store).create('sample-two',definition)
    server=Server(('127.0.0.1',0),fixture.store)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    return fixture,server,thread


def review(page):
    page.locator('#experiment-tracking [data-action="automatic-tracking-review"]').first.click()
    expect(page.locator('#tracking-form')).to_be_visible()
    expect(page.locator('#tracking-dialog')).to_contain_text('up to three read-only requests')
    assert page.locator('#tracking-form input').count()==0


def approve(page,fixture):
    page.locator('#tracking-form button[type="submit"]').click()
    expect(page.locator('#tracking-status')).to_contain_text('QUEUED')
    return Tracking(fixture.store).list('sample-one')[0]


def cancel_and_isolation(page,fixture,run):
    page.locator('#modal [data-action="automatic-tracking-review"]').click()
    expect(page.locator('#tracking-form')).to_be_visible()
    page.locator('#tracking-form button[type="submit"]').focus();page.wait_for_timeout(1200)
    expect(page.locator('#tracking-form')).to_be_visible()
    assert page.evaluate('document.activeElement.type')=='submit'
    page.keyboard.press('Escape')
    page.locator('#experiment-tracking [data-action="automatic-tracking-history"]').click()
    page.locator(f'#modal [data-action="automatic-tracking-run"][data-id="{run["id"]}"]').click()
    page.locator('[data-action="automatic-tracking-cancel"]').click()
    expect(page.locator('#tracking-status')).to_contain_text('CANCELLED')
    with patch('mission_control.tracking_posthog.request') as request:
        assert not run_once(fixture.store);request.assert_not_called()
    page.keyboard.press('Escape')


def observed(page,fixture):
    review(page);run=approve(page,fixture);expected=run['plan']['proposal']['expected_flag']
    with patch('mission_control.experiment_tracking.Vault.get',return_value=fixture.secret()), \
         patch('mission_control.tracking_posthog.request',side_effect=[{'id':123},dict(count=1,results=[expected]),payload()]) as request:
        assert run_once(fixture.store);assert request.call_count==3
    page.locator('[data-action="automatic-tracking-refresh"]').click()
    expect(page.locator('#tracking-status')).to_contain_text('OBSERVED')
    assert page.locator('#tracking-status').get_attribute('aria-live')=='polite'
    assert page.locator('#tracking-dialog tbody tr').count()==4
    expect(page.locator('#tracking-dialog')).to_contain_text('not launch')
    page.locator('#modal [data-action="job"]').click()
    expect(page.locator('#tracking-status')).to_have_count(0);page.wait_for_timeout(1200)
    expect(page.locator('#tracking-status')).to_have_count(0)
    page.keyboard.press('Escape')
    return run


def failed_read(page,fixture):
    review(page);approve(page,fixture)
    with patch('mission_control.experiment_tracking.Vault.get',return_value=fixture.secret()), \
         patch('mission_control.tracking_posthog.request',side_effect=ProviderFailure('PERMISSION_REQUIRED','PRIVATE_DIAGNOSTIC')):
        assert run_once(fixture.store)
    page.locator('[data-action="automatic-tracking-refresh"]').click()
    expect(page.locator('#tracking-status')).to_contain_text('NEEDS REVIEW')
    expect(page.locator('#tracking-dialog')).to_contain_text('PERMISSION REQUIRED')
    assert 'PRIVATE_DIAGNOSTIC' not in page.locator('#tracking-dialog').inner_text()
    expect(page.locator('#modal [data-action="automatic-tracking-review"]')).to_be_visible()


def reconnect_and_reload(page):
    page.keyboard.press('Escape');page.reload();page.locator('#main h1').wait_for()
    page.locator('#app-select').select_option('sample-two')
    page.locator('[data-view="pipeline"]').first.click();review_button=page.locator('#experiment-tracking [data-action="automatic-tracking-review"]')
    review_button.click();expect(page.locator('#modal-title')).to_have_text('Connect experiment measurement')
    page.locator('#modal [data-action="measurement-connections"]').click()
    expect(page.locator('#main h1')).to_have_text('Connect with clarity')


def stale_setup_recovery(page,fixture):
    app=fixture.store.app('sample-one')
    fixture.store.save_app('sample-one',{**app['data'],'release':'changed-build'},app['version'])
    page.locator('#modal [data-action="automatic-tracking-review"]').click()
    expect(page.locator('#modal-title')).to_have_text('Tracking setup needs review')
    expect(page.locator('#tracking-loading')).to_have_count(0)
    page.locator('#modal [data-action="automatic-tracking-reload"]').click()
    expect(page.locator('#modal')).not_to_be_visible()


def main():
    out=ROOT/'.factory';rows=[]
    with sync_playwright() as tool:
        browser=tool.chromium.launch()
        for width,height in [(1440,900),(390,844)]:
            fixture,server,thread=prepare()
            try:
                page=browser.new_page(viewport=dict(width=width,height=height));errors=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{server.server_port}');page.locator('#main h1').wait_for()
                page.locator('[data-view="pipeline"]').first.click()
                review(page);cancel_and_isolation(page,fixture,approve(page,fixture))
                observed(page,fixture);failed_read(page,fixture)
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                layout=page.evaluate('()=>({body:document.querySelector("#tracking-dialog").getBoundingClientRect().height,footer:document.querySelector("#modal .modal-actions").getBoundingClientRect().height})')
                assert layout['body']>layout['footer']
                page.screenshot(path=str(out/f'tracking-{width}.png'))
                html=page.content().replace('<link rel="stylesheet" href="/style.css">','<style>'+(ROOT/'mission_control/static/style.css').read_text(encoding='utf-8')+'</style>')
                (out/f'tracking-rendered-{width}.html').write_text(html,encoding='utf-8')
                stale_setup_recovery(page,fixture);reconnect_and_reload(page);assert not errors,errors
                rows.append(dict(viewport=[width,height],startup_build_id=server.service.build_id,dialog_layout=layout,approval_without_research_fields=True,cancel_no_reads=True,
                    provider_requests=3,aggregate_rows=4,permission_failure_recovery=True,no_raw_diagnostics=True,
                    poll_modal_isolation=True,keyboard_focus_retained=True,no_source_recovery=True,reload=True,
                    stale_setup_recovery=True,horizontal_overflow=False,js_errors=errors,ui_paths=PATHS))
                page.close()
            finally:
                server.shutdown();server.server_close();thread.join();fixture.doCleanups()
        browser.close()
    result=dict(status='PASS',scope='Actual isolated browser with mocked provider responses; not a live campaign or provider permission proof',observations=rows)
    (out/'tracking-browser-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))


if __name__=='__main__':main()
