const test=require('node:test'),assert=require('node:assert/strict');
function load(path){const holder={exports:{}};new Function('module',require('node:fs').readFileSync(path,'utf8'))(holder);return holder.exports;}
const ui=load(process.env.WMM_CONTROL_SOURCE||'mission_control/static/agent-control.js');
const reports=load('mission_control/static/page-reporting.js');
const state=()=>({app:'sample-one',workspace:{app:{id:'sample-one',version:1,data:{name:'Synthetic Café 東京'}},identity:{principal:'github:2'},access:{members:[{principal:'github:2',role:'CHECKER',status:'ACTIVE'}]}}});
test('setup front door uses exact local origin, discoverable modules and explicit grant boundaries',()=>{
 const html=ui.setupMarkup('http://127.0.0.1:9234');
 for(const expected of ['<details','<summary>','mission_control.agent_setup --origin http://127.0.0.1:9234','mission_control.agent_cli catalog','mission_control.agent_mcp --origin http://127.0.0.1:9234 --use-grant','WMM_AGENT_GRANT','trusted local session','never falls back'])assert.ok(html.includes(expected),expected);
 for(const origin of ['https://attacker.test','http://127.0.0.1:8765/<script>','http://127.0.0.1:65536']){
  const rejected=ui.setupMarkup(origin);assert.ok(!rejected.includes('mission_control.agent_mcp'));assert.ok(!rejected.includes('<script>'));
 }
});
const checkpoint=()=>({id:'review-one',input_hash:'a'.repeat(64),envelope:{operation:'growth.save',input:{private:'PRIVATE_SENTINEL'}},checkpoint:{state:'WAITING_REVIEW',revision:1,hash:'b'.repeat(64),checker:null,packet:{maker:'github:1',agent_id:'agent-one',expires:'2030-01-01'},history:[{state:'WAITING_REVIEW',observed_at:'2026-10-23',evidence_hash:null}]},result:{secret:'PRIVATE_SENTINEL'}});
test('app version and identity are bound before mutation',()=>{
 const s=state(),saved=ui.scope(s);assert.doesNotThrow(()=>ui.requireScope(saved,s));
 for(const mutate of [s=>s.app='sample-two',s=>s.workspace.app.version++,s=>s.workspace.identity.principal='github:3']){const copy=state();mutate(copy);assert.throws(()=>ui.requireScope(saved,copy));}
});
test('distinct checker can approve, maker cannot self approve',()=>{
 const s=state(),v=checkpoint();assert.equal(ui.permissions(v,s).approve,true);
 v.checkpoint.packet.maker='github:2';assert.equal(ui.permissions(v,s).approve,false);
});
test('revoked checker and terminal request cannot approve',()=>{
 const s=state(),v=checkpoint();s.workspace.access.members[0].status='REVOKED';assert.equal(ui.permissions(v,s).approve,false);
 s.workspace.access.members[0].status='ACTIVE';v.checkpoint.state='SUCCEEDED';assert.equal(ui.permissions(v,s).approve,false);
});
test('running cancellation needs maker checker or owner; uncertainty needs distinct checker',()=>{
 const s=state(),v=checkpoint();v.checkpoint.state='RUNNING';assert.equal(ui.permissions(v,s).cancel,false);
 v.checkpoint.checker='github:2';assert.equal(ui.permissions(v,s).cancel,true);
 v.checkpoint.state='UNKNOWN';assert.equal(ui.permissions(v,s).reconcile,true);
 v.checkpoint.packet.maker='github:2';assert.equal(ui.permissions(v,s).reconcile,false);
});
const operations={'growth.read':{method:'GET'},'growth.save':{method:'POST'},'customer.save':{method:'POST'}};
const values=()=>({agent_id:'agent-one',operations:['growth.read','growth.save'],reviews:['growth.read','growth.save','customer.save'],hours:'1',max_calls:'20'});
test('grant selects only allowed writes for review with exact scope limits',()=>{
 const result=ui.issueBody(values(),operations,ui.scope(state()),0);
 assert.deepEqual(result.review_operations,['growth.save']);assert.equal(result.manifest_version,1);assert.equal(result.max_calls,20);assert.equal(result.expires,'1970-01-01T01:00:00.000Z');
});
test('empty unsupported operation or invalid quota and expiry rejected',()=>{
 for(const patch of [{operations:[]},{operations:['human.approve']},{hours:'0'},{hours:'25'},{hours:'bad'},{max_calls:'1.5'},{max_calls:'10001'}])assert.throws(()=>ui.issueBody({...values(),...patch},operations,ui.scope(state()),0));
});
test('token delivery never serializes secret into markup',()=>{
 const markup=ui.tokenMarkup({token:'PRIVATE_SENTINEL',grant:{id:'one',expires:'later',max_calls:3}});
 assert.ok(!markup.includes('PRIVATE_SENTINEL'));assert.ok(markup.includes('type="password"'));assert.ok(!markup.includes('value='));
});
test('queue and exact markup escape untrusted payloads',()=>{
 const v=checkpoint();v.envelope.input.private='<script>bad</script>';
 const markup=ui.detailMarkup(v,state());assert.ok(!markup.includes('<script>'));assert.ok(markup.includes('&lt;script&gt;'));
 const queue=ui.queueMarkup({items:[{...v,id:'<img>',operation:'growth.save'}],total:101,offset:0,next_offset:100});
 assert.ok(queue.includes('data-offset="100"'));assert.ok(!queue.includes('<img>'));
});
test('exact report includes hashes history and Unicode without raw input result or state',()=>{
 const s=state(),v=checkpoint();s.secret='PRIVATE_SENTINEL';
 const report=ui.report({scope:ui.scope(s),kind:'detail',data:v},s,reports),raw=JSON.stringify(report);
 assert.ok(raw.includes('Café 東京'));assert.ok(raw.includes(v.checkpoint.hash));assert.ok(!raw.includes('PRIVATE_SENTINEL'));assert.equal(report.metrics[0].value,1);
});
test('grant and queue reports whitelist metadata',()=>{
 const s=state(),saved=ui.scope(s);
 for(const [kind,data] of [['grants',{grants:[{agent_id:'agent-one',status:'ACTIVE',used:1,max_calls:3,operations:['growth.read'],review_operations:[],token:'PRIVATE_SENTINEL'}]}],['queue',{items:[{id:'one',operation:'growth.save',state:'APPROVED',checkpoint_hash:'a'.repeat(64),envelope:{private:'PRIVATE_SENTINEL'}}],total:101,offset:100}]]){
 const report=ui.report({scope:saved,kind,data},s,reports);assert.ok(!JSON.stringify(report).includes('PRIVATE_SENTINEL'));assert.ok(report.metrics.length);
 }
});
test('credential forms do not export and changed scope invalidates reports',()=>{
 const s=state(),saved=ui.scope(s);assert.throws(()=>ui.report({scope:saved,kind:'token',data:{}},s,reports));
 s.app='sample-two';assert.throws(()=>ui.report({scope:saved,kind:'detail',data:checkpoint()},s,reports));
});
test('only app owner sees grant management',()=>{
 const s=state();assert.ok(!ui.panel(s).includes('Manage agent grants'));s.workspace.access.members[0].role='OWNER';assert.ok(ui.panel(s).includes('Manage agent grants'));
 s.workspace.identity={};assert.ok(ui.panel(s).includes('disabled'));
});
