"use strict";

/** Explain delivery evidence separately from imported cohort comparisons. */
function trackingPanel() {
  let rows="";for(const experiment of state.workspace.experiments||[])rows+=`<p><strong>${esc(experiment.data.name)}</strong> ${button("Inspect live tracking","automatic-tracking-review",`data-id="${esc(experiment.id)}"`)}</p>`;
  return `<section class="panel" id="experiment-tracking"><p class="eyebrow">EXPERIMENT DELIVERY EVIDENCE</p><h2>Are the right variants being measured?</h2><p>Review the expected PostHog setup and read counts from this app’s connected project. A flag evaluation is not a confirmed view, and a tracking check does not launch a campaign.</p>${rows||'<p>Register a test before inspecting its delivery evidence.</p>'+button("Plan an experiment","experiment-create")}<div class="toolbar">${button("Saved tracking reads","automatic-tracking-history")}${button("Review source access","measurement-connections")}</div></section>`;
}

/** Show a concrete access path rather than an approval with no usable source. */
function trackingAccess() {
  modal("Connect experiment measurement",`<div class="modal-content" id="tracking-dialog"><p>This app needs a connected PostHog project. Use its project ID and a permitted key with project, feature-flag and query read access. This does not grant provider write permission.</p><p>Once connected, return here. WMM derives the experiment key and expected split from your registered test.</p></div><div class="modal-actions">${button("Open connections","measurement-connections")}${button("Close","close")}</div>`);
}

/** Derive provider read details from the selected app without research fields. */
async function trackingReview(id) {
  const app=state.app,source=state.workspace.insights.sources.find(s=>s.provider==="posthog");
  if(!source||["DISCONNECTED","CLEANUP_REQUIRED"].includes(source.status))return trackingAccess();
  const token=crypto.randomUUID();modal("Review tracking check",'<div class="modal-content"><p id="tracking-loading" role="status">Preparing this app’s current experiment setup…</p></div>');
  $("#modal-body").dataset.trackingReview=token;
  try {
    const plan=await api(`/api/apps/${encodeURIComponent(app)}/experiment-tracking/prepare`,{experiment_id:id,source_id:source.id});
    if(trackingReviewVisible(app,token))trackingForm(plan);
  } catch(error) {
    if(trackingReviewVisible(app,token))modal("Tracking setup needs review",`<div class="modal-content" id="tracking-dialog"><p role="alert">${esc(error.message)}</p><p>The saved setup was not approved or queued. Refresh the workspace and review the current experiment or source connection.</p></div><div class="modal-actions">${button("Refresh workspace","automatic-tracking-reload")}${button("Review source access","measurement-connections")}${button("Close","close")}</div>`);
  }
}

/** Ignore a late setup response after its loading dialog has been replaced. */
function trackingReviewVisible(app,token) {return state.app===app&&$("#modal").open&&$("#tracking-loading")&&$("#modal-body").dataset.trackingReview===token;}

/** Explain the exact target, scope and instrumentation gap before approval. */
function trackingForm(plan) {
  queueMicrotask(()=>{
    if($("#tracking-form")?.dataset.proposal===plan.proposal_hash)
      $("#tracking-error").insertAdjacentHTML("beforebegin",instrumentationDownloadControl(plan));
  });
  modal("Review tracking check",`<form id="tracking-form" data-app="${esc(state.app)}" data-experiment="${esc(plan.experiment_id)}" data-source="${esc(plan.source_id)}" data-proposal="${esc(plan.proposal_hash)}" data-request="${crypto.randomUUID()}"><div class="modal-content" id="tracking-dialog"><p>WMM recommends this setup from the registered experiment. Approve up to three read-only requests per attempt: project identity, experiment flag and scoped aggregate events. An interruption can repeat reads under the existing three-attempt worker recovery limit. Provider usage limits still apply.</p><dl><dt>Project / release / locale</dt><dd>${esc(plan.project_id)} / ${esc(plan.release)} / ${esc(plan.locale)}</dd><dt>Expected experiment key</dt><dd>${esc(plan.flag_key)}</dd><dt>Observation window</dt><dd>${esc(plan.starts_at)} to ${esc(plan.ends_at)}</dd></dl><p>The expected setup includes two variants and continuity across authentication. Your app still needs to emit assignment and rendered-exposure events with this experiment hash. These checks do not install that instrumentation, publish, spend or establish a winner.</p><details><summary>Expected provider configuration and event contract</summary><pre>${esc(JSON.stringify({flag:plan.expected_flag,events:plan.events,experiment_hash:plan.experiment_hash,required_event_properties:["wmm_app_id","wmm_release","wmm_locale","wmm_experiment_hash","wmm_variant"]},null,2))}</pre></details><p>Approval lasts 30 minutes. Changes to this app, source or test require a fresh review.</p><p id="tracking-error" role="alert"></p></div><div class="modal-actions"><button class="button primary" type="submit">Approve read-only check</button>${button("Review source access","measurement-connections")}${button("Cancel","close")}</div></form>`,"REVIEW / APPROVE / NO PROVIDER WRITES");
}

/** Keep installation preparation explicit and separate from read approval. */
function instrumentationDownloadControl(plan) {
  return `<section><h3>Connect the app’s measurement</h3><p>Download an exact browser integration package for this app, release and experiment. It includes source hashes and consent/identity checks. Downloading does not install code, launch variants or verify delivery. Native app integration remains separate.</p>${button("Download browser integration package","automatic-tracking-package",`data-app="${esc(state.app)}" data-id="${esc(plan.experiment_id)}" data-source="${esc(plan.source_id)}" data-proposal="${esc(plan.proposal_hash)}"`)}</section>`;
}

/** Reject stale setup and surface download errors within the current review. */
async function trackingPackage(node) {
  const app=state.app,proposal=node.dataset.proposal;
  const current=()=>state.app===app&&$("#tracking-form")?.dataset.proposal===proposal;
  if(node.dataset.app!==app||!current())return;
  node.disabled=true;
  try {
    const values=[app,"experiment-tracking",node.dataset.id,"instrumentation",node.dataset.source,proposal];
    const response=await fetch("/api/apps/"+values.map(encodeURIComponent).join("/"));
    if(!response.ok)throw Error((await response.json()).error||"Review the current app and tracking setup before downloading.");
    const file=await response.blob();if(!current())return;
    const address=URL.createObjectURL(file),link=document.createElement("a");
    link.href=address;link.download="wmm-"+node.dataset.id+"-instrumentation.zip";link.click();
    setTimeout(()=>URL.revokeObjectURL(address),1000);
  } catch(error) {if(current())$("#tracking-error").textContent=error.message;}
  finally {if(node.isConnected)node.disabled=false;}
}

/** Persist exact read consent without accepting commands or credentials. */
async function trackingSubmit(event) {
  if(event.target.id!=="tracking-form")return;
  event.preventDefault();const form=event.target,app=form.dataset.app,submit=form.querySelector('button[type="submit"]');submit.disabled=true;
  try {
    if(state.app!==app)throw Error("Selected app changed. Review its current setup.");
    const run=await api(`/api/apps/${encodeURIComponent(app)}/experiment-tracking/approve`,{experiment_id:form.dataset.experiment,source_id:form.dataset.source,proposal_hash:form.dataset.proposal,request_key:form.dataset.request,confirm_read:true});
    await refresh();if(state.app===app)trackingRun(run.id);
  } catch(error) {if(form.isConnected)$("#tracking-error").textContent=error.message;}
  finally {if(form.isConnected)submit.disabled=false;}
}

/** Render deduplicated aggregate rows without implying verified human exposure. */
function trackingCounts(result) {
  if(!result?.observed_counts?.length)return '<p>No scoped tracking observations are established by this receipt.</p>';
  let rows="";for(const row of result.observed_counts)rows+=`<tr><td>${esc(row.arm)}</td><td>${esc(label(row.event))}</td><td>${row.event_rows}</td><td>${row.subjects}</td></tr>`;
  return `<div class="table-wrap"><table class="result-table"><thead><tr><th>Variant</th><th>Event</th><th>Rows</th><th>Distinct IDs</th></tr></thead><tbody>${rows}</tbody></table></div><p>IDs observed across both variants: ${result.cross_arm_subjects??"Unknown"}. These counts do not verify distinct people, human views or a causal effect.</p>`;
}

/** Keep current state, evidence limits and concrete recovery guidance together. */
function trackingProgress(run) {
  const result=run.result,findings=result?.flag_findings||[];
  const next=run.next_actions||result?.next_actions||["Keep the local worker running, refresh progress, or stop this check."];
  const saved=run.updated?new Date(run.updated).toLocaleString():"time unavailable";
  return `<p id="tracking-status" role="status" aria-live="polite">${esc(label(run.status))}</p><p>Saved ${esc(saved)}. Changed setup requires a current check.</p>${result?.failure_code?notice(label(result.failure_code),"warning"):""}${findings.map(value=>notice(value,"warning")).join("")}${trackingCounts(result)}<p>${esc(result?.scope||"Read-only tracking check; no campaign launch or automatic evidence approval.")}</p><h3>Next steps</h3><ul>${next.map(value=>`<li>${esc(value)}</li>`).join("")}</ul>${trackingRecovery(run)}<p id="tracking-error" role="alert"></p>`;
}

/** Keep contextual actions in the scrollable evidence area, leaving a compact footer. */
function trackingRecovery(run) {
  return `<div class="toolbar">${run.job_id?button("Inspect worker receipt","job",`data-id="${esc(run.job_id)}"`):""}${run.experiment_id?button("Review current check","automatic-tracking-review",`data-id="${esc(run.experiment_id)}"`):""}${button("Review source access","measurement-connections")}</div>`;
}

/** Open a saved run and follow durable worker state independently of the browser. */
function trackingRun(id) {
  const run=state.workspace.experiment_tracking.find(r=>r.id===id);if(!run)return toast("Refresh this app to inspect the saved tracking read.");
  const active=["QUEUED","READING"].includes(run.status);
  modal("Tracking read result",`<div class="modal-content" id="tracking-dialog">${trackingProgress(run)}</div><div class="modal-actions">${button("Refresh","automatic-tracking-refresh",`data-id="${esc(id)}"`)}${active?button("Stop check","automatic-tracking-cancel",`data-id="${esc(id)}"`):""}${button("Close","close")}</div>`,"SAVED READ / EVIDENCE / RECOVERY");
  $("#modal-body").dataset.trackingRun=id;$("#tracking-dialog").dataset.observation=JSON.stringify(run);
  const key=state.app+":"+id;
  if(active&&state.trackingPoll!==key) {
    state.trackingPoll=key;
    trackingPoll(id,state.app).catch(error=>{const field=$("#tracking-error");if(field)field.textContent=error.message;}).finally(()=>{if(state.trackingPoll===key)state.trackingPoll=null;});
  }
}

/** Stop stale polling when the operator changes apps, dialogs or selected runs. */
function trackingVisible(id,app) {return state.app===app&&$("#modal").open&&$("#tracking-status")&&$("#modal-body").dataset.trackingRun===id;}

/** Leave focus and DOM untouched unless the actual saved receipt changes. */
function trackingUpdate(run) {
  const target=$("#tracking-dialog"),value=JSON.stringify(run);
  if(target.dataset.observation===value)return;
  const focused=target.contains(document.activeElement)?document.activeElement:null;
  const action=focused?.dataset.action,id=focused?.dataset.id;
  target.innerHTML=trackingProgress(run);target.dataset.observation=value;
  if(action&&id)target.querySelector(`[data-action="${CSS.escape(action)}"][data-id="${CSS.escape(id)}"]`)?.focus();
}

/** Poll local state only; reads never reapprove or requeue provider work. */
async function trackingPoll(id,app) {
  while(trackingVisible(id,app)) {
    await new Promise(resolve=>setTimeout(resolve,1000));if(!trackingVisible(id,app))return;
    await refresh();if(!trackingVisible(id,app))return;
    const run=state.workspace.experiment_tracking.find(r=>r.id===id);if(!run)return;
    trackingUpdate(run);
    if(!["QUEUED","READING"].includes(run.status)) {$("#modal-body").querySelector('[data-action="automatic-tracking-cancel"]')?.remove();return;}
  }
}

/** Retain app-scoped history without rerunning an old read on inspection. */
function trackingHistory() {
  let rows="";for(const run of state.workspace.experiment_tracking)rows+=`<p>${esc(label(run.status))} ${button("Inspect tracking result","automatic-tracking-run",`data-id="${esc(run.id)}"`)}</p>`;
  modal("Saved tracking reads",`<div class="modal-content">${rows||"<p>No tracking check is saved for this app.</p>"}</div><div class="modal-actions">${button("Close","close")}</div>`);
}

/** Route only explicit review, inspection and stop operations. */
async function trackingAction(node) {
  const action=node.dataset.action,id=node.dataset.id,app=state.app;
  if(action==="automatic-tracking-review")return trackingReview(id);
  if(action==="automatic-tracking-run")return trackingRun(id);
  if(action==="automatic-tracking-history")return trackingHistory();
  if(action==="automatic-tracking-package")return trackingPackage(node);
  if(action==="automatic-tracking-reload") {await refresh();$("#modal").close();return render();}
  if(action==="automatic-tracking-cancel")await api(`/api/apps/${encodeURIComponent(app)}/experiment-tracking/${encodeURIComponent(id)}/cancel`,{cancel_run:true});
  await refresh();if(state.app===app)trackingRun(id);
}

document.addEventListener("submit",trackingSubmit);
