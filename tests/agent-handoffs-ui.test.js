import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

test('handoff view shows original job, digest and bounded authority without injecting markup', async () => {
  let rendered='';
  const saved={id:'handoff-one',job_action:'pipeline',job_status:'RUNNING',status:'READY',effective_status:'READY',recipient:'<replacement>',
    job_id:'job-one',request_key_hash:'digest-only',context:{app_version:3,resources:{unverified_field_count:1}},created:'2026-01-01',expires:'2026-01-02',
    context_status:'CURRENT',context_changes:[],next_action:'Inspect before retry'};
  const escape=value=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
  const context={document:{querySelector:()=>({addEventListener:()=>{}})},
    state:{app:'sample-one',workspace:{jobs:[{id:'job-one',action:'pipeline',status:'RUNNING'}],
      agent_operations:{local_catalog:{operations:{'jobs.read':{},'handoff.create':{}}}}}},
    esc:escape,button:(label,action,extra='')=>`<button data-action="${action}" ${extra}>${escape(label)}</button>`,
    api:async url=>url.endsWith('handoff-list')?{handoffs:[saved]}:url.endsWith('agent-operations')?{local_catalog:{operations:{'jobs.read':{},'handoff.create':{}}}}:{grants:[{agent_id:'replacement',status:'ACTIVE'}]},
    modal:(title,html)=>{rendered=html;}};
  vm.createContext(context);
  vm.runInContext(fs.readFileSync('mission_control/static/agent-access.js','utf8'),context);
  await context.agentHandoffs();
  assert.match(rendered,/job-one/);assert.match(rendered,/digest-only/);
  assert.match(rendered,/&lt;replacement&gt;/);assert.doesNotMatch(rendered,/<replacement>/);
  assert.match(rendered,/never starts work/);assert.doesNotMatch(rendered,/value="handoff.create"/);
});
