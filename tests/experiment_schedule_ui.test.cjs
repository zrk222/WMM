const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const all=fs.readFileSync('mission_control/static/app-results.js','utf8');
const section=all.slice(all.indexOf('function experimentSchedulePanel('),all.indexOf('function cohortForm('));
function fixture(){
 const state={app:'one',boot:{csrf:'csrf'},workspace:{app:{id:'one',version:3},identity:{status:'AUTHENTICATED',principal:'owner',expires_at_epoch:99999999},access:{members:[{principal:'owner',status:'ACTIVE',role:'OWNER',version:2}]},experiments:[{id:'e1',hash:'hash',state:'OBSERVING'}],schedules:[]}};
 const calls=[],dialogs=[];let action=async(url,body)=>{calls.push({url,body})};
 const c={state,Date,JSON,Number,Object,FormData:class{constructor(form){return Object.entries(form.values)}},esc:v=>String(v??''),status:v=>v,label:v=>v,notice:v=>v,button:v=>v,field:(n,v)=>`${n}:${v}`,modal:(title,html)=>dialogs.push({title,html}),api:(...args)=>action(...args)};
 vm.createContext(c);vm.runInContext(section,c);
 const form={isConnected:true,dataset:{app:'one',id:'e1',version:'',source:'hash',binding:JSON.stringify(c.experimentScheduleIdentity())},values:{enabled:'true',interval_hours:'24',expires_at:'2026-12-01T00:00:00Z',max_observations:'7'}};
 return {state,c,calls,dialogs,form,setApi(fn){action=fn}};
}
test('owner sees finite capacity and saves exact bounds',async()=>{
 const f=fixture();f.state.workspace.schedules=[{experiment_id:'e1',status:'ENABLED',enabled:true,version:1,interval_hours:24,failures:0,next_due:'2026-11-01T00:00:00Z',finite_limit:{remaining:2,max_observations:7,expires_at:'2026-12-01T00:00:00Z'}}];
 assert.match(f.c.experimentSchedulePanel(f.state.workspace.experiments[0]),/2 of 7 observations remaining/);
 await f.c.saveExperimentSchedule(f.form);assert.equal(f.calls.length,1);assert.equal(f.calls[0].body.max_observations,7);assert.equal(f.calls[0].body.manifest_version,3);assert.equal(f.calls[0].body.expires_at,'2026-12-01T00:00:00Z');
});
test('signed-out or non-owner cannot open the writable schedule',()=>{
 for(const change of [f=>f.state.workspace.identity.status='SIGNED_OUT',f=>f.state.workspace.access.members[0].role='MAKER']){const f=fixture();change(f);f.c.experimentScheduleForm('e1');assert.match(f.dialogs[0].title,/Owner access/);assert.equal(f.calls.length,0);}
});
test('stale app, owner, source or closed form cannot submit',async()=>{
 for(const change of [f=>f.state.app='two',f=>f.state.workspace.app.version++,f=>f.state.workspace.identity.principal='other',f=>f.state.workspace.access.members[0].version++,f=>f.state.workspace.experiments[0].hash='new',f=>f.form.isConnected=false]){const f=fixture();change(f);await assert.rejects(f.c.saveExperimentSchedule(f.form),/changed/);assert.equal(f.calls.length,0);}
});
test('duplicate submits are blocked and late identity changes do not auto-retry',async()=>{
 const f=fixture();let resolve;const pending=new Promise(r=>resolve=r);let count=0;f.setApi(async()=>{count++;await pending});
 const first=f.c.saveExperimentSchedule(f.form);await assert.rejects(f.c.saveExperimentSchedule(f.form),/already/);f.state.workspace.identity.principal='other';resolve();await assert.rejects(first,/changed/);assert.equal(count,1);
});
