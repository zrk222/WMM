const test=require('node:test'),assert=require('node:assert/strict'),fs=require('./helpers/module-source.cjs'),vm=require('node:vm');
function fixture(){
 const calls=[],panels={},state={app:'one',workspace:{}},form={dataset:{app:'one',key:'request-one'},isConnected:true};
 const plan={source_hash:'a'.repeat(64),input_hash:'b'.repeat(64),scene:{width:720,height:1280,frame_rate:24,duration_seconds:8,scenes:[{start_seconds:0,end_seconds:8,words:8,words_per_second:1,density_advisory:'NO_FLAG'}]},readiness:{remediation:[]},reuse_candidates:{items:[{render_id:'saved',artifact_bytes:1024}],scanned:1,unavailable:0,truncated:false}};
 const context={state,document:{addEventListener(){}},api:async(path,body)=>{calls.push({path,body});return path.endsWith('hypit-plan')?plan:{render_id:'saved'};},esc:x=>String(x),json:JSON.stringify,notice:x=>x,button:(name,action)=>`<button type="button" data-action="${action}">${name}</button>`,modal:()=>{panels['#hypit-plan']={dataset:{app:'one'},isConnected:true};},$:s=>panels[s],toast(){},refresh:async()=>{}};
 vm.createContext(context);vm.runInContext(fs.readFileSync('mission_control/static/creative-rendering.mjs','utf8'),context);
 context.openRender=id=>{context.opened=id;};return {context,calls,form,plan,panels};
}
test('Hypit preflight shows a plan without submitting a build',async()=>{
 const f=fixture();await f.context.reviewHypitPlan(f.form,{brief_id:'brief',shape:'PORTRAIT'});
 assert.equal(f.calls.length,1);assert.match(f.calls[0].path,/hypit-plan$/);assert.equal(f.panels['#hypit-plan'].production.request_key,'request-one');
});
test('changed app or removed form cannot resurrect an asynchronous plan',async()=>{
 for(const mutate of [f=>f.context.state.app='two',f=>f.form.isConnected=false]){
  const f=fixture();mutate(f);await f.context.reviewHypitPlan(f.form,{});assert.equal(f.panels['#hypit-plan'],undefined);
 }
});
test('explicit reuse rechecks exact source then opens saved artifact without queueing',async()=>{
 const f=fixture();await f.context.reviewHypitPlan(f.form,{brief_id:'brief'});
 await f.context.renderingAction({dataset:{action:'render-reuse',id:'saved'},disabled:false});
 assert.equal(f.context.opened,'saved');assert.deepEqual(f.calls.map(c=>c.path.split('/').pop()),['hypit-plan','hypit-reuse']);assert.equal(f.calls[1].body.source_hash,f.plan.source_hash);
});
test('changed source between review and queue prevents render submission',async()=>{
 const f=fixture();await f.context.reviewHypitPlan(f.form,{});f.plan.source_hash='c'.repeat(64);
 await assert.rejects(f.context.renderingAction({dataset:{action:'render-plan-queue'},disabled:false}),/Production changed/);
 assert.equal(f.calls.length,2);assert.ok(f.calls.every(c=>!c.path.endsWith('hypit-renders')));
});
