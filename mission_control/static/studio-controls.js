/* Human inspector over the same protected Studio manager used by agents. */
(function(root,factory){const value=factory();if(typeof module==='object'&&module.exports)module.exports=value;else root.WMMStudio=value;})(typeof globalThis==='object'?globalThis:this,function(){
 'use strict';
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const json=v=>esc(JSON.stringify(v,null,2));
 const button=(text,action,extra='')=>`<button type="button" class="button outline" data-action="studio-${action}" ${extra}>${esc(text)}</button>`;
 let active=null;
 function clear(){active=null;}
 function scope(state){return {app:state.app,version:state.workspace?.app?.version,principal:state.workspace?.identity?.principal||null};}
 function same(a,b){return a.app===b.app&&a.version===b.version&&a.principal===b.principal;}
 function invalidate(state){if(active&&!same(active.scope,scope(state)))clear();}
 function valid(t,d){return active===t&&same(t.scope,scope(d.state))&&t.node.open;}
 function show(d,title,kind,data,html,captured){
  const selected=captured||scope(d.state);
  d.modal(title,`<div class="modal-content studio-controls" tabindex="-1">${html}<p id="studio-error" class="field-error" role="alert"></p></div>`);
  active={scope:selected,kind,data,node:d.document.querySelector('#modal'),pending:false,uncertain:false,loadedAt:new Date().toISOString()};
  active.node.querySelector('.studio-controls')?.focus();return active;
 }
 function panel(){return `<section class="panel" aria-label="Hypit Studio controls"><p class="eyebrow">SHAPE YOUR MESSAGE</p><h2>Customize a Hypit composition</h2><p>Open an approved caption composition, inspect its live text and appearance controls, and save a precise change. You and your agent use the same session and source history.</p><p>Choose a saved Hypit source below. WMM shows the exact local startup summary before you start. Sign in under Activity &amp; reviews with this app's OWNER role to use Studio. Changes stay in the private project; edited-project MP4 export and isolated live preview remain unfinished.</p>${button('Open Studio sessions','open')}</section>`;}
 async function request(d,t,action,body={},id=null){
  const base='/api/apps/'+encodeURIComponent(t.scope.app)+'/studio/';
  const path=base+(id?encodeURIComponent(id)+'/':'')+action;
  const send=d.fetch||d.browser.fetch.bind(d.browser);
  let response;
  try{response=await send(path,{method:'POST',credentials:'same-origin',redirect:'error',headers:{'Content-Type':'application/json','X-CSRF-Token':d.state.boot?.csrf},body:JSON.stringify(body)});}
  catch(e){const error=new Error('The local response was not received. Inspect saved session state before another change.');error.uncertain=['start','edit','close'].includes(action);throw error;}
  let result;
  try{result=await response.json();}catch(e){const error=new Error('The local response could not be read. Inspect saved session state.');error.uncertain=['start','edit','close'].includes(action);throw error;}
  if(!response.ok){const error=new Error(result.error||'Studio rejected this operation. Refresh its current source and access.');error.uncertain=result.outcome==='UNKNOWN'||(response.status>=500&&['start','edit','close'].includes(action));throw error;}
  return result;
 }
 function error(t,d,e){if(valid(t,d)){t.uncertain=t.uncertain||e.uncertain===true;t.node.querySelector('#studio-error').textContent=e.message+(t.uncertain?' Outcome unknown. Further changes are paused; inspect the session or stop it.':'');}}
 function busy(t,value,text='Reading current session...'){
  if(active!==t)return;
  t.pending=value;t.node.querySelector('.studio-controls')?.setAttribute('aria-busy',String(value));
  const progress=t.node.querySelector('#studio-progress');if(progress)progress.textContent=value?text:'';
  t.node.querySelectorAll('[data-studio-write]').forEach(n=>n.disabled=value||t.uncertain);
 }
 async function open(d){
  const t=show(d,'Your Studio sessions','loading',null,'<p id="studio-progress" role="status">Reading saved sessions...</p>');busy(t,true);
  try{const result=await request(d,t,'sessions');if(valid(t,d))library(d,result,t.scope);}catch(e){error(t,d,e);}finally{busy(t,false);}
 }
 function library(d,data,captured){
  const jobs=d.state.workspace.jobs.filter(j=>j.action==='hypit_render');
  const choices=jobs.map(j=>`<option value="${esc(j.id)}">${esc(j.id)}  /  ${esc(j.status)}</option>`).join('');
  const rows=data.items.map(s=>`<article class="next-step"><div><h3>Session ${esc(s.id)}</h3><p>${esc(s.state)}  /  ${s.owned_object_present?'Owned local process present':'No owned local process'}  /  registry revision ${esc(s.version)}</p>${button('Inspect controls','session',`data-id="${esc(s.id)}"`)}</div></article>`).join('');
  const form=jobs.length?`<form id="studio-source-form"><label class="field">Approved Hypit source<select name="source_job_id">${choices}</select></label><button class="button" type="submit">Review startup summary</button></form>`:'<p>No Hypit source jobs yet. Queue a Hypit caption render from a current video brief, then reopen Studio. WMM rechecks the brief and usage rights before startup.</p>';
  return show(d,'Your Studio sessions','library',data,`<p>${data.items.length} saved sessions in this app. A saved session is separate from a rendered or published video.</p>${form}${rows||'<p>No saved Studio sessions.</p>'}<p>Restart reconciliation is not implemented. A saved active row without an owned process requires recovery; WMM will not adopt an unrelated process.</p><p id="studio-progress" role="status"></p>`,captured);
 }
 function summary(d,t,value){
  const html=`<p>Starting opens a private local Studio and media worker from this exact approved source. This source profile makes no provider calls and does not publish.</p><details open><summary>Exact startup summary and limits</summary><pre>${json(value.summary)}</pre></details><p>Summary hash: ${esc(value.summary_hash)}</p>${button('Start this local session','start','data-studio-write')}${button('Inspect saved sessions','open')}<p id="studio-progress" role="status"></p>`;
  const next=show(d,'Review Studio startup','summary',value,html,t.scope);next.requestKey=d.uuid();return next;
 }
 function options(field){return (field.options||[]).map(o=>typeof o==='object'?o:{value:o,label:o});}
 function input(field,index){
  const name='value',id='studio-value-'+index,label=esc(field.label||'Composition setting');
  if(!field.writable)return `<p>${label}  /  Read only</p><pre>${json(field.value)}</pre>`;
  const attr=`id="${id}" name="${name}"`;
  let control;
  if(field.control==='select')control=`<select ${attr}>${options(field).map((o,i)=>`<option value="${i}" ${JSON.stringify(o.value)===JSON.stringify(field.value)?'selected':''}>${esc(o.label??o.value)}</option>`).join('')}</select>`;
  else if(field.control==='boolean')control=`<select ${attr}><option value="true" ${field.value===true?'selected':''}>Yes</option><option value="false" ${field.value===false?'selected':''}>No</option></select>`;
  else if(field.control==='number')control=`<input ${attr} type="number" step="any" required value="${esc(field.value)}">`;
  else if(['list','record'].includes(field.control))control=`<textarea ${attr} rows="5" required>${json(field.value)}</textarea><small>Structured JSON ${field.control==='list'?'array':'object'}. The compiled schema below is checked on save.</small>`;
  else if(field.multiline)control=`<textarea ${attr} rows="3">${esc(field.value)}</textarea>`;
  else control=`<input ${attr} type="text" value="${esc(field.value)}">`;
  return `<label class="field" for="${id}">${label}${control}</label>`;
 }
 function fieldsMarkup(controls){
  let index=0;
  return controls.owners.map((owner,i)=>`<details ${i===0?'open':''}><summary>${esc(owner.kind)} ${i+1}  /  ${owner.fields.length} settings</summary>${owner.fields.map(field=>{
   const n=index++;return `<section class="panel"><form data-studio-parameter aria-label="Edit ${esc(field.label||'Composition setting')}" data-owner="${esc(owner.id)}" data-field="${esc(field.id)}"><p>Inspect this setting, change its value, then save it to record a new source revision.</p>${input(field,n)}<p>${esc(field.summary||'')} ${esc(field.unit||'')}</p><details><summary>Compiled field schema</summary><pre>${json(field.schema||{})}</pre></details>${field.writable?'<button class="button" type="submit" data-studio-write>Save this setting</button>':''}</form></section>`;
  }).join('')}</details>`).join('');
 }
 function inspector(d,t,value,edited){
  const closed=value.session.state==='CLOSED',controls=closed?null:value.controls;
  const count=Array.isArray(controls?.owners)?controls.owners.reduce((n,o)=>n+o.fields.length,0):null;
  const history=Array.isArray(value.attempts)?`<pre>${json(value.attempts.map(a=>({id:a.id,status:a.status})))}</pre>`:'<p>Attempt history unavailable in this response. Inspect edit history to request retained observations.</p>';
  const html=`<p>Session ${esc(value.session.id)} / ${esc(value.session.state)} / source revision ${esc(value.source_head?.version??'unavailable')} / ${count===null?'Compiled settings unavailable':count+' compiled settings'}.</p><p>${closed?'Owned local cleanup is confirmed. Retained history is separate from live editable controls.':'Save one setting, then read its new source revision. Existing agent edits appear on refresh. A changed source or view rejects stale edits.'}</p>${button('Refresh current controls','refresh')}${button('Inspect edit history','inspect')}${closed?'':button('Stop this local session','stop')}${button('Report / Save PDF','report')}<p id="studio-progress" role="status"></p>${controls?fieldsMarkup(controls):'<p>Live controls unavailable.</p>'}<details><summary>Observed edit attempts</summary>${history}</details>`;
  const next=show(d,'Customize your composition','inspector',value,html,t.scope);
  next.uncertain=!closed&&(t.uncertain||['UNKNOWN','CLEANUP_REQUIRED'].includes(value.session.state)||(value.attempts||[]).some(a=>['PREPARED','UNCERTAIN'].includes(a.status)));
  busy(next,false);if(next.uncertain)error(next,d,new Error('Saved state requires reconciliation. Inspection does not authorize a retry.'));
  if(edited&&!closed){
   const form=Array.from(next.node.querySelectorAll('[data-studio-parameter]')).find(f=>f.dataset.owner===edited.owner&&f.dataset.field===edited.field);
   if(form){for(let parent=form.parentElement;parent&&parent!==next.node;parent=parent.parentElement)if(parent.tagName==='DETAILS')parent.open=true;form.querySelector('[name="value"]')?.focus();}
  }
  return next;
 }
 async function load(d,t,id,inspect=false){
  const result=await request(d,t,inspect?'inspect':'read',{},id);
  if(valid(t,d))inspector(d,t,result);
 }
 function typed(field,text){
  if(field.control==='number'){if(text===''||!Number.isFinite(Number(text)))throw new Error('Enter a finite number.');return Number(text);}
  if(field.control==='boolean'){if(!['true','false'].includes(text))throw new Error('Choose Yes or No.');return text==='true';}
  if(field.control==='select'){const row=options(field)[Number(text)];if(!row)throw new Error('Choose a compiled option.');return row.value;}
  if(['list','record'].includes(field.control)){const value=JSON.parse(text);const ok=field.control==='list'?Array.isArray(value):value!==null&&typeof value==='object'&&!Array.isArray(value);if(!ok)throw new Error('Use the required JSON array or object.');return value;}
  return text;
 }
 function editBody(t,form,d){
  const owner=t.data.controls.owners.find(o=>o.id===form.dataset.owner),field=owner?.fields.find(f=>f.id===form.dataset.field);
  if(!field?.writable||t.uncertain)throw new Error('Reload an editable current field before saving.');
  const body={base_version:t.data.source_head.version,base_hash:t.data.source_head.hash,parameter:{revision:t.data.controls.revision,view_hash:t.data.controls.view_hash,owner_id:owner.id,field_id:field.id,value:typed(field,new d.FormData(form).get('value'))}};
  const fingerprint=JSON.stringify(body);if(t.lastEdit?.fingerprint!==fingerprint)t.lastEdit={fingerprint,key:d.uuid()};
  return {request_key:t.lastEdit.key,...body};
 }
 async function submit(form,d){
  const t=active;if(!t||!valid(t,d)||t.pending)return;
  try{
   if(form.id==='studio-source-form'){busy(t,true,'Checking source, rights, installed runtime and startup summary...');const b={source_job_id:new d.FormData(form).get('source_job_id'),manifest_version:t.scope.version};const v=await request(d,t,'plan',b);if(valid(t,d))summary(d,t,v);return;}
   const b=editBody(t,form,d);busy(t,true,'Applying the exact compiled setting and verifying its source revision...');
   const v=await request(d,t,'edit',b,t.data.session.id);if(valid(t,d))inspector(d,t,v,{owner:form.dataset.owner,field:form.dataset.field});
  }catch(e){error(t,d,e);}finally{busy(t,false);}
 }
 function report(t,d){
  const owners=t.data.session.state==='CLOSED'?null:t.data.controls?.owners,fields=Array.isArray(owners)?owners.flatMap(o=>o.fields):null,attempts=Array.isArray(t.data.attempts)?t.data.attempts:null;
  return {title:'Studio session observation',app_name:d.state.workspace.app.data.name,app_id:t.scope.app,scope:'SELECTED_APP',manifest_version:t.scope.version,generated_at:new Date().toISOString(),loaded_at:t.loadedAt,purpose:'Inspect saved local session state and compiled control coverage.',next_step:'Review current source state before another edit. Render and inspect a final video separately.',filters:{session:t.data.session.id,state:t.data.session.state},cohorts:[],metrics:[['Compiled settings',fields===null?null:fields.length],['Writable settings',fields===null?null:fields.filter(f=>f.writable).length],['Observed attempts',attempts===null?null:attempts.length],['Source revision',t.data.source_head?.version??null]].map(([label,value])=>({label,value,source:'Selected session readback',unit:'count'})),notes:['Local source state is separate from rendered video and publication.','No field values, private source files, credentials or native addresses are included.','Inspection does not authorize repeating an uncertain edit.']};
 }
 async function action(node,d){
  const name=node.dataset.action.slice(7);if(name==='open')return open(d);
  const t=active;if(!t||!valid(t,d)||t.pending)return;
  if(name==='report')return d.pageReports.openReport(report(t,d),d.browser);
  try{
   busy(t,true,name==='start'?'Starting the approved local session...':'Reading current session state...');
   if(name==='session')return await load(d,t,node.dataset.id);
   if(['refresh','inspect'].includes(name))return await load(d,t,t.data.session.id,name==='inspect');
   if(name==='start'){
    if(t.uncertain)throw new Error('Inspect saved sessions before any further startup.');
    const body={source_job_id:t.data.intent.source_job_id,manifest_version:t.scope.version,summary_hash:t.data.summary_hash,request_key:t.requestKey};
    const value=await request(d,t,'start',body);if(valid(t,d))inspector(d,t,value);return;
   }
   if(name==='stop'){const v=await request(d,t,'close',{},t.data.session.id);if(valid(t,d)){const next=inspector(d,t,v);if(!next.uncertain)next.node.querySelector('#studio-error').textContent='Saved cleanup state: '+v.session.state+'.';}return;}
   throw new Error('Unknown Studio action.');
  }catch(e){error(t,d,e);}finally{busy(t,false);}
 }
 return {panel,open,action,submit,clear,invalidate,typed,fieldsMarkup,editBody,request,report};
});
