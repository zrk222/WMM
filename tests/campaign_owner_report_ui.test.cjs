const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('./helpers/module-source.cjs'),vm=require('node:vm'),path=require('node:path');
function fixture(){const nodes=new Map([['#modal',{open:true}]]),c={Date,state:{app:'one',workspace:{app:{version:1},identity:{principal:'owner'}}},esc:x=>String(x??'').replaceAll('<','&lt;'),button:()=>'',crypto:{randomUUID:()=> 'fixed'},FormData:class{constructor(form){return Object.entries(form.values||{});}}};c.$=x=>nodes.get(x);c.modal=(title,html)=>{for(const [key,node] of nodes)if(key!=='#modal')node.isConnected=false;for(const m of html.matchAll(/id="([^"]+)"/g))nodes.set('#'+m[1],{isConnected:true,querySelector:()=>({disabled:false}),textContent:''});};c.api=async path=>path.endsWith('campaign-monitor/history')?{monitors:[]}:{reports:[],plans:[]};vm.createContext(c);vm.runInContext(fs.readFileSync(path.join(__dirname,'../mission_control/static/campaign-owner-reports.mjs'),'utf8'),c);return {a:vm.runInContext('WMMOwnerReports',c),c,nodes};}
const monitors=[{id:'monitor',summary:{proposal:{scope_id:'scope'}}}],values={monitor_id:'monitor',experiment_id:'trial',starts_at:'2026-10-01',ends_at:'2026-11-01'};
test('report selection resolves exact linked scope and existing experiment',()=>{const a=fixture().a,s=a.selection(values,monitors,[{id:'trial'}]);assert.equal(s.scope_id,'scope');assert.equal(s.experiment_id,'trial');assert.throws(()=>a.selection(values,[],[{id:'trial'}]));assert.throws(()=>a.selection({...values,scope_id:'forged',experiment_id:'foreign'},monitors,[]));assert.throws(()=>a.selection({...values,ends_at:values.starts_at},monitors,[{id:'trial'}]));});
test('owner can choose a saved campaign without supplying a monitor',()=>{
 const a=fixture().a,scopes=[{scope_id:'scope'},{scope_id:'other'}],experiments=[{id:'trial'}];
 const selected=a.selection({...values,scope_id:'scope',monitor_id:''},[],experiments,scopes);
 assert.equal(selected.scope_id,'scope');
 assert.equal(selected.monitor_id,null);
 assert.throws(()=>a.selection({...values,scope_id:'other'},monitors,experiments,scopes),/belongs/);
 assert.throws(()=>a.selection({...values,scope_id:'unknown',monitor_id:''},[],experiments,scopes),/existing owner campaign/);
});

test('finite private report schedule rejects excessive or incomplete limits',()=>{const a=fixture().a,clock=Date.parse('2026-11-02'),valid={cadence_seconds:'86400',max_reports:'7',expires_at:'2026-11-08'};assert.equal(a.schedule(valid,{},clock).max_reports,7);for(const bad of [{...valid,max_reports:'101'},{...valid,cadence_seconds:'29'},{...valid,expires_at:'2026-11-10'},{...valid,expires_at:'bad'}])assert.throws(()=>a.schedule(bad,{},clock));});
test('late report source lists cannot cross app owner version or modal boundaries',async()=>{for(const change of [h=>h.c.state.app='two',h=>h.c.state.workspace.app.version++,h=>h.c.state.workspace.identity.principal='other',h=>h.nodes.get('#modal').open=false]){const h=fixture(),pending=[];h.c.api=()=>new Promise(r=>pending.push(r));const p=h.a.open();change(h);pending[0]({plans:[],reports:[]});pending[1]({monitors:[]});pending[2]({scopes:[]});await p;assert.equal(h.nodes.has('#owner-report-form'),false);}});
test('private report model projects measurements and uncertainty without raw secrets',()=>{const a=fixture().a,saved={id:'report',hash:'hash',report:{observed_at:'now',next_action:'Connect missing evidence',source_hash:'source',monitor:{status:'ACTIVE'},campaign:{retained_commitment_minor:80,currency:'CAD',provider_readback:'NOT_PERFORMED',receipts:[{id:'receipt',kind:'AD',status:'UNKNOWN',secret:'PRIVATE'}]},kpi_coverage:{available_rows:0,unknown_rows:1},kpis:{rows:[{metric:'Installs',observed:null,evidence:'No source'}]},selection:{measurement_window:{starts_at:'start',ends_at:'end'}},comparison:{status:'NO_COMPATIBLE_PREVIOUS_SNAPSHOT',previous_id:null,changes:[]},experiment:null,raw:'SECRET'}};const model=a.model(saved,{}),text=JSON.stringify(model);assert.doesNotMatch(text,/PRIVATE|SECRET/);assert.match(text,/not filtered/);assert.ok(model.notes.includes('Saved values for 0 of 1 evidence rows. 1 unknown.'));assert.match(text,/Reported spend is unavailable in this snapshot/);assert.match(a.markup(saved),/Saved values for 0 of 1 evidence rows/);assert.equal(model.metrics.at(-1).value,null);assert.match(text,/UNKNOWN/);});

test('pause readback survives projection with explicit effective uncertainty and escaped UI',()=>{
 const a=fixture().a;
 const receipt={id:'paid',kind:'AD',status:'PAUSED_campaign',pause_readback:{configured_status:'PAUSED',effective_status:'ACTIVE',observed_at:'2026-11-06T06:00:00Z',sha256:'retained-hash'},secret:'PRIVATE'};
 const saved={id:'report',hash:'hash',report:{observed_at:'now',next_action:'Review evidence',source_hash:'source',monitor:{status:'OFF'},campaign:{retained_commitment_minor:80,currency:'CAD',provider_readback:'NOT_PERFORMED',receipts:[receipt]},kpi_coverage:{available_rows:0,unknown_rows:1},kpis:{rows:[]},selection:{measurement_window:{starts_at:'start',ends_at:'end'}},comparison:{status:'NO_COMPATIBLE_PREVIOUS_SNAPSHOT',previous_id:null,changes:[]},experiment:null}};
 const notes=JSON.stringify(a.model(saved,{}));
 assert.match(notes,/configured PAUSED · effective ACTIVE/);assert.match(notes,/retained-hash/);assert.match(notes,/charges may arrive later/);assert.doesNotMatch(notes,/PRIVATE/);
 assert.match(a.markup(saved),/configured PAUSED · effective ACTIVE/);
 receipt.pause_readback.effective_status=null;
 assert.match(JSON.stringify(a.model(saved,{})),/effective Unavailable/);
 receipt.pause_readback.observed_at='<script>attack';
 assert.doesNotMatch(a.markup(saved),/<script>/);assert.match(a.markup(saved),/&lt;script>/);
 delete receipt.pause_readback; assert.match(a.markup(saved),/Local status alone does not establish provider confirmation/); assert.match(JSON.stringify(a.model(saved,{})),/Saved provider pause readback is unavailable/);
});
