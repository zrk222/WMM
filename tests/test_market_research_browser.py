"""Real market-file controls, strict HTTP persistence and reports with synthetic data."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import unittest
from tests import test_agent_grants as fixture
from tests.test_market_research import intent_fixture as research_fixture

PROFILE=os.environ.get('WMM_BROWSER_TEST_PROFILE')=='1'
if PROFILE:
    from playwright.sync_api import sync_playwright, expect
ROOT=Path(__file__).resolve().parents[1]
ARTIFACTS=ROOT/'.factory/organic-video-automation/hypit/market-browser'


@unittest.skipUnless(PROFILE,'Run WMM_BROWSER_TEST_PROFILE=1 with declared browser dependencies')
class MarketResearchBrowserTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.GrantTests();self.f.setUp();self.addCleanup(self.f.tearDown)
        self.pw=sync_playwright().start();self.addCleanup(self.pw.stop)
        self.browser=self.pw.chromium.launch();self.addCleanup(self.browser.close)

    def run_journey(self,width):
        context=self.browser.new_context(viewport=dict(width=width,height=1000),accept_downloads=True)
        self.addCleanup(context.close)
        context.add_cookies([dict(name=c.name,value=c.value,domain='127.0.0.1',path=c.path or '/',httpOnly=True,sameSite='Lax') for c in self.f.owner.cookies])
        context.add_init_script("localStorage.setItem('growth-app','sample-one')")
        page=context.new_page();errors=[];external=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        def route(r):
            if r.request.url.startswith(self.f.origin+'/'):r.continue_()
            else:external.append(r.request.url);r.abort()
        context.route('**/*',route)
        page.goto(self.f.origin)
        page.wait_for_function("() => typeof state !== 'undefined' && state.workspace?.app?.id === 'sample-one'")
        nav=page.locator('[data-view="results"]')
        if not nav.is_visible():page.locator('details').filter(has=nav).locator('summary').first.click()
        nav.click();page.locator('[data-action="growth-research"]').click()
        file=page.locator('#market-research-file');button=page.locator('#growth-review-form button[type="submit"]')
        file.set_input_files(dict(name='invalid.json',mimeType='application/json',buffer=b'{'))
        button.click();expect(page.locator('#growth-form-error')).to_contain_text('Inputs are preserved')
        body=research_fixture()
        stamp=datetime.now(timezone.utc).isoformat()
        snapshot=body['data']['snapshot'];snapshot['observed_at']=stamp
        for source in snapshot['sources']:source['retrieved_at']=stamp
        raw=json.dumps(body['data']).encode()
        file.set_input_files(dict(name='synthetic-research.json',mimeType='application/json',buffer=raw))
        button.click();expect(page.locator('#market-research-preview')).to_contain_text('3 keyword phrases')
        expect(button).to_have_text('Save researched packet')
        ARTIFACTS.mkdir(parents=True,exist_ok=True)
        page.screenshot(path=str(ARTIFACTS/f'{width}-review.png'))
        dialog=page.locator('#modal').evaluate('(node)=>node.outerHTML')
        heading=page.locator('#main .page-heading').evaluate('(node)=>node.outerHTML')
        css=(ROOT/'mission_control/static/style.css').read_text(encoding='utf-8')
        (ARTIFACTS/f'{width}-review.html').write_text(f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>WMM research review</title><style>{css}</style></head><body><main>{heading}{dialog}</main></body></html>',encoding='utf-8')
        self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        # Duplicate source fields survive the client and are rejected by the strict decoder.
        duplicate=raw.replace(b'"release": "build-1"',b'"release":"build-1","release":"build-1"')
        file.set_input_files(dict(name='duplicate.json',mimeType='application/json',buffer=duplicate))
        button.click();button.click();expect(page.locator('#growth-form-error')).to_contain_text('Inputs are preserved')
        file.set_input_files(dict(name='synthetic-research.json',mimeType='application/json',buffer=raw))
        button.click()
        with page.expect_response(lambda r:'/subscription-growth/entries' in r.url and r.request.method=='POST') as response:
            button.click()
        self.assertEqual(response.value.status,201)
        page.wait_for_function("() => !document.querySelector('#modal').open")
        saved=self.f.owner.request('GET','/api/apps/sample-one/subscription-growth')['history']['history']
        self.assertEqual(len(saved),1)
        row=saved[0];self.assertEqual(row['kind'],'MARKET_RESEARCH')
        page.locator(f'[data-action="growth-detail"][data-id="{row["id"]}"]').click()
        expect(page.locator('#modal')).to_contain_text('hiking trails')
        expect(page.locator('#modal')).to_contain_text('search volume: Unknown')
        decision=page.locator('#modal .report-item').first
        expect(decision.get_by_role('heading',name='offline trip planning')).to_be_visible()
        expect(decision).to_contain_text('Review proposed test')
        expect(page.locator('#modal .report-item').nth(1)).to_contain_text('Distinct sources')
        page.locator('#modal summary').focus()
        page.keyboard.press('Enter')
        expect(page.get_by_role('heading',name='Source register')).to_be_visible()
        self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
        expect(page.locator('#modal')).to_contain_text('https://example.com/report')
        with page.expect_download() as download:page.locator('#modal [data-action="growth-json"]').click()
        report=json.loads(Path(download.value.path()).read_text(encoding='utf-8'))
        self.assertEqual(report['title'],'ASO opportunity report')
        self.assertEqual(report['filters']['source_hash'],row['hash'])
        self.assertEqual(report['sections'][0]['items'][0]['title'],'offline trip planning')
        trigger=page.locator('#modal [data-action="growth-report"]')
        trigger.click()
        preview=page.locator('.wmm-report-dialog[open]')
        expect(preview.get_by_role('heading',name='ASO opportunity report')).to_be_focused()
        expect(preview.get_by_role('heading',name='Marketing decisions')).to_be_visible()
        expect(preview.get_by_role('heading',name='Source register')).to_be_visible()
        self.assertIn('hiking trails',preview.inner_text())
        self.assertEqual(preview.locator('.report-section').first.locator('article').count(),3)
        page.emulate_media(media="print")
        expect(preview.locator('.report-controls')).to_be_hidden()
        expect(page.locator('#modal')).to_be_hidden()
        pdf=page.pdf(prefer_css_page_size=True)
        self.assertTrue(pdf.startswith(b'%PDF'))
        page.emulate_media(media="screen")
        if width==1440:
            (ARTIFACTS/'aso-opportunity-report-sample.pdf').write_bytes(pdf)
            css=(ROOT/'mission_control/static/page-reporting.css').read_text(encoding='utf-8')
            html=preview.evaluate('(node)=>node.innerHTML')
            (ARTIFACTS/'aso-opportunity-report.html').write_text(f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>ASO opportunity report</title><style>{css}</style></head><body class="wmm-print-report">{html}</body></html>',encoding='utf-8')
        preview.get_by_role('button',name='Close report').click()
        expect(trigger).to_be_focused()
        self.assertEqual(errors,[]);self.assertEqual(external,[])

    def test_desktop_import_review_persist_and_reports(self):self.run_journey(1440)
    def test_mobile_import_review_persist_and_reports(self):self.run_journey(390)
