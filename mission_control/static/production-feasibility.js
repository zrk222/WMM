"use strict";

const productionOptions=Object.freeze({executions:["SCREEN_RECORDING","SLIDES","HOST","SILENT_UGC","ANIMATION"],talent:["NONE","FOUNDER","TEAM","CONSENTED_CREATOR"],audio:["SILENT","VOICEOVER","MUSIC"],channels:["SHORT_VIDEO","LINKEDIN","X"],narrative:["DEMO","PROBLEM_SOLUTION","EDUCATIONAL","STORY","BEFORE_AFTER","LIST","OTHER"]});

function capabilityState() {
  return state.workspace.capabilities||{profile:[],requirement:[],evaluations:[]};
}

function capabilityEvaluation(id) {
  return capabilityState().evaluations.find(r=>r.reference_id===id)||{status:"BLOCKED",reasons:["Review current production capability and source requirements"]};
}

function capabilityRow(row) {
  return `<div class="next-step"><div><strong>${esc(row.title)}</strong><p>${status(row.status)} ${esc(row.reasons.join("; "))}</p>${button("Review source requirements","capability-requirement",`data-id="${esc(row.reference_id)}"`)}</div></div>`;
}

function capabilitiesPanel() {
  const c=capabilityState();
  return `<section class="panel" id="production-capability"><div class="section-heading"><div><p class="eyebrow">MAKE WHAT YOUR TEAM CAN DELIVER</p><h2>Production capability</h2></div>${button(c.profile.length?"Revise team capability":"Set up team capability","capability-profile")}</div><p>Declare formats, talent, audio, time and cost limits. Sources outside these limits cannot enter a new brief or ranking.</p>${c.profile.length?`<p>Saved version ${c.profile[0].current.version} · current app binding is checked on every evaluation.</p>${button("Inspect saved capability","capability-open",'data-kind="profile"')}`:notice("Setup required. No capabilities are inferred from your app description.","warning")}${c.evaluations.map(capabilityRow).join("")}</section>`;
}

function capabilitySetup() {
  modal("Review production readiness",`<div class="modal-content">${capabilitiesPanel()}${notice("Update the team profile and each source review. Unknown execution, stale reviews and missing rights remain blocked.")}</div><div class="modal-actions">${button("Close","close")}</div>`);
}

function capabilityChoice(key,values,multiple=false) {
  const options=productionOptions[key].map(id=>({id,title:label(id)}));
  return choiceField(key,options,values||"",multiple);
}

function capabilityResources(d) {
  const currency=state.workspace.app.data.currency||"declared currency";
  return field("editing_level",d.editing_level??"","number","0 = basic capture, 1 = cuts/titles, 2 = compositing, 3 = advanced animation")+
    field("cost_minor",d.cost_minor??"","number",`Per-piece production limit or requirement in ${currency} minor units; no spending is authorized`)+
    field("time_minutes",d.time_minutes??"","number","Per-piece whole minutes, 1–10080")+
    field("source",d.source||"","textarea","Who reviewed these constraints, and which actual resources or source inspection support them?")+
    field("checked_at",d.checked_at||new Date().toISOString(),"text","Review time with timezone. Refresh within 30 days.");
}

function capabilityForm(kind,referenceId=null) {
  if(!["profile","requirement"].includes(kind))throw new Error("Unknown production declaration.");
  const c=capabilityState(),source=state.workspace.references.find(r=>r.id===referenceId);
  if(kind==="requirement"&&!source)return referenceForm();
  const old=kind==="profile"?c.profile[0]:c.requirement.find(r=>r.current.data.reference_id===referenceId),d=old?.current.data||{};
  const fields=kind==="profile"?capabilityProfileFields(d):capabilityRequirementFields(d);
  modal(kind==="profile"?"Team production capability":"Source production requirements",`<form id="capability-form" data-app="${esc(state.app)}" data-kind="${kind}" data-id="${esc(old?.id||"")}" data-version="${old?.current.version||""}" data-reference="${esc(referenceId||"")}" data-capture="${esc(source?.current.hash||"")}" data-app-hash="${esc(c.app_hash||"")}"><div class="modal-content">${notice("Declare actual resources and inspected requirements. Saving records your review; it does not verify legal rights or authorize publication.")}<div class="form-grid">${fields}${capabilityResources(d)}</div><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit">Save production review</button></div></form>`);
}

function capabilityProfileFields(d) {
  return ["executions","talent","audio","channels"].map(key=>capabilityChoice(key,d[key],true)).join("")+field("capture_available",d.capture_available??"","boolean","Can the team capture authentic current app screens?");
}

function capabilityRequirementFields(d) {
  const executions=["UNKNOWN",...productionOptions.executions].map(id=>({id,title:label(id)}));
  return choiceField("execution",executions,d.execution||"")+capabilityChoice("talent",d.talent)+capabilityChoice("audio",d.audio)+capabilityChoice("narrative",d.narrative)+field("requires_capture",d.requires_capture??"","boolean")+field("rights_available",d.rights_available??"","boolean","Does permitted adaptation have the necessary rights? Unknown or uncleared means No.");
}

function capabilityHistory(kind,id=null) {
  if(!["profile","requirement"].includes(kind))throw new Error("Unknown production history.");
  const rows=capabilityState()[kind],row=id?rows.find(r=>r.id===id):rows[0];
  if(!row)throw new Error("No saved production history for this app.");
  return row;
}

function capabilityOpen(kind,id) {
  const row=capabilityHistory(kind,id);
  modal("Saved production review",`<div class="modal-content">${row.versions.map(r=>`<details open><summary>Version ${r.version} · ${esc(r.created)}</summary><pre>${json(r.data)}</pre><p class="app-mono">${esc(r.hash)}</p></details>`).join("")}</div><div class="modal-actions">${button("Download review history","capability-download",`data-kind="${kind}" data-id="${esc(row.id)}"`)}</div>`);
}

function capabilityAction(node) {
  const a=node.dataset.action;
  const handlers={"capability-profile":()=>capabilityForm("profile"),"capability-requirement":()=>capabilityForm("requirement",node.dataset.id),"capability-setup":capabilitySetup,"capability-open":()=>capabilityOpen(node.dataset.kind,node.dataset.id),"capability-download":()=>download(`${state.app}-production-review.json`,capabilityHistory(node.dataset.kind,node.dataset.id))};
  if(!Object.hasOwn(handlers,a))throw new Error("Unknown production capability action.");
  return handlers[a]();
}

function capabilityBody(form) {
  const fd=new FormData(form),data=Object.fromEntries(fd),kind=form.dataset.kind;
  for(const key of ["editing_level","cost_minor","time_minutes"])data[key]=Number(data[key]);
  if(kind==="profile") {
    for(const key of ["executions","talent","audio","channels"])data[key]=fd.getAll(key);
    data.capture_available=data.capture_available==="true";data.app_hash=form.dataset.appHash;
  } else {
    for(const key of ["requires_capture","rights_available"])data[key]=data[key]==="true";
    Object.assign(data,{reference_id:form.dataset.reference,capture_hash:form.dataset.capture});
  }
  const body={data};if(form.dataset.id)Object.assign(body,{id:form.dataset.id,version:Number(form.dataset.version)});
  return body;
}

async function capabilitySubmit(event) {
  const form=event.target;if(form.id!=="capability-form")return;
  event.preventDefault();const submit=form.querySelector('[type="submit"]');submit.disabled=true;
  try {
    if(form.dataset.app!==state.app)throw new Error("App changed; reopen production setup.");
    await api(`/api/apps/${encodeURIComponent(form.dataset.app)}/production/${form.dataset.kind}`,capabilityBody(form));
    await refresh();capabilitySetup();toast("Production review saved with immutable history.");
  } catch(error){$("#form-error").textContent=error.message;}finally{submit.disabled=false;}
}
document.addEventListener("submit",capabilitySubmit);
