const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('./helpers/module-source.cjs'),vm=require('node:vm'),path=require('node:path');
const esc=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const context={esc,status:s=>`<span>${esc(s)}</span>`,button:(title,action)=>`<button data-action="${action}">${esc(title)}</button>`,resolutionButton:()=>'',heading:(a,b,c)=>`<h1>${a}</h1><p>${b}</p>${c}`,notice:s=>`<p>${s}</p>`,label:s=>s};
vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(__dirname,'../mission_control/static/guided-workflow.mjs'),'utf8'),context);
const guide=()=>({next_step:2,local_ready_count:1,next_action:{title:'Review current inputs'},steps:Array.from({length:12},(_,i)=>({id:i+1,title:`Stage ${i+1}`,description:'Purpose of stage',local_status:'NEEDS_INPUT',direct_needs:['Current source'],critical_findings:[],dependency_needs:[],deliverable:'Reviewed stage packet',verify:'Verify actual result',tools:[],primary:{id:'app',title:'Edit setup'},record_ids:[]}))});
test('recommended stage appears before native disclosure and every other stage remains accessible',()=>{
 const g=guide(),html=context.guidedStageJourney(g),fold=html.indexOf('<details');
 assert.ok(html.indexOf('id="workflow-step-2"')<fold);
 assert.ok(html.indexOf('id="workflow-step-1"')>fold);
 for(let i=1;i<=12;i++)assert.equal((html.match(new RegExp(`id="workflow-step-${i}"`,'g'))||[]).length,1);
 assert.ok(html.includes('See the other 11 stages'));assert.ok(!html.includes('<details open'));
});
test('critical findings remain outside folded stages and source strings are escaped',()=>{
 const g=guide();g.steps[11].critical_findings=['<img src=x onerror=alert(1)>'];
 context.state={workspace:{workflow:g,worker:{}}};const html=context.guidedView();
 assert.ok(html.indexOf('Critical findings across')<html.indexOf('id="guided-all-stages"'));
 assert.ok(html.includes('&lt;img'));assert.ok(!html.includes('<img'));assert.ok(html.includes('Step 12'));
});
test('every stage shows purpose, needed input, delivered artifact and acceptance',()=>{
 const g=guide();g.steps[1].deliverable='<b>Prepared packet</b>';const html=context.guidedStageJourney(g);
 for(const label of ['Purpose','Needed input','Delivered artifact','Acceptance'])assert.ok(html.includes(`<dt>${label}</dt>`));
 assert.ok(html.includes('Purpose of stage'));assert.ok(html.includes('Current source'));assert.ok(html.includes('Verify actual result'));
 assert.ok(html.includes('&lt;b&gt;Prepared packet'));assert.ok(!html.includes('<b>Prepared packet'));
});

test('evidence-state legend uses the saved vocabulary and escapes it',()=>{
 const g=guide();g.evidence_states=[
  {id:'INPUTS_READY',title:'<img src=x>',detail:'Saved <b>fact</b>'},
  {id:'EXECUTION_APPROVED',title:'Execution approved',detail:'Approved detail'},
  {id:'OUTCOME_OBSERVED',title:'Outcome observed',detail:'Observed detail'}];
 context.state={workspace:{workflow:g}};const html=context.guidedEvidenceStates();
 assert.ok(html.includes('&lt;img src=x&gt;'));assert.ok(!html.includes('<img src=x>'));
 assert.ok(html.includes('&lt;b&gt;fact'));assert.ok(html.includes('onboarding, review and results'));
});

test('all locally ready stages remain available without claiming execution completion',()=>{
 const g=guide();g.next_step=null;const html=context.guidedStageJourney(g);
 assert.equal((html.match(/id="workflow-step-/g)||[]).length,12);assert.ok(!html.includes('guided-all-stages'));
 context.state={workspace:{workflow:g}};
 const states=context.guidedEvidenceStates();for(const text of ['Inputs ready','Execution approved','Outcome observed','Missing results stay unknown'])assert.ok(states.includes(text));
 assert.ok(!/all.*complete|growth guaranteed/i.test(states));
});

test('overview names chosen inputs, saved packet and exact next action without hiding stages',()=>{
 const g=guide();g.next_action.title='<img src=x>';context.state={workspace:{workflow:g}};const html=context.guidedOverviewPanel();
 assert.match(html,/You choose the app facts/);assert.match(html,/saved packet/);assert.match(html,/Continue: &lt;img/);assert.ok(!html.includes('<img'));assert.match(html,/See the complete workflow/);
});
