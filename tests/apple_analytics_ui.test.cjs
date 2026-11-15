const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const holder={exports:{}};new Function('module',fs.readFileSync('mission_control/static/apple-analytics.js','utf8'))(holder);
const apple=holder.exports;

function fixture(){
 const state={app:'one',view:'connections',boot:{csrf:'csrf-1'},workspace:{app:{id:'one',version:2,data:{store_app_id:'123'}},identity:{status:'AUTHENTICATED',principal:'owner',expires_at_epoch:9999999999},access:{configured:true,members:[{principal:'owner',status:'ACTIVE',role:'OWNER',version:1}]},records:[{id:'connection-1',version:3,hash:'hash-1',kind:'connection',data:{provider:'app_store',store_app_id:'123'}}]}};
 const data={app_id:'one',manifest_version:2,store_app_id:'123',connection:{id:'connection-1',version:3,status:'CONFIGURED_UNVERIFIED'},inventory:{job_id:'job-1',status:'WAITING_FOR_REPORTS',observed_at:'2026-01-01T00:00:00Z'},reports:[{id:'report-1',name:'App Downloads Standard',instance_count:0,coverage:'COMPLETE'}],schedule:null};
 let html='',node=null;const dialog={open:false};
 const d={state,document:{querySelector:s=>s==='#modal'?dialog:node},modal:(title,body)=>{if(node)node.isConnected=false;html=body;dialog.open=true;const fields={'#apple-analytics-status':{textContent:''},'#apple-analytics-error':{textContent:''}};node={isConnected:true,fields,setAttribute(){},querySelector:s=>fields[s],querySelectorAll:()=>[]};},
  api:async()=>data,FormData:class{constructor(form){this.values=form.values}get(key){return this.values[key]}},close:()=>{dialog.open=false},connectionSetup(){},openAccess(){},browser:{},pageReports:{model:()=>({filters:{},notes:[],metrics:[],cohorts:[]}),openReport(){}}};
 return {d,data,state,dialog,get html(){return html},get node(){return node}};
}
const defer=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return {promise,resolve,reject};};
function form(values={report_id:'report-1',interval_hours:'24'}){return {id:'apple-analytics-form',isConnected:true,values};}
function click(action){return {dataset:{action:'apple-analytics-'+action}};}

test('shows truthful inventory, schedule and PDF evidence without private fields',async()=>{
 const f=fixture();f.data.schedule={enabled:true,status:'ENABLED',failures:2,last_job:'refresh-1',last_job_status:'FAILED',last_success:null,next_due:1790000000,version:4,interval_hours:48,report_id:'report-1'};
 f.data.secret='PRIVATE_SENTINEL';await apple.open(f.d);
 for(const text of ['0 report instances','not downloads','FAILED','Failures: 2','Pause refresh','Refresh every (hours)','Inspect latest refresh','not a guarantee of current access'])assert.ok(f.html.includes(text),text);
 assert.match(f.html,/<label for="apple-analytics-report">Report<\/label><select id="apple-analytics-report"/);
 assert.match(f.html,/<label for="apple-analytics-interval">Refresh every \(hours\)<\/label><input id="apple-analytics-interval"/);
 const value=apple.report(f.data,f.state,f.d.pageReports);assert.equal(value.metrics[0].value,0);assert.ok(value.notes.join(' ').includes('not downloads'));assert.ok(!JSON.stringify(value).includes('PRIVATE_SENTINEL'));
});
test('a missing local key offers repair and keeps saved reports and pause available',async()=>{
 const f=fixture(),calls=[];let repair=0;
 f.data.connection.status='RECONNECT_REQUIRED';
 f.data.schedule={enabled:true,status:'ENABLED',version:3,failures:0};
 f.data.reports.push({id:'discovery-1',name:'App Store Discovery and Engagement Standard',coverage:'COMPLETE',instance_count:0});
 f.d.api=async(path)=>{calls.push(path);return f.data;};
 f.d.connectionSetup=(provider,id)=>{assert.equal(provider,'app_store');assert.equal(id,'connection-1');repair++;};
 await apple.open(f.d);
 assert.match(f.html,/Reconnect App Store Connect/);
 assert.match(f.html,/WAITING FOR REPORTS|0 report instances/);
 assert.match(f.html,/Pause refresh/);
 assert.match(f.html,/Report \/ Save PDF/);
 assert.doesNotMatch(f.html,/Read Apple inventory|Collect store impressions|Enable refresh|Save refresh settings/);
 await apple.action(click('inventory'),f.d);
 await apple.action(click('impressions'),f.d);
 await apple.submit(form(),f.d);
 assert.equal(calls.length,1);
 await apple.action(click('setup'),f.d);assert.equal(repair,1);
});

test('signed out and nonowner are routed to existing repair choices without data read',async()=>{
 const f=fixture();let calls=0;f.d.api=async()=>{calls++;return f.data};f.state.workspace.identity={status:'SIGNED_OUT'};await apple.open(f.d);assert.match(f.html,/Sign in/);assert.equal(calls,0);
 f.state.workspace.identity={status:'AUTHENTICATED',principal:'reviewer'};await apple.open(f.d);assert.match(f.html,/current app owner/);assert.match(f.html,/Review app access/);assert.equal(calls,0);
});
test('discard async views after app, manifest, connection, session or dialog changes',async()=>{
 for(const change of [f=>f.state.app='two',f=>f.state.workspace.app.version++,f=>f.state.workspace.records[0].version++,f=>f.state.workspace.identity.principal='other',f=>f.state.workspace.identity={...f.state.workspace.identity},f=>f.state.boot.csrf='changed',f=>f.dialog.open=false]){
  apple.clear();const f=fixture(),pending=defer();f.d.api=()=>pending.promise;const request=apple.open(f.d);const before=f.html;change(f);pending.resolve(f.data);await request;assert.equal(f.html,before);
 }
});
test('reject server data for stale app or connection',async()=>{
 const f=fixture();f.data.connection.version=99;await apple.open(f.d);assert.match(f.node.fields['#apple-analytics-error'].textContent,/connection changed/i);assert.doesNotMatch(f.html,/Enable refresh/);
 const g=fixture();g.data.store_app_id='999';await apple.open(g.d);assert.match(g.node.fields['#apple-analytics-error'].textContent,/App setup changed/i);
});
test('save uses exact owner-visible version and prevents duplicate concurrent writes',async()=>{
 const f=fixture(),pending=defer(),calls=[];f.d.api=async(path,body)=>{calls.push({path,body});if(path.endsWith('/view'))return f.data;return pending.promise;};
 await apple.open(f.d);const saving=apple.submit(form(),f.d);await apple.submit(form(),f.d);assert.equal(calls.filter(c=>c.path.endsWith('/schedule')).length,1);
 assert.deepEqual(calls.at(-1).body,{manifest_version:2,enabled:true,interval_hours:24,report_id:'report-1',version:null});
 pending.reject(Error('Connection lost'));await saving;assert.match(f.node.fields['#apple-analytics-error'].textContent,/No request was repeated/);assert.equal(calls.filter(c=>c.path.endsWith('/schedule')).length,1);
});
test('invalid interval or foreign report cannot write and stale session stops post-response repaint',async()=>{
 const f=fixture(),pending=defer(),calls=[];f.d.api=async(path,body)=>{calls.push({path,body});if(path.endsWith('/view'))return f.data;return pending.promise;};await apple.open(f.d);
 await apple.submit(form({report_id:'report-1',interval_hours:'23'}),f.d);await apple.submit(form({report_id:'foreign',interval_hours:'24'}),f.d);assert.equal(calls.length,1);
 const request=apple.submit(form(),f.d);f.state.workspace.identity.principal='someone-else';pending.resolve({enabled:true,version:1});await request;assert.equal(calls.filter(c=>c.path.endsWith('/view')).length,1);
});
test('inventory and pause use displayed source and block repeated submissions',async()=>{
 const f=fixture(),pending=defer(),calls=[];f.data.schedule={enabled:true,version:7,status:'ENABLED',failures:0};
 f.d.api=async(path,body)=>{calls.push({path,body});if(path.endsWith('/view'))return f.data;return pending.promise;};await apple.open(f.d);
 const request=apple.action(click('inventory'),f.d);await apple.action(click('inventory'),f.d);assert.equal(calls.filter(c=>c.path.endsWith('/inventory')).length,1);assert.deepEqual(calls.at(-1).body,{manifest_version:2,connection_id:'connection-1',connection_version:3});pending.resolve({job_id:'queued-1',status:'QUEUED'});await request;assert.match(f.node.fields['#apple-analytics-status'].textContent,/queued-1/);
});
test('pause uses the saved schedule version and a closed modal prevents repair actions',async()=>{
 const f=fixture(),pending=defer(),calls=[];f.data.schedule={enabled:true,version:7,status:'ENABLED',failures:0};let setup=0;f.d.connectionSetup=()=>setup++;
 f.d.api=async(path,body)=>{calls.push({path,body});if(path.endsWith('/view'))return f.data;return pending.promise;};await apple.open(f.d);
 const request=apple.action(click('pause'),f.d);await apple.action(click('pause'),f.d);assert.deepEqual(calls.at(-1).body,{manifest_version:2,enabled:false,version:7});assert.equal(calls.filter(c=>c.path.endsWith('/schedule')).length,1);
 f.dialog.open=false;pending.resolve({enabled:false,version:8});await request;await apple.action(click('setup'),f.d);assert.equal(setup,0);assert.equal(calls.filter(c=>c.path.endsWith('/view')).length,1);
});
test('store impressions queues only the current complete discovery report',async()=>{
 const f=fixture(),calls=[];
 const discovery={id:'discovery-1',name:'App Store Discovery and Engagement Standard',coverage:'PARTIAL',instance_count:1};
 f.data.reports.push(discovery);
 f.d.api=async(path,body)=>{calls.push({path,body});return path.endsWith('/view')?f.data:{job_id:'impression-job'};};
 await apple.open(f.d);assert.doesNotMatch(f.html,/Collect store impressions/);
 await apple.action(click('impressions'),f.d);assert.equal(calls.length,1);
 discovery.coverage='COMPLETE';await apple.open(f.d);
 assert.match(f.html,/Collect store impressions/);assert.match(f.html,/Unique counts can overlap/);
 await apple.action(click('impressions'),f.d);
 assert.deepEqual(calls.at(-1),{path:'/api/apps/one/apple-analytics/impressions',body:{manifest_version:2,report_id:'discovery-1'}});
 assert.match(f.node.fields['#apple-analytics-status'].textContent,/impression-job/);
 assert.doesNotMatch(f.html,/<option value="discovery-1"/);
});
test('impression result distinguishes zero from unavailable and labels unique counts at row grain',()=>{
 const render=store_impressions=>apple.impressionsResult({store_impressions});
 assert.match(render({sample:[]}),/Impressions are unknown/);
 const result=render({impression_rows:1,sample:[{date:'2026-10-23',counts:0,unique_counts:0,dimensions:{territory:'<US>'}}]});
 assert.match(result,/Unique in row/);assert.match(result,/&lt;US&gt;/);
 assert.match(result,/<td>0<\/td><td>0<\/td>/);
});
test('inspect latest refresh opens only the saved job while the app and session remain current',async()=>{
 const f=fixture(),opened=[];f.data.schedule={enabled:true,version:2,status:'ENABLED',failures:1,last_job:'refresh-1',last_job_status:'BLOCKED'};f.d.openJob=id=>opened.push(id);
 await apple.open(f.d);assert.match(f.html,/repair the reported issue/);await apple.action(click('job'),f.d);assert.deepEqual(opened,['refresh-1']);
 f.state.app='two';await apple.action(click('job'),f.d);assert.deepEqual(opened,['refresh-1']);
});
