const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function fixture(goal='measurement'){
 const calls=[],state={app:'one',goalChoice:{app:'one',id:goal},workspace:{app:{id:'one',version:2,data:{}},workflow:{steps:Array.from({length:12},(_,i)=>({id:i+1}))},preparation:{source_hash:'source',ready_count:1,outputs:Array.from({length:12},(_,i)=>({stage:i+1,status:'BLOCKED',missing:['<unsafe>'],packet:{title:'<Title '+(i+1)+'>',operations:{tasks:['<task>']}}}))}}};
 const esc=v=>String(v).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
 const c={state,esc,json:v=>esc(JSON.stringify(v)),notice:esc,button:(s,a,d='')=>`<button data-action="${a}" ${d}>${esc(s)}</button>`,modal:(...a)=>calls.push(['modal',...a]),download:(...a)=>calls.push(['download',...a]),localStorage:{getItem:()=>null},document:{querySelector:()=>null,addEventListener:()=>{}}};
 vm.createContext(c);for(const f of ['guided-workflow.js','automatic-preparation.js'])vm.runInContext(fs.readFileSync('mission_control/static/'+f,'utf8'),c);
 c.guidedNavigate=v=>calls.push(['navigate',v]);c.guidedOpenTool=v=>calls.push(['tool',v]);c.campaignOpen=()=>calls.push(['campaign']);
 const p=vm.runInContext('WMMGoalPacket',c);const node=action=>({dataset:{action,app:'one',version:'2',goal:p.model().goal,sourceHash:'source'}});return {p,c,state,calls,node};
}
test('all four goals retain only fixed evidence subsets, escaped drafts and existing next routes',()=>{
 for(const [goal,stages,route] of [['research',[5,6],'sources'],['creative',[6],'research'],['campaign',[7],'campaign'],['measurement',[3,4,10,11],'results']]){
 const h=fixture(goal),m=h.p.model();assert.deepEqual(Array.from(m.outputs,x=>x.stage),stages);h.p.open(h.node('automatic-goal-open'));assert.match(h.calls[0][2],/LOCAL|Local/);assert.ok(!h.calls[0][2].includes('<unsafe>'));assert.ok(!h.calls[0][2].includes('<Title'));assert.match(h.calls[0][2],/<details>/);assert.match(h.calls[0][2],/automatic-open/);
 h.p.action(h.node('automatic-goal-download'));const saved=h.calls[1][2];assert.equal(saved.app_id,'one');assert.equal(saved.manifest_version,2);assert.equal(saved.source_hash,'source');assert.deepEqual(Array.from(saved.outputs,x=>x.stage),stages);h.p.action(h.node('automatic-goal-next'));assert.equal(h.calls[2].at(-1),route);
 }
});
test('stale app version goal and evidence fail before navigation download or opening',()=>{for(const action of ['automatic-goal-open','automatic-goal-download','automatic-goal-next'])for(const field of ['app','version','goal','sourceHash']){const h=fixture(),n=h.node(action);n.dataset[field]='wrong';assert.throws(()=>h.p.action(n));assert.equal(h.calls.length,0);}});
test('no goal is explicit and cannot download or navigate; missing outputs stay unknown',()=>{const h=fixture('');h.p.open(h.node('automatic-goal-open'));assert.match(h.calls[0][2],/Choose a goal/);assert.ok(!h.calls[0][2].includes('automatic-goal-download'));assert.throws(()=>h.p.action(h.node('automatic-goal-next')));const m=fixture();m.state.workspace.preparation.outputs=[];assert.ok(m.p.model().outputs.every(x=>x.output===null));assert.match(m.p.view(m.p.model()),/UNKNOWN/);});
test('generic advanced workflow still renders all twelve and retains its download',()=>{const h=fixture();h.c.stagePacketCard=o=>`stage-${o.stage};`;h.c.openAutomaticPreparation();assert.match(h.calls[0][2],/1 of 12/);for(let i=1;i<=12;i++)assert.ok(h.calls[0][2].includes(`stage-${i};`));assert.match(h.calls[0][2],/automatic-download/);});
test('missing workflow bindings and malformed outputs stay unknown; absent evidence cannot download',()=>{
 for(const change of [h=>h.state.workspace.workflow.steps=[],h=>h.state.workspace.preparation.outputs.forEach(o=>o.packet=null),h=>h.state.workspace.preparation.outputs.forEach(o=>o.status=null)]){const h=fixture();change(h);assert.ok(h.p.model().outputs.every(o=>o.output===null));assert.match(h.p.view(h.p.model()),/UNKNOWN/);assert.throws(()=>h.p.action(h.node('automatic-goal-download')));assert.equal(h.calls.length,0);}
 const h=fixture();h.state.workspace.preparation.source_hash='';const n=h.node('automatic-goal-download');n.dataset.sourceHash='';assert.throws(()=>h.p.action(n));assert.equal(h.calls.length,0);
});
test('legacy first packet click never synthesizes a fresh binding',async()=>{const h=fixture();await assert.rejects(h.c.automaticPreparationAction({dataset:{action:'automatic-open',firstPacket:'true'}}));assert.equal(h.calls.length,0);});
