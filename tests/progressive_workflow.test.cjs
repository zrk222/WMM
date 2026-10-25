const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const esc=s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
const context={esc,status:s=>`<span>${esc(s)}</span>`,button:(title,action)=>`<button data-action="${action}">${esc(title)}</button>`,resolutionButton:()=>'',heading:(a,b,c)=>`<h1>${a}</h1><p>${b}</p>${c}`,notice:s=>`<p>${s}</p>`,label:s=>s};
vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(__dirname,'../mission_control/static/guided-workflow.js'),'utf8'),context);
const guide=()=>({next_step:2,local_ready_count:1,next_action:{title:'Review current inputs'},steps:Array.from({length:12},(_,i)=>({id:i+1,title:`Stage ${i+1}`,description:'Purpose of stage',local_status:'NEEDS_INPUT',direct_needs:['Current source'],critical_findings:[],dependency_needs:[],verify:'Verify actual result',tools:[],primary:{id:'app',title:'Edit setup'},record_ids:[]}))});
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
test('all locally ready stages remain available without claiming execution completion',()=>{
 const g=guide();g.next_step=null;const html=context.guidedStageJourney(g);
 assert.equal((html.match(/id="workflow-step-/g)||[]).length,12);assert.ok(!html.includes('guided-all-stages'));
 const states=context.guidedEvidenceStates();for(const text of ['Inputs ready','Execution approved','Outcome observed','Missing results stay unknown'])assert.ok(states.includes(text));
 assert.ok(!/all.*complete|growth guaranteed/i.test(states));
});
