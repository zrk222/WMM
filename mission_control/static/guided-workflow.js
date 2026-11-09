"use strict";

function guidedButton(tool,cls="outline") {
  return button(tool.title,"guided-tool",`data-tool="${esc(tool.id)}"`,cls);
}

function guidedOverviewPanel() {
  const g=state.workspace.workflow;
  const title=g.steps.find(s=>s.id===g.next_step)?.title||g.next_action.title;
  return `<section class="panel guided-summary"><div class="section-heading"><div><p class="eyebrow">YOUR NEXT MARKETING DECISION</p><h2>${esc(title)}</h2></div>${button(`Continue: ${g.next_action.title}`,"guided-continue","","")}</div><p>You choose the app facts, research references, uploaded media and analytics connections to use. WMM turns the saved inputs into preparation packets and reports. Connected-source reads and agent actions keep their own scope and approval checks.</p><p><strong>${g.local_ready_count} of 12 local input checks ready.</strong> Start with this step and inspect its saved packet: the work prepared, its sources and any missing evidence. Open the other stages when you need them. Publication and measured app results need separate proof.</p>${button("See the complete workflow","guided-open")}</section>`;
}

function guidedStep(step) {
  const issues=[...step.direct_needs,...step.critical_findings.map(t=>`Resolve critical finding: ${t}`)];
  const input=issues.length?`<ul>${issues.map(t=>`<li>${esc(t)}</li>`).join("")}</ul>`:"<p>Direct local inputs meet their checks.</p>";
  return `<article class="panel guided-step" id="workflow-step-${step.id}"><div class="section-heading"><div><p class="eyebrow">STEP ${step.id} / 12</p><h2>${esc(step.title)}</h2></div>${status(step.local_status)}</div><dl class="guided-stage-facts"><dt>Purpose</dt><dd>${esc(step.description)}</dd><dt>Needed input</dt><dd>${input}</dd><dt>Delivered artifact</dt><dd>${esc(step.deliverable)}</dd><dt>Acceptance</dt><dd>${esc(step.verify)}</dd></dl>${step.dependency_needs.length?`<details><summary>Earlier prerequisites</summary><ul>${step.dependency_needs.map(t=>`<li>${esc(t)}</li>`).join("")}</ul></details>`:""}<div class="toolbar">${resolutionButton(step.id)||guidedButton(step.primary)}</div><details class="guided-tools"><summary>Tools and saved inputs</summary><div class="toolbar">${step.tools.map(t=>guidedButton(t)).join("")}</div><small>${step.record_ids.length} saved input records · current versions are checked again when you continue.</small></details></article>`;
}

function guidedView() {
  const g=state.workspace.workflow;
  return `${heading("Your guided workflow","Resume saved work and take the next useful step.",button("Continue workflow","guided-continue","",""))}<section class="panel guided-summary" id="guided-workflow" aria-label="Workflow progress"><p class="eyebrow">SAVED EVIDENCE / CURRENT RELEASE</p><h2>${g.local_ready_count} of 12 local input checks ready</h2><p>Next: ${esc(g.next_action.title)}</p><p class="description">Saved evidence keeps this checklist current. Ready inputs still need review, publication checks and measured results.</p><div class="toolbar">${button("Refresh saved work","guided-refresh")}${button("Download this checklist","guided-download")}${button("Inspect current packets","automatic-open")}</div><p id="guided-message" class="field-error" role="status" aria-live="polite"></p></section>${guidedExceptionPanel(g.exceptions)}${guidedEvidenceStates()}${guidedCriticalFindings(g)}${notice("Continue opens the next setup or review step. Provider changes keep their own approval.")}${guidedStageJourney(g)}${guidedWorker()}`;
}

/* Plain-language recovery guidance is a projection only. It never infers provider
   effects or creates a retry; action buttons route to existing reviewed controls. */
const WMMExceptionGuidance=(()=>{
 const definitions={
  UNKNOWN:{headline:"Delivery is unconfirmed",reason:"WMM could not confirm whether the provider received this action.",action:"Review saved receipts before retrying.",tool:"campaign"},
  CANCEL_REQUESTED:{headline:"New local work stopped",reason:"A provider action may still be in progress.",action:"Inspect the saved attempt and reconcile it.",tool:"campaign"},
  BLOCKED:{headline:"Work is paused",reason:"A required fact changed or execution was interrupted.",action:"Repair the listed connection or scope, then review it again.",tool:"connections"},
  WAITING_FOR_REPORTS:{headline:"Report rows are not available yet",reason:"The connection works, but the provider has not supplied report rows. This does not mean zero activity.",action:"Keep the bounded read scheduled and check again at its next run.",tool:"connections"},
  EXPIRED:{headline:"Permission or connection expired",reason:"The agent has stopped until fresh access is approved.",action:"Reconnect or renew the current owner-approved access.",tool:"connections"},
  EXHAUSTED:{headline:"Approved check limit reached",reason:"WMM made no additional provider calls after the approved allowance was used.",action:"Inspect the saved receipts before issuing a new bounded approval.",tool:"agreement"}
 };
 const allowedTools=new Set(["campaign","connections","agreement","agents","owner","apple-analytics"]);
 function repairButton(tool){
  if(tool==="apple-analytics")return button("Review Apple analytics","apple-analytics-open");
  return button(`Open ${tool} controls`,"goal-repair",`data-tool="${esc(tool)}"`);
 }
 function normalize(row){
  if(!row||typeof row!=="object")return null;
  const status=String(row.state||row.status||"").toUpperCase();
  const definition=definitions[status]||{headline:"Work needs review",reason:"WMM received a state it cannot safely classify.",action:"Open the saved evidence and review the current scope.",tool:"agreement"};
  const refs=Array.isArray(row.evidence_refs)?row.evidence_refs.filter(v=>typeof v==="string"):typeof row.evidence_ref==="string"?[row.evidence_ref]:[];
  const tool=allowedTools.has(row.repair_route)?row.repair_route:definition.tool;
  return {status,headline:definition.headline,reason:typeof row.reason==="string"?row.reason:definition.reason,action:typeof row.next_action==="string"?row.next_action:definition.action,tool,evidence_refs:refs,source:typeof row.source==="string"?row.source:null,observed_at:typeof row.observed_at==="string"?row.observed_at:null,next_due:typeof row.next_due==="string"?row.next_due:null};
 }
 function panel(rows){
  if(!Array.isArray(rows)||!rows.length)return "";
  const cards=rows.map(normalize).filter(Boolean);
  if(!cards.length)return "";
  return `<section class="panel" aria-label="Workflow exceptions"><h2>Workflow updates</h2><p>See what WMM observed and what to do next.</p><div class="guided-exceptions">${cards.map(c=>`<article class="panel guided-exception" data-exception-state="${esc(c.status)}"><h3>${esc(c.headline)}</h3><p>${esc(c.reason)}</p><p><strong>Next:</strong> ${esc(c.action)}</p>${c.observed_at?`<p><small>Observed: ${esc(c.observed_at)}${c.next_due?` · next due ${esc(c.next_due)}`:""}</small></p>`:""}${c.evidence_refs.length?`<p><small>Evidence: ${c.evidence_refs.map(esc).join(", ")}</small></p>`:""}${c.source?`<p><small>Source: ${esc(c.source)}</small></p>`:""}${repairButton(c.tool)}</article>`).join("")}</div></section>`;
 }
 return {normalize,panel,definitions};
})();
function guidedExceptionPanel(rows){return WMMExceptionGuidance.panel(rows);}

const EVIDENCE_STATE_FALLBACK=[
 {id:"INPUTS_READY",title:"Inputs ready",detail:"The saved facts pass this stage’s local checks."},
 {id:"EXECUTION_APPROVED",title:"Execution approved",detail:"You approved an exact action. Its execution receipt tells you whether it ran."},
 {id:"OUTCOME_OBSERVED",title:"Outcome observed",detail:"A source records what happened. Missing results stay unknown; counts alone do not prove growth."}
];
function guidedEvidenceStates() {
  const saved=typeof state!=="undefined"?state.workspace?.workflow?.evidence_states:null;
  const states=Array.isArray(saved)&&saved.length===3?saved:EVIDENCE_STATE_FALLBACK;
  return `<section class="panel" aria-label="Understand workflow progress"><h2>Know what each result means</h2><p>These labels mean the same thing in onboarding, review and results.</p><dl>${states.map(s=>`<dt><strong>${esc(s.title)}</strong></dt><dd>${esc(s.detail)}</dd>`).join("")}</dl></section>`;
}

function guidedCriticalFindings(g) {
  const findings=g.steps.flatMap(step=>step.critical_findings.map(text=>({step,text})));
  if(!findings.length)return "";
  return `<section class="panel" aria-label="Critical findings across the workflow"><h2>Resolve these critical findings</h2><ul>${findings.map(({step,text})=>`<li><strong>Step ${esc(step.id)}: ${esc(step.title)}</strong> — ${esc(text)}</li>`).join("")}</ul><p>These findings remain open even when a stage is folded below.</p></section>`;
}

function guidedStageJourney(g) {
  const next=g.steps.find(step=>step.id===g.next_step);
  if(!next)return `<div class="guided-grid">${g.steps.map(guidedStep).join("")}</div>`;
  const rest=g.steps.filter(step=>step.id!==next.id);
  return `<section aria-label="Your next useful step"><h2>Start here: step ${esc(next.id)}</h2>${guidedStep(next)}</section><details class="panel" id="guided-all-stages"><summary>See the other ${rest.length} stages and their evidence requirements</summary><p>Every stage remains available. Open any stage to inspect its inputs, actions and verification.</p><div class="guided-grid">${rest.map(guidedStep).join("")}</div></details>`;
}

function guidedWorker() {
  const worker=state.workspace.worker||{}, rows=worker.components||{};
  const names={experiments:"Experiment analysis",analytics:"Analytics reads",followup:"Follow-up preparation",queue:"Local job queue"};
  const failed=Object.values(rows).some(r=>r.failures>0);
  return `<section class="panel" aria-label="Automatic workflow health"><h2>Automatic workflow</h2><p>${esc(label(worker.status||"NOT_STARTED"))} · Shared local worker for all app workspaces.</p><ul>${Object.entries(rows).map(([name,row])=>`<li>${esc(names[name]||name)}: ${esc(label(row.status))}${row.failures?` · ${row.failures} consecutive failures`:""}</li>`).join("")}</ul>${failed?notice(worker.last_error,"error")+button("Retry failed automation","guided-worker-retry"):""}<p class="description">Healthy components keep running. Three consecutive failures pause that component. Retry preserves app opt-ins, failed-job receipts and provider approvals.</p></section>`;
}

function guidedNavigate(view,anchor=null) {
  $("#modal").close();$("#modal-body").replaceChildren();
  state.view=view;render();
  const target=anchor?document.querySelector(anchor):$("#main");
  if(target){target.scrollIntoView({block:"start"});target.focus?.();}
}

function guidedOpenTool(identity) {
  if(identity==="release")return guidedNavigate("connections","#release-inventory-panel");
  if(identity==="subscriptions")return guidedNavigate("connections","#subscription-catalog-panel");
  if(identity==="followup")return followupOpen();
  if(identity==="public_store")return publicStoreOpen();
  if(identity==="pmf")return pmfOpen();
  const evidence=["readiness","measurement","cohort","claim","store","experiment","distribution","route","billing","retention","evaluation","learning"];
  if(evidence.includes(identity))return evidenceForm(identity);
  const routes={app:()=>appForm(false),connections:()=>guidedNavigate("connections"),events:cohortForm,results:()=>guidedNavigate("results"),upload:()=>$("#asset-file").click(),aeo:()=>aeoForm(),sources:()=>referenceForm(),inspection:()=>guidedNavigate("evidence"),ranking:()=>modal("Creative reference ranking",`<div class="modal-content">${rankingPanel()}</div>`),capability:capabilitySetup,brief:()=>briefForm(),render:renderForm,intent:()=>acqIntentForm(),activity:()=>guidedNavigate("activity"),experiments:experimentForm,adoption:()=>guidedNavigate("results","#outcome-learning-panel"),findings:()=>{state.filter="review";guidedNavigate("evidence");}};
  if(!routes[identity])throw new Error("This workflow tool is unavailable. Refresh the checklist.");
  return routes[identity]();
}

async function guidedAction(node) {
  const action=node.dataset.action;
  if(action==="guided-open")return guidedNavigate("workflow");
  if(action==="guided-download")return download(`${state.app}-workflow-checklist.json`,state.workspace.workflow);
  if(state.guidedPending)return;
  const app=state.app,view=state.view,version=state.workspace.app.version;
  state.guidedPending=true;node.disabled=true;
  const message=$("#guided-message");if(message)message.textContent="Checking the latest saved evidence…";
  try {
    if(action==="guided-worker-retry") {
      await api("/api/worker/retry",{app_id:app,manifest_version:version});
      if(state.app!==app||state.view!==view)return;
      await refresh();
      return toast("Recovery requested. Refresh saved work to inspect the next worker poll.");
    }
    await refresh();
    if(state.app!==app||state.view!==view)return;
    if(action==="guided-refresh")return toast("Checklist refreshed from current saved evidence.");
    const g=state.workspace.workflow;
    if(action==="guided-continue") {
      const step=g.steps.find(s=>s.id===g.next_step);
      if(step&&resolutionIssues(step.id).length)return openResolutionStage(step.id);
    }
    const identity=action==="guided-continue"?g.next_action.id:node.dataset.tool;
    const allowed=new Set(g.steps.flatMap(s=>[s.primary.id,...s.tools.map(t=>t.id)]));allowed.add("activity");
    if(!allowed.has(identity))throw new Error("This tool is no longer available. Refresh the checklist.");
    return guidedOpenTool(identity);
  } catch(error) {
    if(state.app!==app||state.view!==view)return;
    const current=$("#guided-message");
    if(current)current.textContent=`${error.message} Saved work is preserved. Use Refresh saved work to retry.`;
    else toast(error.message);
  } finally {state.guidedPending=false;node.disabled=false;}
}

/* Goal choice is local presentation only; existing services retain every approval. */
const WMMGoalJourney=(()=>{
 const choices=Object.freeze({
  research:{title:"Find a useful marketing angle",description:"Compare sourced references and prepare the next experiment.",tool:"sources",next:"Add a research reference",view:"research",need:"Research references and authentic app facts"},
  creative:{title:"Produce or revise a video",description:"Bring your clips, choose the message and review the creative before production.",tool:"render",next:"Open creative production",view:"research",need:"Approved brief, cleared media and production tools"},
  campaign:{title:"Run an approved campaign",description:"Choose Facebook, Instagram, TikTok, YouTube Shorts or LinkedIn for an exact approved post. Paid campaigns use the separate Meta controls.",tool:"campaign",next:"Review campaign setup",view:"connections",need:"Your channel connection, exact content and owner publication approval"},
  measurement:{title:"Understand app results",description:"Find the next conversion or retention question supported by your measurements.",tool:"results",next:"Review measurement evidence",view:"results",need:"Your analytics connection or an actual results import"}
 });
 const key=app=>"wmm-goal-choice:"+app;
 const fixed=id=>Object.hasOwn(choices,id)?id:"";
 function read(storage,app){try{return fixed(storage?.getItem(key(app)));}catch{return "";}}
 function save(storage,app,id){if(!fixed(id))throw new Error("Choose one of the displayed goals.");try{if(!storage)return false;storage.setItem(key(app),id);return true;}catch{return false;}}
 function model(workspace,id){
  const goal=choices[fixed(id)];
  return {app_id:workspace.app.id,version:workspace.app.version,objective:workspace.app.data.job||"",goal:goal?{id,...goal}:null,
   accounts:(workspace.social_access?.accounts||[]).filter(a=>["facebook","instagram","tiktok","youtube","linkedin"].includes(a.provider)).map(a=>({status:a.status,destination:(a.data?.destination?.name||a.provider)+" ("+a.provider+")"})),
   classification:"PRESENTATION_ONLY_NO_AUTHORITY"};
 }
 function view(workspace,id,html){
  const m=model(workspace,id),g=m.goal;
  const cards=Object.entries(choices).map(([name,c])=>`<button type="button" class="button outline" data-action="goal-select" data-goal="${name}" data-app="${html(m.app_id)}" data-version="${m.version}" aria-pressed="${name===id}">${html(c.title)}</button>`).join("");
  const next=g?`<section class="panel" aria-label="Your selected goal"><h2>${html(g.title)}</h2><p>${html(g.description)}</p><p><strong>Bring:</strong> ${html(g.need)}.</p><p>${g.id==="campaign"?m.accounts.length?m.accounts.map(a=>html(a.destination)+": "+html(a.status)).join(" · "):"No channel connection is saved for this app.":"Use saved evidence or configure your own supported connection. Missing measurements remain unknown."}</p><p>Account setup is not execution approval. Existing workflow and campaign checks still apply.</p><div class="toolbar"><button type="button" class="button" data-action="goal-next" data-goal="${g.id}" data-app="${html(m.app_id)}" data-version="${m.version}">${html(g.next)}</button><button type="button" class="button outline" data-action="goal-readiness">Check connections for this goal</button><button type="button" class="button outline" data-view="agents">Connect your agent</button></div></section>`:"<p>Choose one goal to see the relevant tools. This selection starts no work and grants no permission.</p>";
  return `<section class="panel" aria-label="Choose your marketing goal"><h2>What would you like to accomplish?</h2><p>Start with one useful result. Your agent and you use the same saved app facts, tools and approval checks.</p><p><strong>Your app purpose:</strong> ${html(m.objective||"Add the problem your app solves in App setup.")}</p><div class="toolbar" role="group" aria-label="Marketing goals">${cards}</div><p id="goal-message" role="status" aria-live="polite"></p></section>${next}`;
 }
 function browserStorage(){try{return globalThis.localStorage??null;}catch{return null;}}
 return {read,save,model,view,choices,browserStorage};
})();

function needsYouPanel(){
 const rows=state.workspace?.workflow?.exceptions||[];
 if(!rows.length)return "";
 const top=rows.slice(0,3).map(c=>`<article class="next-step"><div><h3>${esc(c.headline)}</h3><p>${esc(c.reason)}</p><p><strong>Next:</strong> ${esc(c.action)}</p></div></article>`).join("");
 return `<section class="panel" aria-label="Needs you"><div class="section-heading"><div><p class="eyebrow">NEEDS YOU</p><h2>${rows.length} item${rows.length===1?"":"s"} need a decision</h2></div><button type="button" class="button outline" data-view="workflow">Review workflow</button></div>${top}${rows.length>3?`<p class="description">${rows.length-3} more in the workflow view.</p>`:""}</section>`;
}

function firstMeasuredPostPanel(){
 return `<section class="panel" aria-label="First measured post"><div class="section-heading"><div><p class="eyebrow">START HERE</p><h2>Your first measured post</h2><p>Four steps: tagged link, exact post approval, one publish, then what the source recorded. Each step keeps its own approval; nothing publishes or spends on its own.</p></div>${button("Start the guided path","first-post-open")}</div></section>`;
}

function goalOverview(){
 const id=state.goalChoice?.app===state.app?state.goalChoice.id:WMMGoalJourney.read(WMMGoalJourney.browserStorage(),state.app);
 return heading("Set your goal","Choose one outcome. Watch the work. Review what happened.")+needsYouPanel()+firstMeasuredPostPanel()+WMMGoalJourney.view(state.workspace,id,esc)+button("Open your first packet","automatic-goal-open",WMMGoalPacket.attributes(WMMGoalPacket.model()))+`<details class="panel" id="goal-advanced"><summary>Advanced app overview and twelve-stage diagnostics</summary><div class="toolbar">${button("Review combined automation agreement","goal-agreement")}${button("Monitor approved campaigns","campaign-monitor-open")}${button("Review private campaign outcomes","owner-report-open")}${button("Measure one organic post","observational-campaign-open")}</div>${detailedOverview().replace(/<h1>/g,"<h2>").replace(/<\/h1>/g,"</h2>")}</details>`;
}

function goalAction(node){
 if(node.dataset.action==="goal-agreement")return WMMAgreement.open();
 if(node.dataset.action==="goal-readiness")return WMMGoalReadiness.open();
 if(node.dataset.action==="goal-repair")return WMMGoalReadiness.repair(node.dataset.tool);
 if(node.dataset.app!==state.app||Number(node.dataset.version)!==state.workspace?.app.version)throw new Error("App changed. Choose the goal again for the current app.");
 const id=node.dataset.goal;if(!Object.hasOwn(WMMGoalJourney.choices,id))throw new Error("Choose one of the displayed goals.");
 if(node.dataset.action==="goal-select"){const saved=WMMGoalJourney.save(WMMGoalJourney.browserStorage(),state.app,id);state.goalChoice={app:state.app,id};render();const target=document.querySelector(`[data-action="goal-next"][data-goal="${id}"]`);target?.focus();const msg=document.querySelector("#goal-message");if(msg)msg.textContent=saved?"Goal selected for this app. No work has started.":"Goal selected for this session. Browser storage is unavailable; no work has started.";return;}
 if(node.dataset.action!=="goal-next")throw new Error("Unknown goal action.");
 if(id==="campaign")return guidedNavigate("connections");
 if(id==="creative")return guidedNavigate("research");
 if(id==="research")return guidedOpenTool("sources");
 return guidedNavigate("results");
}

/* Readiness is an owner-only observation, never an automation agreement. */
const WMMGoalReadiness=(()=>{
 const presets={research:['local_evidence','experiment_preparation'],creative:['video_authoring_editing','hypit_caption_render'],campaign:['social_publish','organic_publication'],measurement:['local_evidence','experiment_preparation']};
 const names={local_evidence:'Collect and review app evidence',experiment_preparation:'Prepare or assess an experiment',video_authoring_editing:'Edit and customize video',hypit_caption_render:'Compose Hypit title/caption scenes',social_publish:'Publish exact approved Facebook Page posts',organic_publication:'Publish reviewed Instagram, TikTok, YouTube Shorts or LinkedIn posts',paid_effects:'Run separately approved paid Meta campaigns'};
 let active=null;
 function snapshot(){return {app:state.app,version:state.workspace.app.version,principal:state.workspace.identity?.principal,goal:state.goalChoice?.app===state.app?state.goalChoice.id:WMMGoalJourney.read(WMMGoalJourney.browserStorage(),state.app)};}
 function same(a,b){return a.app===b.app&&a.version===b.version&&a.principal===b.principal&&a.goal===b.goal;}
 function valid(t){return active===t&&same(t.scope,snapshot())&&t.node?.isConnected&&$('#modal').open;}
 function owner(){return state.workspace.access?.members?.some(r=>r.principal===state.workspace.identity?.principal&&r.role==='OWNER'&&r.status==='ACTIVE');}
 function selection(values,saved){const allowed=presets[saved.goal]||[];const workflows=values.workflows||[];if(!workflows.length||workflows.some(w=>!allowed.includes(w)&&!(saved.goal==='campaign'&&w==='paid_effects'))||new Set(workflows).size!==workflows.length)throw new Error('Choose only the workflows displayed for this goal.');return {agent_id:values.agent_id,manifest_version:saved.version,workflows,agent_connection_id:values.agent_connection_id||null,social_connection_ids:values.social_connection_ids||[]};}
 const blockerHelp={
  EXACT_OWNER_CAMPAIGN_SCOPE_REQUIRED:'Review campaign scope to approve the exact posts, accounts, limits and expiry.',
  EXACT_CURRENT_OWNER_PUBLICATION_APPROVAL_REQUIRED:'Review the exact post, destination, media rights, timing and check allowance under Organic publishing.',
  PUBLICATION_CONNECTION_REQUIRED:'Instagram publishing uses a Facebook Page linked to the Instagram professional account; direct Instagram Login is read-only for this workflow.',
  FRESH_INFERENCE_TEST_REQUIRED:'Repair agent connection, then run its connection test.',
  FRESH_DESTINATION_ACCOUNT_REQUIRED:'Repair account connection and verify each selected destination again.',
  PUBLICATION_ADAPTER_REQUIRED:'Select a Facebook Page with supported publishing access.',
  LOCAL_MEDIA_RUNTIME_VERIFICATION_REQUIRED:'Verify the local video tools before rendering.',
  LIVE_VIRAL_COLLECTOR_REQUIRED:'Viral-only discovery needs a verified live collector. Review the available research connections before enabling it.',
  COMPLETE_AGENT_AND_HUMAN_EDITOR_REQUIRED:'Review the selected editor and its supported controls before enabling video work.',
  COMPLETE_KPI_OPERATION_COVERAGE_REQUIRED:'Review KPI coverage and connect the sources needed for missing measurements.',
  RELEASE_EFFECT_OPERATION_COVERAGE_REQUIRED:'Build and deployment actions need a supported execution path before they can run.',
  CURRENT_NATIVE_DEVICE_HOST_REQUIRED:'Open the native iPhone or iPad app for on-device video work.',
  NATIVE_RUNTIME_SETUP_REQUIRED:'Check the app-screen video tools and complete their setup.'
 };
 const statusLabels={BLOCKED:'Needs setup',READY_FOR_SCOPE_REVIEW:'Ready to review permissions',TESTED_FRESH:'Recently verified',MISSING:'Not connected',STALE:'Verification needs refreshing',NOT_VERIFIED:'Not yet verified',INVALID_VERIFICATION:'Verification needs checking',EXPIRED:'Access expired',EXPIRY_UNKNOWN:'Expiry not confirmed',SCOPES_UNKNOWN:'Permissions not confirmed',PROVIDER_SETUP_CHANGED:'Connection settings changed',RENEWING:'Renewing access',DISCONNECTED:'Disconnected'};
 function label(table,key,fallback){return Object.hasOwn(table,key)?table[key]:fallback;}
 function statusLabel(value){return label(statusLabels,value,'Needs review');}
 function markup(data){const i=data.inventory;
  const workflows=i.workflows.map(w=>'<li><strong>'+esc(label(names,w.id,w.name))+'</strong>: '+esc(statusLabel(w.status))+(w.blockers.length?'<ul>'+w.blockers.map(b=>'<li>'+esc(label(blockerHelp,b,'Open Connections to inspect the selected agent and accounts. If setup is current, send the Technical details and saved evidence to support; this check has not authorized work.'))+'</li>').join('')+'</ul>':'')+'</li>').join('');
  const details=i.workflows.map(w=>'<li>'+esc(w.name)+': '+esc(w.status)+'<ul>'+w.blockers.map(b=>'<li><code>'+esc(b)+'</code></li>').join('')+'</ul>'+(w.repair?'<p>'+esc(w.repair)+'</p>':'')+'</li>').join('');
  return '<h3>'+esc(statusLabel(i.scope_status))+'</h3><p>Checked '+esc(data.observed_at)+'. No approval, grant, job or campaign has been created.</p><ul>'+workflows+'</ul><p>Agent connection: '+esc(statusLabel(i.inference.status))+' · last successful test '+esc(i.inference.last_successful_test||'None')+'. Provider quota remains unknown.</p><p>Selected destinations: '+(i.accounts.length?i.accounts.map(a=>esc(a.provider)+' / '+esc(a.destination_id)+' · '+esc(statusLabel(a.status))).join('; '):'None')+'</p><p>Readiness permits scope review only. Campaign publishing and paid work need their own exact owner scope; editor/runtime blockers remain visible.</p><div class="toolbar">'+button('Repair agent connection','goal-repair','data-tool="agents"')+button('Repair account connection','goal-repair','data-tool="connections"')+button('Review automation agreement','goal-repair','data-tool="agreement"')+(i.workflows.some(w=>w.id==='organic_publication')?button('Review organic publication','goal-repair','data-tool="organic-publication"'):'')+(i.workflows.some(w=>['social_publish','paid_effects'].includes(w.id))?button('Review campaign scope','goal-repair','data-tool="campaign"'):'')+'</div><details><summary>Technical details</summary><p>Scope: '+esc(i.scope_status)+' · agent: '+esc(i.inference.status)+'</p><ul>'+details+'</ul><p>Accounts: '+esc(i.accounts.map(a=>a.provider+' / '+a.destination_id+': '+a.status).join('; ')||'None')+'</p><p>Evidence binding: '+esc(data.inventory_sha256)+'</p></details>';
 }
 function open(){const saved=snapshot();if(!presets[saved.goal])throw new Error('Choose a goal first.');if(!owner()){modal('Connect your accounts','<div class="modal-content"><p>Sign in and establish this app’s owner before inspecting private account readiness. This check does not start work.</p>'+button('Open owner setup','goal-repair','data-tool="owner"')+'</div>');return;}
 modal('Choose your agent setup','<div id="goal-readiness-mode" class="modal-content"><p>Keep using your agent’s own model, or check setup for WMM-managed work. This step starts no work and grants no permission. Review exact permissions in the separate approval controls.</p><div class="toolbar">'+button('Use my personal agent','goal-repair','data-tool="external-agent"','primary')+button('Check WMM-managed setup','goal-repair','data-tool="standing-readiness"','outline')+'</div></div>');active={scope:saved,node:$('#goal-readiness-mode'),pending:false};}
 function standing(saved){const profiles=state.workspace.agent_access?.profiles||[],accounts=state.workspace.social_access?.accounts||[],workflows=[...presets[saved.goal],...(saved.goal==='campaign'?['paid_effects']:[])];
 modal('WMM-managed automation setup','<form id="goal-readiness-form" class="modal-content"><p>Optional for ordinary external-agent grants. Choose the WMM-managed agent and accounts to inspect. Saved connection labels do not prove current access; the server checks exact app-owned revisions and freshness.</p><label class="field">Agent identifier<input name="agent_id" pattern="[a-z0-9][a-z0-9-]*" maxlength="200" required placeholder="my-marketing-agent"></label><label class="field">Inference connection<select name="agent_connection_id"><option value="">Not connected</option>'+profiles.map(p=>'<option value="'+esc(p.id)+'">'+esc(p.data.label)+' · '+esc(p.status)+'</option>').join('')+'</select></label><fieldset><legend>Work for this goal</legend>'+workflows.map(w=>'<label class="check-row"><input name="workflows" type="checkbox" value="'+w+'" '+(presets[saved.goal].includes(w)&&w!=='organic_publication'?'checked':'')+'>'+esc(names[w])+'</label>').join('')+'</fieldset><fieldset><legend>Account destinations</legend>'+accounts.map(a=>'<label class="check-row"><input name="social_connection_ids" type="checkbox" value="'+esc(a.id)+'">'+esc(a.provider)+' · '+esc(a.data?.destination?.name||a.subject_id)+' · '+esc(a.status)+'</label>').join('')+'</fieldset><p>Analytics imports and provider-specific connection tests remain in Connections and Results; this inventory checks the selected agent/workflow scope, not every KPI collector.</p><p id="goal-readiness-error" role="alert"></p><button type="submit" class="button">Check selected connections</button>'+button('Cancel','close')+'</form>');active={scope:saved,node:$('#goal-readiness-form'),pending:false};}
 async function submit(form){const t=active;if(!t||t.pending||!valid(t))return;t.pending=true;const submit=form.querySelector('[type=submit]');submit.disabled=true;try{const fd=new FormData(form),values=Object.fromEntries(fd);values.workflows=fd.getAll('workflows');values.social_connection_ids=fd.getAll('social_connection_ids');const body=selection(values,t.scope);const data=await api('/api/apps/'+encodeURIComponent(t.scope.app)+'/agent-grants/automation-readiness',body);if(valid(t)){modal('WMM-managed readiness checklist','<div class="modal-content">'+markup(data)+'</div>');active=null;}}catch(e){if(valid(t))$('#goal-readiness-error').textContent=e.message+' Your selections are preserved.';}finally{t.pending=false;submit.disabled=false;}}
 function repair(tool){if(['external-agent','standing-readiness'].includes(tool)){const t=active;if(!t||!valid(t)||!owner())throw new Error('Reopen setup for the current app and goal.');active=null;if(tool==='external-agent')return WMMAgentControl.action({dataset:{action:'control-grants'}},growthReviewServices());return standing(t.scope);}active=null;if(tool==='campaign')return campaignOpen();if(tool==='agreement')return WMMCompleteAutomation.action({dataset:{action:'standing-open'}},growthReviewServices());if(tool==='owner')return guidedNavigate('activity');if(tool==='organic-publication')return guidedNavigate('connections','#publication-heading');if(['agents','connections'].includes(tool))return guidedNavigate(tool);throw new Error('Choose an available repair.');}
 return {open,submit,selection,markup,repair,same};
})();

const WMMAgreement=(()=>{
 let active=null;
 const scope=()=>({app:state.app,version:state.workspace.app.version,principal:state.workspace.identity?.principal});
 const same=(a,b)=>a.app===b.app&&a.version===b.version&&a.principal===b.principal;
 function valid(t){return active===t&&same(t.scope,scope())&&t.node?.isConnected&&$('#modal').open;}
 function selection(values,saved){const value={manifest_version:saved.version,workflow_policy_id:values.workflow_policy_id||null,campaign_scope_id:values.campaign_scope_id||null,schedule_batch_id:values.schedule_batch_id||null};if(!Object.values(value).slice(1).some(Boolean))throw new Error('Select at least one saved scope or scheduled batch.');return value;}
 function options(rows,key){return '<option value="">Not selected</option>'+rows.map(r=>'<option value="'+esc(r[key])+'"'+(r.evidence_unavailable?' disabled':'')+'>'+esc(r[key])+' · '+esc(r.evidence_unavailable?'Review saved campaign receipts':r.effective_status||r.status)+'</option>').join('');}
 async function open(){const saved=scope();modal('Automation agreement','<div id="agreement-loading" class="modal-content"><p role="status">Reading your saved scopes…</p></div>');const ticket=active={scope:saved,node:$('#agreement-loading')};try{const [local,campaign,batches]=await Promise.all([api('/api/apps/'+saved.app+'/agent-grants/automation-status',{}),api('/api/apps/'+saved.app+'/campaigns/history',{}),api('/api/apps/'+saved.app+'/campaigns/schedule-history',{})]);if(!valid(ticket))return;
 modal('Choose your automation agreement','<form id="agreement-form" class="modal-content"><p>Review local work, campaign effects and schedules together. Their existing approvals remain separate; this review activates nothing.</p><label class="field">Local workflow scope<select name="workflow_policy_id">'+options(local.policies,'id')+'</select></label><label class="field">Campaign scope<select name="campaign_scope_id">'+options(campaign.scopes,'scope_id')+'</select></label><label class="field">Scheduled batch<select name="schedule_batch_id">'+options(batches.batches,'id')+'</select></label><p>A batch includes its linked campaign. Select that same campaign or leave the campaign field empty.</p><p id="agreement-error" role="alert"></p><button class="button" type="submit">Review combined agreement</button>'+button('Cancel','close')+'</form>');active={scope:saved,node:$('#agreement-form'),pending:false};}catch(e){if(valid(ticket))ticket.node.textContent=e.message+' Sign in as the app owner and reconnect required scopes.';}}
 function guidance(s){
  if(s.dispatch_uncertain)return {label:'Delivery needs reconciliation',next:'Inspect saved campaign receipts before any retry. Unknown delivery keeps its existing budget commitment.',tool:'campaign'};
  if(s.campaign?.effective_status!=='ACTIVE'&&s.campaign)return {label:'Campaign needs attention',next:'Open campaign controls to inspect expiry, account access and the exact approved limits.',tool:'campaign'};
  if(s.local_work?.effective_status!=='ACTIVE'&&s.local_work)return {label:'Local work needs attention',next:s.local_work.repair||'Open local scope controls to inspect its current status and approval.',tool:'agreement'};
  if(s.schedule?.effective_status!=='ACTIVE'&&s.schedule)return {label:'Schedule needs attention',next:'Inspect the saved batch. OFF or blocked work does not resume through this review.',tool:'campaign'};
  return {label:'Selected scopes reviewed',next:'Watch saved work and delivery receipts. This review starts no execution.',tool:null};
 }
 function overview(s){const guide=guidance(s),families=[s.local_work,s.campaign,s.schedule].filter(Boolean).length;return '<section class="panel"><h3>'+esc(guide.label)+'</h3><p>'+esc(guide.next)+'</p><dl class="summary-grid"><div><dt>Selected scopes</dt><dd>'+families+'</dd></div><div><dt>Scheduled items</dt><dd>'+(s.schedule?.items.length||0)+'</dd></div><div><dt>Retained media commitment</dt><dd>'+esc(s.campaign?s.campaign.commitment_held_minor+' minor '+s.campaign.approval.currency:'No campaign selected')+'</dd></div></dl>'+(guide.tool?button('Inspect '+(guide.tool==='campaign'?'campaign receipts':'local scope'),'goal-repair','data-tool="'+guide.tool+'"','primary'):'')+'</section>';}
 function scopeDestination(operation,approval){
  const id=operation==='campaign.ad-launch'?approval?.ad_account_id:operation==='campaign.publish'?approval?.page_id:null;
  if(typeof id!=='string'||!/^[0-9]{1,40}$/.test(id))return 'Unavailable';
  return (operation==='campaign.ad-launch'?'Meta ad account ':'Facebook Page ')+id;
 }
 function campaignDestinations(approval){
  const page=scopeDestination('campaign.publish',approval),ads=scopeDestination('campaign.ad-launch',approval);
  return 'Page for posts '+page+' · paid promotion '+(approval?.ad_account_id===null?'None selected':ads);
 }
 function campaignLimits(c){
  const a=c.approval||{};
  return 'Permission expires '+(c.permission_expires_at||a.expires_at||'Unavailable')
   +' · original approval '+(a.expires_at||'Unavailable')
   +' · posts '+(a.max_posts??'Unavailable')+' · campaigns '+(a.max_campaigns??'Unavailable')+' · calls '+(a.max_calls??'Unavailable');
 }
 function scheduledMarkup(item,approval){
  const currency=approval?.currency||'Unknown';
  const paid=item.operation==='campaign.ad-launch',r=item.request,intent=item.intent;
  const ids=paid?Object.entries(intent?.ids||{}).map(([kind,id])=>esc(kind)+': '+esc(id)).join('; '):esc(intent?.remote_id||'Not confirmed');
  const postLink=paid?'':'<p>Approved post link <span>'+esc(r.link||'None')+'</span></p>';
  return '<article><h4>'+esc(item.operation||'campaign.publish')+' · '+esc(item.due_at)+'</h4><p>Scope destination '+esc(scopeDestination(item.operation||'campaign.publish',approval))+'</p><p>'+esc(paid?'Promotion of verified Page post '+r.post_id:r.message)+'</p>'+postLink+(paid?'<p>Exact media budget '+esc(r.lifetime_budget_minor)+' minor '+esc(currency)+' · ends '+esc(r.end_time)+'</p><p>Audience countries '+esc((r.targeting?.countries||[]).join(', '))+'</p><p>Retained commitment '+esc(intent?.commitment??'Not yet recorded')+' minor '+esc(intent?.currency||currency)+'. Provider fees and taxes are separate.</p>':'')+'<p>Effective state '+esc(item.effective_status||'Unknown')+' · worker '+esc(item.job_status||'Not queued')+' · saved result '+esc(intent?.status||'Unconfirmed')+'</p><p>Saved provider IDs: '+(ids||'Not confirmed')+'</p></article>';
 }
 function draftMarkup(data){
  const s=data.summary,c=s.campaign;
  return '<section class="panel"><h3>Draft automation agreement</h3><p>No execution authority is issued.</p>'+
   '<h4>Exact proposed Facebook posts</h4>'+c.draft_posts.map(post=>
    '<article><p>'+esc(post.message)+'</p><p>Proposed post link <span>'+esc(post.link||'None')+
    '</span></p><small>Content hash: '+esc(post.content_hash)+'</small></article>').join('')+
   '<p>'+esc(campaignLimits(c))+'</p><details><summary>Agreement details and stop rules</summary>'+
   '<p>'+esc(campaignDestinations(c.approval))+'</p><p>'+esc(campaignExecutor(s))+'</p>'+
   '<p>'+esc(s.stop_rules.join('; '))+'</p><p>Summary hash: '+esc(data.summary_hash)+'</p></details></section>';
 }
 function campaignExecutor(s){
  if(s.schedule)return 'Scheduled executor when the batch is active — WMM background worker. Owner '+(s.owner?.principal||'Unavailable')+'. Batch '+s.schedule.id+'. Campaign scope '+(s.campaign?.id||'Unavailable')+'. Dispatch rechecks the exact batch, scope and stop rules.';
  return 'No agent selected by campaign scope. Direct execution requires separate owner, worker or scoped grant authority.';
 }
 function fingerprintLabels(approval){return [["Approved content fingerprints",approval?.approved_content_hashes],["Approved rights fingerprints",approval?.approved_rights_hashes],["Approved targeting fingerprints",approval?.approved_targeting_hashes]];}
 function fingerprintValue(values){return !Array.isArray(values)?"Unavailable":values.length?values.map(String).join(", "):"None approved";}
 function fingerprintMarkup(approval){return '<details><summary>Exact approved content, rights and targeting hashes</summary><ul>'+fingerprintLabels(approval).map(([label,values])=>'<li><strong>'+label+': </strong>'+(!Array.isArray(values)?"Unavailable":values.length?values.map(value=>'<code>'+esc(value)+'</code>').join(", "):"None approved")+'</li>').join("")+'</ul></details>';}
 function campaignReportNotes(c){const a=c.approval||{};return ["Campaign "+c.id+" "+c.effective_status,campaignDestinations(a),campaignLimits(c),"Per-campaign media cap "+(a.max_campaign_minor??"Unavailable")+" minor "+(a.currency||"Unknown"),"Maximum total media commitment "+(a.max_total_minor??"Unavailable")+" minor "+(a.currency||"Unknown"),...fingerprintLabels(a).map(([label,values])=>label+": "+fingerprintValue(values))];}
 function markup(data){const s=data.summary,l=s.local_work,c=s.campaign,b=s.schedule;return overview(s)+'<h3>'+esc(data.status==='success'?'Combined scope reviewed':'Needs attention')+'</h3><p>App '+esc(s.app.id)+' · version '+s.app.version+' · owner '+esc(s.owner.principal)+'</p><p><strong>No execution authority is issued.</strong> Each existing scope keeps its own enforcement and OFF control.</p>'+(l?'<section class="panel"><h3>Local agent work</h3><p>Agent '+esc(l.summary?.inventory?.selection?.agent_id||'Unavailable')+' · '+esc(l.effective_status)+' · expires '+esc(l.summary?.stops_at||'Unavailable')+'</p><details><summary>Exact permitted local operations</summary><p>'+esc((l.summary?.operations||[]).join(', '))+'</p></details><p>Zero local spend · calls '+esc(l.usage?.used??'Unknown')+'/'+esc(l.usage?.max_calls??'Unknown')+'</p>'+(l.repair?'<p>'+esc(l.repair)+'</p>':'')+'</section>':'<p>No local-work scope selected.</p>')+(c?'<section class="panel"><h3>Campaign effects</h3><p>'+esc(campaignExecutor(s))+'</p><p>Local preparation keeps its own agent assignment and permissions.</p><p>'+esc(c.effective_status)+' · '+esc(campaignDestinations(c.approval))+'</p><p>'+esc(campaignLimits(c))+'</p><p>Per-campaign media cap '+esc(c.approval.max_campaign_minor??'Unavailable')+' minor '+esc(c.approval.currency)+'; maximum total media commitment '+esc(c.approval.max_total_minor??'Unavailable')+' minor '+esc(c.approval.currency)+'; held '+esc(c.commitment_held_minor)+'.</p>'+fingerprintMarkup(c.approval)+'<p>Scopes '+esc((c.account.reported_scopes||[]).join(', '))+' · '+esc(c.account.status)+'</p><p>'+esc(c.billing_notice)+'</p><p>'+esc(c.blockers.join('; '))+'</p></section>':'<p>No campaign scope selected.</p>')+(b?'<section class="panel"><h3>Scheduled work</h3><p>'+esc(b.effective_status)+' · batch '+esc(b.id)+' · captured deadline '+esc(b.permission_expires_at||c?.approval.expires_at||'Unavailable')+'</p>'+'<p>'+esc((b.blockers||[]).join('; '))+'</p>'+b.items.map(i=>scheduledMarkup(i,c?.approval)).join('')+'</section>':'<p>No batch selected.</p>')+'<p>Stop rules: '+esc(s.stop_rules.join('; '))+'</p><p>'+esc(s.revocation)+'</p><p>Inference pricing unknown. Provider spend can lag. Credential availability is revalidated at dispatch.</p><p>Summary hash: '+esc(data.summary_hash)+'</p><div class="toolbar">'+button('Local scope controls','goal-repair','data-tool="agreement"')+button('Campaign controls','goal-repair','data-tool="campaign"')+button('Agreement report / Save PDF','agreement-report')+'</div>';}
 async function submit(form){const t=active;if(!t||t.pending||!valid(t))return;t.pending=true;const submit=form.querySelector('[type=submit]');submit.disabled=true;try{const values=Object.fromEntries(new FormData(form));const data=await api('/api/apps/'+t.scope.app+'/agent-grants/agreement-preview',selection(values,t.scope));if(!valid(t))return;modal('Your combined automation agreement','<div id="agreement-summary" class="modal-content">'+markup(data)+'</div>');active={scope:t.scope,node:$('#agreement-summary'),data};}catch(e){if(valid(t))$('#agreement-error').textContent=e.message+' Your selections are preserved.';}finally{t.pending=false;submit.disabled=false;}}
 function localWorkReportNotes(l){
  if(!l)return ['No local policy'];
  const operations=Array.isArray(l.summary?.operations)?(l.summary.operations.length?l.summary.operations.map(String).join(', '):'None'):'Unavailable';
  return [
   'Local policy '+(l.id||'Unavailable')+' '+(l.effective_status||'Unknown'),
   'local-work agent '+(l.summary?.inventory?.selection?.agent_id||'Unavailable'),
   'Local-work permitted operations '+operations,
   'Local-work permission expires '+(l.summary?.stops_at||'Unavailable'),
   'Local-work calls '+(l.usage?.used??'Unknown')+'/'+(l.usage?.max_calls??'Unknown'),
   'Local-work spend limit '+(l.spend_limit_minor??'Unavailable')+' minor'
  ];
 }
 function reportModel(data,base){const s=data.summary,c=s.campaign;return {...base,title:'Combined automation agreement',purpose:'Review selected independent scope identities, states and resource allowances.',metrics:[{label:'Selected scope families',value:[s.local_work,c,s.schedule].filter(Boolean).length,unit:'count',source:'Current owner agreement snapshot'},{label:'Needs attention',value:s.blocked?'Yes':'No',unit:'state',source:'Current owner agreement snapshot'},{label:'Retained media commitment',value:c?.commitment_held_minor??null,unit:c?'minor '+c.approval.currency:'unavailable',source:'Saved campaign intents'}],cohorts:[],notes:['Summary '+data.summary_hash+'; observed '+data.observed_at,'App '+s.app.id+' version '+s.app.version,c?campaignExecutor(s):'No campaign executor selected','No approval or execution authority issued; underlying scope controls remain separate.',...localWorkReportNotes(s.local_work),...(c?campaignReportNotes(c):['No campaign']),s.schedule?'Batch '+s.schedule.id+' '+s.schedule.effective_status:'No batch',...(s.schedule?.items||[]).map(i=>'Item '+(i.item_id||'Unknown')+' '+(i.operation||'campaign.publish')+' · due '+(i.due_at||'Unknown')+' · Scope destination '+scopeDestination(i.operation||'campaign.publish',c?.approval)+' · '+(i.effective_status||'Unknown')+(i.operation==='campaign.ad-launch'?' · media budget '+i.request.lifetime_budget_minor+' minor '+(c?.approval.currency||'Unknown')+' · held '+(i.intent?.commitment??'Not yet recorded')+' · ends '+i.request.end_time+' · saved provider IDs '+Object.entries(i.intent?.ids||{}).map(([k,v])=>k+': '+v).join('; '):'')),'Private content, rights prose and credentials are excluded. Business improvement is not established.']};}
 function report(){if(!active?.data||!valid(active))throw new Error('Reload the current agreement first.');return WMMPageReports.openReport(reportModel(active.data,WMMPageReports.model(state)),window);}
 return {open,submit,selection,guidance,markup,draftMarkup,reportModel,report};
})();
