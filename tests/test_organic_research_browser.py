"""Actual product controls with real owner HTTP and synthetic agent submissions."""
import json
import hashlib
import os
import platform
from datetime import datetime, timezone
from pathlib import Path
import unittest

from mission_control.db import connection
from tests import test_organic_research_http as fixture

BROWSER_PROFILE = os.environ.get('WMM_BROWSER_TEST_PROFILE') == '1'
if BROWSER_PROFILE:
    from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).parents[1]
ARTIFACTS = ROOT / '.factory/organic-video-automation/hypit/t15-browser'


@unittest.skipUnless(BROWSER_PROFILE, 'Run WMM_BROWSER_TEST_PROFILE=1 with the declared browser dependencies')
class OrganicResearchBrowserTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.ResearchHTTPTests()
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)
        self.playwright = sync_playwright().start()
        self.addCleanup(self.playwright.stop)
        self.browser = self.playwright.chromium.launch()
        self.addCleanup(self.browser.close)

    def page(self, width):
        context = self.browser.new_context(viewport=dict(width=width, height=1000), accept_downloads=True)
        self.addCleanup(context.close)
        context.add_cookies([dict(name=c.name, value=c.value, domain='127.0.0.1', path=c.path or '/', httpOnly=True, sameSite='Lax') for c in self.f.client.cookies])
        context.add_init_script("localStorage.setItem('growth-app','sample-one')")
        page = context.new_page()
        errors, external = [], []
        page.on('pageerror', lambda error: errors.append(str(error)))
        def boundary(route):
            if route.request.url.startswith(self.f.origin+'/'):
                route.continue_()
            else:
                external.append(route.request.url)
                route.abort()
        context.route('**/*', boundary)
        page.goto(self.f.origin)
        page.wait_for_function("() => typeof state !== 'undefined' && state.workspace?.app?.id === 'sample-one'")
        # Use the visible navigation and the actual product module, not a fixture UI.
        nav = page.locator('[data-view="research"]')
        if not nav.is_visible():
            page.locator('details').filter(has=nav).locator('summary').first.click()
        nav.click()
        page.locator('[data-action="oresearch-open"]').click()
        page.wait_for_selector('[data-action="oresearch-new"]')
        return context, page, errors, external

    def snapshot(self, page, width, stage):
        ARTIFACTS.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(ARTIFACTS / f'{width}-{stage}.png'), full_page=False)
        heading = page.locator('#main h1').evaluate('(node)=>node.outerHTML')
        dialog = page.locator('#modal').evaluate('(node)=>node.outerHTML')
        css = (ROOT/'mission_control/static/style.css').read_text(encoding='utf-8')
        html = f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>WMM synthetic research acceptance</title><style>{css}</style></head><body><main>{heading}{dialog}</main></body></html>'
        (ARTIFACTS / f'{width}-{stage}.html').write_text(html, encoding='utf-8')
        self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))

    def approval_and_reports(self, width):
        context, page, errors, external = self.page(width)
        self.snapshot(page, width, 'history')
        page.locator('[data-action="oresearch-read"]').first.click()
        page.wait_for_selector('[data-action="oresearch-adopt"]')
        self.assertIn('100000', page.locator('#modal').inner_text())
        page.locator('[data-action="oresearch-adopt"]').click()
        page.wait_for_function("() => document.querySelector('#oresearch-adopt-form') || document.querySelector('#oresearch-error')?.textContent")
        self.assertEqual(page.locator('#oresearch-error').inner_text(), '')
        fields = dict(title='Synthetic opening question', duration='30', hook_end='3', hook='An opening question',
                      mechanism='Curiosity followed by an app demonstration', rationale='The app rehearses this conversation',
                      requirements='Authentic app screen', experiment='Compare two original app openings', uncertainty='Reported counts; app sales unknown')
        for name, value in fields.items():
            page.locator(f'#oresearch-adopt-form [name="{name}"]').fill(value)
        for name, value in dict(industry='BUSINESS', narrative='APP_DEMO', treatment='TALKING_HEAD').items():
            page.select_option(f'#oresearch-adopt-form [name="{name}"]', value)
        proof = self.f.f.body['review']['card']['authentic_evidence_ids'][0]
        page.locator(f'[name="evidence"][value="{proof}"]').check()
        page.locator('[name="inspected"]').check()
        page.locator('[name="duration"]').fill('0')
        page.locator('#oresearch-adopt-form button[type="submit"]').click()
        expect(page.locator('[name="duration"]')).to_have_attribute('aria-invalid', 'true')
        page.locator('[name="duration"]').fill('30')
        self.assertIsNone(page.locator('[name="duration"]').get_attribute('aria-invalid'))
        self.snapshot(page, width, 'review-form')
        page.locator('#oresearch-adopt-form button[type="submit"]').click()
        page.wait_for_function("() => document.querySelector('[data-action=\"oresearch-confirm\"]') || document.querySelector('#oresearch-error')?.textContent")
        self.assertEqual(page.locator('#oresearch-error').inner_text(), '')
        self.assertIn('No production or publication is approved', page.locator('#modal').inner_text())
        page.locator('[data-action="oresearch-confirm"]').focus()
        page.keyboard.press('Enter')
        page.wait_for_selector('[data-action="oresearch-json"]')
        page.wait_for_function("() => document.querySelector('#modal').textContent.includes('Research card saved:')")
        self.snapshot(page, width, 'approved-research')
        with connection(self.f.store.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM organic_video_intakes').fetchone()[0], 1)
            jobs = db.execute('SELECT count(*) FROM jobs').fetchone()[0]
        self.assertEqual(jobs, 0)
        with page.expect_download() as captured:
            page.locator('[data-action="oresearch-json"]').click()
        download = captured.value
        report = json.loads(Path(download.path()).read_text(encoding='utf-8'))
        self.assertEqual(report['schema'], 'wmm.organic-research-report.v1')
        self.assertEqual(report['metrics'][1]['value'], 1)
        self.assertNotIn('token', json.dumps(report))
        with page.expect_popup() as report_window:
            page.locator('[data-action="oresearch-pdf"]').click()
        popup = report_window.value
        popup.wait_for_selector('#print-page-report')
        self.assertIn('no media reuse', popup.locator('body').inner_text())
        pdf = popup.pdf()
        self.assertTrue(pdf.startswith(b'%PDF'))
        popup.close()
        # Reopening reads the durable task and saved intake, without repeating adoption.
        page.locator('#modal [data-action="oresearch-open"]').click()
        page.locator('#modal [data-action="oresearch-read"]').first.click()
        page.wait_for_function("() => document.querySelector('#modal').textContent.includes('Research card saved:')")
        self.assertEqual(page.locator('[data-action="oresearch-adopt"]').count(), 0)
        page.keyboard.press('Escape')
        self.assertFalse(page.locator('#modal').evaluate('(node)=>node.open'))
        self.assertEqual(errors, [])
        self.assertEqual(external, [])
        sources = ['mission_control/static/organic-research.js','mission_control/static/app.js','mission_control/static/index.html',
                   'mission_control/static/style.css','mission_control/organic_video_collector.py','mission_control/organic_video_http.py','mission_control/server.py']
        (ARTIFACTS / f'{width}-receipt.json').write_text(json.dumps(dict(width=width, actual_owner_http=True,
            observed_at=datetime.now(timezone.utc).isoformat(), python=platform.python_version(), chromium=self.browser.version,
            source_hashes={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources},
            adopted_research=1, jobs=0, json_export=True, pdf_header=True, external_requests=external, page_errors=errors)), encoding='utf-8')

    def test_desktop_source_review_approval_and_exports(self):
        self.approval_and_reports(1440)

    def test_mobile_source_review_approval_and_exports(self):
        self.approval_and_reports(390)

    def assignment_with_lost_response(self, mode):
        context, page, errors, external = self.page(390)
        calls = []
        original_prepare = self.f.origin+'/api/apps/sample-one/organic-video/prepare'
        readbacks = []
        if mode == 'readback':
            def deny_readback_once(route):
                readbacks.append(True)
                if len(readbacks) == 1:
                    route.fulfill(status=403, content_type='application/json', body='{"error":"Readback identity needs refreshing"}')
                else:
                    route.continue_()
            context.route(self.f.origin+'/api/apps/sample-one/organic-video/task-read', deny_readback_once)
        def lose_once(route):
            calls.append(route.request.post_data_json)
            if len(calls) == 1 and mode != 'readback':
                route.fetch()  # Save reached the real server; the browser loses its response.
                route.abort()
            else:
                route.continue_()
        context.route(original_prepare, lose_once)
        page.locator('[data-action="oresearch-new"]').click()
        page.wait_for_selector('#oresearch-task-form')
        for name, value in dict(genre='Conversation practice', app_type='Coaching app', search_terms='conversation opening').items():
            page.locator(f'#oresearch-task-form [name="{name}"]').fill(value)
        page.locator('[name="platform"][value="tiktok"]').check()
        page.locator('#oresearch-task-form button[type="submit"]').click()
        page.wait_for_selector('[data-action="oresearch-confirm"]')
        page.locator('[data-action="oresearch-confirm"]').click()
        page.wait_for_selector('[data-action="oresearch-inspect"]')
        self.assertEqual(len(calls), 1)
        action = 'inspect' if mode == 'readback' else mode
        page.locator(f'[data-action="oresearch-{action}"]').click()
        page.wait_for_selector('[data-action="oresearch-json"]')
        self.assertIn('No collection has run yet', page.locator('#modal').inner_text())
        self.assertEqual(len(calls), 2 if mode == 'retry' else 1)
        if mode == 'retry':
            self.assertEqual(calls[0], calls[1])
        with connection(self.f.store.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM organic_discovery_tasks').fetchone()[0], 2)
        self.assertEqual(errors, [])
        self.assertEqual(external, [])

    def test_lost_assignment_response_is_inspected_without_retry(self):
        self.assignment_with_lost_response('inspect')

    def test_explicit_identical_assignment_retry_creates_no_duplicate(self):
        self.assignment_with_lost_response('retry')

    def test_acknowledged_save_with_denied_readback_retains_inspectable_request(self):
        self.assignment_with_lost_response('readback')

    def test_late_history_response_cannot_reopen_changed_context(self):
        _, page, errors, external = self.page(1440)
        page.keyboard.press('Escape')
        page.evaluate('''() => {
          const original=window.fetch.bind(window);
          window.fetch=(url,options)=>String(url).endsWith('/organic-video/task-list')
            ? new Promise(resolve=>{window.releaseResearch=()=>resolve(original(url,options))}) : original(url,options);
        }''')
        page.locator('[data-action="oresearch-open"]').click()
        page.wait_for_function('() => typeof releaseResearch === "function"')
        page.evaluate('''() => {state.workspace.access.members.find(x=>x.principal===state.workspace.identity.principal).status='REVOKED'; WMMOrganicResearch.invalidate(state); releaseResearch();}''')
        page.wait_for_load_state('networkidle')
        self.assertFalse(page.locator('#modal').evaluate('(node)=>node.open'))
        self.assertEqual(page.locator('#modal-body').inner_text(), '')
        self.assertEqual(errors, [])
        self.assertEqual(external, [])


if __name__ == '__main__':
    unittest.main()
