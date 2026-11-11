"""Synthetic desktop and mobile owner browser acceptance for campaign attribution."""
from datetime import datetime, timedelta
import os
import unittest

from tests import test_observational_campaign_transport as fixtures
from tests.test_verified_review import OWNER_TOKEN


@unittest.skipUnless(os.environ.get('WMM_BROWSER_TEST_PROFILE') == '1', 'Enable the WMM browser test profile')
class ObservationalCampaignBrowserTests(unittest.TestCase):
    def setUp(self):
        from playwright.sync_api import sync_playwright

        self.fixture = fixtures.ObservationalCampaignTransportTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        playwright = sync_playwright().start()
        self.addCleanup(playwright.stop)
        self.browser = playwright.chromium.launch()
        self.addCleanup(self.browser.close)

    def test_private_study_and_report(self):
        for width in (1440, 390):
            with self.subTest(width=width):
                self.exercise_study(width)

    def exercise_study(self, width):
        from playwright.sync_api import expect

        page = self.browser.new_page(viewport=dict(width=width, height=900))
        self.addCleanup(page.close)
        errors=[]
        page.on('pageerror',lambda error: errors.append(str(error)))
        page.goto(self.fixture.fixture.origin)
        expect(page.locator('#app-select')).to_have_value('sample-one')
        page.locator('#navigation > [data-view=activity]').click()
        page.get_by_role('button',name='Sign in for verified review',exact=True).click()
        page.get_by_label('GitHub identity token',exact=True).fill(OWNER_TOKEN)
        page.get_by_role('button',name='Verify my identity',exact=True).click()
        expect(page.get_by_role('button',name='Sign out of review session')).to_be_visible()
        page.locator('#navigation > [data-view=overview]').click()
        page.locator('#goal-advanced > summary').click()
        page.get_by_role('button',name='Measure one organic post',exact=True).click()
        page.get_by_text('Register a study',exact=True).click()
        page.get_by_label('Study name').fill(f'Synthetic {width}')
        page.get_by_label('What will you learn?').fill('Observe tagged registrations')
        page.get_by_label('Creative reference').fill('synthetic-reel')
        start=datetime.now()+timedelta(hours=2)
        page.get_by_label('Starts (local time)').fill(start.strftime('%Y-%m-%dT%H:%M'))
        page.get_by_label('Ends (local time)').fill((start+timedelta(days=1)).strftime('%Y-%m-%dT%H:%M'))
        page.get_by_label('Collector source ID').fill('synthetic-collector')
        page.get_by_label('Landing event in your source').fill('page_view')
        page.get_by_label('Registration event in your source').fill('registration_completed')
        page.get_by_role('button',name='Save study').click()
        page.get_by_role('button',name='Preview tagged link').click()
        expect(page.locator('#observational-campaign-receipt')).to_contain_text('utm_campaign=')
        page.get_by_role('button',name='Read results').click()
        expect(page.get_by_role('status').filter(has_text='Linked registrations')).to_contain_text('Unavailable')
        with page.expect_popup() as pdf:
         page.get_by_role('button',name='Save private report as PDF').click()
        expect(pdf.value.get_by_role('heading',name='Organic campaign attribution')).to_be_visible()
        expect(pdf.value.locator('body')).to_contain_text('Source hash')
        expect(pdf.value.locator('body')).to_contain_text('Still collecting')
        expect(pdf.value.locator('body')).to_contain_text('After the fixed window ends')
        pdf.value.close()
        page.evaluate("() => { window.open = () => { document.activeElement.blur(); return null; }; window.print = () => { window.reportPrinted = true; }; }")
        button = page.get_by_role('button', name='Save private report as PDF')
        button.click()
        report = page.get_by_role('dialog', name='Organic campaign attribution')
        expect(report).to_be_visible()
        expect(report).to_contain_text('Source hash')
        expect(report.get_by_role('heading', level=1)).to_be_focused()
        report.get_by_role('button', name='Print / Save as PDF').click()
        assert page.evaluate('window.reportPrinted')
        page.emulate_media(media='print')
        assert page.locator('body > :not(.wmm-report-dialog)').evaluate_all(
            "(elements) => elements.every(el => getComputedStyle(el).display === 'none')")
        expect(report.get_by_role('button', name='Print / Save as PDF')).to_be_hidden()
        assert page.pdf().startswith(b'%PDF')
        page.emulate_media(media='screen')
        page.keyboard.press('Escape')
        expect(report).to_have_count(0)
        expect(button).to_be_focused()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.keyboard.press('Escape')
        history_offsets=[]
        def older_study(route):
            offset=route.request.post_data_json['offset']
            history_offsets.append(offset)
            if offset==0:
                route.fulfill(json={'offset':0,'limit':100,'records':[{'kind':'INGESTED'}]*100})
            else:
                route.fulfill(response=route.fetch(post_data={'offset':0}))
        page.route('**/observational-campaign/history',older_study)
        page.locator('[data-action="first-post-open"]').click()
        expect(page.get_by_text('No current study registrations on this page.')).to_be_visible()
        page.get_by_role('button',name='Older activity').click()
        study = page.get_by_label('Registered study')
        expect(page.get_by_role('button',name='Newer activity')).to_be_visible()
        assert history_offsets==[0,100],history_offsets
        expect(study.locator('option').nth(1)).to_be_attached()
        selected = study.locator('option').nth(1).inner_text()
        study.select_option(index=1)
        expect(page.get_by_label('Exact tagged link')).to_have_value(
            __import__('re').compile('utm_campaign=' + selected))
        expect(page.locator('#first-post-progress')).to_contain_text('destination')
        expect(page.get_by_role('region',name='Study measurement checkpoint')).to_contain_text('Still collecting')
        expect(page.get_by_role('button',name='Save study report as PDF')).to_be_visible()
        page.get_by_role('button',name='Import installs for this study').click()
        expect(page.get_by_label('Campaign token')).to_have_value(selected)
        assert page.get_by_label('Campaign token').get_attribute('readonly') is not None
        assert page.get_by_label('Window start (UTC ISO)').input_value()
        assert page.get_by_label('Window end (UTC ISO)').input_value()
        expect(page.get_by_label('Source coverage is complete')).not_to_be_checked()
        assert not errors,errors
