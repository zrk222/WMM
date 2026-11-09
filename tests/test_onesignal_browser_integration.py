"""Browser through the real loopback owner gateway, synthetic vault/provider only."""
import os
import re
import unittest
from pathlib import Path
from unittest.mock import patch

BROWSER_PROFILE = os.environ.get('WMM_BROWSER_TEST_PROFILE') == '1'
if BROWSER_PROFILE:
    from playwright.sync_api import sync_playwright, expect
from mission_control.onesignal_setup import OneSignalSetup
from mission_control.operator_client import ClientError, OperatorClient
from tests import test_agent_grants as grants
from tests.test_measurement_connectors import FakeVault
from tests.test_onesignal_transport import APP, ORG, KEY

@unittest.skipUnless(BROWSER_PROFILE, 'Run the explicitly provisioned browser profile')
class OneSignalBrowserIntegration(unittest.TestCase):
    def test_owner_journey(self):
        with sync_playwright() as runner:
            browser=runner.chromium.launch(headless=True)
            try:
                for width in (390, 768, 1440):
                    fixture=grants.GrantTests();fixture.setUp();FakeVault.values={};calls=[]
                    apps=[{'id':APP,'name':'Synthetic grant app','organization_id':ORG}]
                    created='33333333-3333-4333-8333-333333333333'
                    def provider(action,key,app_id=None,fields=None,alive=lambda:None):
                        alive();calls.append((action,app_id))
                        if action=='list':return list(apps)
                        if action=='view':return next(a for a in apps if a['id']==app_id)
                        if action=='create':
                            uncertain=fields['name']=='Uncertain synthetic app'
                            value={'id':('44444444-4444-4444-8444-444444444444' if uncertain else created),'name':fields['name'],'organization_id':fields['organization_id']};apps.append(value)
                            if uncertain: raise OSError('Synthetic response lost')
                            return value
                        raise AssertionError('Unexpected provider action: '+action)
                    def setup(store,vault_factory=None):return OneSignalSetup(store,FakeVault,provider)
                    context=browser.new_context(viewport={'width':width,'height':900});unexpected=[];errors=[]
                    context.add_cookies([dict(name=c.name,value=c.value,url=fixture.origin,sameSite='Lax') for c in fixture.owner.cookies])
                    def local_only(route):
                        if route.request.url.startswith(fixture.origin+'/'):route.continue_()
                        else:unexpected.append(route.request.url);route.abort()
                    context.route('**/*',local_only)
                    try:
                        with patch('mission_control.onesignal_setup_http.OneSignalSetup',side_effect=setup):
                            page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
                            page.goto(fixture.origin);page.locator('#navigation summary').click();page.locator('#navigation [data-view="connections"]').click()
                            opener = page.locator('[data-action="onesignal-open"]')
                            opener.click();expect(page.locator('#onesignal-key-form')).to_be_visible()
                            expect(page.locator('#modal')).to_be_focused()
                            page.keyboard.press('Tab');expect(page.locator('#close-modal')).to_be_focused()
                            page.keyboard.press('Tab');expect(page.locator('#onesignal-key-form [name="kind"]')).to_be_focused()
                            page.keyboard.press('Tab');expect(page.locator('#onesignal-key-form [name="key"]')).to_be_focused()
                            page.keyboard.press('Tab');expect(page.locator('#onesignal-key-form button')).to_be_focused()
                            page.keyboard.press('Escape');expect(page.locator('#modal')).not_to_be_visible();expect(opener).to_be_focused()
                            opener.click();expect(page.locator('#onesignal-key-form')).to_be_visible()
                            out=Path(__file__).resolve().parents[1]/'.factory/onesignal-setup/browser';out.mkdir(parents=True,exist_ok=True)
                            page.screenshot(path=str(out/f'onesignal-loopback-{width}.png'))
                            if width==1440:
                                html=re.sub(r'<script\b[^>]*>.*?</script>','',page.content(),flags=re.S)
                                static=Path(__file__).resolve().parents[1]/'mission_control/static'
                                for name in ('style.css','page-reporting.css','video-editor.css','packaging.css'):
                                    html=html.replace(f'<link rel="stylesheet" href="/{name}">','<style>'+(static/name).read_text(encoding='utf-8')+'</style>')
                                (out/'onesignal-loopback.html').write_text(html,encoding='utf-8')
                            page.locator('[name="kind"]').select_option('org');page.locator('[name="key"]').fill(KEY)
                            page.locator('#onesignal-key-form button').click();expect(page.locator('#onesignal-read-form')).to_be_visible()
                            self.assertNotIn(KEY,page.locator('#onesignal-root').inner_text())
                            expect(page.locator('.onesignal-steps li')).to_have_count(3)
                            page.locator('#onesignal-read-form button').click();expect(page.locator('[data-action="onesignal-bind"]')).to_be_visible()
                            page.locator('[data-action="onesignal-bind"]').click();expect(page.locator('#onesignal-root')).to_contain_text('APP_BOUND')
                            expect(page.locator('#onesignal-root')).to_contain_text('SDK_BUILD_NOT_VERIFIED');expect(page.locator('#onesignal-root')).to_contain_text('DEVICE_SUBSCRIPTION_NOT_VERIFIED')
                            self.assertIn(('list',None),calls)
                            with self.assertRaises(ClientError):
                                fixture.owner.request('POST','/api/apps/sample-one/onesignal/bind',{'provider_app_id':APP,'expected_name':'Synthetic grant app','expected_org':ORG,'version':1})
                            with self.assertRaises(ClientError):
                                fixture.owner.request('POST','/api/apps/sample-two/onesignal/status',{})
                            anonymous=OperatorClient(fixture.origin);anonymous.bootstrap()
                            with self.assertRaises(ClientError):
                                anonymous.request('POST','/api/apps/sample-one/onesignal/status',{})
                            page.locator('#onesignal-create-options > summary').click()
                            page.locator('#onesignal-create-form [name="name"]').fill('New synthetic app')
                            page.locator('#onesignal-create-form [name="organization_id"]').fill(ORG)
                            page.locator('#onesignal-create-form button').click();expect(page.locator('[data-action="onesignal-execute"]')).to_be_visible()
                            self.assertFalse(any(a=='create' for a,_ in calls))
                            page.locator('[data-action="onesignal-execute"]').click()
                            expect(page.locator('#onesignal-root')).to_contain_text(created)
                            self.assertEqual(sum(a=='create' for a,_ in calls),1)
                            page.locator('#onesignal-create-options > summary').click()
                            page.locator('#onesignal-create-form [name="name"]').fill('Uncertain synthetic app')
                            page.locator('#onesignal-create-form [name="organization_id"]').fill(ORG)
                            page.locator('#onesignal-create-form button').click();expect(page.locator('[data-action="onesignal-execute"]')).to_be_visible()
                            page.locator('[data-action="onesignal-execute"]').click();expect(page.locator('#onesignal-recovery-form')).to_be_visible()
                            fixture.store.save_app('sample-one',dict(name='Changed synthetic app',release='build-2',locale='en-US',currency='USD'),1)
                            page.locator('#onesignal-recovery-form [name="provider_app_id"]').fill('44444444-4444-4444-8444-444444444444')
                            page.locator('#onesignal-recovery-form [name="key_kind"]').select_option('org')
                            page.locator('#onesignal-recovery-form [name="key"]').fill(KEY)
                            page.locator('#onesignal-recovery-form button').click();expect(page.locator('[data-action="onesignal-recovery-confirm"]')).to_be_visible()
                            expect(page.locator('#onesignal-root')).to_contain_text('App revision: 1 → 2')
                            self.assertNotIn(KEY,page.locator('#onesignal-root').inner_text())
                            page.locator('[data-action="onesignal-recovery-confirm"]').click();expect(page.locator('#onesignal-key-options > summary')).to_be_visible()
                            self.assertEqual(sum(a=='create' for a,_ in calls),2)
                            self.assertEqual(errors,[]);self.assertEqual(unexpected,[])
                    finally:context.close();fixture.tearDown();fixture.doCleanups()
            finally:browser.close()
