/* Owner-operated app-sales workflows, exact request recovery and displayed exports. */
(function(root,factory){const value=factory(root.WMMFunnelModel||(typeof require==='function'?require('./funnel-model.js'):null));if(typeof module==='object'&&module.exports)module.exports=value;else root.WMMFunnels=value;})(globalThis,function(m){
 'use strict';
 let active=null;const writes=new Map();
 const scope=s=>({app:s.app,version:s.workspace?.app?.version,principal:s.workspace?.identity?.principal||null});
 const same=(a,b)=>m.equal(a,b);
 const valid=(t,d)=>active===t&&same(t.scope,scope(d.state))&&t.node.open;
 const base=t=>'/api/apps/'+encodeURIComponent(t.scope.app)+'/funnels';
 function clear(){active=null;}
 function invalidate(state){if(active&&!same(active.scope,scope(state)))clear();}
 function panel(){return `<section class="panel" id="funnel-panel"><p class="eyebrow">FROM ATTENTION TO APP VALUE</p><h2>See how your videos lead to app sales</h2><p>Connect a creative and a saved cohort to your app page, installs, onboarding, first value, purchases and renewals. Record what each source observed. WMM shows stage counts, comparable drop-off and existing subscription economics, then delivers a report you can save.</p><p>Start with a saved creative brief and an event-ledger cohort matching this app’s release, language and currency. Choose the stages and app capabilities that fit your product.</p>${m.button('Open app-sales funnels','open')}<p>Your inputs stay in this local app workspace. A saved plan does not publish content, spend money or change a live paywall.</p></section>`;}
 function show(d,title,kind,data,html,captured){
  d.modal(title,`<div class="modal-content funnel-workspace" tabindex="-1">${html}<p id="funnel-progress" role="status" aria-live="polite"></p><p id="funnel-error" class="field-error" role="alert"></p></div>`,'APP SALES');
  active={scope:captured||scope(d.state),kind,data,node:d.document.querySelector('#modal'),pending:false,unknown:null};
  active.node.scrollTop=0;active.node.querySelector('#modal-body').scrollTop=0;
  active.node.querySelector('.funnel-workspace')?.focus({preventScroll:true});return active;
 }
 function busy(t,value,message=''){
  t.pending=value;if(active!==t)return;
  t.node.querySelector('.funnel-workspace').setAttribute('aria-busy',String(value));t.node.querySelector('#funnel-progress').textContent=message;
  t.node.querySelectorAll('[data-funnel-write]').forEach(n=>n.disabled=value||Boolean(t.unknown));
 }
 function fail(t,d,error){if(valid(t,d))t.node.querySelector('#funnel-error').textContent=error.message+' Your entered work is preserved. Inspect app owner access, source freshness and the declared inputs before your next action.';}
 async function request(d,path,body){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),30000),method=body===undefined?'GET':'POST';let response,value;
  try{
   response=await (d.fetch||d.browser.fetch.bind(d.browser))(path,{method,credentials:'same-origin',redirect:'error',signal:controller.signal,...(body===undefined?{}:{headers:{'Content-Type':'application/json','X-CSRF-Token':d.state.boot?.csrf},body})});
   value=await response.json();
  }catch(cause){const e=new Error('The local response was not received or could not be read.');e.uncertain=method==='POST';throw e;}
  finally{clearTimeout(timer);}
  if(!response.ok){const e=new Error(value.error||'The funnel request was rejected.');e.uncertain=method==='POST'&&response.status>=500;throw e;}return value;
 }
 function pendingList(t){return [...writes.values()].filter(w=>same(w.scope,t.scope)).map(w=>`<p>${m.esc(w.state)} request ${m.esc(w.id)}. ${m.button('Inspect retained request','recover',w.id)}</p>`).join('');}
 function listHTML(t,page){
  const rows=page.items.map(r=>`<article class="next-step"><div><h3>${m.esc(r.outcome.milestone)}</h3><p>${m.esc(r.id)} · ${m.esc(r.cohort_id)} · ${m.esc(m.human(r.source_status))}</p>${m.button('Inspect stages and results','detail',r.id)}</div></article>`).join('');
  return `<p>Choose a saved funnel to inspect its source evidence and results, or define a new app-sales path. This page shows ${page.items.length} of ${page.total} saved plans from offset ${page.offset}.</p><div class="button-row">${m.button('Create app-sales funnel','new')}${m.button('Reload saved funnels','open')}</div>${pendingList(t)}${rows||'<p>No app-sales plans yet. Create a plan after preparing a current creative and a matching event-ledger cohort.</p>'}<div class="button-row">${page.offset?m.button('Previous plans','page',String(Math.max(0,page.offset-100))):''}${page.next_offset===null?'':m.button('Next plans','page',String(page.next_offset))}</div>`;
 }
 async function open(d,offset=0){
  const t=show(d,'Your app-sales funnels','loading',null,'<p>Reading saved app-sales plans...</p>');busy(t,true,'Reading current app evidence...');
  try{const page=await request(d,base(t)+'?offset='+m.integer(offset,'Page offset',0,10000));if(valid(t,d))show(d,'Your app-sales funnels','list',page,listHTML(t,page),t.scope);}catch(e){fail(t,d,e);}finally{busy(t,false);}
 }
 function outcomeFields(s){
  const f=m.input;
  return `<fieldset><legend>1. Name the app outcome</legend><div class="form-grid">${f('audience','Who is this app for?',s.facts.audience)}${f('pain','What specific problem does it solve?','','textarea')}${f('milestone','First useful task in the app',s.facts.activation)}${f('metric','Outcome metric name')}${f('target','Your target count','','number')}${f('due_at','Target date and time with timezone')}${m.select('research','Optional customer evidence (multiple)',s.research.map(r=>[r.id,r.id]),'',true)}</div></fieldset>`;
 }
 function connectionFields(s){
  const f=m.input;
  return `<fieldset><legend>2. Connect the creative and acquisition cohort</legend><div class="form-grid">${m.select('cohort_id','Saved acquisition cohort',s.cohorts.map(c=>[c.cohort_id,c.cohort_id+' / '+c.starts_at+' to '+c.ends_at]))}${m.select('creative','Current creative briefs (select one or more)',s.creatives.map(r=>[r.id,r.id+' / version '+r.version]),'',true)}${f('hook','Video opening hook','','textarea')}${f('cta','Call to action')}${f('destination','App or store destination URL','','url')}${m.select('route','Acquisition route',s.contract.routes.map(v=>[v,m.human(v)]),'APP_DOWNLOAD')}${f('method','How the source attributes results')}${f('identity_scope','Exact source identity scope')}${f('conversion_window_seconds','Conversion window in seconds','86400','number')}</div><p>The selected cohort supplies the exact acquisition dates. Counts must use the stated source identity scope; views are not linked people.</p></fieldset>`;
 }
 function planForm(s,id){
  const f=m.input;
  return `<form id="funnel-plan-form" data-id="${m.esc(id)}">${outcomeFields(s)}${connectionFields(s)}<fieldset><legend>3. Choose stages and actual app capabilities</legend><p>Open a stage to edit its ID, type, count unit and eligible population. Parent IDs must refer to earlier stages. After moving or removing a stage, update its affected parent references. One to32 stages.</p><div id="funnel-stage-list">${m.defaults().map((r,i)=>m.stageFields(r,i,s.contract)).join('')}</div>${m.button('Add stage','stage-add')}<div class="form-grid">${f('free_deliverables','What the free app includes (one item per line)','','textarea',false)}${f('paid_deliverables','What paid plans unlock (one item per line)','','textarea',false)}</div></fieldset><p>Saving freezes the selected sources, app setup and cohort. To revise a saved plan, create a new plan; original evidence stays retained.</p><button type="submit" class="button" data-funnel-write>Save app-sales plan</button></form>`;
 }
 async function newPlan(d){
  const t=show(d,'Build your app-sales path','loading',null,'<p>Loading the current app-sales input contract...</p>');
  try{const catalog=await request(d,'/api/apps/'+encodeURIComponent(t.scope.app)+'/agent-operations');if(!valid(t,d))return;
   const snapshot=m.sources(d.state,catalog.local_catalog.domain_contracts.app_sales_funnel);
   if(!snapshot.cohorts.length||!snapshot.creatives.length)throw new Error('Prepare a current creative brief and define a matching event-ledger cohort under Results, then reopen this form.');
   show(d,'Build your app-sales path','plan',snapshot,planForm(snapshot,d.uuid()),t.scope);
  }catch(e){fail(t,d,e);}
 }
 function stageRows(t){return [...t.node.querySelectorAll('[data-funnel-stage]')].map(node=>{const value=suffix=>node.querySelector(`[name$="-${suffix}"]`).value;return {id:value('id'),type:value('type'),label:value('label'),parents:value('parents').split(',').map(s=>s.trim()).filter(Boolean),unit:value('unit'),denominator_definition:value('denominator_definition')};});}
 function editStage(t,mode,index){
  const rows=stageRows(t);if(mode==='add'){if(rows.length>=32)throw new Error('Use at most32 stages.');rows.push({id:'stage-'+(rows.length+1),type:'ACTIVATION',label:'New app milestone',parents:[],unit:'UNIQUE_SUBJECTS',denominator_definition:''});index=rows.length-1;}
  else if(mode==='remove')rows.splice(index,1);
  else{const target=index+(mode==='up'?-1:1);if(target<0||target>=rows.length)return;[rows[index],rows[target]]=[rows[target],rows[index]];}
  t.node.querySelector('#funnel-stage-list').innerHTML=rows.map((r,i)=>m.stageFields(r,i,t.data.contract)).join('');
  const target=t.node.querySelectorAll('[data-funnel-stage]')[Math.min(index,rows.length-1)];if(target){target.open=true;target.querySelector('summary').focus();}
 }
 async function detail(d,id){
  const t=show(d,'Your app-sales stage results','loading',null,'<p>Reading the saved plan and complete stage report...</p>');
  try{const [saved,report]=await Promise.all([request(d,base(t)+'/'+encodeURIComponent(id)),request(d,base(t)+'/'+encodeURIComponent(id)+'/report')]);if(!valid(t,d))return;
   if(saved.hash!==report.definition_hash)throw new Error('The saved definition and report do not agree. Reload current evidence.');
   const html=m.results(saved,report)+`<div class="button-row">${m.button('Record stage observation','observe')}${m.button('Import JSON observations','batch')}${m.button('Inspect saved observations','observations','0')}${m.button('Reload stage results','detail',saved.id)}${m.button('Report / Save PDF','pdf')}${m.button('Download report JSON','json')}${m.button('Download stage CSV','csv')}${m.button('Back to saved funnels','open')}</div>`;
   show(d,'Your app-sales stage results','detail',{saved,report},html,t.scope);
  }catch(e){fail(t,d,e);}
 }
 function observationForm(saved){
  const p=saved.data.definition,f=m.input;
  return `<form id="funnel-observation-form"><p>Choose the saved stage, identify the exact source export and record what it observed. Population, unit, cohort and identity scope come from this immutable plan.</p><div class="form-grid">${m.select('stage_id','Saved funnel stage',p.stages.map(s=>[s.id,s.label+' / '+s.unit]))}${f('event_id','Stable event ID from the source')}${f('source_ref','Source export reference')}${f('source_sha256','Source export SHA256')}${f('starts_at','Observation start with timezone',p.attribution.starts_at)}${f('ends_at','Observation end with timezone',p.attribution.ends_at)}${f('observed_at','Source observed at, with timezone')}${m.select('coverage','Coverage', [['OBSERVED','Complete supplied observation'],['PARTIAL','Partial supplied observation'],['UNKNOWN','Unknown; count is not established']])}${f('count','Observed count (zero is valid)','','number')}</div><p>For Unknown coverage, WMM saves a null count regardless of the count field. Partial counts remain partial and do not create a complete conversion ratio.</p><button type="submit" class="button" data-funnel-write>Save stage observation</button></form>`;
 }
 function batchForm(saved){
  return `<form id="funnel-batch-form"><p>Paste one JSON array of1 to500 observations, up to1 MiB per request. Use exact saved stage IDs, populations, cohort and identity scope. Duplicate source/event identities must have identical content.</p><label class="field" for="funnel-batch-file">Optional local JSON file<input id="funnel-batch-file" type="file" accept=".json,application/json"></label>${m.input('observations','Observation JSON array','','textarea')}<details><summary>Exact observation fields and selected plan scope</summary><pre>${m.esc(JSON.stringify({fields:['event_id','stage_id','source_ref','source_sha256','cohort_id','starts_at','ends_at','observed_at','coverage','count','unit','denominator_definition','identity_scope'],definition:saved.data.definition},null,2))}</pre></details><p>The original JSON is validated by the server; duplicate keys and unknown fields are rejected. Raw input stays in the form if rejected.</p><button type="submit" class="button" data-funnel-write>Import observation batch</button></form>`;
 }
 function importForm(d,t,batch){
  const saved=t.data.saved;if(!saved)throw new Error('Open the saved funnel before recording observations.');
  show(d,batch?'Import source observations':'Record a stage observation',batch?'batch':'observation',{saved},batch?batchForm(saved):observationForm(saved),t.scope);
 }
 async function observations(d,t,offset){
  const saved=t.data.saved;if(!saved)throw new Error('Open the saved funnel first.');
  const page=await request(d,base(t)+'/'+encodeURIComponent(saved.id)+'/observations?offset='+m.integer(offset,'Observation page',0,10000));if(!valid(t,d))return;
  const rows=page.items.map(r=>r.data.observation),html=`<p>${page.items.length} of ${page.total} saved observations from offset ${page.offset}. Historical rows stay retained; the stage report uses the complete bounded history.</p>${m.valuesTable(rows,['Event','Stage','Count','Coverage','Source','Observed at'],r=>[r.event_id,r.stage_id,r.count??'Unknown',r.coverage,r.source_ref,r.observed_at])}<div class="button-row">${page.offset?m.button('Previous observations','observations',String(Math.max(0,page.offset-100))):''}${page.next_offset===null?'':m.button('Next observations','observations',String(page.next_offset))}${m.button('Back to stage results','detail',saved.id)}</div>`;
  show(d,'Saved stage observations','observations',{saved,page},html,t.scope);
 }
 function recoveryHTML(record){return `<p>Request ${m.esc(record.id)}: ${m.esc(record.state)}. WMM has not automatically resent it. Inspect saved evidence first; an explicit retry sends the identical immutable plan or source-event batch, which the server deduplicates.</p><details><summary>Inspect the exact retained local request</summary><pre>${m.esc(record.body)}</pre></details><div class="button-row">${m.button('Inspect retained request','recover',record.id)}${m.button('Reconcile saved evidence','reconcile',record.id)}${m.button('Retry exact retained request','retry',record.id)}${m.button('Back to saved funnels','open')}</div>`;}
 function recover(d,id){const record=writes.get(id);if(!record||!same(record.scope,scope(d.state)))throw new Error('The retained request belongs to different app or identity context. Inspect saved funnels.');const t=show(d,'Inspect an uncertain request','recovery',record,recoveryHTML(record),record.scope);if(record.state==='PENDING')busy(t,true,'The original request is still in flight.');return t;}
 function writeTicket(t,d,record){if(valid(t,d))return t;if(active?.kind==='recovery'&&active.data===record&&valid(active,d))return active;return null;}
 async function writeSuccess(t,d,record,result){
  const current=writeTicket(t,d,record);writes.delete(record.id);if(!current)return;
  d.toast('Local app-sales evidence saved. Inspect its stage results.');await detail(d,record.funnelId||result.id);
 }
 function writeFailure(t,d,record,e){
  record.state=e.uncertain?'UNKNOWN':'REJECTED';if(!e.uncertain)writes.delete(record.id);
  const current=writeTicket(t,d,record);if(!current)return;
  current.unknown=e.uncertain?record.id:null;fail(current,d,e);
  if(e.uncertain)current.node.querySelector('#funnel-error').insertAdjacentHTML('afterend',recoveryHTML(record));
 }
 async function sendWrite(d,t,record){
  if(!valid(t,d)||t.pending)throw new Error('Reopen this form under the same app owner context.');
  record.state='PENDING';writes.set(record.id,record);busy(t,true,'Saving exact local evidence...');
  try{const result=await request(d,record.path,record.body);await writeSuccess(t,d,record,result);}
  catch(e){writeFailure(t,d,record,e);}
  finally{const current=writeTicket(t,d,record);busy(t,false);if(current&&current!==t)busy(current,false);}
 }
 async function submit(form,d){
  const t=active;if(!t||!valid(t,d)||t.pending||t.unknown)return;
  try{const data=new d.FormData(form),values=Object.fromEntries(data);let body,path=base(t),funnelId=null;
   if(form.id==='funnel-plan-form')body=JSON.stringify(m.plan(values,name=>data.getAll(name),stageRows(t),t.data,form.dataset.id));
   else{const saved=t.data.saved;funnelId=saved.id;path+='/'+encodeURIComponent(saved.id)+'/observations';body=m.importBody(saved,t.scope.version,values,form.id==='funnel-batch-form'?values.observations:undefined);}
   await sendWrite(d,t,{id:d.uuid(),scope:m.copy(t.scope),path,body,funnelId,state:'PENDING'});
  }catch(e){fail(t,d,e);}
 }
 async function savedObservations(d,t,id){
  const rows=[];let offset=0;
  for(let i=0;i<=100;i++){if(!valid(t,d))throw new Error('App or identity context changed.');const page=await request(d,base(t)+'/'+encodeURIComponent(id)+'/observations?offset='+offset);rows.push(...page.items.map(r=>r.data.observation));if(page.next_offset===null)return rows;if(page.next_offset<=offset)throw new Error('Observation paging did not advance.');offset=page.next_offset;}
  throw new Error('Observation reconciliation exceeded the bounded history.');
 }
 async function reconcile(d,t){
  const record=t.data;if(record.state==='PENDING')throw new Error('Wait for the original request response before reconciling.');const wanted=JSON.parse(record.body);let confirmed;
  if(record.funnelId){const rows=await savedObservations(d,t,record.funnelId);confirmed=wanted.observations.every(w=>rows.some(r=>r.source_ref===w.source_ref&&r.event_id===w.event_id&&m.comparableObservation(r,w)));}
  else{const saved=await request(d,base(t)+'/'+encodeURIComponent(wanted.id));confirmed=m.comparablePlan(saved.data.definition,wanted.data)&&saved.data.manifest_version===wanted.manifest_version;}
  if(!valid(t,d))return;if(!confirmed)throw new Error('The complete retained request is not confirmed in saved evidence. Inspect it or explicitly retry the identical request.');writes.delete(record.id);d.toast('The exact retained request is confirmed in saved evidence.');await detail(d,record.funnelId||wanted.id);
 }
 function download(d,t,kind){
  const {saved,report}=t.data;if(!saved||!report)throw new Error('Reload the exact stage results before exporting.');
  const text=kind==='csv'?m.csv(saved,report):JSON.stringify(m.exportData(saved,report),null,2),mime=kind==='csv'?'text/csv;charset=utf-8':'application/json';
  const url=d.browser.URL.createObjectURL(new d.browser.Blob([text],{type:mime})),a=d.document.createElement('a');try{a.href=url;a.download=t.scope.app+'-'+saved.id+'-funnel.'+kind;a.click();}finally{d.browser.URL.revokeObjectURL(url);}
 }
 async function change(node,d){
  const t=active;if(!t||!valid(t,d))return;
  if(node.name==='coverage'){const count=t.node.querySelector('[name="count"]');count.disabled=node.value==='UNKNOWN';count.required=!count.disabled;return;}
  if(node.id!=='funnel-batch-file')return;
  try{const file=node.files[0];if(!file||file.size>1048576)throw new Error('Choose a JSON file up to1 MiB.');const text=await file.text();if(valid(t,d))t.node.querySelector('[name="observations"]').value=text;}catch(e){fail(t,d,e);}
 }
 async function action(node,d){
  const mode=node.dataset.action.slice(7),id=node.dataset.id||'';
  try{
   const entries={open:()=>open(d),page:()=>open(d,id),new:()=>newPlan(d),detail:()=>detail(d,id),recover:()=>recover(d,id)};
   if(entries[mode])return await entries[mode]();
   const t=active;if(!t||!valid(t,d))throw new Error('Reopen the selected app funnel.');if(t.pending)return;
   return await activeAction(mode,id,t,d);
  }catch(e){if(active)fail(active,d,e);}
 }
 async function activeAction(mode,id,t,d){
  if(mode.startsWith('stage-'))return editStage(t,mode.slice(6),Number(id));
  const actions={observe:()=>importForm(d,t,false),batch:()=>importForm(d,t,true),observations:()=>observations(d,t,id),pdf:()=>d.pageReports.openReport(m.printable(t.data.saved,t.data.report,d.pageReports,d.state),d.browser),json:()=>download(d,t,'json'),csv:()=>download(d,t,'csv'),reconcile:()=>reconcileAction(d,t,id),retry:()=>retryAction(d,t,id)};
  if(!actions[mode])throw new Error('Unknown app-sales action.');return actions[mode]();
 }
 function reconcileAction(d,t,id){const record=writes.get(id);if(!record)throw new Error('No retained request remains. Reload saved funnels.');return reconcile(d,t.kind==='recovery'?t:recover(d,id));}
 function retryAction(d,t,id){const r=writes.get(id);if(!r||r.state!=='UNKNOWN'||!same(r.scope,scope(d.state)))throw new Error('Only an uncertain identical request in the current context can be retried.');t.unknown=null;return sendWrite(d,t,r);}
 return {scope,same,valid,base,clear,invalidate,panel,show,busy,fail,request,pendingList,listHTML,open,outcomeFields,connectionFields,planForm,newPlan,stageRows,editStage,detail,observationForm,batchForm,importForm,observations,recoveryHTML,recover,writeTicket,writeSuccess,writeFailure,sendWrite,submit,savedObservations,reconcile,download,change,action,activeAction,reconcileAction,retryAction};
});
