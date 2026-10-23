"use strict";

document.querySelector('#modal').addEventListener('close',()=>{
  document.querySelectorAll('#agent-setup-form input[type=password]').forEach(input=>input.value='');
});

function agentAccessView() {
  const access=state.workspace.agent_access;
  if(!access)return heading("Your agents","Reload to inspect saved agent connections.");
  const cleanup=access.cleanup_pending?`<section class="panel">${notice('Old protected keys need cleanup. Active connections are kept. Interrupted setup stages become eligible after five minutes.','warning')}${button('Retry key cleanup','agent-cleanup')}</section>`:'';
  const profiles=access.profiles.map(row=>`<section class="connection-card"><h2>${esc(row.data.label)}</h2><p>${esc(access.providers[row.data.provider].name)} · ${esc(row.data.model||"Provider default model")}</p>${status(row.status)}<p>Allowance and exact cost: unknown. ${row.last_test?`Last completed test: ${esc(new Date(row.last_test).toLocaleString())}`:"No completed capability test."}</p><div class="button-row">${button("Test connection","agent-test",`data-id="${esc(row.id)}" ${row.status==='DISCONNECTED'?'disabled':''}`)}${button("Replace connection","agent-setup",`data-id="${esc(row.data.provider)}" data-profile="${esc(row.id)}"`)}${button("Disconnect this app","agent-disconnect",`data-id="${esc(row.id)}" ${row.status==='DISCONNECTED'?'disabled':''}`)}</div></section>`).join('');
  const adapters=Object.entries(access.providers).map(([id,p])=>`<section class="connection-card"><h2>${esc(p.name)}</h2><p>${esc(p.explanation)}</p><div class="button-row">${p.tool?button("Detect installed tool","agent-detect",`data-id="${esc(id)}"`):''}${button(p.tool?'Use existing sign-in':p.mode==='local'?'Connect local server':'Add protected API key','agent-setup',`data-id="${esc(id)}"`)}</div></section>`).join('');
  return heading("Your agents","Use an existing agent subscription, your API key, a local model server, or a mix by task.")+notice("No subscription or checkout for Mission Control. Provider allowances and API charges are separate from campaign budgets. Connections stay saved on this workstation; no silent paid fallback.")+cleanup+`<section class="panel"><h2>How the work flows</h2><p>Connect → test → choose task routes → review the exact app facts → approve one draft. Drafts never publish or spend.</p><div class="button-row">${button("Choose task routes","agent-routes")}${button("Prepare agent work","agent-work")}</div></section><div class="connection-grid">${profiles}</div><h2>Add a connection</h2><div class="connection-grid">${adapters}</div>`;
}

function agentSetup(provider,identity='') {
  const access=state.workspace.agent_access,p=access.providers[provider];
  const row=access.profiles.find(r=>r.id===identity),needsModel=['byok','local'].includes(p.mode);
  modal("Connect "+p.name,`<form id="agent-setup-form" class="modal-content" data-app="${esc(state.app)}" data-provider="${esc(provider)}" data-profile="${esc(identity)}" data-version="${row?.version||''}"><p>${esc(p.explanation)}</p>${p.tool?notice("This uses the official tool's existing sign-in. If it is signed out, sign in through that tool, then Detect and Test here."):''}${p.link?`<p><a href="${esc(p.link)}" target="_blank" rel="noopener noreferrer">Official provider setup ↗</a></p>`:''}<label class="field">Connection name<input name="label" maxlength="100" required value="${esc(row?.data.label||p.name)}"></label><label class="field">Model ${needsModel?'':'(optional)'}<input name="model" maxlength="120" ${needsModel?'required':''} value="${esc(row?.data.model||'')}" placeholder="${needsModel?'Your enabled provider model':'Use provider default'}"></label>${agentProviderFields(provider,p,row)}<p id="agent-error" role="alert"></p><div class="modal-actions"><button class="button primary" type="submit">Save protected connection</button>${button("Cancel","close")}</div></form>`,"AGENT ACCESS");
}

function agentProviderFields(provider,p,row) {
  const local=p.mode==='local',keyed=['byok','local'].includes(p.mode)||provider==='glm_coding';
  const endpoint=['compatible_api','local_api'].includes(provider)?agentEndpointField(local,p,row):'';
  const key=keyed?agentKeyField(local):'';
  const consent=['byok','local'].includes(p.mode)?agentConsentField(local):'';
  return endpoint+key+consent;
}

function agentEndpointField(local,p,row) {
  return `<label class="field">${local?'Local HTTP API base URL':'Public HTTPS API base URL'}<input name="endpoint" type="url" required value="${esc(row?.data.endpoint||(local?p.endpoint:''))}" placeholder="${local?'http://127.0.0.1:11434/v1':'https://api.your-provider.com/v1'}"></label>`;
}

function agentKeyField(local) {
  return `<label class="field">${local?'Local server bearer key (optional)':'Provider key'}<input name="api_key" type="password" autocomplete="off" ${local?'':'required'} minlength="${local?1:16}" maxlength="1800"></label><p>Supplied keys are protected with Windows Credential Manager and excluded from app exports.</p>`;
}

function agentConsentField(local) {
  return `<label class="check-row"><input type="checkbox" name="charges" required> ${local?'I approve explicitly reviewed requests to this local server and any charges from its downstream configuration.':'I approve provider API charges for explicitly approved requests.'} Exact cost is not yet verified.</label>`;
}

function agentRoutes() {
  const access=state.workspace.agent_access,route=access.routing;
  const options=selected=>`<option value="">Recommend a tested permitted connection</option>`+access.profiles.filter(p=>p.status!=='DISCONNECTED').map(p=>`<option value="${esc(p.id)}" ${p.id===selected?'selected':''}>${esc(p.data.label)}</option>`).join('');
  modal("Choose how agents work",`<form id="agent-routes-form" class="modal-content" data-app="${esc(state.app)}" data-version="${route.version}"><div class="field"><label for="agent-route-mode">Access mode</label><select id="agent-route-mode" name="mode">${[['subscription','Existing subscriptions'],['byok','API keys only'],['local','Local model servers only'],['mixed','Mix by task']].map(([id,name])=>`<option value="${id}" ${route.data.mode===id?'selected':''}>${name}</option>`).join('')}</select></div>${Object.keys(access.tasks).map(task=>`<div class="field"><label for="agent-route-${esc(task)}">${esc(label(task))}</label><select id="agent-route-${esc(task)}" name="${task}">${options(route.data.routes[task])}</select></div>`).join('')}<p>Recommendations use tested connections in this access mode. Comparative quality and cost are not measured. An unavailable route needs another approval; it never silently changes provider.</p><p id="agent-error" role="alert"></p><div class="modal-actions"><button class="button primary" type="submit">Save task routes</button>${button("Cancel","close")}</div></form>`);
}

function agentWorkForm(focus='') {
  const access=state.workspace.agent_access;
  modal("What should your agent prepare?",`<form id="agent-work-form" class="modal-content" data-app="${esc(state.app)}"><label class="field">Task<select name="task">${Object.keys(access.tasks).map(t=>`<option value="${t}">${esc(label(t))}</option>`).join('')}</select></label><label class="field">Focus (optional)<textarea name="focus" maxlength="1000" rows="3" placeholder="For example: propose a small test for our first useful user outcome.">${esc(focus)}</textarea></label><p>The agent sources public app facts, workflow gaps and saved provider observations automatically. You review the exact transmission before execution. Personal histories and uploaded documents are not included.</p><p id="agent-error" role="alert"></p><div class="modal-actions"><button class="button primary" type="submit">Review proposed work</button>${button("Cancel","close")}</div></form>`);
}

function agentFeedbackSummary(context) {
  const data=context?.sources.find(s=>s.id==='action_feedback')?.data;
  if(!data)return '';
  const reuse=data.reusable_public_observation;
  return `<section class="panel"><h3>Saved work included in this request</h3><p>${esc(data.coverage)} · ${esc(data.inspected)} inspected · ${esc(data.omitted)} older runs outside this window.</p>${data.latest.length?`<ul>${data.latest.map(row=>`<li>${esc(label(row.tool))}: ${esc(label(row.state))}</li>`).join('')}</ul>`:'<p>No saved evidence actions in this window.</p>'}${reuse?`<p>Current public observation can be reused. Repair codes: ${esc(reuse.repair_codes.join(', ')||'None reported')}.</p>`:''}<p>These outcomes are partial evidence. They do not verify the app journey or campaign success.</p></section>`;
}

async function agentReview(data) {
  const app=state.app,review=await api(`/api/apps/${app}/agent-access/proposal`,data);
  if(state.app!==app||!currentWorkspace())return;
  const p=review.proposal,connection=state.workspace.agent_access.profiles.find(r=>r.id===p.connection_id);
  const grounding=p.context?`<section class="panel"><h3>What your agent will use</h3><p>Public app and brand facts, all 12 workflow stages, saved App Store observations and derived ledger status. Saved observations do not prove current access or a working app journey.</p><details><summary>Sources and next steps</summary><ul>${p.context.sources.map(s=>`<li><strong>${esc(s.id)}</strong> · ${esc(s.classification)}${s.data.status?' · '+esc(s.data.status):''}${s.data.missing_count?' · '+esc(s.data.missing_count)+' checks need evidence':''}${s.data.resolution?' · '+esc(s.data.resolution):''}</li>`).join('')}</ul></details><p>No personal histories, uploaded files, customer review text, financial amounts or credentials. If evidence changes, this approval expires and a fresh review is required.</p></section>`:'<p>This connection test sends no app facts or campaign evidence.</p>';
  modal(data.task==='connection_test'?"Test this connection":"Approve one agent draft",`<form id="agent-approve-form" class="modal-content" data-app="${esc(app)}"><h3>${esc(label(data.task))}</h3><p>Connection: <strong>${esc(connection?.data.label)}</strong>. Model: ${esc(p.model||'Provider default')}.</p>${connection?.data.provider==='local_api'?`<p>Request destination: <code>${esc(connection.data.endpoint)}</code>. This local server controls any downstream cloud execution and charges.</p>`:''}<p>${esc(review.cost)}</p>${grounding}${agentFeedbackSummary(p.context)}<p>Only the displayed context and focus are sent. No publication, ad spending, automatic provider fallback or verified-evidence promotion.</p><details><summary>Review the exact text sent to this provider</summary><pre>${esc(p.prompt)}</pre></details><p id="agent-error" role="alert"></p><div class="modal-actions"><button class="button primary" type="submit">Approve and run once</button>${button("Cancel or edit","agent-edit-work")}</div></form>`,"REVIEW BEFORE EXECUTION");
  $('#agent-approve-form').agentRequest={...data,source_hash:review.source_hash,request_key:crypto.randomUUID()};
}

function agentEvidenceActions(item) {
  const stages=[...new Set(item.source_ids.filter(id=>/^stage_([1-9]|1[0-2])$/.test(id)).map(id=>Number(id.slice(6))))].sort((a,b)=>a-b);
  const stage=stages.find(id=>resolutionIssues(id).length>0);
  return stage?resolutionButton(stage,`Review evidence actions · Step ${stage}`):button('Review current workflow','agent-workflow');
}

function agentRunMarkup(job) {
  const r=job.result,d=r?.draft,active=['QUEUED','RUNNING'].includes(job.status);
  return `<div id="agent-job-status" role="status">${status(job.status)}</div>${d?`<h3>${esc(d.summary)}</h3>${d.items.map(item=>`<section class="panel"><h4>${esc(item.title)}</h4><p>${esc(item.detail)}</p><small>${item.source_ids.length?'Sources: '+esc(item.source_ids.join(', ')):'Proposal, not independently verified'}</small><div class="button-row">${agentEvidenceActions(item)}</div></section>`).join('')}<h3>What remains unknown</h3><ul>${d.unknowns.map(u=>`<li>${esc(u)}</li>`).join('')}</ul><p>Draft only. Publication: not run. Exact cost and remaining quota: unknown.</p>`:notice(r?.error||'Waiting for the approved agent to finish.','warning')}${active?button("Cancel this agent run","agent-cancel",`data-id="${esc(job.id)}"`):button("Prepare another request","agent-work")}`;
}

function agentOpenRun(id) {
  const job=state.workspace.jobs.find(j=>j.id===id&&j.action==='agent_run');if(!job)return toast('Reload this app to inspect its saved agent work.');
  const app=state.app;modal("Agent draft",`<div class="modal-content" id="agent-run" data-job="${esc(id)}">${agentRunMarkup(job)}</div>`,"SAVED AGENT WORK");
  clearTimeout(agentOpenRun.timer);
  if(['QUEUED','RUNNING'].includes(job.status))agentOpenRun.timer=setTimeout(()=>agentPoll(app,id,job.status),900);
}

async function agentPoll(app,id,previous) {
  if(state.app!==app||!$('#modal').open||$('#agent-run')?.dataset.job!==id)return;
  try {
    const workspace=await api(`/api/apps/${app}`);
    if(state.app!==app||$('#agent-run')?.dataset.job!==id)return;
    state.workspace=workspace;const job=workspace.jobs.find(j=>j.id===id);
    if(!job)return;
    if(job.status!==previous)$('#agent-run').innerHTML=agentRunMarkup(job);
    if(['QUEUED','RUNNING'].includes(job.status))agentOpenRun.timer=setTimeout(()=>agentPoll(app,id,job.status),1200);
  }catch(error){if(state.app===app&&$('#agent-run')?.dataset.job===id)$('#agent-run').insertAdjacentHTML('beforeend',notice('Status could not refresh. Your saved run is preserved; close and reopen it.','warning'));}
}

async function agentAction(node) {
  const id=node.dataset.id,action=node.dataset.action,app=state.app;
  if(action==='agent-next-step')return agentWorkForm('Use current action_feedback to plan the next useful step. Reuse valid saved observations; prioritize repair codes and remaining proof. Explain any need for a fresh read. No publication or spending.');
  if(action==='agent-edit-work') {const saved=$('#agent-approve-form')?.agentRequest;if(saved?.task==='connection_test')return $('#modal').close();agentWorkForm(saved?.focus||'');if(saved&&saved.task in state.workspace.agent_access.tasks)$('#agent-work-form [name=task]').value=saved.task;return;}
  if(action==='agent-workflow') {$('#modal').close();state.view='workflow';render();return $('#main').focus();}
  if(action==='agent-cleanup') {
    const result=await api(`/api/apps/${app}/agent-access/cleanup`,{});
    if(state.app!==app)return;await refresh();return toast(result.remaining?'Some setup stages are not eligible yet. Retry after five minutes.':'Old protected keys removed. Active connections are unchanged.');
  }
  if(action==='agent-setup')return agentSetup(id,node.dataset.profile);
  if(action==='agent-routes')return agentRoutes();
  if(action==='agent-work')return agentWorkForm();
  if(action==='agent-test')return agentReview({task:'connection_test',focus:'',connection_id:id});
  if(action==='agent-detect') {
    const found=await api(`/api/apps/${app}/agent-access/detect`,{provider:id});if(state.app!==app)return;
    return modal("Installed agent",`<div class="modal-content">${status(found.login_state)}<p>Detected version ${esc(found.version)}. Remaining quota: unknown. Account identity is not independently verified.</p><p>Detection checks installation and sign-in; Test connection must still complete before campaign drafts can run.</p>${button("Use this installed tool","agent-setup",`data-id="${esc(id)}"`)}</div>`);
  }
  if(action==='agent-disconnect') {
    const row=state.workspace.agent_access.profiles.find(p=>p.id===id);
    return modal("Disconnect this app?",`<div class="modal-content"><p>Disable ${esc(row.data.label)} for this app and remove its local API key. Other apps and the provider's existing tool sign-in remain unchanged.</p>${button("Disconnect this connection","agent-confirm-disconnect",`data-id="${esc(id)}" data-version="${row.version}"`)}${button("Keep connected","close")}</div>`);
  }
  if(action==='agent-confirm-disconnect') {
    const r=await api(`/api/apps/${app}/agent-access/${id}/disconnect`,{version:Number(node.dataset.version)});
    if(state.app!==app)return;$('#modal').close();await refresh();return toast(r.cleanup==='LOCAL_KEY_CLEANUP_REQUIRED'?'Disconnected; protected key cleanup needs attention.':'Disconnected for this app. Other sign-ins are retained.');
  }
  if(action==='agent-cancel') {await api(`/api/apps/${app}/jobs/${id}/cancel`,{});if(state.app!==app)return;await refresh();return agentOpenRun(id);}
}

async function agentSubmit(form) {
  const submit=form.querySelector('[type=submit]'),app=form.dataset.app;submit.disabled=true;
  try {
    if(app!==state.app)throw new Error('App changed. Reopen connection setup in this workspace.');
    const values=Object.fromEntries(new FormData(form));
    if(form.id==='agent-setup-form') {
      const data={provider:form.dataset.provider,label:values.label,model:values.model,endpoint:values.endpoint||'',api_key:values.api_key||'',allow_api_charges:values.charges==='on',id:form.dataset.profile||null,version:form.dataset.version?Number(form.dataset.version):null};
      const saved=await api(`/api/apps/${app}/agent-access/save`,data);
      if(state.app!==app)return;form.reset();$('#modal').close();await refresh();toast(saved.cleanup==='LOCAL_KEY_CLEANUP_REQUIRED'?'Connection saved. Old key cleanup needs attention; use Retry key cleanup.':'Connection saved. Run its capability test before choosing campaign work.');
    }else if(form.id==='agent-routes-form') {
      await api(`/api/apps/${app}/agent-access/routes`,{version:Number(form.dataset.version),mode:values.mode,routes:Object.fromEntries(Object.keys(state.workspace.agent_access.tasks).map(t=>[t,values[t]||null]))});
      if(state.app!==app)return;$('#modal').close();await refresh();toast('Task routes saved.');
    }else if(form.id==='agent-work-form')await agentReview({task:values.task,focus:values.focus,connection_id:null});
    else if(form.id==='agent-approve-form') {
      const job=await api(`/api/apps/${app}/agent-access/approve`,form.agentRequest);
      if(state.app!==app)return;await refresh();agentOpenRun(job.id);
    }
  }catch(error){if(state.app===app&&form.isConnected)form.querySelector('#agent-error').textContent=error.message;}
  finally{submit.disabled=false;}
}
