"""Real desktop and mobile owner journey; every provider is a local fixture."""
import json,os,unittest
from pathlib import Path
from mission_control.common import digest
from mission_control.db import connection
from tests import test_publication_server as server_fixture
APP=server_fixture.APP
ROOT=Path(__file__).resolve().parents[1]
ARTIFACTS=ROOT/'.factory/multichannel/browser'
PROFILE=os.environ.get('WMM_BROWSER_TEST_PROFILE')=='1'
if PROFILE:
 from playwright.sync_api import sync_playwright,expect

@unittest.skipUnless(PROFILE,'Use the provisioned browser profile')
class PublicationBrowserTests(unittest.TestCase):
 def setUp(self):
  self.fixture=server_fixture.PublicationServerTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
  self.playwright=sync_playwright().start();self.addCleanup(self.playwright.stop)
  executable=os.environ.get('WMM_BROWSER_EXECUTABLE');self.browser=self.playwright.chromium.launch(**({'executable_path':executable} if executable else {}));self.addCleanup(self.browser.close)
 def journey(self,width):
  context=self.browser.new_context(viewport={'width':width,'height':900});self.addCleanup(context.close)
  context.add_cookies([dict(name=c.name,value=c.value,domain='127.0.0.1',path=c.path or '/',httpOnly=True) for c in self.fixture.owner.cookies])
  context.add_init_script("localStorage.setItem('growth-app',"+json.dumps(APP)+")")
  page=context.new_page();page.set_default_timeout(10000);errors=[];external=[]
  page.on('pageerror',lambda error:errors.append(str(error)))
  def guard(route):
   if route.request.url.startswith(self.fixture.origin+'/'):route.continue_()
   else:external.append(route.request.url);route.abort()
  context.route('**/*',guard);page.goto(self.fixture.origin)
  page.wait_for_function("() => typeof state !== 'undefined' && state.workspace?.app?.id === "+json.dumps(APP))
  self.goal_connections(page,width)
  nav=page.locator('[data-view="connections"]')
  if not nav.is_visible():page.locator('details').filter(has=nav).locator('summary').first.click()
  nav.click();page.locator('[data-action="publication-load"]').click()
  form=page.locator('#publication-draft-form');expect(form).to_be_visible()
  form.locator('[name=provider]').select_option('linkedin')
  form.locator('[name=kind]').select_option('linkedin_text')
  form.locator('[name=connection_id]').select_option(self.fixture.f.connection)
  form.locator('[name=visibility]').select_option('PUBLIC')
  form.locator('[name=caption]').fill('Synthetic owner review')
  form.locator('button[type=submit]').click()
  approval=page.locator('#publication-approval-form');expect(approval).to_be_visible()
  expect(approval).to_contain_text('Synthetic member');expect(approval).to_contain_text('profile1');expect(approval).to_contain_text('Synthetic owner review')
  self.snapshot(page,width,'review',approval)
  approval.locator('[name=confirm_publish]').check();approval.locator('[name=confirm_rights]').check()
  approval_id=approval.get_attribute('data-id')
  button=approval.locator('button[value=approve]');button.focus();self.assertTrue(button.evaluate('(e)=>document.activeElement===e'));button.press('Enter')
  expect(page.locator('[data-action="publication-execute"]')).to_be_visible()
  with connection(self.fixture.store.path) as db:self.assertEqual(db.execute("SELECT count(*) FROM jobs WHERE action='social_publication'").fetchone()[0],0)
  self.snapshot(page,width,'panel',page.locator('.publication-panel'))
  self.report_exports(page,approval_id)
  self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'))
  with page.expect_response(lambda response: response.url.endswith('/publications/execute')) as queued:
   page.locator('[data-action="publication-execute"]').click()
  self.assertEqual(queued.value.status,200);expect(page.locator('.publication-records')).to_contain_text('Queue state: QUEUED')
  expect(page.locator('.publication-records')).to_contain_text('Worker: QUEUED');expect(page.locator('.publication-records')).to_contain_text('Provider phase: NOT STARTED')
  expect(page.locator('[data-action="publication-revoke"]')).to_be_visible()
  with connection(self.fixture.store.path) as db:self.assertEqual(db.execute("SELECT status FROM jobs WHERE action='social_publication'").fetchone()[0],'QUEUED')
  with page.expect_response(lambda response: response.url.endswith('/revoke')) as revoked:
   page.locator('[data-action="publication-revoke"]').click()
  self.assertEqual(revoked.value.status,200);expect(page.locator('.publication-records')).to_contain_text('REVOKED')
  with connection(self.fixture.store.path) as db:self.assertEqual(db.execute("SELECT status FROM jobs WHERE action='social_publication'").fetchone()[0],'CANCELLED')
  self.assertTrue(page.evaluate('document.documentElement.scrollWidth <= innerWidth'));self.assertEqual(errors,[]);self.assertEqual(external,[])
 def goal_connections(self,page,width):
  """Actual goal-first selection reaches organic publication without creating authority."""
  page.locator('[data-action="goal-select"][data-goal="campaign"]').click()
  expect(page.get_by_role('region',name='Your selected goal')).to_contain_text('Synthetic member')
  page.locator('[data-action="goal-readiness"]').click()
  page.locator('[data-action="goal-repair"][data-tool="standing-readiness"]').click()
  form=page.locator('#goal-readiness-form');expect(form).to_be_visible()
  for name in ('Instagram','TikTok','YouTube Shorts','LinkedIn'):expect(form).to_contain_text(name)
  organic=form.locator('[name=workflows][value=organic_publication]');expect(organic).not_to_be_checked()
  form.locator('[name=agent_id]').fill('synthetic-marketing-agent')
  form.locator('[name=workflows][value=social_publish]').uncheck();organic.check()
  form.locator('[name=social_connection_ids]').check()
  form.locator('[type=submit]').click()
  body=page.locator('#modal-body');expect(body).to_contain_text('No approval, grant, job or campaign')
  expect(body).to_contain_text('Review the exact post')
  self.snapshot(page,width,'goal-readiness',body)
  with connection(self.fixture.store.path) as db:
   self.assertEqual(db.execute("SELECT count(*) FROM jobs WHERE action='social_publication'").fetchone()[0],0)
  self.assertEqual(self.fixture.owner.request('GET',self.fixture.base)['authorities'],[])
  body.get_by_role('button',name='Review organic publication',exact=True).press('Enter')
  expect(page.get_by_role('heading',name='Organic publishing',exact=True)).to_be_focused()
  page.keyboard.press('Tab')
  expect(page.get_by_role('button',name='Load publishing options',exact=True)).to_be_focused()
  self.assertEqual(self.fixture.owner.request('GET',self.fixture.base)['authorities'],[])
  page.locator('[data-action="social-setup"][data-provider="youtube"]').click()
  setup=page.locator('#social-setup-form');expect(setup).to_be_visible()
  expect(setup).to_contain_text('Google');expect(setup.locator('[name=campaign_access]')).to_have_value('read')
  self.snapshot(page,width,'youtube-setup',setup);page.keyboard.press('Escape')
  expect(setup).to_be_hidden()
 def snapshot(self,page,width,name,node):
  """Retain bounded synthetic panel/review evidence for CI visual audits."""
  ARTIFACTS.mkdir(parents=True,exist_ok=True)
  image=ARTIFACTS/f'{width}-{name}.png';node.screenshot(path=str(image),animations='disabled')
  self.assertLess(image.stat().st_size,4_000_000)
  markup=node.evaluate('(element)=>element.outerHTML')
  css='\n'.join((ROOT/'mission_control/static'/file).read_text(encoding='utf-8') for file in ('style.css','page-reporting.css','video-editor.css','packaging.css'))
  html=f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Synthetic publication {name}</title><style>{css}</style></head><body>{markup}</body></html>'
  target=ARTIFACTS/f'{width}-{name}.html';target.write_text(html,encoding='utf-8');self.assertLess(target.stat().st_size,2_000_000)
 def report_exports(self,page,approval_id):
  """Downloaded JSON and printable output must identify the approved channel."""
  selector=f'[data-action="publication-report-json"][data-id="{approval_id}"]'
  trigger=page.locator(selector);trigger.focus();self.assertTrue(trigger.evaluate('(e)=>document.activeElement===e'))
  with page.expect_download() as downloaded:trigger.press('Enter')
  report=json.loads(Path(downloaded.value.path()).read_text(encoding='utf-8'))
  self.assertEqual(report['id'],approval_id);self.assertEqual(report['report']['approval']['id'],approval_id)
  channel=report['report']['channel'];self.assertEqual(channel['provider'],'linkedin');self.assertEqual(channel['destination_id'],'profile1')
  self.assertEqual(report['report']['channel_hash'],digest(channel))
  self.assertEqual(report['report']['latest_metric_sample']['reason'],'NO_PROVIDER_READ_RECORDED')
  with page.expect_popup() as captured:
   page.locator(f'[data-action="publication-report-pdf"][data-id="{approval_id}"]').click()
  popup=captured.value;popup.wait_for_selector('#print-page-report')
  self.assertIn(approval_id,popup.locator('body').inner_text());self.assertIn(report['report']['channel_hash'],popup.locator('body').inner_text())
  self.assertIn('No provider read has been saved.',popup.locator('body').inner_text())
  self.assertTrue(popup.pdf().startswith(b'%PDF'));popup.close()
 def test_desktop(self):self.journey(1440)
 def test_mobile(self):self.journey(390)

if __name__=='__main__':unittest.main()
