"""Real desktop/mobile browser controls against an isolated WMM HTTP server.

Identity and provider responses are synthetic; this never accesses a real account.
"""
from pathlib import Path
import json
import sys
from unittest.mock import patch
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Standalone tool: resolve this checkout before importing its application/fixtures.
from mission_control.apple_metrics_schedule import AppleMetricsSchedules  # noqa: E402
from mission_control.common import now  # noqa: E402
from mission_control.worker import run_once  # noqa: E402
from tests.test_apple_metrics_http_route import AppleMetricsRouteTests  # noqa: E402

OUT = ROOT / '.factory/apple-analytics-ui/browser'


def journey(browser, width, height):
    fixture = AppleMetricsRouteTests('test_owner_can_queue_observe_and_pause_without_provider_calls')
    fixture.setUp()
    origin = 'http://127.0.0.1:' + str(fixture.server.server_port)
    context = browser.new_context(viewport={'width': width, 'height': height})
    # The complete application runs; external requests are forbidden.
    context.route('**/*', lambda route: route.continue_()
                  if route.request.url.startswith(origin + '/') else route.abort())
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    try:
        page.goto(origin)
        page.locator('#main h1').wait_for()
        page.locator('#app-select').select_option('sample-one')
        page.get_by_text('Advanced tools', exact=True).click()
        page.locator('[data-view="connections"]').click()
        page.locator('[data-action="apple-analytics-open"]').click()
        dialog = page.locator('#modal')
        expect(dialog).to_contain_text('Sign in with the app owner account')
        dialog.get_by_role('button', name='Sign in', exact=True).click()
        page.locator('#identity-token').fill('synthetic_owner_identity_token')
        dialog.get_by_role('button', name='Verify my identity', exact=True).click()
        expect(dialog).not_to_be_visible()
        page.wait_for_function("() => state.workspace?.identity?.status === 'AUTHENTICATED'")
        page.locator('[data-action="apple-analytics-open"]').click()
        root = page.locator('#apple-analytics-root')
        expect(root).to_contain_text('No saved refresh schedule')
        expect(root).to_contain_text('No current report inventory')
        root.get_by_role('button', name='Read Apple inventory', exact=True).click()
        expect(root.locator('#apple-analytics-status')).to_contain_text('Inventory queued')
        result = dict(provider='app_store', operation='analytics_reports', app_id='sample-one',
                      store_app_id='123', status='WAITING_FOR_REPORTS', coverage='COMPLETE',
                      observed_at=now(), reports=[dict(id='report-1', name='App Downloads Standard',
                                                     coverage='COMPLETE', instances=[])])
        with patch('mission_control.worker.read_report', return_value=result) as provider:
            assert run_once(fixture.store)
            provider.assert_called_once()
        root.get_by_role('button', name='Refresh saved status', exact=True).click()
        expect(root).to_contain_text('0 report instances')
        expect(root).to_contain_text('Missing metrics remain unknown')
        form = root.locator('#apple-analytics-form')
        expect(form.get_by_label('Report', exact=True)).to_have_value('report-1')
        form.get_by_label('Report', exact=True).focus()
        page.keyboard.press('Tab')
        expect(form.get_by_label('Refresh every (hours)', exact=True)).to_be_focused()
        form.get_by_label('Refresh every (hours)', exact=True).fill('48')
        form.get_by_role('button', name='Enable refresh', exact=True).click()
        expect(root).to_contain_text('ENABLED')
        saved = AppleMetricsSchedules(fixture.store).get('sample-one')
        assert saved['enabled'] and saved['interval_hours'] == 48
        assert saved['last_success'] is None
        # A queued read and saved schedule are not fabricated numeric evidence.
        expect(root).to_contain_text('Last success: Not recorded')
        assert root.evaluate('(node) => node.scrollWidth <= node.clientWidth + 1')
        page.locator('#modal').screenshot(path=str(OUT / f'analytics-{width}.png'))
        rendered = page.evaluate(r'''() => {
          const styles=Array.from(document.styleSheets).flatMap(sheet=>{
            try{return Array.from(sheet.cssRules).map(rule=>rule.cssText)}catch{return []}
          }).join('\n');
          const snapshot=document.documentElement.cloneNode(true);
          snapshot.querySelectorAll('script,link[rel="stylesheet"]').forEach(node=>node.remove());
          const style=document.createElement('style');style.textContent=styles;
          snapshot.querySelector('head').append(style);
          return '<!doctype html>'+snapshot.outerHTML;
        }''')
        (OUT / f'analytics-{width}.html').write_text(rendered, encoding='utf-8')
        root.get_by_role('button', name='Pause refresh', exact=True).focus()
        page.keyboard.press('Enter')
        expect(root).to_contain_text('PAUSED')
        assert AppleMetricsSchedules(fixture.store).get('sample-one')['enabled'] is False
        # Report uses actual inventory counts and its caveats, not synthetic app metrics.
        reports = []
        page.on('popup', lambda popup: reports.append(popup))
        root.get_by_role('button', name='Report / Save PDF', exact=True).click()
        page.wait_for_timeout(200)
        assert reports, 'Report action did not open its printable report'
        report = reports[-1]
        report.wait_for_load_state()
        expect(report.locator('body')).to_contain_text('Apple analytics inventory')
        expect(report.locator('body')).to_contain_text('unavailable measurements remain unknown')
        report.close()
        page.locator('#close-modal').click()
        # An app switch must not retain another app's owner/source controls.
        page.locator('#app-select').select_option('sample-two')
        page.locator('[data-action="apple-analytics-open"]').click()
        expect(root).to_contain_text('requires the current app owner')
        expect(root.locator('#apple-analytics-form')).to_have_count(0)
        assert not errors, errors
        return dict(width=width, height=height, status='PASS', keyboard='VERIFIED',
                    inventory='SYNTHETIC_HTTP_VERIFIED', schedule_save_pause='VERIFIED',
                    pdf_report='PRINTABLE_REPORT_VERIFIED', app_isolation='VERIFIED',
                    overflow=False, page_errors=errors)
    except Exception:
        # Synthetic-only diagnostics; retain the first failed browser state.
        target = OUT / f'first-failure-{width}.html'
        if not target.exists():
            target.write_text(page.content(), encoding='utf-8')
        raise
    finally:
        context.close()
        fixture.doCleanups()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as runtime:
        browser = runtime.chromium.launch()
        try:
            observations = [journey(browser, width, height)
                            for width, height in ((1440, 900), (390, 844))]
            result = dict(status='PASS', browser=browser.version, observations=observations,
                          data='DISPOSABLE_SYNTHETIC', live_provider_execution='NOT_RUN')
            (OUT / 'observations.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
            print(json.dumps(result))
        finally:
            browser.close()


if __name__ == '__main__':
    main()
