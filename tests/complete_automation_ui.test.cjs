const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const loaded={exports:{}};new Function('module',fs.readFileSync(path.join(__dirname,'../mission_control/static/complete-automation.js'),'utf8'))(loaded);const ui=loaded.exports;
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
