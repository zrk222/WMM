const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
function load(path){const holder={exports:{}};new Function('module',fs.readFileSync(path,'utf8'))(holder);return holder.exports;}
const customer=load(process.env.WMM_CUSTOMER_TEST_SOURCE||'mission_control/static/customer-workflow.js');
const pages=load('mission_control/static/page-reporting.js');
function data(){return {buyer:'Synthetic founder',micro_behavior:'Reconcile a first renewal',desired_outcome:'Find the missing step',release:'build-1',locale:'en-US',currency:'USD',prototype_test:'Observe task completion',sources:[{id:'source-one',url:'https://synthetic.example/source',content_sha256:'a'.repeat(64),observed_at:'2026-10-01T00:00:00Z',expires_at:'2026-12-01T00:00:00Z',availability:'AVAILABLE',excerpt:'Café 東京 needs a renewal report',evidence_type:'FIRSTHAND_COMPLAINT',frequency:'Weekly, supplied',impact:'Unmeasured'}],features:[{id:'feature-one',description:'Show the renewal step',source_ids:['source-one'],validation:'Observe a tester finding the missing step'}],excluded_features:[{feature:'CRM',reason:'Outside renewal reconciliation'}]};}
function row(){const value=data();return {id:'workflow-one',hash:'b'.repeat(64),created:'2026-10-22T00:00:00Z',imported:0,data:value,readout:{status:'HYPOTHESIS_READY_FOR_REVIEW',unavailable_source_ids:[],features:value.features.map(item=>({...item,state:'HYPOTHESIS_READY_FOR_REVIEW'}))}};}
function state(){return {app:'one',view:'results',workspace:{app:{id:'one',version:1,data:{name:'Synthetic Café 東京',release:'build-1',locale:'en-US',currency:'USD'}},subscription_growth:{app_id:'one',context:{manifest_version:1},observed_at:'2026-10-23T00:00:00Z',customer_workflows:{app_id:'one',source_hash:'c'.repeat(64),history:[row()]}}}};}
function values(draft){
  const result={};
  for(const key of ['buyer','micro_behavior','desired_outcome','release','locale','currency','prototype_test'])result[key]=draft[key];
  for(const kind of ['sources','features','excluded_features'])draft[kind].forEach((item,index)=>Object.entries(item).filter(([name])=>name!=='id').forEach(([name,value])=>result[kind+'.'+index+'.'+name]=value));
  return result;
}
class FormDataFixture{
  constructor(form){this.values=form.values;}
  get(name){return this.values[name]??null;}
  getAll(name){return this.values[name]||[];}
}
function form(){const draft=data(),error={textContent:''},button={disabled:false},fields={inert:false};return {dataset:{app:'one',version:'1',id:'new-workflow'},customerDraft:draft,values:values(draft),isConnected:true,error,button,fields,querySelector:selector=>selector.includes('submit')?button:selector==='#customer-draft-fields'?fields:error};}

test('context, history and selected reject foreign/stale/unavailable workspace',()=>{
  const s=state();assert.equal(customer.selected(s,'workflow-one').hash,'b'.repeat(64));
  assert.throws(()=>customer.selected(s,'missing'));
  s.app='two';assert.throws(()=>customer.context(s));s.app='one';s.workspace.app.version=2;assert.throws(()=>customer.history(s));
  s.workspace.app.version=1;s.workspace.subscription_growth.customer_workflows.app_id='two';assert.throws(()=>customer.context(s));
});
test('metrics, panel and historyList distinguish local assertions and repeated versions from demand',()=>{
  const s=state();const html=customer.panel(s);
  assert.ok(html.includes('Record customer workflow'));assert.ok(html.includes('Report / Save PDF'));assert.ok(html.includes('not unique customers'));
  assert.equal(customer.metrics([row()])[1].value,1);
  s.workspace.subscription_growth.customer_workflows.history[0].imported=1;
  assert.ok(customer.panel(s).includes('imported assertion'));
  assert.ok(customer.panel({...s,app:'two'}).includes('Retry workspace'));
  assert.ok(customer.historyList([]).includes('No workflows saved'));
});
test('newDraft creates stable source-feature links and revisions clone without overwriting old data',()=>{
  const s=state();let n=0;const fresh=customer.newDraft(s,()=> 'id-'+(++n));
  assert.deepEqual(fresh.features[0].source_ids,[fresh.sources[0].id]);assert.equal(fresh.release,'build-1');
  const revised=customer.newDraft(s,()=> 'other','workflow-one');revised.sources[0].excerpt='Changed draft';
  assert.notEqual(revised.sources[0].excerpt,customer.selected(s,'workflow-one').data.sources[0].excerpt);
  assert.deepEqual(revised.features[0].source_ids,['source-one']);
});
test('capture and payload construct only typed fields with exact repeated-source links',()=>{
  const f=form();f.values.credentials='PRIVATE_SENTINEL';
  assert.deepEqual(customer.capture(f,FormDataFixture),data());
  const packet=customer.payload(f,FormDataFixture,state());assert.equal(packet.id,'new-workflow');assert.equal(packet.manifest_version,1);
  assert.equal(JSON.stringify(packet).includes('PRIVATE_SENTINEL'),false);
  f.dataset.app='two';assert.throws(()=>customer.payload(f,FormDataFixture,state()));f.dataset.app='one';f.dataset.version='2';assert.throws(()=>customer.payload(f,FormDataFixture,state()));
});
test('addRow retains draft values and enforces source/feature/exclusion bounds',()=>{
  const draft=data();customer.addRow(draft,'source',()=> 'second');assert.equal(draft.sources[0].excerpt,data().sources[0].excerpt);
  customer.addRow(draft,'feature',()=> 'feature-two');assert.deepEqual(draft.features[1].source_ids,[]);
  customer.addRow(draft,'exclusion',()=> 'unused');assert.equal(draft.excluded_features.length,2);
  draft.sources=Array.from({length:100},(_,i)=>({...data().sources[0],id:'s-'+i}));assert.throws(()=>customer.addRow(draft,'source',()=> 'overflow'));
  draft.features=Array.from({length:20},()=>data().features[0]);assert.throws(()=>customer.addRow(draft,'feature',()=> 'overflow'));
  draft.excluded_features=Array.from({length:20},()=>data().excluded_features[0]);assert.throws(()=>customer.addRow(draft,'exclusion',()=> 'overflow'));
  assert.throws(()=>customer.addRow(draft,'unknown',()=> 'overflow'));
});
test('removeRow prunes only removed source links and leaves remaining feature identities stable',()=>{
  const draft=data();customer.addRow(draft,'source',()=> 'source-two');draft.features[0].source_ids.push('source-two');
  customer.removeRow(draft,'source','source-one');assert.deepEqual(draft.features[0].source_ids,['source-two']);assert.equal(draft.features[0].id,'feature-one');
  assert.throws(()=>customer.removeRow(draft,'source','source-two'));
  customer.addRow(draft,'feature',()=> 'feature-two');customer.removeRow(draft,'feature','feature-two');assert.equal(draft.features.length,1);
  customer.addRow(draft,'exclusion',()=> 'unused');customer.removeRow(draft,'exclusion','1');assert.equal(draft.excluded_features.length,1);
  assert.throws(()=>customer.removeRow(draft,'unknown','x'));
});
test('field, choice, sourceRows, featureRows and formHTML use explicit labels and escaped text',()=>{
  const draft=data();draft.sources[0].excerpt='<script>PRIVATE_TEXT</script>';
  const html=customer.formHTML(draft);
  for(const text of ['Inspected content SHA256','What observation would support or reject','Supporting observations for feature 1','Keep the scope small'])assert.ok(html.includes(text));
  assert.equal(html.includes('<script>'),false);assert.ok(html.includes('&lt;script&gt;'));
  assert.ok(customer.field('buyer','Buyer','<bad>',false,'Helpful').includes('aria-describedby'));
  assert.ok(customer.choice('x','Label','AVAILABLE',[['AVAILABLE','Available']]).includes('selected'));
});
test('openForm binds one immutable identity, current app version and mutable draft separate from reports',()=>{
  const s=state(),element={};let html='';customer.openForm({state:s,uuid:()=> 'new-id',modal:(_,value)=>html=value,document:{getElementById:()=>element}},'workflow-one');
  assert.ok(html.includes('data-id="new-id"'));assert.ok(html.includes('data-version="1"'));assert.ok(html.includes('customer-workflow-form'));
  assert.deepEqual(element.customerDraft,data());
});
test('editRows retains current form values and announces relinking without saving',()=>{
  const f=form(),message={textContent:'',focus(){this.focused=true;}};f.querySelector=selector=>selector==='#customer-draft-message'?message:f.fields;
  f.values.buyer='Edited while drafting';
  customer.editRows({dataset:{action:'customer-add-source'}},{document:{getElementById:()=>f},FormData:FormDataFixture,uuid:()=> 'second'});
  assert.equal(f.customerDraft.buyer,'Edited while drafting');assert.equal(f.customerDraft.sources.length,2);assert.equal(message.focused,true);
  f.dataset.pending='true';customer.editRows({dataset:{action:'customer-add-source'}},{document:{getElementById:()=>f}});assert.equal(f.customerDraft.sources.length,2);
});
test('entryNotes, sourceNotes and report preserve source-feature-exclusion lineage and explicit unverified claims',()=>{
  const s=state();s.private='PRIVATE_SENTINEL';s.workspace.credentials='PRIVATE_SENTINEL';
  const r=s.workspace.subscription_growth.customer_workflows.history[0];r.data.sources[0].excerpt='Café 東京 '+ 'Public words '.repeat(40)+'END_MARKER';
  const report=customer.report(s,pages,'workflow-one'),html=pages.reportHTML(report,'http://127.0.0.1:1');
  for(const text of ['Café 東京','END_MARKER','source-one','feature-one','Excluded: CRM','Demand verified: false','Paid behavior verified: false'])assert.ok(html.includes(text));
  assert.equal(html.includes('PRIVATE_SENTINEL'),false);assert.equal(report.metrics[0].value,1);assert.equal(report.filters.scope,'Exact saved workflow workflow-one');
  r.imported=1;r.readout.status='STALE_APP_SCOPE';assert.ok(customer.entryNotes(r).join(' ').includes('imported assertion'));assert.ok(customer.entryNotes(r).join(' ').includes('stale app scope'));
});
test('submit freezes draft editing, blocks duplicates and retains inputs after real errors',async()=>{
  const f=form();let calls=0,release;const waiting=new Promise(resolve=>release=resolve);
  const deps={state:state(),FormData:FormDataFixture,api:async()=>{calls++;await waiting;throw new Error('Source rejected');},refresh:async()=>{},close:()=>{},toast:()=>{}};
  const saving=customer.submit(f,deps);await customer.submit(f,deps);assert.equal(calls,1);assert.equal(f.fields.inert,true);
  release();await saving;assert.equal(f.fields.inert,false);assert.equal(f.button.disabled,false);assert.ok(f.error.textContent.includes('Inputs are preserved'));assert.equal(f.values.buyer,data().buyer);
});
test('submit cannot refresh or close another app after a pending save',async()=>{
  const f=form(),s=state();let refreshed=0,closed=0;
  await customer.submit(f,{state:s,FormData:FormDataFixture,api:async()=>{s.app='two';},refresh:async()=>refreshed++,close:()=>closed++,toast:()=>{}});
  assert.equal(refreshed,0);assert.equal(closed,0);
});
test('detail and action use selected app data, revision and scoped report services',()=>{
  const s=state();let invoked='';const deps={state:s,modal:()=>invoked='detail',refresh:()=>invoked='refresh',pageReports:{...pages,openReport:()=>invoked='report'},browser:{}};
  customer.action({dataset:{action:'customer-detail',id:'workflow-one'}},deps);assert.equal(invoked,'detail');
  customer.action({dataset:{action:'customer-report',id:'workflow-one'}},deps);assert.equal(invoked,'report');
  customer.action({dataset:{action:'customer-refresh'}},deps);assert.equal(invoked,'refresh');
  assert.throws(()=>customer.action({dataset:{action:'customer-unknown'}},deps));
});
