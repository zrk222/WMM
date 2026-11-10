/* Owner-confirmed standing scope; no preference or optimistic switch grants authority. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.WMMCompleteAutomation=api;})(typeof globalThis==='object'?globalThis:this,function(){
 'use strict';
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const button=(text,action,extra='')=>`<button type="button" class="button outline" data-action="standing-${action}" ${extra}>${esc(text)}</button>`;
 let active=null;
 const automationProfiles={
  research:{label:'Research & experiments',workflows:['local_evidence','experiment_preparation'],description:'Read and save research, import evidence, and prepare experiments. Review the exact operations before enabling this profile.'},
  organic:{label:'Organic marketing',workflows:['local_evidence','pipeline_preparation','hypit_caption_render'],description:'Prepare research, Hypit/editor work and delivery reports. Publication still needs the separate exact organic policy and destination approval. Verified delivery is separate from analytics; missing analytics stays visible.'},
  meta:{label:'Bounded Meta media buyer',workflows:['local_evidence','pipeline_preparation','social_publish','paid_effects'],description:'Prepare and report on Meta work. Publishing, paid effects and budget remain behind the separate exact campaign scope. Verified delivery is separate from analytics; missing analytics stays visible.'}
 };
 function profileWorkflows(profile){return automationProfiles[profile]?.workflows?.slice()||[];}
 function resolveAutomationProfile(profile,available){
  const definition=automationProfiles[profile];
  if(!definition)return {available:true,selected:[],missing:[]};
  const ids=new Set(available||[]),missing=definition.workflows.filter(id=>!ids.has(id));
  return {available:missing.length===0,selected:definition.workflows.filter(id=>ids.has(id)),missing};
 }
 function profileAfterWorkflowEdit(){return 'custom';}
 function bindAutomationProfiles(form){
  const picker=form.querySelector('#standing-goal-profile'),note=form.querySelector('[data-standing-profile-note]');
  if(!picker)return;
  const boxes=[...form.querySelectorAll('input[name="workflows"]')],available=new Set(boxes.map(input=>input.value));
  const render=()=>{
   const definition=automationProfiles[picker.value];
   if(!definition){if(note)note.textContent='Custom keeps your selected workflows. The exact operation list remains visible in the review step.';return;}
   const resolved=resolveAutomationProfile(picker.value,available);
   boxes.forEach(input=>{input.checked=resolved.selected.includes(input.value);});
   if(note)note.textContent=resolved.missing.length?`${definition.label} is unavailable for this catalog until ${resolved.missing.join(', ')} is implemented or restored. No hidden operation was added.`:`${definition.description} This preset only fills the form; it does not issue authority.`;
  };
  picker.addEventListener('change',render);
  form.addEventListener('change',event=>{if(event.target.name==='workflows'&&event.target!==picker)picker.value=profileAfterWorkflowEdit();});
  render();
 }
 function decorateAutomationSetup(node){
  const form=node?.querySelector?.('#standing-scope-form');
  if(!form||form.querySelector('#standing-goal-profile'))return;
  form.insertAdjacentHTML('afterbegin','<p>Start with the outcome you want. A preset fills the form; it never grants authority or bypasses readiness checks.</p><label class="field">Automation profile<select id="standing-goal-profile" name="standing_goal_profile"><option value="research">Research only</option><option value="organic">Organic marketing</option><option value="meta">Bounded Meta media buyer</option><option value="custom">Custom advanced scope</option></select></label><p data-standing-profile-note role="status"></p>');
  const accountSection=form.querySelectorAll('fieldset')[1];
  if(accountSection)accountSection.insertAdjacentHTML('beforebegin','<p>Choosing an account only identifies a destination for readiness checks. It does not publish, spend, or grant provider permission.</p>');
  const submit=form.querySelector('[type="submit"]');
  if(submit)submit.textContent='Review exact agreement';
  bindAutomationProfiles(form);
 }
 function scope(state){return {app:state.app,version:state.workspace.app.version,principal:state.workspace.identity?.principal};}
 function same(saved,state){const current=scope(state);return saved.app===current.app&&saved.version===current.version&&saved.principal===current.principal;}
 function owner(state){return state.workspace.access?.members?.some(r=>r.principal===state.workspace.identity?.principal&&r.role==='OWNER'&&r.status==='ACTIVE');}
 function clear(){if(active?.node)active.node.querySelectorAll('[data-standing-secret]').forEach(n=>n.value='');active=null;}
  function expiryUI(){return globalThis.WMMAuthorityExpiry||(typeof require==='function'?require('./authority-expiry.js'):null);}
 function invalidate(state){if(active&&!same(active.scope,state))clear();}
 function panel(state,ownerNext=''){return `<section class="panel" aria-label="Automation authority"><h2>Choose what your agent can do for you</h2><p>Select the workflows, connect and test the required accounts, then review the actions, destinations, expiry and limits. Once enabled, your agent can perform included actions within this approved scope. Inspect its recorded stages and saved results in Live workflow progression.</p><p>Open controls to read the current OFF, ACTIVE or BLOCKED state. Saving planning defaults does not enable execution.</p>${button('Open automation controls','open',owner(state)?'':'disabled')}${owner(state)?'<p>You are this app’s owner.</p>':ownerNext||'<p>Sign in as the app owner to manage automation.</p>'}</section>`;}
 function valid(ticket,deps){return active===ticket&&same(ticket.scope,deps.state)&&ticket.node?.isConnected&&deps.document.querySelector('#modal').open;}
 function show(deps,title,kind,data,markup,saved=scope(deps.state)){
  deps.modal(title,`<div class="modal-content" id="standing-dialog">${markup}<p id="standing-error" role="alert"></p></div>`,'YOUR AUTOMATION AUTHORITY');
  active={scope:saved,kind,data,node:deps.document.querySelector('#standing-dialog'),pending:false};if(kind==='setup')decorateAutomationSetup(active.node);return active;
 }
 const endpoint=(app,action)=>`/api/apps/${encodeURIComponent(app)}/agent-grants/automation-${action}`;
 function summaryMarkup(summary){
  const i=summary.inventory,profile=i.inference;
  return `<h3>What you are authorizing</h3><p>Agent: ${esc(i.selection.agent_id)} · app ${esc(i.app.id)} · setup version ${esc(i.app.version)}</p><p>Purpose: ${esc(summary.purpose)}</p><p>Connection: ${esc(profile.provider)} · ${esc(profile.model||'Provider default')} · ${esc(profile.status)}. Last successful test: ${esc(profile.last_successful_test||'None')}. Account identity: ${esc(profile.account_identity)}.</p><p>Stops at ${esc(summary.stops_at)} · ${esc(summary.limits.max_calls)} calls · ${esc(summary.limits.max_inflight)} concurrent work units · spend ceiling ${esc(summary.limits.spend_limit_minor)} minor ${esc(summary.limits.currency)}. Provider allowance and price remain unknown.</p><ul>${i.workflows.map(w=>`<li><strong>${esc(w.name)}</strong>: ${esc(w.status)}${w.blockers.length?` · ${esc(w.blockers.join(', '))}`:''}${w.repair?`<p>${esc(w.repair)}</p>`:''}</li>`).join('')}</ul><p>Actions: ${esc(summary.operations.join(', '))}</p><p>Destinations: ${i.accounts.length?i.accounts.map(a=>`${esc(a.provider)} / ${esc(a.subject_id)} / ${esc(a.destination_id)} · ${esc(a.status)} · scopes ${esc((a.reported_scopes||[]).join(', '))} · expires ${esc(a.expires_at??'Unknown')}`).join('; '):'No external account destination in this selected scope.'}</p><p>${esc(summary.content)}</p><p>Stop rules: ${esc(summary.stop_rules.join('; '))}</p><p>${esc(summary.revocation)}</p>`;
 }
 function statusMarkup(data){
  const live=data.policies.find(p=>p.status==='ACTIVE');
  const state=live?.effective_status||'OFF';
   return `<p><strong>Automation: ${esc(state)}</strong></p><button type="button" role="switch" aria-checked="${state==='ACTIVE'}" class="button" data-action="standing-toggle" ${live?`data-id="${esc(live.id)}" data-version="${esc(live.version)}"`:''}>${live?'Switch automation OFF':'Review scope to switch ON'}</button>${live?.repair?`<p role="alert">${esc(live.repair)}</p>`:''}<p>ON requires final owner confirmation after checking the selected workflows and credentials. OFF revokes future admissions under this local-work policy; inspect receipts for work already dispatched. Campaign scopes have their own OFF and provider-pause controls in Connections.</p><div class="button-row">${button('Refresh saved status','open')}${button('Report / Save PDF','report')}${button('Download automation data','download')}</div>${data.policies.map(p=>{const expiry=p.permission_expires_at||p.expires_at||p.summary?.permission_expires_at;return `<section class="panel"><h3>${esc(p.effective_status)} · policy ${esc(p.id)}</h3><p>Revision ${esc(p.version)} · calls ${esc(p.usage?.used??'Unavailable')} / ${esc(p.usage?.max_calls??'Unavailable')} · ${p.executions.length} recorded actions</p>${expiry&&p.status==='ACTIVE'&&p.effective_status==='ACTIVE'?button('Extend expiry','extend',`data-id="${esc(p.id)}" data-expires="${esc(expiry)}"`):''}${p.summary?summaryMarkup(p.summary):'<p>Saved summary needs repair; use OFF to revoke active authority.</p>'}<details><summary>Action outcomes (${p.executions.length})</summary><ul>${p.executions.map(e=>`<li>${esc(e.operation)} · ${esc(e.status)} · ${esc(e.write_commits)} committed local transactions · ${esc(e.updated)} · result ${esc(e.result_hash||'Unconfirmed')} ${e.jobs.map(j=>` · job ${esc(j.action)} ${esc(j.status)}`).join('')}</li>`).join('')}</ul></details></section>`;}).join('')||'<p>No standing approval has been issued for this app.</p>'}`;
 }
 async function open(deps){
  if(!owner(deps.state))throw new Error('Sign in as this app’s owner.');
  const ticket=show(deps,'Automation controls','loading',null,'<p role="status">Reading saved authority…</p>');
   try{const data=await deps.api(endpoint(ticket.scope.app,'status'),{});if(valid(ticket,deps)){const clocks=data.policies.map(p=>`<p>Policy ${esc(p.id)} · permission expires ${esc(expiryUI().dateLine(p.permission_expires_at||p.expires_at))} · verification due ${esc(expiryUI().dateLine(p.verification_due_at))}. Verification and provider readiness remain independent.</p>`).join('');show(deps,'Automation controls','status',data,statusMarkup(data).replace('<p><strong>Automation:',`${clocks}<p><strong>Automation:`),ticket.scope);}}
  catch(e){if(valid(ticket,deps))ticket.node.querySelector('#standing-error').textContent=e.message;}
 }
 function setup(deps,data,saved){
  const profiles=deps.state.workspace.agent_access?.profiles||[],accounts=deps.state.workspace.social_access?.accounts||[];
   const expiry=expiryUI(),ticket=show(deps,'Choose your automation scope','setup',data,`<form id="standing-scope-form"><p>Choose the workflows for this app. Each selected workflow must meet its requirements before activation. Missing implementations stay visible.</p><label class="field">Agent identifier<input name="agent_id" required pattern="[a-z0-9][a-z0-9-]*" maxlength="200"></label><label class="field">Purpose<textarea name="purpose" maxlength="500" required></textarea></label><label class="field">Inference connection<select name="agent_connection_id" required><option value="">Choose a tested connection</option>${profiles.map(p=>`<option value="${esc(p.id)}">${esc(p.data.label)} · ${esc(p.status)} · tested ${esc(p.last_test||'Never')}</option>`).join('')}</select></label><p>First, test your agent connection. Open Your agents, complete its protected setup and test it, then return here. Keys and OAuth sign-in stay in their protected onboarding flow.</p><fieldset><legend>Workflows</legend>${Object.entries(data.catalog.workflows).map(([id,w])=>`<label class="check-label"><input type="checkbox" name="workflows" value="${esc(id)}"> ${esc(w.name)}${w.blockers.length?' · Setup or implementation required':''}</label>`).join('')}</fieldset><fieldset><legend>Account destinations</legend>${accounts.map(a=>`<label class="check-label"><input type="checkbox" name="social_connection_ids" value="${esc(a.id)}"> ${esc(a.provider)} · ${esc(a.subject_id)} · ${esc(a.status)}</label>`).join('')||'<p>No social account is onboarded. Connect it under Connections when your selected workflow requires it.</p>'}</fieldset><div class="form-grid">${expiry.expiryInput('expires_at',Date.now()+60*60*1000,'Automation approval expires — device local time')}<label class="field">Maximum calls<input type="number" name="max_calls" min="1" max="10000" value="20" required></label><label class="field">Concurrent work units<input type="number" name="max_inflight" min="1" max="8" value="1" required></label></div>${expiry.consentMarkup()}<p>This selected standing scope has a zero spend ceiling. It does not authorize paid provider effects or external publication. A model connection does not establish its subscription allowance or price.</p><p>For publishing and paid Meta work, approve the separate exact campaign scope in Connections. Its own OFF control attempts a verified provider pause.</p><button type="button" class="button outline" data-action="campaign-open">Open campaign automation</button><button type="submit" class="button">Review actions and limits</button></form>`,saved);expiry.bindConsent(ticket.node.querySelector('#standing-scope-form'));
 }
 function proposal(values,saved,now=Date.now()){
  const hours=Number(values.hours),calls=Number(values.max_calls),inflight=Number(values.max_inflight);
  if(!Number.isInteger(calls)||calls<1||calls>10000||!Number.isInteger(inflight)||inflight<1||inflight>8)throw new Error('Use the displayed resource limits.');
  if(!values.workflows?.length)throw new Error('Choose at least one workflow.');
  let expires,extended=false;if(values.expires_at){const checked=expiryUI().validateExpiry(values.expires_at,values.extended_expiry_consent==='on',now);expires=checked.expires;extended=checked.extended;}else{if(!Number.isInteger(hours)||hours<1||hours>24)throw new Error('Use the displayed resource limits.');expires=new Date(now+hours*3600000).toISOString();}
   return {selection:{agent_id:values.agent_id,manifest_version:saved.version,workflows:values.workflows,agent_connection_id:values.agent_connection_id||null,social_connection_ids:values.social_connection_ids||[]},purpose:values.purpose,limits:{expires,max_calls:calls,max_inflight:inflight,currency:values.currency||'USD',spend_limit_minor:0},...(extended?{extended_expiry_consent:true}:{})};
 }
 async function submit(form,deps){
  const ticket=active;if(!ticket||ticket.pending||!valid(ticket,deps))return;
  ticket.pending=true;const submit=form.querySelector('[type=submit]');submit.disabled=true;
  try{
   const fields=new deps.FormData(form),values=Object.fromEntries(fields);values.workflows=fields.getAll('workflows');values.social_connection_ids=fields.getAll('social_connection_ids');values.currency=deps.state.workspace.app.data.currency||'USD';
   const data=await deps.api(endpoint(ticket.scope.app,'preview'),proposal(values,ticket.scope));
    if(valid(ticket,deps))show(deps,'Review automation authority','confirm',data,`${summaryMarkup(data.summary)}${data.proposal.extended_expiry_consent===true?'<p>You explicitly consented to this selected expiry being more than 24 hours away.</p>':''}<p>Summary SHA256: ${esc(data.summary_hash)}</p>${data.summary.inventory.scope_status==='READY_FOR_SCOPE_REVIEW'?button('Approve scope and switch ON','activate'):'<p role="alert">Activation is blocked. Repair the listed connection or workflow requirements and prepare a new summary.</p>'}`,ticket.scope);
  }catch(e){if(valid(ticket,deps))ticket.node.querySelector('#standing-error').textContent=e.message+' Your inputs are preserved.';}
  finally{ticket.pending=false;submit.disabled=false;}
 }
 function report(data,state,reports){
  const base=reports.model({...state,view:'activity'}),executions=data.policies.flatMap(p=>p.executions);
  return {...base,title:'Automation authority and outcomes',purpose:'Review the owner-approved scope and recorded action outcomes.',next_step:'Inspect uncertain work and switch OFF before changing scope.',filters:{scope:'Selected app standing approvals'},metrics:[{label:'Saved policies',value:data.policies.length,unit:'count',source:'Authenticated owner automation status'},{label:'Recorded actions',value:executions.length,unit:'count',source:'Saved automation executions'},{label:'Uncertain actions',value:executions.filter(e=>['UNKNOWN','CANCEL_REQUESTED'].includes(e.status)).length,unit:'count',source:'Saved automation executions'}],cohorts:[],notes:data.policies.flatMap(p=>[`Policy ${p.id}: ${p.effective_status}; revision ${p.version}; calls ${p.usage?.used??'Unknown'}/${p.usage?.max_calls??'Unknown'}.`,...(p.summary?[`Agent ${p.summary.inventory.selection.agent_id}; app ${p.summary.inventory.app.id}; expires ${p.summary.stops_at}; actions ${p.summary.operations.join(', ')}; zero spend ${p.summary.limits.currency}.`]:[]),...p.executions.map(e=>`${e.operation}: ${e.status}; input hash ${e.input_hash}; result hash ${e.result_hash||'Unconfirmed'}; committed transactions ${e.write_commits}.`)]).concat('Metadata only; no bearer token, private operation input/result or credentials. Provider spending and business outcomes are not established by these counts.')};
 }
 async function action(node,deps){
  const command=node.dataset.action.slice(9);if(command==='open')return open(deps);
   const ticket=active;if(!ticket||!valid(ticket,deps)||ticket.pending)return;
   if(command==='extend'){
    const row=ticket.data.policies.find(p=>p.id===node.dataset.id&&p.status==='ACTIVE'&&p.effective_status==='ACTIVE'),expires=row&&(row.permission_expires_at||row.expires_at||row.summary?.permission_expires_at);if(!row||!expires)throw new Error('Reload the active automation approval before extending it.');
    return expiryUI().open({kind:'AUTOMATION',id:row.id,expires,app:ticket.scope.app,api:deps.api,modal:deps.modal,document:deps.document,FormData:deps.FormData,uuid:deps.uuid,owner:()=>owner(deps.state),current:()=>same(ticket.scope,deps.state),done:()=>open(deps)});
   }
  if(command==='toggle'){
   const row=ticket.data.policies.find(p=>p.id===node.dataset.id);
   if(!row)return setup(deps,ticket.data,ticket.scope);
   return show(deps,'Switch automation OFF','off',row,`<p>Revoke policy ${esc(row.id)}. New admissions stop and owned queued work is cancelled. Already committed work remains in its receipts.</p>${button('Confirm switch OFF','off')}`,ticket.scope);
  }
  if(command==='report')return deps.pageReports.openReport(report(ticket.data,deps.state,deps.pageReports),deps.browser);
  if(command==='download'){
   const model=report(ticket.data,deps.state,deps.pageReports),blob=new deps.browser.Blob([JSON.stringify(model,null,2)],{type:'application/json'}),url=deps.browser.URL.createObjectURL(blob),link=deps.document.createElement('a');link.href=url;link.download=ticket.scope.app+'-automation.json';link.click();deps.browser.URL.revokeObjectURL(url);return;
  }
  if(command==='reveal'){const input=ticket.node.querySelector('[data-standing-secret]');input.type=input.type==='password'?'text':'password';return;}
  ticket.pending=true;
  try{
   if(command==='activate'&&ticket.kind==='confirm'){
    const data=await deps.api(endpoint(ticket.scope.app,'activate'),{proposal:ticket.data.proposal,summary_hash:ticket.data.summary_hash});
    if(!valid(ticket,deps)){deps.toast('Scope was activated after the dialog changed. Inspect saved authority and revoke it if needed. The token was cleared.');return;}
    const shown=show(deps,'Automation enabled','token',null,`<p>The server activated the exact approved scope. Deliver this once-only credential to your selected agent’s protected credential input.</p><label class="field">Once-only automation token<input type="password" data-standing-secret readonly autocomplete="off"></label>${button('Show or hide token','reveal')}${button('Inspect saved authority','open')}<p>Closing this view clears the displayed token. Use Live workflow progression to follow actual work.</p>`,ticket.scope);
    shown.node.querySelector('[data-standing-secret]').value=data.token;
   }else if(command==='off'&&ticket.kind==='off'){
    await deps.api(endpoint(ticket.scope.app,'off'),{id:ticket.data.id,version:ticket.data.version});if(valid(ticket,deps))await open(deps);
   }
  }catch(e){if(valid(ticket,deps))ticket.node.querySelector('#standing-error').textContent=e.message+' Reload the current scope before retrying.';}
  finally{ticket.pending=false;}
 }
 return {panel,open,action,submit,clear,invalidate,proposal,summaryMarkup,statusMarkup,report,automationProfiles,profileWorkflows,resolveAutomationProfile,profileAfterWorkflowEdit};
});
