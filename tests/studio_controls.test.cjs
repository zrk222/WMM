const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const loaded={exports:{}};new Function('module',fs.readFileSync(path.join(__dirname,'../mission_control/static/studio-controls.js'),'utf8'))(loaded);
const studio=loaded.exports;
const field=(control,value,extra={})=>({id:control,label:control,control,value,writable:true,...extra});
const controls={revision:3,view_hash:'view-hash',owners:[{id:'owner',kind:'item',fields:[field('text','hello'),field('number',38),field('boolean',false),field('select',true,{options:[{value:true,label:'Enabled'},{value:4,label:'Four'}]}),field('color','#102030'),field('list',[1]),field('record',{x:1}),field('text','derived',{id:'derived',writable:false})]}]};
const snapshot=(extra={})=>({session:{id:'session-one',state:'ACTIVE'},source_head:{version:2,hash:'head-hash'},controls,...extra});
function fixture(){
 studio.clear();let html='',serial=0;const calls=[],reports=[],nodes={},focused=[],modals=[];
 const details={tagName:'DETAILS',open:false,parentElement:null};
 const forms=()=>[...html.matchAll(/data-owner="([^"]+)" data-field="([^"]+)"/g)].map(m=>({dataset:{owner:m[1],field:m[2]},parentElement:details,querySelector:()=>({focus:()=>focused.push(m[2])})}));
 const root={open:true,querySelector:s=>nodes[s]||(nodes[s]={textContent:'',setAttribute(){},focus:()=>focused.push(s)}),querySelectorAll:s=>s==='[data-studio-parameter]'?forms():[]};
 const d={state:{app:'sample-one',boot:{csrf:'CSRF_SENTINEL'},workspace:{app:{version:1,data:{name:'Synthetic app'}},jobs:[{id:'source-one',action:'hypit_render',status:'SUCCEEDED'}]}},
  document:{querySelector:()=>root},modal:(title,value)=>{modals.push(title);studio.clear();html=value;for(const k of Object.keys(nodes))delete nodes[k];},uuid:()=>`request-${++serial}`,
  FormData:class{constructor(form){this.value=form.values;}get(k){return this.value[k];}},
  pageReports:{openReport:r=>reports.push(r)},browser:{}};
 d.fetch=async(url,request)=>{calls.push({url,request,body:JSON.parse(request.body)});const action=url.split('/').at(-1);
  let value={};if(action==='sessions')value={items:[]};if(action==='plan')value={summary:{effects:['START_OWNED_LOCAL_STUDIO']},summary_hash:'summary',intent:{source_job_id:'source-one'}};if(['start','read','edit','inspect'].includes(action))value=snapshot();if(action==='close')value=snapshot({session:{id:'session-one',state:'CLOSED'}});
  return {ok:true,status:200,json:async()=>value};};
 return {d,calls,reports,root,nodes,focused,details,modals,html:()=>html};
}
const action=(name,extra={})=>({dataset:{action:'studio-'+name,...extra}});
const form=(value,which='number')=>({id:'',dataset:{owner:'owner',field:which},values:{value}});
async function started(f){await studio.open(f.d);await studio.submit({id:'studio-source-form',values:{source_job_id:'source-one'}},f.d);await studio.action(action('start'),f.d);}

test('all compiled controls render with typed values, unique input IDs and escaped metadata',()=>{
 const html=studio.fieldsMarkup(controls);assert.equal((html.match(/data-studio-parameter/g)||[]).length,8);
 const ids=[...html.matchAll(/id="(studio-value-\d+)"/g)].map(x=>x[1]);assert.equal(new Set(ids).size,ids.length);
 assert.equal((html.match(/Save this setting/g)||[]).length,7);assert.ok(html.includes('Read only'));
 const hostile=JSON.parse(JSON.stringify(controls));hostile.owners[0].fields[0].value='</textarea><img src=x onerror=alert(1)>';
 hostile.owners[0].fields[0].label='<script>bad</script>';const safe=studio.fieldsMarkup(hostile);
 assert.ok(!safe.includes('<img'));assert.ok(!safe.includes('<script>'));assert.ok(safe.includes('&lt;script&gt;'));
});
test('typed editors preserve compiled option primitive types and reject malformed structured values',()=>{
 assert.equal(studio.typed(field('number',0),'46'),46);assert.equal(studio.typed(field('boolean',false),'false'),false);
 assert.equal(studio.typed(controls.owners[0].fields[3],'0'),true);assert.equal(studio.typed(controls.owners[0].fields[3],'1'),4);
 assert.deepEqual(studio.typed(field('list',[]),'[1,"two"]'),[1,'two']);assert.deepEqual(studio.typed(field('record',{}),'{"x":2}'),{x:2});
 for(const [kind,value] of [['number',''],['number','Infinity'],['boolean','yes'],['list','{}'],['record','[]'],['record','null'],['select','99']])assert.throws(()=>studio.typed(field(kind,null,{options:['a']}),value));
});
test('source summary precedes startup and edit binds exact view/source identities',async()=>{
 const f=fixture();await studio.open(f.d);assert.equal(f.calls.length,1);
 await studio.submit({id:'studio-source-form',values:{source_job_id:'source-one'}},f.d);
 assert.deepEqual(f.calls.map(c=>c.url.split('/').at(-1)),['sessions','plan']);assert.ok(f.html().includes('Exact startup summary'));
 await studio.action(action('start'),f.d);assert.deepEqual(f.calls[2].body,{source_job_id:'source-one',manifest_version:1,summary_hash:'summary',request_key:'request-1'});
 await studio.submit(form('46'),f.d);const edit=f.calls.at(-1);assert.equal(edit.url,'/api/apps/sample-one/studio/session-one/edit');
 assert.deepEqual(edit.body,{request_key:'request-2',base_version:2,base_hash:'head-hash',parameter:{revision:3,view_hash:'view-hash',owner_id:'owner',field_id:'number',value:46}});
 assert.equal(edit.request.headers['X-CSRF-Token'],'CSRF_SENTINEL');assert.equal(edit.request.redirect,'error');
});
test('uncertain edit stops resends and inspection does not silently reauthorize mutations',async()=>{
 const f=fixture();await started(f);let sends=0;
 const original=f.d.fetch;f.d.fetch=async(url,body)=>{if(url.endsWith('/edit')){sends++;return {ok:false,status:409,json:async()=>({error:'Inspect retained state',outcome:'UNKNOWN',reconciliation_required:true})};}return original(url,body);};
 await studio.submit(form('46'),f.d);assert.match(f.nodes['#studio-error'].textContent,/Outcome unknown/);
 await studio.submit(form('47'),f.d);assert.equal(sends,1);
 await studio.action(action('inspect'),f.d);await studio.submit(form('48'),f.d);assert.equal(sends,1);
});
test('pending duplicate saves send once and late replies cannot replace another app or dialog',async()=>{
 const f=fixture();await started(f);let resolve,sends=0;
 f.d.fetch=()=>{sends++;return new Promise(r=>resolve=r);};
 const first=studio.submit(form('46'),f.d);await studio.submit(form('46'),f.d);assert.equal(sends,1);
 const old=f.html(),modalCount=f.modals.length;f.d.state.app='sample-two';studio.invalidate(f.d.state);
 resolve({ok:true,status:200,json:async()=>snapshot()});await first;assert.equal(f.html(),old);assert.equal(f.modals.length,modalCount);
});
test('closed dialog discards late load and report excludes field values, private payloads and credentials',async()=>{
 const f=fixture();await started(f);await studio.action(action('report'),f.d);
 const report=JSON.stringify(f.reports[0]);assert.ok(!report.includes('hello'));assert.ok(!report.includes('CSRF_SENTINEL'));assert.ok(!report.includes('head-hash'));
 assert.equal(f.reports[0].metrics[0].value,8);
 let resolve;f.d.fetch=()=>new Promise(r=>resolve=r);const call=studio.action(action('refresh'),f.d);f.root.open=false;const old=f.html(),modalCount=f.modals.length;
 resolve({ok:true,status:200,json:async()=>snapshot()});await call;assert.equal(f.html(),old);assert.equal(f.modals.length,modalCount);
});
test('network ambiguity is not a rejected edit and explicit stop shows durable cleanup',async()=>{
 const f=fixture();await started(f);const original=f.d.fetch;f.d.fetch=async()=>{throw new Error('offline');};
 await studio.submit(form('46'),f.d);assert.match(f.nodes['#studio-error'].textContent,/Outcome unknown/);
 f.d.fetch=original;await studio.action(action('stop'),f.d);assert.match(f.nodes['#studio-error'].textContent,/CLOSED/);
});
test('workspace and submit hooks use the shared module and clear stale modal state',()=>{
 const dir=path.join(__dirname,'../mission_control/static'),app=fs.readFileSync(path.join(dir,'app.js'),'utf8'),index=fs.readFileSync(path.join(dir,'index.html'),'utf8');
 for(const hook of ['WMMStudio.panel()','WMMStudio.invalidate(state)','WMMStudio.clear()','WMMStudio.submit(form,growthReviewServices())','WMMStudio.action(node,growthReviewServices())'])assert.ok(app.includes(hook),hook);
 assert.ok(index.includes('src="/studio-controls.js"'));
});
test('confirmed close rerenders truthful terminal state and removes stale fields even after uncertainty',async()=>{
 const f=fixture();await started(f);const original=f.d.fetch;
 f.d.fetch=async()=>{throw new Error('offline');};await studio.submit(form('46'),f.d);
 f.d.fetch=original;await studio.action(action('stop'),f.d);
 assert.match(f.html(),/session-one \/ CLOSED/);assert.ok(!f.html().includes('data-studio-parameter'));
 assert.ok(!f.html().includes('studio-stop'));assert.ok(!f.html().includes('Save one setting'));
 assert.doesNotMatch(f.nodes['#studio-error'].textContent,/unknown|reconciliation/i);
 await studio.action(action('report'),f.d);assert.equal(f.reports[0].filters.state,'CLOSED');
 assert.deepEqual(f.reports[0].metrics.slice(0,2).map(m=>m.value),[null,null]);
});
test('missing coverage and history stay unavailable while supplied empty collections count zero',async()=>{
 const f=fixture();await started(f);await studio.action(action('report'),f.d);
 assert.equal(f.reports.at(-1).metrics[2].value,null);assert.match(f.html(),/Attempt history unavailable/);
 f.d.fetch=async()=>({ok:true,json:async()=>snapshot({controls:null})});await studio.action(action('refresh'),f.d);
 assert.match(f.html(),/Compiled settings unavailable/);assert.ok(!f.html().includes('0 compiled settings'));
 await studio.action(action('report'),f.d);assert.deepEqual(f.reports.at(-1).metrics.slice(0,3).map(m=>m.value),[null,null,null]);
 f.d.fetch=async()=>({ok:true,json:async()=>snapshot({controls:{owners:[]},attempts:[]})});await studio.action(action('inspect'),f.d);
 await studio.action(action('report'),f.d);assert.deepEqual(f.reports.at(-1).metrics.slice(0,3).map(m=>m.value),[0,0,0]);
});
test('reports retain snapshot receipt timestamp until a successful new observation',async()=>{
 const NativeDate=Date;let current='2026-10-25T12:00:00.000Z';
 global.Date=class extends NativeDate{constructor(...args){super(...(args.length?args:[current]));}};
 try{
  const f=fixture();await started(f);current='2026-10-25T12:30:00.000Z';await studio.action(action('report'),f.d);
  assert.equal(f.reports.at(-1).loaded_at,'2026-10-25T12:00:00.000Z');assert.equal(f.reports.at(-1).generated_at,current);
  current='2026-10-25T13:00:00.000Z';await studio.action(action('refresh'),f.d);await studio.action(action('report'),f.d);
  assert.equal(f.reports.at(-1).loaded_at,current);
 }finally{global.Date=NativeDate;}
});
test('replaced dialogs receive focus and successful saves restore the edited setting in expanded owner',async()=>{
 const f=fixture();await started(f);assert.equal(f.focused.at(-1),'.studio-controls');
 await studio.submit(form('46'),f.d);assert.equal(f.focused.at(-1),'number');assert.equal(f.details.open,true);
 await studio.action(action('stop'),f.d);assert.equal(f.focused.at(-1),'.studio-controls');
});

test('principal changes invalidate pending replies before replacing owner controls',async()=>{
 const f=fixture();f.d.state.workspace.identity={principal:'first-owner'};await started(f);
 let resolve;f.d.fetch=()=>new Promise(r=>resolve=r);const count=f.modals.length;
 const pending=studio.action(action('refresh'),f.d);f.d.state.workspace.identity.principal='second-owner';
 resolve({ok:true,status:200,json:async()=>snapshot()});await pending;assert.equal(f.modals.length,count);
});
