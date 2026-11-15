const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('./helpers/module-source.cjs');
const path=require('node:path');
const load=source=>{const mod={exports:{}};new Function('module',fs.readFileSync(path.join(__dirname,'..',source),'utf8'))(mod);return mod.exports;};
const expiry=load('mission_control/static/authority-expiry.js');
globalThis.WMMAuthorityExpiry=expiry;
const agent=load('mission_control/static/agent-control.js');
const automation=load('mission_control/static/complete-automation.js');
const discovery=load('mission_control/static/discovery-model.js');
const organicModule={exports:{}};
new Function('module','globalThis',fs.readFileSync(path.join(__dirname,'../mission_control/static/organic-policy.js'),'utf8'))(organicModule,{WMMDiscoveryModel:discovery});
const organic=organicModule.exports;

const now=Date.UTC(2026,0,1,12);
const local=value=>expiry.localInput(new Date(value));

test('owner-selected expiry needs typed consent only beyond 24 hours and has no new horizon cap',()=>{
  assert.equal(expiry.validateExpiry(local(now+23*60*60*1000),false,now).extended,false);
  assert.throws(()=>expiry.validateExpiry(local(now+25*60*60*1000),false,now),/Explicit consent/);
  assert.equal(expiry.validateExpiry(local(now+3650*24*60*60*1000),true,now).extended,true);
  assert.throws(()=>expiry.validateExpiry(local(now-1),true,now),/future/);
  assert.throws(()=>expiry.validateExpiry(local(now+25*60*60*1000),true,now,local(now+26*60*60*1000)),/later than the current/);
});

test('grant and automation issuance preserve exact finite dates and include true consent only when extended',()=>{
  const operations={read:{method:'GET'},write:{method:'POST'}};
  const base={agent_id:'wmm-agent',operations:['read'],reviews:[],max_calls:'8'};
  const grant=agent.issueBody({...base,expires_at:local(now+48*60*60*1000),extended_expiry_consent:'on'},operations,{version:7},now);
  assert.equal(grant.expires,new Date(now+48*60*60*1000).toISOString());
  assert.equal(grant.extended_expiry_consent,true);
  const defaultGrant=agent.issueBody({...base,expires_at:local(now+12*60*60*1000)},operations,{version:7},now);
  assert.equal(Object.hasOwn(defaultGrant,'extended_expiry_consent'),false);

  const proposal=automation.proposal({agent_id:'wmm-agent',purpose:'review',workflows:['research'],agent_connection_id:'conn',social_connection_ids:[],expires_at:local(now+90*24*60*60*1000),extended_expiry_consent:'on',max_calls:'10',max_inflight:'1'},{version:3},now);
  assert.equal(proposal.limits.expires,new Date(now+90*24*60*60*1000).toISOString());
  assert.equal(proposal.extended_expiry_consent,true);
  assert.throws(()=>automation.proposal({agent_id:'wmm-agent',purpose:'review',workflows:['research'],expires_at:local(now+25*60*60*1000),max_calls:'10',max_inflight:'1'},{version:3},now),/Explicit consent/);
});

test('organic policy body includes owner consent for an exact long expiry',()=>{
  const context={app:{id:'app-one',version:2,hash:'a'.repeat(64)},review:{session_binding:'b'.repeat(64)},pages:[{binding:{version:1,config_version:1,data_hash:'c'.repeat(64)},connection_id:'page-connection',page_id:'page-one'}],eligible:{sources:[{id:'source-one',sha256:'d'.repeat(64),review_version:1}],claims:[{id:'claim-one',sha256:'e'.repeat(64)}]},approved_outputs:[{sha256:'f'.repeat(64)}],missing:[]};
  const value={request_id:'request-one',owner_version:1,page:'page-connection',mode:'EXACT',sources:['source-one'],claims:['claim-one'],outputs:['f'.repeat(64)],expiry:local(now+45*24*60*60*1000),currency:'USD',max_generations:'2',max_posts:'1',max_calls:'20',templates:[{id:'caption-one',caption:'Reviewed caption',claim_ids:['claim-one']}]};
  assert.throws(()=>organic.policyBody(context,value,now),/Explicit consent/);
  const body=organic.policyBody(context,{...value,extended_expiry_consent:true},now);
  assert.equal(body.policy.expires_at,new Date(now+45*24*60*60*1000).toISOString());
  assert.equal(body.policy.extended_expiry_consent,true);
});

test('extension review presents local and UTC dates, unchanged usage and dependent deadlines safely',()=>{
  const html=expiry.reviewMarkup({preview:{kind:'CAMPAIGN',id:'scope-1',old_expiry:'2026-01-02T00:00:00Z',new_expiry:'2026-01-04T00:00:00+00:00',usage:{calls:8,max_calls:20},bundle:[],dependent_deadlines:[{id:'child-1',expires:'2026-01-03T00:00:00Z'}]}},'a'.repeat(64));
  assert.match(html,/Current permission change review|Exact permission change/);
  assert.match(html,/Current usage, remaining allowances and earlier deadlines/);
  assert.match(html,/max_calls/);
  assert.match(html,/child-1/);
  assert.match(html,/remaining/);
  assert.match(html,/Preview SHA256/);
  assert.equal(expiry.receiptRows([{kind:'AGENT_GRANT',id:'g1',old_expiry:'a',new_expiry:'b',secret:'not shown'}])[0].secret,undefined);
});

test('all owner surfaces load one helper and expose owner expiry consent and extension hooks',()=>{
  const root=path.resolve(__dirname,'..');
  const index=fs.readFileSync(path.join(root,'mission_control/static/index.html'),'utf8');
assert.match(index,/<script type="module" src="\/dashboard\.mjs"><\/script>/);assert.equal((require('node:fs').readFileSync(require('node:path').join(__dirname,'../mission_control/static/feature-apis.mjs'),'utf8').match(/import ['"]\.\/authority-expiry\.js['"];/g)||[]).length,1);
  const agentText=fs.readFileSync(path.join(root,'mission_control/static/agent-control.js'),'utf8');
  const automationText=fs.readFileSync(path.join(root,'mission_control/static/complete-automation.js'),'utf8');
  const campaignText=fs.readFileSync(path.join(root,'mission_control/static/campaign-execution.mjs'),'utf8');
  const organicText=fs.readFileSync(path.join(root,'mission_control/static/organic-policy.js'),'utf8');
  for(const [source,kind] of [[agentText,'AGENT_GRANT'],[automationText,'AUTOMATION'],[campaignText,'CAMPAIGN'],[organicText,'ORGANIC_POLICY']]){
    assert.ok(source.includes(kind),`missing ${kind} binding`);
    assert.ok(source.includes('extended_expiry_consent'),`missing ${kind} consent field`);
    assert.ok(source.includes('Extend expiry'),`missing ${kind} active extension control`);
  }
  assert.match(campaignText,/authority-expiry\/preview|campaign-extend/);
  assert.match(organicText,/authority-expiry\/preview|expiryRequest/);
});
