"""Synthetic browser interaction; all network is blocked."""
from datetime import datetime, timedelta
from pathlib import Path
import json
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
out = ROOT / '.factory' / 'campaign-paid-schedule-ui'
out.mkdir(parents=True, exist_ok=True)
with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    results = []
    for width in (1440, 390):
        context = browser.new_context(viewport={'width':width,'height':900})
        context.route('**/*', lambda route: route.fulfill(status=200, content_type='text/html',
            body='<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><main id="modal"></main></body></html>')
            if route.request.url == 'http://127.0.0.1:8765/' else route.abort())
        page = context.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto('http://127.0.0.1:8765/')
        page.add_style_tag(path=str(ROOT / 'mission_control/static/style.css'))
        page.evaluate("""() => {
          window.state={app:'sample',workspace:{app:{version:1},identity:{principal:'owner'}}};
          window.$=s=>document.querySelector(s);
          window.esc=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
          window.button=(label,action,attrs='',kind='')=>'<button type="button" class="button '+kind+'" data-action="'+action+'" '+attrs+'>'+label+'</button>';
          window.modal=(title,html)=>{document.querySelector('#modal').innerHTML='<h1>'+title+'</h1>'+html};
          window.WMMPageReports={model:()=>({}),openReport:r=>{window.savedReport=r}};
          window.calls=[];
          window.api=async(path,body)=>{window.calls.push({path,body});
            if(path.endsWith('/campaigns/status'))return window.fixtureCampaign;
            if(path.endsWith('schedule-prepare'))return {summary:{batch_id:'batch',items:body.items},summary_hash:'synthetic-hash'};
            if(path.endsWith('schedule-activate'))return {};
            if(path.endsWith('schedule-status')){window.scheduleReads=(window.scheduleReads||0)+1;return {id:'batch',status:'ACTIVE',version:2,summary:{items:[{item_id:'i',request:{lifetime_budget_minor:80,message:'PRIVATE COPY'}}]},items:[{item_id:'i',due_at:new Date().toISOString(),operation:'campaign.ad-launch',effective_status:window.scheduleReads>1?'PAUSED_VERIFIED':'NEEDS_RECONCILIATION',status:'QUEUED',job_status:'BLOCKED',intent:{status:'UNKNOWN',ids:{campaign:'123'},commitment:80,currency:'CAD'}}]};}
            throw Error('Unexpected request')};
          document.addEventListener('submit',e=>{e.preventDefault();campaignScheduleSubmit(e.target)});
          document.addEventListener('click',e=>{const b=e.target.closest('[data-action]');if(b)campaignScheduleAction(b)});
        }""")
        page.add_script_tag(path=str(ROOT / 'mission_control/static/campaign-execution.js'))
        page.evaluate("""async () => {
          const countries={countries:['CA']};const hash=await campaignHash(countries);
          const scope={scope_id:'scope',status:'ACTIVE',ad_account_id:'456',page_id:'123',currency:'CAD',expires_at:new Date(Date.now()+3600000).toISOString(),max_campaign_minor:100,max_total_minor:100,approved_targeting_hashes:[hash]};
          const post={scope_id:'scope',page_id:'123',status:'VERIFIED',remote_id:'123_777',content_hash:'c'.repeat(64),rights_hash:'b'.repeat(64)};
          window.fixtureCampaign={scope,intents:[post]};
          await campaignStatus('scope');
        }""")
        page.get_by_role('button',name='Schedule verified post promotion').click()
        form = page.locator('#campaign-schedule-form')
        expect(form.get_by_label('Verified Page post')).to_have_value('123_777')
        form.get_by_label('Verified Page post').focus()
        form.get_by_label('Verified Page post').press('Tab')
        expect(form.get_by_label('Audience country codes')).to_be_focused()
        form.get_by_label('Audience country codes').fill('CA')
        form.get_by_label('Media budget in minor units (CAD)').fill('80')
        form.get_by_label('Start local date and time').fill((datetime.now()+timedelta(minutes=5)).strftime('%Y-%m-%dT%H:%M'))
        form.get_by_label('End local date and time').fill((datetime.now()+timedelta(minutes=30)).strftime('%Y-%m-%dT%H:%M'))
        form.get_by_label('Campaign name').fill('Synthetic promotion')
        form.get_by_role('button',name='Review exact promotion').click()
        review = page.locator('#campaign-schedule-review')
        expect(review).to_contain_text('123_777')
        expect(review).to_contain_text('80 minor CAD')
        expect(review).to_contain_text('synthetic-hash')
        page.screenshot(path=str(out / f'paid-review-{width}.png'),full_page=True)
        (out / f'paid-review-{width}.html').write_text(page.content(), encoding='utf-8')
        review.get_by_role('button',name='Approve exact batch and schedule').click()
        progress = page.locator('#campaign-schedule-progress')
        expect(progress).to_contain_text('NEEDS_RECONCILIATION')
        expect(progress).to_contain_text('retained commitment 80')
        report_button = progress.get_by_role('button',name='Report / Save PDF')
        report_button.focus()
        expect(progress).to_contain_text('PAUSED_VERIFIED', timeout=12000)
        expect(report_button).to_be_focused()
        report_button.click()
        assert 'PRIVATE COPY' not in json.dumps(page.evaluate('window.savedReport'))
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
        assert not errors, errors
        calls = page.evaluate('window.calls')
        assert [x['path'].split('/')[-1] for x in calls] == ['status','schedule-prepare','schedule-activate','schedule-status','schedule-status']
        assert calls[1]['body']['items'][0]['operation'] == 'campaign.ad-launch'
        results.append({'width':width,'review':True,'progress':True,'keyboard_focus':True,'live_saved_stage':True,'report_redacted':True,'network':'blocked','js_errors':errors})
        context.close()
    browser.close()
print(json.dumps(results))
