"use strict";

function guidedButton(tool,cls="outline") {
  return button(tool.title,"guided-tool",`data-tool="${esc(tool.id)}"`,cls);
}

function guidedOverviewPanel() {
  const g=state.workspace.workflow;
  const title=g.steps.find(s=>s.id===g.next_step)?.title||g.next_action.title;
  return `<section class="panel guided-summary"><div class="section-heading"><div><p class="eyebrow">NEXT AGENT WORK / YOUR APPROVAL</p><h2>${esc(title)}</h2></div>${button("Continue workflow","guided-continue","","")}</div><p>${g.local_ready_count} of 12 local input checks ready. Review the agent’s action and evidence; publication and measured results need separate proof.</p>${button("See the complete workflow","guided-open")}</section>`;
}

function guidedStep(step) {
  const issues=[...step.direct_needs,...step.critical_findings.map(t=>`Resolve critical finding: ${t}`)];
  return `<article class="panel guided-step" id="workflow-step-${step.id}"><div class="section-heading"><div><p class="eyebrow">STEP ${step.id} / 12</p><h2>${esc(step.title)}</h2></div>${status(step.local_status)}</div><p>${esc(step.description)}</p>${issues.length?`<ul>${issues.map(t=>`<li>${esc(t)}</li>`).join("")}</ul>`:"<p>Direct local inputs meet their checks. Verify the actual result separately.</p>"}${step.dependency_needs.length?`<details><summary>Earlier prerequisites</summary><ul>${step.dependency_needs.map(t=>`<li>${esc(t)}</li>`).join("")}</ul></details>`:""}<div class="toolbar">${resolutionButton(step.id)||guidedButton(step.primary)}</div><details class="guided-tools"><summary>Tools and verification</summary><p>${esc(step.verify)}</p><div class="toolbar">${step.tools.map(t=>guidedButton(t)).join("")}</div><small>${step.record_ids.length} saved input records · current versions are checked again when you continue.</small></details></article>`;
}

function guidedView() {
  const g=state.workspace.workflow;
  return `${heading("Your guided workflow","Resume saved work and take the next useful step.",button("Continue workflow","guided-continue","",""))}<section class="panel guided-summary" id="guided-workflow" aria-label="Workflow progress"><p class="eyebrow">SAVED EVIDENCE / CURRENT RELEASE</p><h2>${g.local_ready_count} of 12 local input checks ready</h2><p>Next: ${esc(g.next_action.title)}</p><p class="description">Saved evidence keeps this checklist current. Ready inputs still need review, publication checks and measured results.</p><div class="toolbar">${button("Refresh saved work","guided-refresh")}${button("Download this checklist","guided-download")}${button("Inspect current packets","automatic-open")}</div><p id="guided-message" class="field-error" role="status" aria-live="polite"></p></section>${guidedEvidenceStates()}${guidedCriticalFindings(g)}${notice("Continue opens the next setup or review step. Provider changes keep their own approval.")}${guidedStageJourney(g)}${guidedWorker()}`;
}

function guidedEvidenceStates() {
  return `<section class="panel" aria-label="Understand workflow progress"><h2>Know what each result means</h2><dl><dt><strong>Inputs ready</strong></dt><dd>The saved facts pass this stage’s local checks.</dd><dt><strong>Execution approved</strong></dt><dd>You approved an exact action. Its execution receipt tells you whether it ran.</dd><dt><strong>Outcome observed</strong></dt><dd>A source records what happened. Missing results stay unknown; counts alone do not prove growth.</dd></dl></section>`;
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
