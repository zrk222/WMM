const test=require('node:test'),assert=require('node:assert/strict');
function load(path){const holder={exports:{}};new Function('module',require('node:fs').readFileSync(path,'utf8'))(holder);return holder.exports;}
global.WMMAuthorityExpiry=load('mission_control/static/authority-expiry.js');
const ui=load(process.env.WMM_CONTROL_SOURCE||'mission_control/static/agent-control.js');
const catalog={
 'workspace.read':{effect:'READ_PRIVATE_LOCAL_DATA',method:'GET'},'operations.read':{effect:'READ_LOCAL_POLICY',method:'GET'},'report.read':{effect:'READ_PRIVATE_LOCAL_DATA',method:'GET'},'measurement.read':{effect:'READ_PRIVATE_LOCAL_DATA',method:'GET'},'growth.read':{effect:'READ_PRIVATE_LOCAL_DATA',method:'GET'},'growth.history':{effect:'READ_PRIVATE_LOCAL_DATA',method:'GET'},'customer.history':{effect:'READ_PRIVATE_LOCAL_DATA',method:'GET'},'discovery.history':{effect:'READ_PRIVATE_LOCAL_DATA',method:'POST'},'discovery.read':{effect:'READ_PRIVATE_LOCAL_DATA',method:'POST'},'discovery.handoff':{effect:'READ_PRIVATE_LOCAL_DATA',method:'POST'},'hypit.read':{effect:'READ_PRIVATE_LOCAL_DATA',method:'GET'},'hypit.plan':{effect:'READ_PRIVATE_EXECUTION_PLAN',method:'POST'},'editor.list':{effect:'READ_PRIVATE_LOCAL_DATA',method:'GET'},'editor.read':{effect:'READ_PRIVATE_LOCAL_DATA',method:'GET'},'editor.renders':{effect:'READ_PRIVATE_LOCAL_DATA',method:'GET'},'media.sources':{effect:'READ_PRIVATE_LOCAL_DATA',method:'GET'},'jobs.read':{effect:'READ_PRIVATE_LOCAL_DATA',method:'GET'},'campaign.history':{effect:'READ_PRIVATE_LOCAL_DATA',method:'POST'},'campaign.status':{effect:'READ_PRIVATE_LOCAL_DATA',method:'POST'},'campaign.reconcile':{effect:'READ_OWNED_PROVIDER_STATUS',method:'POST'},
 'discovery.collect':{effect:'WRITE_LOCAL_EVIDENCE',method:'POST'},'discovery.review':{effect:'WRITE_LOCAL_EVIDENCE',method:'POST'},'creative.brief.save':{effect:'WRITE_LOCAL_PLAN',method:'POST'},'packaging.checklist':{effect:'READ_PRIVATE_LOCAL_DATA',method:'POST'},'hypit.queue':{effect:'QUEUE_LOCAL_PREPARATION',method:'POST'},'editor.edit':{effect:'WRITE_LOCAL_PLAN',method:'POST'},'editor.queue':{effect:'QUEUE_LOCAL_PREPARATION',method:'POST'},'organic-video.policy-read':{effect:'READ_PRIVATE_LOCAL_DATA',method:'POST'},'organic-video.policy-reserve':{effect:'RESERVE_APPROVED_LOCAL_GENERATION',method:'POST'},'organic-video.policy-admit':{effect:'ADMIT_OUTPUT_UNDER_EXACT_OWNER_POLICY',method:'POST'},'organic-video.claim':{effect:'WRITE_LOCAL_EVIDENCE',method:'POST'},'organic-video.submit':{effect:'WRITE_LOCAL_EVIDENCE',method:'POST'},'organic-video.workflow-prepare':{effect:'READ_PRIVATE_EXECUTION_PLAN',method:'POST'},'organic-video.intent-create':{effect:'PREPARE_ADMITTED_EXTERNAL_EFFECT',method:'POST'},'organic-video.intent-read':{effect:'READ_PRIVATE_LOCAL_DATA',method:'POST'},'organic-video.intent-execute':{effect:'PUBLISH_WITH_EXACT_ORGANIC_POLICY',method:'POST'},'growth.save':{effect:'WRITE_LOCAL_EVIDENCE',method:'POST'},'campaign.publish':{effect:'PUBLISH_WITH_STANDING_CAMPAIGN_AUTHORITY',method:'POST'},'campaign.ad-launch':{effect:'SPEND_WITH_STANDING_CAMPAIGN_AUTHORITY',method:'POST'},'campaign.pause':{effect:'PAUSE_OWNED_EXTERNAL_CAMPAIGN',method:'POST'},'experiment.evaluate':{effect:'WRITE_LOCAL_ASSESSMENT',method:'POST'},'experiment.action':{effect:'WRITE_LOCAL_DECISION',method:'POST'}
};
for(const n of Object.keys(ui.taskProfiles.meta.operations))catalog[n]||={effect:ui.taskProfiles.meta.operations[n],method:'POST'};
test('exactly three named presets plus Custom are declared',()=>{
 assert.deepEqual(Object.keys(ui.taskProfiles),['research','organic','meta']);
 const html=ui.grantForm(catalog);for(const [id,label] of [['research','Research only'],['organic','Organic marketing'],['meta','Bounded Meta media buyer']])assert.ok(html.includes(`value="${id}"`)&&html.includes(label));
 assert.match(html,/id="grant-task-profile" name="task_profile"/);assert.match(html,/data-task-summary role="status" aria-live="polite"/);assert.match(html,/<details data-task-advanced>/);assert.match(html,/value="20"/);assert.match(html,/Default: 20/);assert.match(html,/no automatic weekly refill/);assert.match(html,/Require independent review/);
});
test('research is checked against fixed explicit read effects and contains no writes',()=>{
 const profile=ui.taskProfiles.research,resolved=ui.resolveTaskProfile('research',catalog),read=new Set(['READ_PRIVATE_LOCAL_DATA','READ_LOCAL_POLICY','READ_PRIVATE_EXECUTION_PLAN','READ_PRIVATE_LOCAL_ARTIFACT','READ_OWNED_PROVIDER_STATUS']);
 assert.equal(resolved.available,true);assert.equal(resolved.selected.length,Object.keys(profile.operations).length);
 for(const [name,effect] of Object.entries(profile.operations)){assert.ok(read.has(effect));assert.equal(catalog[name].effect,effect);}
});

test('external effect and independent review explanations match the proposed capabilities',()=>{
 const form=new FormShim();ui.bindGrantPresets(form,catalog);form.changeProfile('organic');
 assert.match(form.summary.textContent,/policy-gated publication/);
 const html=ui.grantForm(catalog);
 assert.match(html,/without a checker, including publication or spending/);
 assert.match(html,/Exact campaign or organic-policy approval, accounts and budget still apply/);
 assert.doesNotMatch(html,/delegate that local write directly/);
});
test('missing or effect-changed required operations reject a profile as a whole',()=>{
 for(const [missingName,change] of [['hypit.plan',ops=>delete ops['hypit.plan']],['campaign.reconcile',ops=>ops['campaign.reconcile']={...ops['campaign.reconcile'],effect:'WRITE_LOCAL_EVIDENCE'}]]){
  const changed={...catalog};change(changed);const result=ui.resolveTaskProfile('research',changed);assert.equal(result.available,false);assert.ok(result.missing.some(item=>item.startsWith(`${missingName} `)));
 }
 assert.equal(ui.resolveTaskProfile('custom',{}).available,true);
});
class FormShim{
 constructor(){this.listeners={};this.summary={textContent:''};this.profile={value:'custom',listeners:{},addEventListener:(name,fn)=>this.profile.listeners[name]=fn};this.fields=Object.keys(catalog).map(value=>({name:'operations',value,checked:false}));this.reviews=Object.keys(catalog).filter(value=>catalog[value].method==='POST'&&!['READ_PRIVATE_LOCAL_DATA','READ_PRIVATE_EXECUTION_PLAN','READ_PRIVATE_LOCAL_ARTIFACT','READ_LOCAL_POLICY','READ_OWNED_PROVIDER_STATUS'].includes(catalog[value].effect)).map(value=>({name:'reviews',value,checked:true}));this.agent={value:'owner-entered-agent'};this.date={value:'2030-04-05T12:00'};}
 querySelector(selector){return selector==='#grant-task-profile'?this.profile:selector==='[data-task-summary]'?this.summary:null;}
 querySelectorAll(selector){const fields=selector.includes('reviews')?this.reviews:this.fields;return selector.includes(':checked')?fields.filter(field=>field.checked):fields;}
 addEventListener(name,fn){this.listeners[name]=fn;}
 changeProfile(value){this.profile.value=value;this.profile.listeners.change();}
 changeField(name){this.listeners.change({target:{name}});}
}
test('selection updates actual checkbox state and summary, preserves owner inputs, and makes no API calls',()=>{
 const form=new FormShim(),apiCalls=[];ui.bindGrantPresets(form,catalog);form.changeProfile('organic');
 const organic=ui.taskProfiles.organic;assert.deepEqual(form.fields.filter(field=>field.checked).map(field=>field.value).sort(),Object.keys(organic.operations).sort());
 assert.match(form.summary.textContent,/Organic marketing/);assert.match(form.summary.textContent,/never issues a grant/);assert.doesNotMatch(form.summary.textContent,/discovery\.collect|WRITE_LOCAL|READ_PRIVATE/);
 assert.ok(form.reviews.find(field=>field.value==='discovery.collect').checked);assert.ok(form.reviews.find(field=>field.value==='creative.brief.save').checked);assert.ok(!form.reviews.some(field=>field.value==='hypit.plan'));
 assert.equal(form.agent.value,'owner-entered-agent');assert.equal(form.date.value,'2030-04-05T12:00');assert.equal(apiCalls.length,0);
 form.fields.find(field=>field.value==='discovery.collect').checked=false;form.changeField('operations');assert.equal(form.profile.value,'custom');
 assert.ok(!form.fields.find(field=>field.value==='discovery.collect').checked);assert.match(form.summary.textContent,/28 selected operations/);assert.match(form.summary.textContent,/local evidence or plans/);assert.equal(apiCalls.length,0);
});
test('unavailable state remains Custom and never drops operations silently',()=>{
 const form=new FormShim(),changed={...catalog};delete changed['campaign.ad-launch'];ui.bindGrantPresets(form,changed);form.changeProfile('meta');
 assert.equal(form.profile.value,'custom');assert.match(form.summary.textContent,/unavailable/);assert.match(form.summary.textContent,/campaign.ad-launch/);assert.match(form.summary.textContent,/no operation was silently removed/);
});
test('issue body still requires an explicit available scope and defaults to 20 lifetime calls',()=>{
 const now=Date.now(),values={agent_id:'agent-one',expires_at:new Date(now+3600000).toISOString(),operations:['growth.read','growth.save'],reviews:['growth.save'],max_calls:'20'},saved={app:'sample',version:3};
 const result=ui.issueBody(values,catalog,saved,now);assert.equal(result.agent_id,'agent-one');assert.equal(result.max_calls,20);assert.deepEqual(result.operations,values.operations);assert.deepEqual(result.review_operations,['growth.save']);
 for(const bad of [{...values,operations:[]},{...values,operations:['missing.operation']},{...values,max_calls:'0'}])assert.throws(()=>ui.issueBody(bad,catalog,saved,now));
});
