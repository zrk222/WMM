"use strict";

/** Present a finite recommendation and retained runs without requiring manual research. */
function sequencePanel() {
  const value=state.workspace.sequences;if(!value)return "";
  const p=value.proposal;
  return `<section class="panel" id="campaign-sequence"><p class="eyebrow">AGENT FOLLOW-THROUGH</p><h2>Review once. Follow the progress.</h2><p>${p.steps.length?`${p.steps.length} available evidence actions are ready for review.`:"The next work needs source access or an implementation step."} The local worker follows your approved list and keeps its results when you close the browser.</p><div class="toolbar">${button("Review execution plan","automatic-sequence-review")}${button("View saved runs","automatic-sequence-history")}</div>${sequenceRecent(value.history)}</section>`;
}

/** Keep the latest saved runs visible while retaining the full app-scoped history. */
function sequenceRecent(history) {
  let html="";for(const run of history.slice(0,3))html+=`<p>${esc(label(run.state))} · ${esc(run.summary)} ${button("Inspect progress","automatic-sequence-run",`data-id="${esc(run.id)}"`)}</p>`;
  return html;
}

/** Name the reviewed target without exposing raw request or credential material. */
function sequenceTarget(step) {
  return step.parameters.url||step.parameters.name||step.parameters.provider||"This app's connected sources";
}

/** Explain each optional action and its evidence limit before approval. */
function sequenceChoices(proposal) {
  let html="";
  for(const step of proposal.steps)html+=`<article class="panel"><label class="check-row"><input type="checkbox" name="step" value="${esc(step.id)}" checked><strong>${esc(step.title)}</strong></label><p>${esc(sequenceTarget(step))}</p><p>${esc(step.artifact)}</p><details><summary>Scope, cost and limits</summary><p>${esc(step.cost)}</p><p>${esc(step.limits)}</p></details></article>`;
  return html;
}

/** Review the exact current ordered list; edits may remove actions. */
function sequenceReview() {
  const p=state.workspace.sequences.proposal;
  modal("Review the next work",`<form id="sequence-form" data-app="${esc(state.app)}" data-proposal="${esc(p.proposal_hash)}" data-request="${crypto.randomUUID()}"><div class="modal-content" id="sequence-dialog"><p>Keep the actions you want the agent to perform. After approval, the local worker follows this list, records each outcome, and continues independent work when a check fails.</p><p>Approval covers these actions for ${Math.round(p.approval_seconds/60)} minutes. A changed app or source can require a new approval. These evidence checks do not publish a campaign or spend an advertising budget.</p>${p.existing_site_evidence?notice("A current website observation is already saved; this plan avoids repeating that read."):""}${sequenceChoices(p)}${!p.steps.length?notice(p.next_actions[0],"warning"):""}<p id="sequence-error" role="alert"></p></div><div class="modal-actions">${p.steps.length?'<button type="submit" class="button primary">Approve and run selected actions</button>':""}${button("Review source access","measurement-connections")}${button("Cancel","close")}</div></form>`,"REVIEW / EDIT / APPROVE");
  $("#modal-body").dataset.sequence="";
}

/** Open retained app-specific runs without restarting their execution. */
function sequenceHistory() {
  let html="";for(const run of state.workspace.sequences.history)html+=`<article class="panel"><h3>${esc(label(run.state))}</h3><p>${esc(run.summary)}</p>${button("Inspect progress","automatic-sequence-run",`data-id="${esc(run.id)}"`)}</article>`;
  modal("Saved execution runs",`<div class="modal-content">${html||"<p>No approved sequence is saved for this app yet.</p>"}</div><div class="modal-actions">${button("Review next work","automatic-sequence-review")}${button("Close","close")}</div>`);
  $("#modal-body").dataset.sequence="";
}

/** Give each action a readable state and a link to its native evidence receipt. */
function sequenceProgress(run) {
  let items="";
  for(let i=0;i<run.steps.length;i++) {
    const step=run.steps[i],outcome=run.step_outcomes.find(o=>o.position===i);
    const pending=i===run.checkpoint&&run.state==="WAITING"?"Waiting for the saved action":"Not run";
    items+=`<li><strong>${esc(step.title)}</strong><p>${esc(outcome?label(outcome.state):pending)}</p>${outcome?.job_id?button("Inspect evidence","automatic-resolution-run",`data-id="${esc(outcome.job_id)}"`):""}</li>`;
  }
  return `<p id="sequence-status" role="status" aria-live="polite">${esc(label(run.state))} · ${esc(run.summary)}</p><p>${run.checkpoint} of ${run.steps.length} actions recorded. Evidence still needs review against the original requirements.</p><ol>${items}</ol><h3>Next steps</h3><ul>${run.next_actions.map(sequenceNextItem).join("")}</ul>`;
}

/** Escape server-provided recovery guidance before presenting it. */
function sequenceNextItem(value) {return `<li>${esc(value)}</li>`;}

/** Inspect live progress while keeping cancellation and recovery easy to reach. */
function sequenceRun(id) {
  const run=state.workspace.sequences.history.find(r=>r.id===id);
  if(!run)return toast("Refresh this app to inspect the saved run.");
  const active=["QUEUED","WAITING"].includes(run.state);
  modal("Execution progress",`<div class="modal-content" id="sequence-dialog">${sequenceProgress(run)}<p id="sequence-error" role="alert"></p></div><div class="modal-actions">${button("Refresh progress","automatic-sequence-refresh",`data-id="${esc(id)}"`)}${active?button("Stop this plan","automatic-sequence-cancel",`data-id="${esc(id)}"`):""}${button("Review next work","automatic-sequence-review")}${button("Close","close")}</div>`,"SAVED WORK / EVIDENCE / NEXT STEPS");
  $("#modal-body").dataset.sequence=id;
  $("#sequence-dialog").dataset.observation=JSON.stringify(run);
  const key=state.app+":"+id;
  if(active&&state.sequencePoll!==key) {
    state.sequencePoll=key;
    sequencePoll(id,state.app).catch(sequenceError).finally(()=>{if(state.sequencePoll===key)state.sequencePoll=null;});
  }
}

/** Preserve the saved view on connection errors and leave a visible retry control. */
function sequenceError(error) {const target=$("#sequence-error");if(target)target.textContent=error.message;}

/** A different review or evidence modal must never receive stale polling updates. */
function sequenceVisible(id,app) {
  return state.app===app&&$("#modal").open&&$("#sequence-status")&&$("#modal-body").dataset.sequence===id;
}

/** Keep focus and existing DOM intact when the saved progress has not changed. */
function sequenceUpdate(run) {
  const target=$("#sequence-dialog"),value=JSON.stringify(run);
  if(target.dataset.observation===value)return;
  const active=target.contains(document.activeElement)?document.activeElement:null;
  const action=active?.dataset.action,id=active?.dataset.id;
  target.innerHTML=sequenceProgress(run)+'<p id="sequence-error" role="alert"></p>';
  target.dataset.observation=value;
  if(action&&id)target.querySelector(`[data-action="${CSS.escape(action)}"][data-id="${CSS.escape(id)}"]`)?.focus();
}

/** Follow saved state only; polling never authorizes or replays a tool action. */
async function sequencePoll(id,app) {
  while(sequenceVisible(id,app)) {
    await new Promise(resolve=>setTimeout(resolve,1000));
    if(!sequenceVisible(id,app))return;
    await refresh();
    if(!sequenceVisible(id,app))return;
    const run=state.workspace.sequences.history.find(r=>r.id===id);if(!run)return;
    sequenceUpdate(run);
    if(!["QUEUED","WAITING"].includes(run.state)) {
      $("#modal-body").querySelector('[data-action="automatic-sequence-cancel"]')?.remove();return;
    }
  }
}

/** Route only the declared review, readback and cancellation controls. */
async function sequenceAction(node) {
  const action=node.dataset.action,id=node.dataset.id,app=state.app;
  if(action==="automatic-sequence-review")return sequenceReview();
  if(action==="automatic-sequence-history")return sequenceHistory();
  if(action==="automatic-sequence-run")return sequenceRun(id);
  if(action==="automatic-sequence-cancel")await api(`/api/apps/${encodeURIComponent(app)}/sequences/${encodeURIComponent(id)}/cancel`,{confirm_cancel:true});
  await refresh();if(state.app===app)sequenceRun(id);
}

/** Submit current selections once; the server binds all authority and target details. */
async function sequenceSubmit(event) {
  if(event.target.id!=="sequence-form")return;
  event.preventDefault();const form=event.target,app=form.dataset.app,submit=form.querySelector('button[type="submit"]');
  submit.disabled=true;
  try {
    if(state.app!==app||state.workspace.sequences.proposal.proposal_hash!==form.dataset.proposal)throw Error("App or sources changed. Review the current plan.");
    const ids=Array.from(form.querySelectorAll('input[name="step"]:checked')).map(sequenceSelectedId);
    if(!ids.length)throw Error("Keep at least one action to approve.");
    const run=await api(`/api/apps/${encodeURIComponent(app)}/sequences/approve`,{proposal_hash:form.dataset.proposal,selected_steps:ids,request_key:form.dataset.request});
    await refresh();if(state.app===app)sequenceRun(run.id);
  } catch(error) {if(form.isConnected)sequenceError(error);}
  finally {if(form.isConnected)submit.disabled=false;}
}

/** Read only the selected opaque action identity from the form. */
function sequenceSelectedId(input) {return input.value;}

document.addEventListener("submit",sequenceSubmit);
