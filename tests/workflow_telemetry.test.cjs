const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const context={module:{exports:{}},setTimeout,clearTimeout};vm.createContext(context);
vm.runInContext(fs.readFileSync(require('node:path').join(__dirname,'../mission_control/static/workflow-telemetry.js'),'utf8'),context);
const ui=context.module.exports;
test('completed reads distinguish missing provider reports without claiming metrics or scheduled work',()=>{
 const run={id:'waiting',action:'sync',status:'SUCCEEDED',outcome_code:'WAITING_FOR_REPORTS',attempts:1,processed_stages:0,blocked_stages:0,activity:'Worker finished',events:[],updated:'now'};
 const html=ui.markup({runs:[run]});
 assert.match(html,/Read completed · waiting for reports/);assert.match(html,/This read supplied no app metrics/);assert.match(html,/check its refresh schedule in Connections/);assert.match(html,/An enabled schedule/);
 assert.ok(!html.includes('Worker finished'));assert.ok(html.includes('telemetry-open-job'));
 for(const changes of [{action:'pipeline'},{status:'FAILED'},{status:'RUNNING'},{outcome_code:'PRIVATE_UNKNOWN'}]){
  const other=ui.markup({runs:[{...run,...changes}]});assert.ok(!other.includes('Read completed · waiting for reports'));assert.ok(!other.includes('PRIVATE_UNKNOWN'));
 }
});
test('waiting saved-result summary exposes only a validated source receipt hash',()=>{
 const result={status:'WAITING_FOR_REPORTS',token:'PRIVATE_TOKEN',error:'PRIVATE_ERROR',outputs:[{secret:'PRIVATE_OUTPUT'}],source_hash:'a'.repeat(64)};
 const html=ui.waitingResultMarkup(result);assert.ok(html.includes('a'.repeat(64)));assert.ok(!html.includes('PRIVATE_'));assert.match(html,/This read supplied no app metrics/);
 for(const source_hash of [null,{},'<img src=x>','PRIVATE_HASH','A'.repeat(64)]){const other=ui.waitingResultMarkup({...result,source_hash});assert.match(other,/Not supplied by this read/);assert.ok(!other.includes('PRIVATE_'));assert.ok(!other.includes('<img'));}
});
test('waiting result summary precedes resolution and Play dispatch without changing nonwaiting routing',()=>{
 const source=fs.readFileSync(require('node:path').join(__dirname,'../mission_control/static/app-ui.js'),'utf8');
 const start=source.indexOf('function openJob(id) {'),end=source.indexOf('\nfunction prepareReview()',start);
 assert.ok(start>=0&&end>start);
 for(const operation of ['play_releases','play_subscriptions']){
  const job={id:'waiting',action:'sync',status:'SUCCEEDED',data:{options:{operation}},result:{status:'WAITING_FOR_REPORTS',error:'PRIVATE_ERROR',outputs:[{secret:'PRIVATE_OUTPUT'}]}};
  const calls=[],ctx={state:{workspace:{jobs:[job],resolutions:{history:[{job_id:job.id}]}}},WMMTelemetry:ui,notice:x=>x,button:()=>'',status:x=>x,esc:x=>x,$:()=>({dataset:{}}),modal:(title,body)=>calls.push(body),playOpenJob:()=>calls.push('play'),openResolutionRun:()=>calls.push('resolution'),agentOpenRun:()=>calls.push('agent'),providerResult:()=>{throw Error('raw result');},stagePacketCard:()=>{throw Error('raw output');}};
  vm.createContext(ctx);vm.runInContext(source.slice(start,end),ctx);ctx.openJob(job.id);
  assert.equal(calls.length,1);assert.match(calls[0],/Read completed · waiting for reports/);assert.ok(!calls[0].includes('PRIVATE_'));
  calls.length=0;job.status='FAILED';ctx.openJob(job.id);assert.deepEqual(calls,['resolution']);
  calls.length=0;ctx.state.workspace.resolutions.history=[];ctx.openJob(job.id);assert.deepEqual(calls,['play']);
 }
});
test('monitor displays actual stage and fixed activity without injecting source markup',()=>{
 const html=ui.markup({runs:[{action:'pipeline',status:'RUNNING',attempts:1,processed_stages:2,blocked_stages:1,updated:'now',latest:{stage:3,stage_title:'<script>bad</script>',observed_at:'now'},activity:'Checking evidence',events:[{observed_at:'now',stage:3,message:'<img src=x>'}]}]});
 assert.match(html,/Stage 3/);assert.match(html,/2 stages processed/);assert.match(html,/Checking evidence/);
 assert.ok(!html.includes('<script>'));assert.ok(!html.includes('<img'));assert.ok(!html.includes('%'));
});
test('empty and unobserved attempts do not invent stage completion',()=>{
 assert.match(ui.markup({runs:[]}),/No workflow runs yet/);
 const html=ui.markup({runs:[{action:'pipeline',status:'QUEUED',attempts:0,processed_stages:0,blocked_stages:0,activity:'No worker event',events:[],updated:'now'}]});
 assert.match(html,/No event recorded/);assert.ok(!html.includes('Stage undefined'));assert.equal(ui.POLL_MS,2000);
});

function resultFixture(){
 const state={app:'one',view:'workflow',refreshGeneration:0,workspace:{app:{id:'one'},identity:{principal:'owner'},jobs:[{id:'saved'}]}},opened=[],messages=[];
 const deps={state,toast:text=>messages.push(text),openJob:id=>opened.push(id),refresh:async()=>{state.refreshGeneration++;state.workspace={...state.workspace,jobs:[{id:'saved',status:'SUCCEEDED'}]};return {app:state.app,generation:state.refreshGeneration,workspace:state.workspace};}};
 return {state,opened,messages,deps,node:{disabled:false,isConnected:true,dataset:{id:'saved'}}};
}
test('result action opens the exact job only after a current applied refresh',async()=>{
 const f=resultFixture();await ui.openResult(f.node,f.deps);assert.deepEqual(f.opened,['saved']);assert.equal(f.node.disabled,false);
 for(const alter of [f=>f.state.app='other',f=>f.state.view='results',f=>f.state.workspace.identity.principal='other',f=>f.state.refreshGeneration++]){
  const f=resultFixture(),read=f.deps.refresh;f.deps.refresh=async()=>{const receipt=await read();alter(f);return receipt;};await ui.openResult(f.node,f.deps);assert.deepEqual(f.opened,[]);
 }
});
test('missing current history, failed and superseded refresh never open cached results',async()=>{
 for(const kind of ['missing','failed','not-applied','stale-receipt','wrong-app','wrong-workspace']){
  const f=resultFixture(),read=f.deps.refresh;
  f.deps.refresh=async()=>{if(kind==='failed'){f.state.refreshGeneration++;throw Error('offline');}const receipt=await read();if(kind==='missing')f.state.workspace.jobs=[];if(kind==='wrong-workspace')f.state.workspace.app.id='other';if(kind==='not-applied')return;if(kind==='stale-receipt')return {...receipt,workspace:{}};if(kind==='wrong-app')return {...receipt,app:'other'};return receipt;};
  await ui.openResult(f.node,f.deps);assert.deepEqual(f.opened,[]);assert.equal(f.messages.length,1);assert.equal(f.node.disabled,false);
 }
});
test('result inspection remains single-flight across remount and replacement buttons',async()=>{
 const f=resultFixture(),read=f.deps.refresh;let resolve;f.deps.refresh=()=>new Promise(r=>resolve=r);
 const first=ui.openResult(f.node,f.deps);assert.equal(f.node.disabled,true);ui.clear();
 const replacement={...f.node,disabled:false};await ui.openResult(replacement,f.deps);await ui.openResult(f.node,f.deps);
 resolve(await read());await first;assert.deepEqual(f.opened,['saved']);
});
test('run guidance preserves uncertainty and escapes job button identities',()=>{
 const run={id:'" onclick="bad',action:'pipeline',status:'UNKNOWN',attempts:1,processed_stages:0,blocked_stages:0,activity:'Pending reconciliation',events:[],updated:'now'};
 const html=ui.markup({runs:[run]});assert.match(html,/Do not automatically resend/);assert.match(html,/data-id="&quot; onclick=&quot;bad"/);assert.ok(!html.includes('data-id="" onclick='));
 assert.ok(!ui.markup({runs:[{...run,id:null}]}).includes('telemetry-open-job'));assert.match(ui.nextAction('NEW_STATE'),/do not establish completion/);
 for(const status of ['QUEUED','RUNNING','RETRY_WAIT','FAILED','BLOCKED','SUCCEEDED','CANCELLED','CANCEL_REQUESTED'])assert.ok(ui.nextAction(status).length>30);
});
function pollFixture(){
 const timers=new Map();let seq=0;
 const ctx={module:{exports:{}},setTimeout:(fn,ms)=>{timers.set(++seq,{fn,ms});return seq;},clearTimeout:id=>timers.delete(id)};vm.createContext(ctx);vm.runInContext(fs.readFileSync(require('node:path').join(__dirname,'../mission_control/static/workflow-telemetry.js'),'utf8'),ctx);
 const list={innerHTML:'retained',contains:()=>false},status={textContent:''},worker={textContent:''},refresh={};
 const announcements=[];
 const stage={get textContent(){return announcements.at(-1)??'';},set textContent(value){announcements.push(value);}};
 const targets={'[data-live-runs]':list,'[data-live-status]':status,'[data-live-worker]':worker,'[data-live-stage]':stage};
 const node={isConnected:true,querySelector:s=>targets[s]??refresh};
 const document={hidden:false,activeElement:null,querySelector:()=>node};let calls=0,answer=async()=>({app_id:'one',observed_at:'now',runs:[]});
 const deps={state:{app:'one'},document,api:()=>{calls++;return answer();}};
 return {ui:ctx.module.exports,timers,list,status,worker,announcements,node,document,deps,refresh,get calls(){return calls;},set answer(value){answer=value;},async settle(){await new Promise(setImmediate);},async tick(){assert.equal(timers.size,1);const [id,row]=timers.entries().next().value;timers.delete(id);await row.fn();},delay(){assert.equal(timers.size,1);return timers.values().next().value.ms;}};
}
test('failed progress reads back off with a bounded timer and recover to normal cadence',async()=>{
 const f=pollFixture();f.answer=async()=>{throw Error('offline');};f.ui.mount(f.deps);await f.settle();
 for(const delay of [4000,8000,16000,32000,32000]){assert.equal(f.delay(),delay);assert.equal(f.list.innerHTML,'retained');await f.tick();}
 f.answer=async()=>({app_id:'one',observed_at:'now',runs:[]});await f.tick();assert.equal(f.delay(),2000);assert.match(f.status.textContent,/Last refresh/);f.ui.clear();assert.equal(f.timers.size,0);
});
test('fresh telemetry distinguishes worker recovery, health and stopped state',async()=>{
 const f=pollFixture(),reply=worker=>async()=>({app_id:'one',observed_at:'now',runs:[],worker});
 f.answer=reply({status:'RECOVERING',last_success:'prior-poll',last_error:'PRIVATE_ERROR'});
 f.ui.mount(f.deps);await f.settle();
 assert.match(f.worker.textContent,/Worker needs attention/);assert.match(f.status.textContent,/prior-poll/);
 assert.doesNotMatch(f.worker.textContent,/PRIVATE_ERROR|healthy/);
 f.answer=reply({status:'RUNNING',runtime_mode:'HEADLESS'});await f.tick();assert.match(f.worker.textContent,/reported healthy/);
 assert.match(f.worker.textContent,/Headless mode.*Closing this browser leaves the worker running/);
 f.answer=reply({status:'STARTING',runtime_mode:'DESKTOP'});await f.tick();assert.match(f.worker.textContent,/Desktop mode.*Keep WMM open/);
 f.answer=reply({status:'STARTING',runtime_mode:'PRIVATE_MODE'});await f.tick();assert.match(f.worker.textContent,/Run mode unavailable/);
 assert.doesNotMatch(f.worker.textContent,/PRIVATE_MODE/);
 f.answer=reply({status:'STOPPED'});await f.tick();assert.match(f.worker.textContent,/Start WMM on the host/);
 f.answer=async()=>{throw Error('offline');};await f.tick();assert.match(f.worker.textContent,/status unavailable/);
 assert.match(f.ui.panel(),/Open the private-host setup guide/);f.ui.clear();
});
test('manual refresh cancels backoff and cannot overlap an in-flight read',async()=>{
 const f=pollFixture();f.answer=async()=>{throw Error('offline');};f.ui.mount(f.deps);await f.settle();assert.equal(f.delay(),4000);
 let resolve;f.answer=()=>new Promise(r=>resolve=r);f.refresh.onclick();assert.equal(f.timers.size,0);const calls=f.calls;f.refresh.onclick();assert.equal(f.calls,calls);
 resolve({app_id:'one',observed_at:'now',runs:[]});await f.settle();assert.equal(f.delay(),2000);f.ui.clear();
});
test('hidden views do not read; wrong-app replies and focused lists preserve displayed content',async()=>{
 const f=pollFixture();f.document.hidden=true;f.ui.mount(f.deps);assert.equal(f.calls,0);await f.tick();assert.equal(f.calls,0);
 f.document.hidden=false;f.answer=async()=>({app_id:'other',runs:[]});await f.tick();assert.equal(f.list.innerHTML,'retained');assert.match(f.status.textContent,/Updates unavailable/);
 f.answer=async()=>({app_id:'one',observed_at:'now',runs:[]});f.list.contains=()=>true;await f.tick();assert.equal(f.list.innerHTML,'retained');
 f.list.contains=()=>false;await f.tick();assert.match(f.list.innerHTML,/No workflow runs yet/);f.ui.clear();
});
test('unmount or app change discards an in-flight progress response',async()=>{
 for(const change of [f=>f.ui.clear(),f=>f.deps.state.app='other']){
  const f=pollFixture();let resolve;f.answer=()=>new Promise(r=>resolve=r);f.ui.mount(f.deps);change(f);resolve({app_id:'one',observed_at:'now',runs:[]});await f.settle();assert.equal(f.list.innerHTML,'retained');assert.equal(f.timers.size,0);f.ui.clear();
 }
});

test('actual workspace refresh returns an applied receipt and superseded reads return none',async()=>{
 const source=fs.readFileSync(require('node:path').join(__dirname,'../mission_control/static/app.js'),'utf8');const start=source.indexOf('async function refresh()'),end=source.indexOf('\nfunction currentWorkspace()',start);
 const pending=[],state={app:'one',refreshGeneration:0,workspace:{app:{id:'one'}}};
 const ctx={state,api:()=>new Promise(resolve=>pending.push(resolve)),currentWorkspace:()=>state.workspace?.app.id===state.app,render(){},localStorage:{setItem(){}},$:()=>({textContent:''})};vm.createContext(ctx);vm.runInContext(source.slice(start,end),ctx);
 const first=ctx.refresh(),second=ctx.refresh();const workspace={app:{id:'one',data:{name:'Synthetic'}}};pending[1](workspace);const applied=await second;
 assert.equal(applied.app,'one');assert.equal(applied.generation,2);assert.equal(applied.workspace,workspace);
 pending[0]({app:{id:'one',data:{name:'Stale'}}});assert.equal(await first,undefined);assert.equal(state.workspace,workspace);
});

test('unchanged polls retain the job list; new measured timings update it once',async()=>{
 const f=pollFixture();let markup=f.list.innerHTML,writes=0;
 Object.defineProperty(f.list,'innerHTML',{get:()=>markup,set:v=>{markup=v;writes++;}});
 let timing={initial_queue_ms:450};
 f.answer=async()=>({app_id:'one',observed_at:String(f.calls),runs:[{id:'sample',action:'render',status:'RUNNING',attempts:1,processed_stages:0,blocked_stages:0,events:[],timing}]});
 f.ui.mount(f.deps);await f.settle();
 assert.equal(writes,1);assert.match(markup,/Waited &lt;1 s to start/);assert.doesNotMatch(markup,/Worker ran/);
 await f.tick();await f.tick();assert.equal(writes,1);
 timing={initial_queue_ms:450,attempt_ms:64000};
 await f.tick();assert.equal(writes,2);assert.match(markup,/Worker ran for 1 min 4 s/);
 await f.tick();assert.equal(writes,2);f.ui.clear();
});


test('progress announces the active stage once and preserves it during stale or failed reads',async()=>{
 const f=pollFixture();
 const stage={id:'active',action:'pipeline',status:'RUNNING',attempts:1,processed_stages:0,blocked_stages:0,events:[],
  latest:{stage:2,stage_title:'Research',observed_at:'earlier'},activity:'Research started.',updated:'earlier'};
 let reply={app_id:'one',observed_at:'earlier',runs:[{...stage,id:'done',status:'SUCCEEDED',activity:'Finished.'},stage]};
 f.answer=async()=>reply;
 assert.match(f.ui.panel(),/data-live-stage role="status"/);
 f.ui.mount(f.deps);
 try{
  await f.settle();
  assert.deepEqual(f.announcements,['Workflow update: Stage 2: Research. Research started.']);
  reply={...reply,observed_at:'later',runs:[reply.runs[0],{...stage,updated:'later'}]};
  await f.tick();
  assert.equal(f.announcements.length,1);
  f.list.contains=()=>true;
  const retained=f.list.innerHTML;
  reply={...reply,runs:[{...stage,latest:{stage:3,stage_title:'Creative'},activity:'Drafting.'}]};
  await f.tick();
  assert.equal(f.list.innerHTML,retained);
  assert.equal(f.announcements.at(-1),'Workflow update: Stage 3: Creative. Drafting.');
  const count=f.announcements.length;
  reply={...reply,app_id:'other',runs:[{...stage,activity:'FOREIGN'}]};
  await f.tick();
  f.answer=async()=>{throw Error('PRIVATE_FAILURE');};
  await f.tick();
  assert.equal(f.announcements.length,count);
 }finally{f.ui.clear();}
});
