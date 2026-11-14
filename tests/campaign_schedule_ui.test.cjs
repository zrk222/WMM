const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('./helpers/module-source.cjs'),vm=require('node:vm'),path=require('node:path'),{webcrypto}=require('node:crypto');
const src=fs.readFileSync(path.join(__dirname,'../mission_control/static/campaign-execution.mjs'),'utf8');
function fixture(){
 const calls=[],panels={},modals=[];
 const c={Date,TextEncoder,Uint8Array,crypto:webcrypto,FormData:class {constructor(form){return Object.entries(form.values||{})}},state:{app:'one',workspace:{app:{version:1},identity:{principal:'owner'}}},document:{},$:s=>panels[s]||null,esc:s=>String(s).replaceAll('<','&lt;'),button:(label,action)=>'<button data-action="'+action+'">'+label+'</button>',modal:(title,html)=>{modals.push({title,html});panels['#campaign-schedule-review']={dataset:{app:'one',version:'1',principal:'owner'},isConnected:true}},api:async(...a)=>calls.push(a),WMMPageReports:{model:()=>({}),openReport:x=>x},window:{}};
 vm.createContext(c);vm.runInContext(src,c);return {c,calls,panels,modals};
}
const scope={scope_id:'scope',status:'ACTIVE',ad_account_id:'456',page_id:'123',currency:'CAD',expires_at:'2026-11-02T14:00:00Z',max_campaign_minor:100,max_total_minor:100,approved_targeting_hashes:['approved']};
const post={scope_id:'scope',page_id:'123',status:'VERIFIED',remote_id:'123_777',content_hash:'c'.repeat(64),rights_hash:'r'.repeat(64)};
const values={due_at:'2026-11-02T12:30:00Z',end_time:'2026-11-02T13:30:00Z',countries:'US, CA',budget:'80',name:'Approved promotion'};
const clock=Date.parse('2026-11-02T12:00:00Z');
test('scheduled post times remain finite and within scope',()=>{const h=fixture(),p={request_id:'fixed'};const result=h.c.campaignScheduleItems([p],{due_0:values.due_at},scope.expires_at,clock);assert.equal(result[0].request,p);for(const due of ['bad','2026-11-02T11:00:00Z',scope.expires_at])assert.throws(()=>h.c.campaignScheduleItems([p],{due_0:due},scope.expires_at,clock));assert.throws(()=>h.c.campaignScheduleItems(Array(21).fill(p),{},scope.expires_at));});
test('paid item uses the exact verified post, targeting, dates and finite commitment',()=>{const h=fixture(),item=h.c.campaignPaidScheduleItem(scope,post,values,'approved','request-id',clock);assert.equal(item.operation,'campaign.ad-launch');assert.equal(item.request.post_id,'123_777');assert.equal(item.request.lifetime_budget_minor,80);assert.deepEqual(Array.from(item.request.targeting.countries),['CA','US']);assert.equal(item.request.targeting_hash,'approved');assert.equal(item.request.end_time,'2026-11-02T13:30:00.000Z');});
test('paid validation rejects missing or foreign post, changed audience, budget and dates',()=>{const h=fixture(),run=(s,p,v,hash='approved')=>h.c.campaignPaidScheduleItem(s,p,v,hash,'id',clock);for(const p of [null,{...post,status:'UNKNOWN'},{...post,scope_id:'foreign'},{...post,page_id:'foreign'}])assert.throws(()=>run(scope,p,values));for(const v of [{...values,budget:'101'},{...values,budget:'0'},{...values,countries:'CA, CA'},{...values,end_time:scope.expires_at.replace('14:00','15:00')},{...values,due_at:'2026-11-02T11:00:00Z'}])assert.throws(()=>run(scope,post,v));assert.throws(()=>run(scope,post,values,'unapproved'));assert.equal(h.calls.length,0);});
test('verified selector excludes other scopes and unconfirmed records',()=>{const h=fixture(),items=h.c.campaignVerifiedPosts({scope,intents:[post,{...post,scope_id:'foreign'},{...post,status:'UNKNOWN'},{...post,kind:'AD'}]});assert.equal(items.length,1);assert.equal(items[0].remote_id,'123_777');});
test('review shows owner selected exact paid terms and escapes content',()=>{const h=fixture(),item=h.c.campaignPaidScheduleItem(scope,post,{...values,name:'<safe>'},'approved','id',clock),html=h.c.campaignScheduleReviewItem(item,scope);for(const x of ['123_777','CA, US','80','2026-11-02T12:30','2026-11-02T13:30','&lt;safe>'])assert.ok(html.includes(x));});
test('stale app, version, owner and detached modal cannot continue',()=>{const h=fixture(),panel={dataset:{app:'one',version:'1',principal:'owner'},isConnected:true};h.c.campaignBound(panel);for(const change of ['app','version','principal','detached']){const p={...panel,dataset:{...panel.dataset}};if(change==='app')p.dataset.app='other';if(change==='version')p.dataset.version='2';if(change==='principal')p.dataset.principal='other';if(change==='detached')p.isConnected=false;assert.throws(()=>h.c.campaignBound(p));}});
test('paid progress and report show saved IDs, commitment and no creative prose',()=>{const h=fixture(),data={items:[{item_id:'i',operation:'campaign.ad-launch',due_at:values.due_at,effective_status:'NEEDS_RECONCILIATION',status:'QUEUED',intent:{status:'UNKNOWN',ids:{campaign:'123',adset:'bad<script>'},commitment:80,currency:'CAD'}}],summary:{items:[{item_id:'i',request:{lifetime_budget_minor:80,message:'SECRET COPY',rights_prose:'SECRET RIGHTS'}}]}};const html=h.c.campaignScheduleProgressItem(data.items[0],data),report=h.c.campaignScheduleReport(data),text=JSON.stringify(report);assert.match(html,/NEEDS_RECONCILIATION/);assert.match(html,/retained commitment 80/);assert.match(text,/campaign: 123/);assert.match(text,/retained 80/);assert.doesNotMatch(text,/SECRET COPY|SECRET RIGHTS|bad<script>/);});
test('detached modal after delayed preparation never opens approval',async()=>{const h=fixture();let resolve;h.c.api=()=>new Promise(r=>resolve=r);const submit={disabled:false},form={dataset:{app:'one',version:'1',principal:'owner'},isConnected:true,querySelector:()=>submit,campaign:{scope,posts:[post]},values:{due_0:new Date(Date.now()+10000).toISOString()}};form.campaign.scope={...scope,expires_at:new Date(Date.now()+60000).toISOString()};const promise=h.c.campaignScheduleSubmit(form);assert.equal(submit.disabled,true);form.isConnected=false;resolve({summary:{items:[]},summary_hash:'x'});await promise;assert.equal(h.modals.length,0);});
test('duplicate schedule submit is suppressed during in-flight preparation',async()=>{const h=fixture();let resolve,n=0;h.c.api=()=>{n++;return new Promise(r=>resolve=r)};const submit={disabled:false},form={dataset:{app:'one',version:'1',principal:'owner'},isConnected:true,querySelector:()=>submit,campaign:{scope:{...scope,expires_at:new Date(Date.now()+60000).toISOString()},posts:[post]},values:{due_0:new Date(Date.now()+10000).toISOString()}};const first=h.c.campaignScheduleSubmit(form);await h.c.campaignScheduleSubmit(form);assert.equal(n,1);form.isConnected=false;resolve({summary:{items:[]},summary_hash:'x'});await first;});
test('paid modal closure while hashing blocks preparation',async()=>{const h=fixture();let resolve;h.c.campaignHash=()=>new Promise(r=>resolve=r);const submit={disabled:false},form={dataset:{app:'one',version:'1',principal:'owner'},isConnected:true,querySelector:()=>submit,campaign:{scope:{...scope,expires_at:new Date(Date.now()+60000).toISOString()}},paidPosts:[post],requestID:'id',values:{post_id:post.remote_id,countries:'CA',budget:'80',name:'Test',due_at:new Date(Date.now()+10000).toISOString(),end_time:new Date(Date.now()+30000).toISOString()}};const pending=h.c.campaignScheduleSubmit(form);form.isConnected=false;resolve('approved');await pending;assert.equal(h.calls.length,0);assert.equal(h.modals.length,0);});
test('status response after owner or modal changes does not open stale progress',async()=>{const h=fixture();let resolve;h.c.api=()=>new Promise(r=>resolve=r);const source={isConnected:true};const pending=h.c.campaignScheduleStatus('batch',source);h.c.state.workspace.identity.principal='other';resolve({});await pending;assert.equal(h.modals.length,0);});

test('late schedule status cannot reopen an abandoned weekly interaction', async () => {
  const h = fixture();
  let resolve;
  let current = true;
  h.c.api = () => new Promise((done) => { resolve = done; });
  const pending = h.c.campaignScheduleStatus('batch', null, () => current);
  current = false;
  resolve({});
  await pending;
  assert.equal(h.modals.length, 0);
});
test('duplicate activation is suppressed while request is pending',async()=>{const h=fixture();let resolve,n=0;h.c.api=()=>{n++;return new Promise(r=>resolve=r)};const panel={dataset:{app:'one',version:'1',principal:'owner'},isConnected:true,campaign:{summary:{batch_id:'batch'},summary_hash:'hash'},querySelector:()=>({textContent:''})};h.panels['#campaign-schedule-review']=panel;const node={dataset:{action:'campaign-schedule-activate'},disabled:false};const pending=h.c.campaignScheduleAction(node);await h.c.campaignScheduleAction(node);assert.equal(n,1);panel.isConnected=false;resolve({});await pending;assert.equal(n,1);});

function liveFixture(){const h=fixture(),timers=[],elements={'#schedule-batch-state':{textContent:''},'#schedule-live-items':{innerHTML:''},'#schedule-live-stage':{textContent:''}},panel={dataset:{app:'one',version:'1',principal:'owner'},isConnected:true,campaign:{id:'batch',version:2,status:'ACTIVE',items:[]},querySelector:s=>elements[s]};h.c.setTimeout=(fn,delay)=>{timers.push({fn,delay});return timers.length;};h.c.clearTimeout=()=>{};return {...h,timers,elements,panel};}
test('scope refresh retains pending approved posts only for the same unused active approval', async () => {
  for (const change of ['none', 'hash', 'off', 'intent']) {
    const h = fixture();
    const original = {...scope, ad_account_id: null, approval_hash: 'original'};
    const plan = {scope: original, posts: [{request_id: 'approved-post'}]};
    const panel = {dataset: {app: 'one', version: '1', principal: 'owner'},
      isConnected: true, campaign: plan};
    h.c.modal = (title, html) => h.modals.push({title, html});
    h.panels['#campaign-progress'] = panel;
    h.c.api = async (path, body) => {
      h.calls.push({path, body});
      return {scope: {...original, approval_hash: change === 'hash' ? 'changed' : 'original',
        status: change === 'off' ? 'OFF' : 'ACTIVE'},
        intents: change === 'intent' ? [{id: 'intent', status: 'UNKNOWN'}] : []};
    };
    await h.c.campaignAction({dataset: {action: 'campaign-status', id: 'scope'},
      isConnected: true, closest: () => panel});
    assert.equal(h.calls.length, 1);
    assert.equal(h.calls[0].path, '/api/apps/one/campaigns/status');
    assert.equal(h.calls[0].body.scope_id, 'scope');
    const html = h.modals[0].html;
    assert.equal(html.includes('Schedule approved posts'), change === 'none');
    assert.equal(html.includes('Run approved workflow'), change === 'none');
    assert.equal(panel.campaign.posts?.[0]?.request_id, change === 'none' ? 'approved-post' : undefined);
  }
});
test('live saved progress refreshes states in place with no effect request',async()=>{const h=liveFixture();h.c.api=async(path,body)=>{h.calls.push({path,body});return {id:'batch',version:2,status:'ACTIVE',items:[{item_id:'i',operation:'campaign.publish',effective_status:'VERIFIED',job_status:'SUCCEEDED',intent:{status:'VERIFIED',remote_id:'123_777'}}]};};const stop=h.c.campaignScheduleWatch(h.panel);assert.equal(h.timers[0].delay,5000);await h.timers.shift().fn();assert.equal(h.calls[0].path,'/api/apps/one/campaigns/schedule-status');assert.match(h.elements['#schedule-live-items'].innerHTML,/VERIFIED/);assert.match(h.elements['#schedule-live-stage'].textContent,/Saved stage/);assert.equal(h.panel.campaign.items.length,1);stop();await h.timers.shift().fn();assert.equal(h.calls.length,1);});
test('live progress suppresses overlapping reads and closed or changed contexts',async()=>{for(const change of [h=>h.panel.isConnected=false,h=>h.c.state.app='two',h=>h.c.state.workspace.app.version++,h=>h.c.state.workspace.identity.principal='other']){const h=liveFixture();let resolve,n=0;h.c.api=()=>{n++;return new Promise(r=>resolve=r)};h.c.campaignScheduleWatch(h.panel);const tick=h.timers.shift().fn;const pending=tick();await tick();assert.equal(n,1);change(h);resolve({id:'batch',version:2,status:'OFF',items:[]});await pending;assert.equal(h.elements['#schedule-batch-state'].textContent,'');assert.equal(h.timers.length,0);}});
test('hidden progress avoids reads and failures back off while preserving prior status',async()=>{const h=liveFixture();let calls=0;h.c.api=async()=>{calls++;throw Error('failed');};h.c.document.hidden=true;h.c.campaignScheduleWatch(h.panel);await h.timers.shift().fn();assert.equal(calls,0);h.c.document.hidden=false;await h.timers.shift().fn();assert.equal(calls,1);assert.equal(h.panel.campaign.status,'ACTIVE');assert.equal(h.timers[0].delay,10000);assert.match(h.elements['#schedule-live-stage'].textContent,/refresh failed/);});

test('unreadable batch report keeps missing counts unknown and gives the repair action',()=>{
 const h=fixture(),repair='Saved schedule evidence is unreadable. Check campaign receipts before retrying.';
 const report=h.c.campaignScheduleReport({evidence_unavailable:true,repair,summary:null,items:[]});
 assert.deepEqual(Array.from(report.metrics,x=>x.value),[null,null]);
 assert.ok(report.notes.includes(repair));
});
