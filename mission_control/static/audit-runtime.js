"use strict";

let auditDetected=null;
let auditArchives={app:null,rows:[],shown:0};
function auditArchiveCards(rows) {
  return rows.map(r=>`<article class="panel"><h4>Imported assertion</h4><p>${esc(r.created)} · Historical evidence only; not current execution or readiness.</p>${button("Download imported evidence","audit-download",`data-id="${esc(r.id)}"`)}</article>`).join("");
}
function auditPath(app,action) { return `/api/apps/${app}/inspections/${action}`; }
function auditRow(step={action:"wait_for",selector:"main",value:"visible"}) {
  return `<fieldset class="panel audit-step"><legend>Declared step</legend><label class="field">Action<select name="action">${["wait_for","goto","click","press","select_option"].map(a=>`<option value="${a}" ${a===step.action?"selected":""}>${esc(label(a))}</option>`).join("")}</select></label>${field("selector",step.selector,"text","CSS selector; blank for navigation",false)}${field("value",step.value,"text","Wait: visible/hidden/attached/detached; navigation: URL; key/option: literal; click: blank",false)}${button("Remove step","audit-remove")}</fieldset>`;
}
function auditRender(view,tools) {
  const app=state.workspace.app,saved=view.config,request=saved?.data.request;
  auditArchives={app:app.id,rows:view.archives||[],shown:20};
  const runs=view.runs.map(r=>`<article class="panel"><h3>${esc(r.status)}</h3><p>${esc(r.created)}</p>${r.error?notice(r.error,"error"):""}<div class="toolbar">${["QUEUED","RUNNING"].includes(r.status)?button("Cancel inspection","audit-cancel",`data-id="${r.id}"`):""}${button("Download evidence","audit-download",`data-id="${r.id}"`)}</div></article>`).join("");
  modal("REA / ECC inspections",`<div class="modal-content" id="audit-runtime"><p class="eyebrow">${esc(app.data.name)} · LOCAL EXECUTION</p>${notice("Declare a credential-free inspection. Fixture interactions require an isolated non-personal test service. Public mode allows navigation and waiting only. ECC applies deterministic skill rules; no independent model, PMF or release approval.")}<p role="status">Detected tools: <strong>${esc(tools.status)}</strong> ${esc(tools.repair||"REA 6.4.0, Chromium and two installed ECC skills")}</p><div class="toolbar">${button("Refresh status","audit-open")}${button("Back to PMF","audit-back")}</div><form id="audit-form" data-app="${esc(app.id)}" data-manifest="${app.version}" data-tool="${esc(tools.id||"")}"><label class="field">Inspection scope<select name="mode"><option value="PUBLIC_PASSIVE">This app's public website (passive)</option><option value="OWNED_FIXTURE">Owned isolated loopback fixture</option></select></label>${field("start_url",request?.start_url||app.data.website||"","url","Exact origin; no queries, fragments or credentials")}<label class="field">Viewport<select name="viewport"><option value="mobile">Mobile 390 x 844</option><option value="desktop">Desktop 1440 x 1000</option></select></label><div id="audit-steps">${(request?.steps||[undefined]).map(s=>auditRow(s)).join("")}</div>${button("Add step","audit-add")}<label class="check-row"><input type="checkbox" name="confirm_scope" required> I confirm this credential-free scope and own any isolated fixture used; no personal data or real account actions.</label><p id="audit-error" class="field-error" role="alert"></p><div class="toolbar"><button type="submit" class="button" ${tools.status!=="READY"?"disabled":""}>Save inspection scope</button>${saved?button("Run inspection","audit-run",`data-scope="${saved.hash}" data-manifest="${app.version}"`):""}</div></form><h3>Saved runs</h3><p>Worker: ${esc(view.worker?.status||"UNKNOWN")}. ${esc(view.worker?.repair||"")}</p><p>Runs persist after reload. Incomplete and interrupted work requires an explicit new run; no automatic replay. Refresh status to read progress.</p>${runs||"<p>No native runs yet.</p>"}</div>`);
  $("#audit-runtime").insertAdjacentHTML("beforeend",`<h3>Imported inspection history</h3><p>Backups preserve historical assertions without restoring configuration, credentials, queues or approval. ${auditArchives.rows.length} archived records.</p><div id="audit-archives">${auditArchiveCards(auditArchives.rows.slice(0,20))||"<p>No imported inspection history.</p>"}</div>${auditArchives.rows.length>20?button("Load older history","audit-older"):""}`);
  if(request){$("#audit-form [name=confirm_scope]").checked=true;$("#audit-form [name=mode]").value=request.mode;$("#audit-form [name=viewport]").value=request.viewport;}
}
async function auditOpen() {
  const app=state.app;
  try {
    const view=await api(auditPath(app,"view"),{}),tools=await api(auditPath(app,"detect"),{});
    if(state.app!==app)return;
    auditDetected=tools;auditRender(view,tools);
  }catch(error){toast(error.message);}
}
async function auditAction(node) {
  const action=node.dataset.action,app=state.app;
  if(action==="audit-open")return auditOpen();
  if(action==="audit-back")return pmfOpen();
  if(action==="audit-add") {
    if(document.querySelectorAll(".audit-step").length>=12)return toast("At most 12 steps");
    return $("#audit-steps").insertAdjacentHTML("beforeend",auditRow());
  }
  if(action==="audit-remove")return node.closest(".audit-step").remove();
  const form=$("#audit-form");
  if(form?.dataset.app!==app)throw Error("App changed; reopen inspection setup");
  if(action==="audit-older") {
    if(auditArchives.app!==app)throw Error("App changed; reopen inspection history");
    $("#audit-archives").insertAdjacentHTML("beforeend",auditArchiveCards(auditArchives.rows.slice(auditArchives.shown,auditArchives.shown+20)));
    auditArchives.shown+=20;
    if(auditArchives.shown>=auditArchives.rows.length)node.remove();
    return;
  }
  if(action==="audit-download") {
    const result=await api(auditPath(app,"detail"),{id:node.dataset.id});
    if(state.app===app)download(`${app}-inspection-${node.dataset.id}.json`,{authority:"PASSIVE_EVIDENCE_ONLY",...result});
    return;
  }
  if(action==="audit-cancel")await api(auditPath(app,"cancel"),{id:node.dataset.id});
  if(action==="audit-run") {
    if(!form.elements.confirm_scope.checked)throw Error("Confirm the saved scope before running");
    await api(auditPath(app,"queue"),{request_key:crypto.randomUUID(),manifest_version:Number(node.dataset.manifest),scope_hash:node.dataset.scope});
  }
  if(state.app===app)await auditOpen();
}
document.addEventListener("click",async event=>{
  const node=event.target.closest('[data-action^="audit-"]');if(!node)return;
  node.disabled=true;
  try{await auditAction(node);}catch(error){const box=$("#audit-error");if(box)box.textContent=error.message;else toast(error.message);}finally{node.disabled=false;}
});
document.addEventListener("submit",async event=>{
  if(event.target.id!=="audit-form")return;
  event.preventDefault();const form=event.target,app=state.app,submit=event.submitter;
  submit.disabled=true;
  try {
    if(form.dataset.app!==app)throw Error("App changed; reopen inspection setup");
    const value=new FormData(form),steps=[...form.querySelectorAll(".audit-step")].map(row=>Object.fromEntries(["action","selector","value"].map(k=>[k,row.querySelector(`[name=${k}]`).value])));
    await api(auditPath(app,"save"),{manifest_version:Number(form.dataset.manifest),tool_id:form.dataset.tool,mode:value.get("mode"),start_url:value.get("start_url"),viewport:value.get("viewport"),steps,confirm_scope:form.elements.confirm_scope.checked});
    if(state.app===app)await auditOpen();
  }catch(error){if(form.isConnected)$("#audit-error").textContent=error.message;}finally{submit.disabled=false;}
});

document.addEventListener("input",event=>{const form=event.target.closest("#audit-form");if(form&&event.target.name!=="confirm_scope"){const run=form.querySelector("[data-action=audit-run]");if(run){run.disabled=true;run.title="Save the edited scope before running";}}});
