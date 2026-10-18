"use strict";

function packetNeed(message) {
  const match=String(message).match(/^Add current ([a-z_]+) evidence/);
  const steps={readiness:"Run and record the core journey tests.",measurement:"Connect measurement and record its verified setup.",cohort:"Add source-backed economics for a mature cohort.",claim:"Add a claim supported by current app evidence.",asset:"Add a rights-cleared screenshot of this release.",store:"Verify the store or web destination.",experiment:"Set the hypothesis, primary metric and stopping rules.",distribution:"Choose a channel, destination and approved limits.",route:"Test the first-value entry routes.",billing:"Test plans, purchase and restore.",retention:"Add observed retained-value cohort data.",evaluation:"Record an evidence-based experiment decision.",learning:"Review a learning proposal and its holdout."};
  if(match)return steps[match[1]]||`Add ${String(state.boot.labels[match[1]]||label(match[1])).toLowerCase()} for this release.`;
  return String(message).replace(/^Finish stage (\d+): /,"First complete step $1: ");
}

function stagePacketCard(output,jobId=null) {
  const packet=output.packet,missing=output.missing||[];
  const step=state.workspace.workflow.steps.find(s=>s.id===Number(output.stage));
  const needs=missing.length>0||output.status==="BLOCKED";
  const tasks=packet.operations?.tasks||[];
  const action=needs?resolutionButton(Number(output.stage)):step?guidedButton(step.primary):"";
  const tools=step?step.tools.map(t=>guidedButton(t)).join(""):"";
  const downloadButton=jobId?button("Download packet","download-packet",`data-job="${esc(jobId)}" data-stage="${esc(output.stage)}"`):button("Download packet","automatic-packet",`data-stage="${esc(output.stage)}"`);
  return `<article class="panel packet-stage" data-packet-stage="${esc(output.stage)}"><div class="section-heading"><h3>Step ${esc(output.stage)} · ${esc(packet.title)}</h3><span class="status ${needs?"needs_input":"ready"}">${needs?"Needs input":"Draft prepared"}</span></div><p>${esc(packet.operations?.deliverable||"Review this stage's prepared work.")}</p>${missing.length?`<ul>${missing.map(m=>`<li>${esc(packetNeed(m))}</li>`).join("")}</ul>`:"<p class=\"description\">Local inputs met their checks when this draft was prepared. Verify the actual result separately.</p>"}<div class="toolbar">${action}</div><details><summary>Tasks and verification</summary><ol>${tasks.map(t=>`<li>${esc(t)}</li>`).join("")}</ol><p>${esc(packet.operations?.verify||"")}</p><div class="toolbar">${tools}</div></details><details class="packet-technical"><summary>Technical packet (JSON)</summary><pre>${json(packet)}</pre>${downloadButton}</details></article>`;
}

function automaticPreparationPanel() {
  const p=state.workspace.preparation;
  if(!p)return "";
  return `<section class="panel" id="automatic-preparation"><div class="section-heading"><div><p class="eyebrow">PREPARED AUTOMATICALLY</p><h2>Your work is ready to inspect</h2></div>${button("Inspect current work","automatic-open")}</div><p>All 12 stages are prepared from this app’s current evidence. ${p.ready_count} meet local checks; ${p.needs.length} distinct evidence needs remain.</p><p class="description">No preparation run is required. Missing proof stays blocked. Publication and spending keep their approval controls.</p>${campaignCollectionPanel()}</section>${sequencePanel()}${trackingPanel()}`;
}

function campaignCollectionPanel() {
  const c=state.workspace.preparation?.collection;
  if(!c)return "";
  const names={identity_inventory:"App and account inventory",reviews:"Public customer reviews",subscription_catalog:"Subscription catalog",release_inventory:"Selected release and screenshots"};
  const rows=c.tasks.map(t=>`<li>${esc(names[t.operation]||label(t.operation))} · ${esc(label(t.provider))} · ${esc(t.job?label(t.job.status):"Ready to collect")}${t.job?` ${button("Inspect source result","job",`data-id="${esc(t.job.id)}"`)}`:""}</li>`).join("");
  const work=c.tasks.length?`<ul>${rows}</ul>${button("Collect campaign inputs","automatic-collect-inputs")}`:"<p>No usable app-owned provider source is connected for these reads. The agent still needs a permitted source; no campaign facts have been invented.</p>";
  return `<section class="campaign-collection" aria-label="Agent input collection"><h3>Let the agent collect the facts</h3><p>Reads are selected from this app’s saved connections and release. You do not need to enter report parameters. Collection does not publish or spend.</p>${work}<div class="toolbar">${button("Review source access","measurement-connections")}${button("Review agent operating rules","automatic-manifest")}</div><details><summary>What the agent still needs to do</summary><ul>${c.agent_remaining.map(s=>`<li>${esc(s)}</li>`).join("")}</ul>${c.excluded.length?`<ul>${c.excluded.map(s=>`<li>${esc(s.reason)}</li>`).join("")}</ul>`:""}<p>Reads are reused within the current source/hour. Failed or cancelled reads remain visible; starting again does not silently retry them.</p></details></section>`;
}

function campaignManifestDialog() {
  const p=state.workspace.preparation.collection.operating_manifest;
  modal("Agent operating rules",`<div class="modal-content"><h3>${esc(state.workspace.app.data.name)}</h3><p>${esc(p.objective||"No app objective is recorded yet.")}</p><p>You approve or edit. This installed execution profile supports app-owned provider reads only; publication, spending and live A/B execution are not enabled.</p><h3>Evidence standards</h3><ul>${p.source_rules.map(s=>`<li>${esc(s)}</li>`).join("")}</ul><h3>Resolution workflow</h3><ul>${p.resolution_contract.map(s=>`<li>${esc(s)}</li>`).join("")}</ul><h3>A/B operating contract</h3><ul>${p.ab_contract.map(s=>`<li>${esc(s)}</li>`).join("")}</ul><details><summary>Exact versioned manifest</summary><pre>${json(p)}</pre></details></div><div class="modal-actions">${button("Edit app objective","edit-app")}${button("Close","close")}</div>`,"ENFORCED SOURCE-COLLECTION PROFILE");
}

function openAutomaticPreparation() {
  const p=state.workspace.preparation;
  modal("Your prepared workflow",`<div class="modal-content">${notice("These are working drafts, not completed campaigns. Use each step's button to open its current workflow. Nothing is published and no money is spent here.")}<h3>${p.ready_count} of 12 steps have the required local inputs</h3>${p.outputs.map(o=>stagePacketCard(o)).join("")}<details><summary>Technical source reference</summary><p class="app-mono">${esc(p.source_hash)}</p></details></div><div class="modal-actions">${button("Download all packets","automatic-download")}${button("Close","close")}</div>`,"CURRENT WORKFLOW");
  if(p.recommendations)$("#modal .modal-content").insertAdjacentHTML("afterbegin",automationPanel("packet-automation"));
}

async function automaticPreparationAction(node) {
  if(node.dataset.action.startsWith("automatic-tracking-"))return trackingAction(node);
  if(node.dataset.action.startsWith("automatic-sequence-"))return sequenceAction(node);
  if(node.dataset.action==="automatic-resolution-stage") {
    const app=state.app;await refresh();
    if(state.app===app)return openResolutionStage(Number(node.dataset.stage));
    return;
  }
  if(node.dataset.action==="automatic-resolution-issue")return openResolutionIssue(node.dataset.id);
  if(node.dataset.action==="automatic-resolution-run")return openResolutionRun(node.dataset.id);
  if(node.dataset.action==="automatic-resolution-refresh") {
    const app=state.app,id=node.dataset.id;await refresh();
    if(state.app===app)return openResolutionRun(id);
    return;
  }
  if(node.dataset.action==="automatic-resolution-options-refresh") {
    const app=state.app,id=node.dataset.id;await refresh();
    if(state.app===app)return openResolutionIssue(id);
    return;
  }
  if(node.dataset.action==="automatic-manifest")return campaignManifestDialog();
  if(node.dataset.action==="automatic-collect-inputs") {
    const app=state.app,c=state.workspace.preparation.collection;
    node.disabled=true;
    try {
      const result=await api(`/api/apps/${encodeURIComponent(app)}/campaign-inputs`,{manifest_version:c.manifest_version,source_hash:c.source_hash});
      if(state.app!==app)return;
      await refresh();
      if(state.app!==app)return;
      toast(`${result.tasks.length} source reads queued or retained. Inspect their job results; collection is not campaign completion.`);
    } finally {if(node.isConnected)node.disabled=false;}
    return;
  }
  if(node.dataset.action==="automatic-open")return openAutomaticPreparation();
  if(node.dataset.action==="automatic-download")return download(`${state.app}-current-work.json`,state.workspace.preparation);
  if(node.dataset.action==="automatic-packet") {
    const output=state.workspace.preparation.outputs.find(o=>o.stage===Number(node.dataset.stage));
    if(output)return download(`${state.app}-stage-${output.stage}.json`,output.packet);
  }
  if(node.dataset.action==="automatic-stage")return openStage(node.dataset.id);
}

function resolutionIssues(stage) {
  const all=state.workspace.resolutions?.issues||[];
  const direct=all.filter(i=>i.stages.includes(stage));
  if(direct.length)return direct;
  const step=state.workspace.workflow.steps.find(s=>s.id===stage);
  const dependencies=(step?.dependency_needs||[]).map(s=>Number(s.match(/^Finish stage (\d+)/)?.[1]));
  return all.filter(i=>i.stages.some(id=>dependencies.includes(id)));
}

function resolutionButton(stage,title="Review agent resolution") {
  return resolutionIssues(stage).length?button(title,"automatic-resolution-stage",`data-stage="${stage}"`):"";
}

function openResolutionStage(stage) {
  const issues=resolutionIssues(stage),history=state.workspace.resolutions?.history||[];
  modal("Agent resolution options",`<div class="modal-content"><p>The agent proposes the work. Review the action, approve it or edit the target; inspect its evidence before treating the requirement as verified.</p>${issues.map(issue=>`<article class="panel"><h3>${esc(issue.goal)}</h3><p><strong>Acceptance target (not yet verified):</strong> ${esc(issue.verification)}</p>${button("Review agent options","automatic-resolution-issue",`data-id="${esc(issue.id)}"`)}<details><summary>Evidence gap and affected steps</summary><p>${esc(issue.gap)}</p><p>Steps ${esc(issue.stages.join(", "))}</p></details>${history.filter(h=>h.issue_id===issue.id).slice(0,3).map(h=>`<p>${esc(label(h.status))} ${button("Inspect agent result","automatic-resolution-run",`data-id="${esc(h.job_id)}"`)}</p>`).join("")}</article>`).join("")||"<p>No direct unverified input is recorded for this stage. Review its existing evidence and prerequisites.</p>"}</div><div class="modal-actions">${button("Review source access","measurement-connections")}${button("Close","close")}</div>`,"AGENT WORK / OWNER APPROVAL");
}

function optionDescription(option) {
  const name=option.parameters.provider||option.parameters.name;
  return name?`${option.title} · ${name}`:option.title;
}

function resolutionOptionBody(issue,option) {
  const target=option.tool==="inspect_site"?field("resolution_target",option.parameters.url||"","url","Optional edit; must stay on this app's public website origin.",false):option.tool==="reuse_observation"?`<details><summary>Exact saved observation</summary><p>${esc(option.parameters.url)}</p><p>Artifact: ${esc(option.parameters.artifact_id)}</p><p>SHA256: ${esc(option.parameters.artifact_hash)}</p><p>Source run: ${esc(option.parameters.source_job_id)}</p></details>`:"";
  return `<h3>${esc(option.title)}</h3><p>${esc(option.access)}</p><dl><dt>Expected evidence</dt><dd>${esc(option.artifact)}</dd><dt>What this verifies</dt><dd>${esc(option.verifies)}</dd><dt>What remains unverified</dt><dd>${esc(option.limits)}</dd><dt>Cost and limits</dt><dd>${esc(option.cost)}</dd></dl>${target}<details><summary>Recovery and stopping rules</summary><p>${esc(option.fallback)}</p><p>${esc(option.stop)}</p></details>${!option.ready?notice("This action needs source access or an app target first. Review that prerequisite below; no execution has been claimed."):""}<div class="toolbar">${option.ready?'<button type="submit" class="button">Approve agent action</button>':button("Review required access",option.prerequisite==="app"?"edit-app":"measurement-connections")}${button("Review source access","measurement-connections")}${button("Edit app target","edit-app")}</div>`;
}

function openResolutionIssue(id) {
  const issue=state.workspace.resolutions?.issues.find(i=>i.id===id);
  if(!issue)return modal("Resolution needs refreshed",`<div class="modal-content"><p>This input changed or now meets its local check. Review the current workflow; old approval is not reused.</p></div><div class="modal-actions">${button("Close","close")}</div>`);
  modal("Review the agent action",`<form id="resolution-form" data-app="${esc(state.app)}" data-manifest="${state.workspace.app.version}" data-issue="${esc(issue.id)}" data-source="${esc(issue.source_hash)}" data-request="${crypto.randomUUID()}"><div class="modal-content"><h3>${esc(issue.goal)}</h3><p><strong>Acceptance target (not yet verified):</strong> ${esc(issue.verification)}</p><label class="field" for="resolution-option">Proposed action<select id="resolution-option" name="option">${issue.options.map(o=>`<option value="${esc(o.id)}">${esc(optionDescription(o))}${o.ready?"":" — access needed"}</option>`).join("")}</select></label><div id="resolution-option-body">${resolutionOptionBody(issue,issue.options[0])}</div><p id="resolution-error" class="field-error" role="alert"></p>${button("Refresh options","automatic-resolution-options-refresh",`data-id="${esc(issue.id)}"`)}<details><summary>Source and approval boundary</summary><p>${esc(issue.gap)}</p><p>Approval applies to the displayed app, action and target for 30 minutes. Edits require a new exact approval. No campaign publication, ad spending or automatic proof promotion is authorized.</p></details></div></form>`,"APPROVE / EDIT");
}

function resolutionRunDetails(row) {
  const actions=row.next_actions.map(a=>typeof a==="string"?a:a?.instruction||"Inspect this source finding in Evidence references before choosing the next action.");
  return `<p id="resolution-live-status" role="status" aria-live="polite">${esc(label(row.status))} · ${esc(row.summary)}</p><p>Proof status: ${esc(label(row.proof_status))}. This result has not automatically verified the original requirement.</p>${row.children.length?`<h3>Source work</h3><ul>${row.children.map(c=>`<li>${esc(label(c.status))} · ${esc(c.job_id)}</li>`).join("")}</ul>`:""}<h3>Next agent resolution steps</h3><ul>${actions.map(a=>`<li>${esc(a)}</li>`).join("")}</ul><details><summary>Evidence references</summary><ul>${row.artifacts.map(a=>`<li>${esc(a.kind||"source job")} · ${esc(a.id||a.job_id||a.experiment_id||a.source_id)}${a.sha256?` · ${esc(a.sha256)}`:""}</li>`).join("")||"<li>No accepted artifact is available yet.</li>"}</ul></details>`;
}

function openResolutionRun(id) {
  const row=state.workspace.resolutions?.history.find(r=>r.job_id===id);
  if(!row)return toast("This saved resolution is not in the current history. Refresh the selected app.");
  modal("Agent evidence result",`<div class="modal-content"><div id="resolution-run-details">${resolutionRunDetails(row)}</div></div><div class="modal-actions">${button("Refresh progress","automatic-resolution-refresh",`data-id="${esc(id)}"`)}${button("Plan next agent step","agent-next-step")}${button("Review next resolution","automatic-resolution-issue",`data-id="${esc(row.issue_id)}"`)}${button("Review source access","measurement-connections")}${["QUEUED","RUNNING"].includes(row.job_status)?button("Cancel local run","cancel-job",`data-id="${esc(id)}"`):""}${button("Close","close")}</div>`,"EXECUTION / EVIDENCE / REMAINING PROOF");
  $("#modal-body").dataset.job=id;
  const key=`${state.app}:${id}`;
  if(["QUEUED","RUNNING","COLLECTING_SOURCES","WAITING_FOR_SOURCES"].includes(row.status)&&state.resolutionPoll!==key) {
    state.resolutionPoll=key;
    pollResolution(id,state.app).catch(error=>toast(error.message)).finally(()=>{if(state.resolutionPoll===key)state.resolutionPoll=null;});
  }
}

async function pollResolution(id,app) {
  for(let attempt=0;attempt<120;attempt++) {
    await new Promise(resolve=>setTimeout(resolve,1000));
    if(state.app!==app||!$("#modal").open||$("#modal-body").dataset.job!==id)return;
    await refresh();if(state.app!==app||!$("#modal").open||$("#modal-body").dataset.job!==id)return;
    const row=state.workspace.resolutions?.history.find(r=>r.job_id===id);
    if(!row)return;
    const target=$("#resolution-run-details");
    const value=JSON.stringify(row);
    if(target&&target.dataset.observation!==value){target.innerHTML=resolutionRunDetails(row);target.dataset.observation=value;}
    if(!["QUEUED","RUNNING"].includes(row.job_status))$("#modal-body").querySelector('[data-action="cancel-job"]')?.remove();
    if(!["QUEUED","RUNNING","COLLECTING_SOURCES","WAITING_FOR_SOURCES"].includes(row.status))return;
  }
  toast("Evidence work continues in the durable worker. Refresh progress to inspect its next result.");
}

document.addEventListener("change",event=>{
  if(event.target.id!=="resolution-option")return;
  const form=event.target.closest("form"),issue=state.workspace.resolutions?.issues.find(i=>i.id===form.dataset.issue);
  if(!issue||form.dataset.app!==state.app)return;
  if(form.dataset.source!==issue.source_hash){$("#resolution-error").textContent="Sources changed. Refresh the options before approving.";return;}
  const option=issue.options.find(o=>o.id===event.target.value);
  $("#resolution-option-body").innerHTML=resolutionOptionBody(issue,option);
  form.dataset.request=crypto.randomUUID();
});

document.addEventListener("submit",async event=>{
  if(event.target.id!=="resolution-form")return;
  event.preventDefault();const form=event.target,app=form.dataset.app,submit=event.submitter;
  if(submit)submit.disabled=true;
  try {
    const issue=state.workspace.resolutions?.issues.find(i=>i.id===form.dataset.issue);
    if(state.app!==app||form.dataset.manifest!==String(state.workspace.app.version)||issue?.source_hash!==form.dataset.source)throw Error("App or sources changed. Refresh the resolution options before approving.");
    const option=issue.options.find(o=>o.id===form.elements.option.value);
    const target=option.tool==="inspect_site"?form.elements.resolution_target.value:null;
    const job=await api(`/api/apps/${encodeURIComponent(app)}/resolutions/approve`,{issue_id:issue.id,option_id:option.id,source_hash:issue.source_hash,target_url:target,request_key:form.dataset.request});
    if(state.app!==app)return;
    await refresh();if(state.app!==app)return;
    openResolutionRun(job.id);
  } catch(error) {if(form.isConnected)$("#resolution-error").textContent=error.message;}
  finally {if(submit?.isConnected)submit.disabled=false;}
});
