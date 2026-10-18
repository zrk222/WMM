"""Actual campaign-sequence UI approval and readback with synthetic provider responses."""
from pathlib import Path
from unittest.mock import patch
import json,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from playwright.sync_api import sync_playwright,expect
from test_tracking_browser import prepare
from mission_control.experiment_tracking import Tracking
from mission_control.worker import run_once
from tests.test_tracking_contract import payload


def journey(page,fixture):
    page.locator('[data-view="pipeline"]').first.click()
    page.locator('#campaign-sequence [data-action="automatic-sequence-review"]').click()
    form=page.locator('#sequence-form');expect(form).to_be_visible()
    for choice in form.locator('input[name="step"]').all():choice.uncheck()
    action=form.locator('article').filter(has_text='Check tracking:').first
    target=action.inner_text()
    for expected in (fixture.experiment['id'],fixture.source['id'],fixture.app['data']['locale'],fixture.app['data']['release']):
        assert expected in target,(expected,target)
    action.locator('input').check();form.locator('button[type="submit"]').click()
    expect(page.locator('#sequence-status')).to_contain_text('QUEUED')
    assert run_once(fixture.store)
    child=Tracking(fixture.store).list('sample-one')[0]
    expected=child['plan']['proposal']['expected_flag']
    with patch('mission_control.experiment_tracking.Vault.get',return_value=fixture.secret()), \
         patch('mission_control.tracking_posthog.request',side_effect=[{'id':123},dict(count=1,results=[expected]),payload()]) as request:
        assert run_once(fixture.store);assert request.call_count==3
    assert run_once(fixture.store)
    expect(page.locator('#sequence-status')).to_contain_text('EVIDENCE REVIEW REQUIRED',timeout=6000)
    expect(page.locator('#sequence-dialog')).to_contain_text('EVIDENCE GATHERED')
    page.keyboard.press('Escape');page.reload();page.locator('#main h1').wait_for()
    page.locator('[data-view="pipeline"]').first.click()
    page.locator('#experiment-tracking [data-action="automatic-tracking-history"]').click()
    page.locator(f'#modal [data-action="automatic-tracking-run"][data-id="{child["id"]}"]').click()
    expect(page.locator('#tracking-status')).to_contain_text('OBSERVED')
    assert page.locator('#tracking-dialog tbody tr').count()==4
    return dict(exact_scope_visible=True,one_selected_action=True,provider_requests=3,
                durable_parent_and_native_history=True,automatically_verified=False)


def main():
    rows=[]
    with sync_playwright() as runtime:
        browser=runtime.chromium.launch()
        for width,height in ((1440,900),(390,844)):
            fixture,server,thread=prepare()
            try:
                page=browser.new_page(viewport=dict(width=width,height=height));errors=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(f'http://127.0.0.1:{server.server_port}');page.locator('#main h1').wait_for()
                result=journey(page,fixture)
                assert not errors,errors
                assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                rows.append(dict(result,viewport=[width,height],startup_build_id=server.service.build_id,
                                 js_errors=errors,horizontal_overflow=False))
                page.close()
            finally:
                server.shutdown();server.server_close();thread.join();fixture.doCleanups()
        browser.close()
    result=dict(status='PASS',scope='Actual isolated browser and synthetic provider responses; no live campaign',observations=rows)
    (ROOT/'.factory/tracking-sequence-browser.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':main()
