const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
function load(path) {const holder={exports:{}};new Function('module',fs.readFileSync(path,'utf8'))(holder);return holder.exports;}
const growth=load(process.env.WMM_GROWTH_TEST_SOURCE || 'mission_control/static/growth-review.js');
const pages=load('mission_control/static/page-reporting.js');

function state() {
  return {app:'one',view:'results',workspaceObservedAt:'2026-10-23T00:00:00Z',workspace:{app:{id:'one',version:2,data:{name:'Synthetic Café 東京',release:'build-1',locale:'en-US',currency:'USD'}},subscription_growth:{app_id:'one',context:{manifest_version:2},source_hash:'c'.repeat(64),observed_at:'2026-10-23T00:00:00Z',history:{history:[]},journeys:[],experiments:[],issues:[],ads_sources:[],evidence_states:{local_evidence:{state:'RECORDED'},provider_verification:{state:'SEPARATE_ACCEPTANCE_REQUIRED',reason:'No approval'},outcomes:{state:'NOT_ESTABLISHED_BY_THIS_REVIEW',reason:'No causal growth'}}}}};
}
function listingRow() {
  return {id:'listing',hash:'a'.repeat(64),kind:'ASO_LISTING',created:'2026-10-22',data:{listing:{fields:{title:'Café 東京 <script>',description:'Original long description'},platform:'iOS'}},readout:{availability:'CURRENT_LOCAL_EVIDENCE',analysis:{status:'READY_FOR_REVIEW',fields:[{field:'title',characters:17,maximum_characters:30}],findings:[]}}};
}
function form(mode='listing') {
  const error={textContent:''},button={disabled:false};
  return {dataset:{app:'one',version:'2',id:'new-entry',mode,target:'listing'},isConnected:true,querySelector:selector=>selector.includes('submit')?button:error,error,button};
}
const values={platform:'iOS',locale:'en-US',release:'build-1',title:'Café 東京',subtitle:'Useful steps',keywords:'useful,steps',description:'Original',promotional_text:'Optional original',surface:'MANUAL_METADATA',test_fields:'title, subtitle'};

test('review, history and selected enforce app ownership and current manifest',()=>{
  const s=state();s.workspace.subscription_growth.history.history=[listingRow()];
  assert.equal(growth.selected(s,'listing').hash,'a'.repeat(64));
  assert.throws(()=>growth.selected(s,'other'));
  s.app='two';assert.throws(()=>growth.review(s));
  s.app='one';s.workspace.subscription_growth.context.manifest_version=1;assert.throws(()=>growth.history(s));
});
test('panel and historyList render guide, operational metrics, evidence states and recovery',()=>{
  const s=state();s.workspace.subscription_growth.history.history=[listingRow()];s.workspace.subscription_growth.issues=[{next_action:'Inspect source <safe>'}];
  const html=growth.panel(s);
  for(const text of ['Save a listing','Add benchmark source','Compare saved report','Report / Save PDF','Journey cohorts','No causal growth','Inspect source &lt;safe&gt;'])assert.ok(html.includes(text));
  assert.ok(growth.panel({...s,app:'two'}).includes('Retry workspace'));
  assert.equal(growth.metrics(s.workspace.subscription_growth)[0].value,1);
});
test('listingData preserves original localized text and supported store field sets',()=>{
  const apple=growth.listingData(values);
  assert.equal(apple.listing.fields.promotional_text,values.promotional_text);
  assert.equal(apple.listing.fields.title,values.title);
  assert.deepEqual(apple.listing.test_fields,['title','subtitle']);
  const android=growth.listingData({...values,platform:'Android'});
  assert.equal(android.listing.fields.short_description,values.subtitle);
  assert.equal(android.listing.fields.keywords,undefined);
  assert.equal(apple.listing.rule_version,'2026-10-22.v1');
});
test('referenceData freezes exact declared provenance and metric denominator without guessing units',()=>{
  const v={...values,metric:'CR',value:'0.2',percentile:'50',source_url:'https://synthetic.example/report',currency:'JPY',private_key:'PRIVATE_SENTINEL'};
  const data=growth.referenceData(v);
  assert.equal(data.reference.denominator,'TAPS');assert.equal(data.reference.value,0.2);
  assert.equal(data.reference.currency,'JPY');assert.equal(data.reference.private_key,undefined);
  assert.equal(data.reference.source_url,v.source_url);
});
test('comparisonData uses exact saved selectors and refuses caller totals or stale sources',()=>{
  const s=state(),r={...listingRow(),kind:'BENCHMARK_REFERENCE'};s.workspace.subscription_growth.history.history=[r];
  s.workspace.subscription_growth.ads_sources=[{job_id:'job',report_hash:'b'.repeat(64),state:'CURRENT_SAVED_SOURCE'}];
  const data=growth.comparisonData({reference_id:'listing',job_id:'job',metric:'CPT_MINOR',category:'Health',territory:'US',placement:'SEARCH_RESULTS',campaign_type:'GENERIC',numerator:999},s);
  assert.equal(data.reference_hash,r.hash);assert.equal(data.report_hash,'b'.repeat(64));assert.equal(data.numerator,undefined);
  s.workspace.subscription_growth.ads_sources[0].state='SOURCE_REVIEW_NEEDED';assert.throws(()=>growth.comparisonData({reference_id:'listing',job_id:'job'},s));
});
test('payload enforces app/version, preserves one identity and exact note target without approval',()=>{
  const s=state(),f=form();
  assert.equal(growth.payload(f,values,s).id,'new-entry');
  f.dataset.version='1';assert.throws(()=>growth.payload(f,values,s));f.dataset.version='2';f.dataset.app='two';assert.throws(()=>growth.payload(f,values,s));
  s.workspace.subscription_growth.history.history=[listingRow()];
  const note=growth.payload(form('note'),{decision:'KEEP',rationale:'Local bookkeeping'},s);
  assert.equal(note.kind,'EDITORIAL_NOTE');assert.equal(note.data.target_hash,'a'.repeat(64));assert.equal(note.data.approved,undefined);
});
test('openForm and labeled inputs provide scope, source hints and escaped public values',()=>{
  const s=state();let html='';const deps={state:s,uuid:()=> 'stable-id',modal:(_,value)=>html=value};
  growth.openForm('listing',deps);
  assert.ok(html.includes('data-app="one"'));assert.ok(html.includes('data-version="2"'));assert.ok(html.includes('Apple promotional text'));
  assert.ok(growth.input('x','Label','<bad>').includes('&lt;bad&gt;'));assert.ok(growth.select('x','Label',[['x','<bad>']]).includes('&lt;bad&gt;'));
  growth.openForm('reference',deps);assert.ok(html.includes('Source SHA256')||html.includes('source SHA256'));
  growth.openForm('comparison',deps);assert.ok(html.includes('before comparing'));
  assert.throws(()=>growth.openForm('unknown',deps));
});
test('entryNotes and report retain source metrics, Unicode and original long text without private state',()=>{
  const s=state(),row=listingRow();row.data.listing.fields.description='Long '.repeat(900)+'END_MARKER';
  s.workspace.subscription_growth.history.history=[row];s.private_key='PRIVATE_SENTINEL';s.workspace.credentials='PRIVATE_SENTINEL';
  const report=growth.report(s,pages,'listing');
  const html=pages.reportHTML(report,'http://127.0.0.1:1');
  assert.ok(html.includes('Café 東京'));assert.ok(html.includes('END_MARKER'));assert.ok(html.includes('limit 30'));
  assert.ok(!html.includes('<script>'));assert.ok(!html.includes('PRIVATE_SENTINEL'));
  assert.equal(report.filters.scope,'Exact saved item listing');assert.equal(report.cohorts.length,0);
});
test('referenceNotes, comparisonNotes and editorial entry reports retain unavailable differences and boundaries',()=>{
  const row={...listingRow(),kind:'BENCHMARK_COMPARISON',data:{reference_id:'ref',reference_hash:'a',job_id:'job',report_hash:'b',metric:'CPT_MINOR',projection:{observed:null}},readout:{availability:'STALE_APP_SCOPE',analysis:{status:'SOURCE_REVIEW_NEEDED',difference:null,reasons:['Refresh source']}}};
  assert.ok(growth.entryNotes(row).join(' ').includes('Unavailable'));
  assert.ok(growth.comparisonNotes(row).includes('Refresh source'));
  row.kind='EDITORIAL_NOTE';row.data={decision:'DEFER',rationale:'Review later',target_id:'ref',target_hash:'a'};
  assert.ok(growth.entryNotes(row).join(' ').includes('No approval authority'));
});
test('submit preserves errors and blocks repeated pending requests',async()=>{
  const f=form(),s=state();let calls=0,release;
  const wait=new Promise(resolve=>release=resolve);
  const deps={state:s,FormData:class {constructor(){return Object.entries(values)}},api:async()=>{calls++;await wait;throw new Error('Version changed');},refresh:async()=>{},close:()=>{},toast:()=>{}};
  const saving=growth.submit(f,deps);await growth.submit(f,deps);assert.equal(calls,1);assert.equal(f.button.disabled,true);
  release();await saving;assert.ok(f.error.textContent.includes('Inputs are preserved'));assert.equal(f.dataset.id,'new-entry');assert.equal(f.button.disabled,false);
});
test('submit never refreshes or closes another app after an in-flight save',async()=>{
  const f=form(),s=state();let refreshed=0,closed=0;
  const deps={state:s,FormData:class{constructor(){return Object.entries(values)}},api:async()=>{s.app='two';},refresh:async()=>refreshed++,close:()=>closed++,toast:()=>{}};
  await growth.submit(f,deps);assert.equal(refreshed,0);assert.equal(closed,0);
});
test('action delegates real reports, selected details, experiments and retry',async()=>{
  const s=state();s.workspace.subscription_growth.history.history=[listingRow()];let called='';
  const deps={state:s,modal:()=>called='detail',refresh:()=>called='refresh',openExperiment:()=>called='experiment',pageReports:{...pages,openReport:()=>called='report'},browser:{}};
  for(const action of ['detail','report','experiment','refresh']) {growth.action({dataset:{action:'growth-'+action,id:action==='refresh'?'':'listing'}},deps);assert.equal(called,action);}
});
