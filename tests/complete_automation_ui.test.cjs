const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const loaded={exports:{}};new Function('module',fs.readFileSync(path.join(__dirname,'../mission_control/static/complete-automation.js'),'utf8'))(loaded);const ui=loaded.exports;
test('goal profiles are bounded form presets and keep campaign effects separately governed',()=>{
 assert.deepEqual(ui.profileWorkflows('research'),['local_evidence','experiment_preparation']);
 assert.deepEqual(ui.profileWorkflows('organic'),['local_evidence','pipeline_preparation','hypit_caption_render']);
 assert.deepEqual(ui.profileWorkflows('meta'),['local_evidence','pipeline_preparation','social_publish','paid_effects']);
 assert.deepEqual(ui.profileWorkflows('custom'),[]);
 assert.match(ui.automationProfiles.meta.description,/separate exact campaign scope/);
 assert.match(ui.automationProfiles.meta.description,/Verified delivery is separate from analytics/);
});
test('profile resolution checks the live catalog and selects only supported workflows',()=>{
 const resolved=ui.resolveAutomationProfile('organic',['local_evidence','pipeline_preparation','hypit_caption_render','social_publish']);
 assert.equal(resolved.available,true);
 assert.deepEqual(resolved.selected,['local_evidence','pipeline_preparation','hypit_caption_render']);
 assert.deepEqual(resolved.missing,[]);
});
test('manual workflow edits and missing catalog entries cannot silently expand a profile',()=>{
 const missing=ui.resolveAutomationProfile('meta',['local_evidence','pipeline_preparation','social_publish']);
 assert.equal(missing.available,false);
 assert.deepEqual(missing.selected,['local_evidence','pipeline_preparation','social_publish']);
 assert.deepEqual(missing.missing,['paid_effects']);
 assert.equal(ui.resolveAutomationProfile('custom',['paid_effects']).selected.length,0);
});
test('profiles never select account destinations or create authority',()=>{
 for(const definition of Object.values(ui.automationProfiles)){
  assert.equal('accounts' in definition,false);
  assert.equal('social_connection_ids' in definition,false);
 }
 assert.equal(ui.resolveAutomationProfile('meta',['local_evidence','pipeline_preparation','social_publish','paid_effects']).available,true);
});
test('setup copy keeps outcome, permission and agreement boundaries explicit',()=>{
 const source=fs.readFileSync(path.join(__dirname,'../mission_control/static/complete-automation.js'),'utf8');
 assert.match(source,/Start with the outcome you want/);
 assert.match(source,/does not publish, spend, or grant provider permission/);
 assert.match(source,/Review exact agreement/);
});
test('proposal contains exact chosen scope and finite zero-spend limits',()=>{
 const values={agent_id:'agent-one',purpose:'A specific purpose',workflows:['local_evidence'],agent_connection_id:'profile',social_connection_ids:[],hours:'1',max_calls:'20',max_inflight:'1',currency:'USD'};
 const proposal=ui.proposal(values,{version:2},0);assert.equal(proposal.selection.manifest_version,2);assert.equal(proposal.limits.spend_limit_minor,0);assert.equal(proposal.limits.expires,'1970-01-01T01:00:00.000Z');
 for(const change of [{hours:0},{hours:25},{max_calls:10001},{max_inflight:9},{workflows:[]}])assert.throws(()=>ui.proposal({...values,...change},{version:2},0));
});
test('status switch reads authority and keeps OFF usable when saved authority is blocked',()=>{
 assert.match(ui.statusMarkup({policies:[]}),/aria-checked="false"/);
 const html=ui.statusMarkup({policies:[{id:'scope',version:1,status:'ACTIVE',effective_status:'BLOCKED',repair:'Test connection',usage:{used:1,max_calls:2},summary:null,executions:[]}]});
 assert.match(html,/Switch automation OFF/);assert.match(html,/BLOCKED/);assert.match(html,/aria-checked="false"/);assert.ok(!html.includes('disabled'));
});
test('metadata reports exclude private operation bodies and arbitrary credential fields',()=>{
 const data={policies:[{id:'policy',version:1,effective_status:'ACTIVE',usage:{used:1,max_calls:2},summary:null,token:'PRIVATE_SECRET',executions:[{operation:'growth.read',status:'UNKNOWN',input_hash:'hash',result_hash:null,write_commits:0,input:'PRIVATE_INPUT',result:'PRIVATE_RESULT'}]}]};
 const model=ui.report(data,{}, {model:()=>({})});assert.equal(model.metrics[2].value,1);assert.ok(!JSON.stringify(model).includes('PRIVATE_'));assert.match(model.notes.join(' '),/Unconfirmed/);
});
test('owner launcher stays unavailable without current owner membership',()=>{
 const html=ui.panel({workspace:{identity:{principal:'agent'},access:{members:[]}}});assert.match(html,/disabled/);assert.match(html,/Sign in as the app owner/);
});
