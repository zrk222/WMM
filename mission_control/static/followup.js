"use strict";

function followupOpen() {
  const w=state.workspace.followup,p=w.policy[0];
  const items=(kind,title)=>`<section class="panel"><h3>${title}</h3>${w[kind].length?w[kind].map(row=>`<div class="next-step"><div><strong>${esc(row.id)}</strong><p>${esc(kind==="subject"?`${row.data.confirmed&&!row.imported?"Supplied consent":"Revoked or imported"} · ${row.data.timezone}`:row.data.action)}</p>${kind==="task"?status(w.eligibility[row.id].status):""}${button(kind==="subject"?"Review / revoke consent":"Review / complete checkpoint","followup-edit",`data-kind="${kind}" data-id="${esc(row.id)}"`)}${kind==="task"&&w.eligibility[row.id].status==="ELIGIBLE"?button("Prepare handoff","followup-prepare",`data-id="${esc(row.id)}"`):""}</div></div>`).join(""):"<p>No saved items.</p>"}</section>`;
  modal("Value follow-up",`<div class="modal-content">${notice("Local preparation only. No message is sent. Use opaque app-scoped subject IDs; never enter contacts or private conversations. Revocation blocks future preparation and downloads; previously exported files cannot be recalled.")}<section class="panel"><p class="eyebrow">AUTOMATIC PREPARATION</p><h3>${p?.data.enabled&&!p.imported?"Enabled":"Disabled or imported"}</h3><p>${esc(p?.data.cadence||state.workspace.automation.cadence||"Declare this app’s useful-value cadence.")}</p><p>Maximum one handoff per subject per local calendar day.</p>${button("Set follow-up policy","followup-policy")}</section><div class="toolbar">${button("Register consent","followup-subject")}${button("Add checkpoint","followup-task")}${button("Refresh eligibility","followup-refresh")}</div>${items("subject","Consent and quiet hours")}${items("task","Checkpoints and suppression")}<section class="panel"><h3>Prepared handoffs · never sent</h3>${w.handoff.length?w.handoff.map(h=>`<div class="next-step"><div><strong>${esc(h.data.action)}</strong><p>${esc(h.data.subject_id)} · ${esc(w.handoff_status[h.id])}</p>${button("Recheck and download","followup-download",`data-id="${esc(h.id)}"`)}</div></div>`).join(""):"<p>Eligible checkpoints prepare automatically while the local service is running, after policy setup is enabled.</p>"}</section><p class="field-error" id="form-error" role="alert"></p></div><div class="modal-actions">${button("Close","close")}</div>`,"CONSENT / USEFUL VALUE");
}

function followupForm(kind,id=null) {
  const row=state.workspace.followup[kind].find(r=>r.id===(id||(kind==="policy"?"policy":null))),d=row?.data||{};
  let fields=[];
  if(kind==="policy")fields=[field("enabled",d.enabled&&!row.imported,"boolean","Prepare local handoffs automatically; this does not send messages"),field("cadence",d.cadence||state.workspace.automation.cadence||"","textarea"),field("prompt",d.prompt||"","textarea","Neutral checkpoint prompt; maximum 500 characters")];
  if(kind==="subject")fields=[field("id",row?.id||"","text","Opaque app-scoped identifier, not a name, email or phone"),field("confirmed",d.confirmed&&!row.imported,"boolean","Confirm supplied consent; choose No to revoke"),field("source",d.source||"","text","Consent evidence reference, not raw contacts"),field("granted_at",d.granted_at||"","text","ISO timestamp with timezone"),field("expires_at",d.expires_at||"","text","ISO timestamp with timezone"),field("timezone",d.timezone||Intl.DateTimeFormat().resolvedOptions().timeZone,"text","IANA timezone, e.g. America/Toronto"),field("quiet_start",d.quiet_start||"21:00","text","HH:MM in recipient local time"),field("quiet_end",d.quiet_end||"09:00","text","HH:MM in recipient local time")];
  if(kind==="task")fields=[field("id",row?.id||"","text","Opaque checkpoint identity; one handoff per checkpoint"),field("subject_id",d.subject_id||"","text","An existing consent subject in this app"),field("action",d.action||"","textarea","Useful checkpoint action; do not enter personal documents"),field("due_at",d.due_at||"","text","ISO timestamp with explicit timezone"),field("expires_at",d.expires_at||"","text","ISO timestamp with explicit timezone"),experimentSelect("state","Checkpoint state",["OPEN","COMPLETED","CANCELLED"].map(v=>[v,label(v)]),d.state||"OPEN")];
  modal(kind==="subject"?"Consent and quiet hours":kind==="task"?"Useful checkpoint":"Follow-up policy",`<form id="followup-form" data-kind="${kind}" data-app="${esc(state.app)}" data-manifest="${state.workspace.app.version}" data-version="${row?.version||""}"><div class="modal-content">${notice("Saved changes invalidate prior handoffs. Imported history needs explicit review. No external delivery is performed.")}<div class="form-grid">${fields.join("")}</div><p id="form-error" class="field-error" role="alert"></p></div><div class="modal-actions"><button type="submit" class="button">Save ${kind==="subject"?"consent":kind==="task"?"checkpoint":"policy"}</button>${button("Cancel","close")}</div></form>`);
  if(row&&kind!=="policy")$("#followup-form [name=id]").readOnly=true;
  if(kind==="task")$("#followup-form [name=state]").value=d.state||"OPEN";
}

async function followupAction(node) {
  const action=node.dataset.action;
  if(action==="followup-policy")return followupForm("policy");
  if(action==="followup-subject")return followupForm("subject");
  if(action==="followup-task")return followupForm("task");
  if(action==="followup-edit")return followupForm(node.dataset.kind,node.dataset.id);
  const app=state.app;
  if(action==="followup-prepare") {
    const eligible=state.workspace.followup.eligibility[node.dataset.id];
    await api(`/api/apps/${encodeURIComponent(app)}/followup/prepare`,{id:node.dataset.id,manifest_version:state.workspace.app.version,source_hash:eligible.source_hash});
  }
  if(action==="followup-download") {
    const result=await api(`/api/apps/${encodeURIComponent(app)}/followup/download`,{id:node.dataset.id});
    if(state.app!==app)throw new Error("App changed. Reopen the handoff in its own workspace.");
    return download(`${app}-followup-handoff.json`,result);
  }
  await refresh();if(state.app===app)followupOpen();
}

document.addEventListener("submit",async event=>{
  const form=event.target;if(form.getAttribute("id")!=="followup-form")return;
  event.preventDefault();const submit=form.querySelector('[type="submit"]');submit.disabled=true;
  try {
    const app=form.dataset.app;
    if(app!==state.app||Number(form.dataset.manifest)!==state.workspace.app.version)throw new Error("App setup changed. Reopen this form; your input is preserved.");
    const data=Object.fromEntries(new FormData(form)),id=data.id;delete data.id;
    for(const key of ["enabled","confirmed"])if(key in data)data[key]=data[key]==="true";
    await api(`/api/apps/${encodeURIComponent(app)}/followup/${form.dataset.kind}`,{id,data,version:form.dataset.version?Number(form.dataset.version):null,manifest_version:Number(form.dataset.manifest)});
    await refresh();if(state.app===app)followupOpen();
  }catch(error){form.querySelector("#form-error").textContent=error.message;}finally{submit.disabled=false;}
});
