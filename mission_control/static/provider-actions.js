"use strict";

function providerActionsPanel() {
  const rows=state.workspace.provider_actions || [];
  return `<section class="panel"><div class="section-heading"><div><p class="eyebrow">EXACT PROVIDER CHANGES</p><h2>Approve, send, verify</h2></div>${button("Prepare store text change","provider-action-prepare")}</div><p class="description">A separate checker approves the exact change before the maker sends it. This supports App Store promotional text only, with zero ad spending.</p>${rows.length?rows.map(r=>`<button class="record-row" data-action="provider-action-open" data-id="${esc(r.id)}"><span class="record-main"><strong>${esc(r.packet.record.title)}</strong><small>${esc(r.packet.before.locale)} · iOS ${esc(r.packet.before.release)} · ${r.dispatches} dispatch</small></span>${status(r.status)}</button>`).join(""):notice("No provider changes prepared. Configure App Store Connect, add store evidence and establish verified app access to begin.")}</section>`;
}

function providerPrepareForm() {
  if(reviewIdentity().status!=="AUTHENTICATED")return identityLogin();
  if(!["MAKER","OWNER"].includes(myReviewRole()?.role))return toast("Ask this app's owner to assign your maker role first.");
  const records=state.workspace.records.filter(r=>r.kind==="store"),connections=state.workspace.records.filter(r=>r.kind==="connection"&&r.data.provider==="app_store"&&r.data.auth_mode!=="disconnected");
  if(!records.length||!connections.length)return modal("Set up your store change",`<div class="modal-content">${notice("Add current store evidence in Evidence and configure an authorized App Store Connect key in Connections. Then return here; no developer configuration or opaque resource ID is required.")}</div><div class="modal-actions">${button("Open Evidence","provider-action-evidence")}${button("Open Connections","provider-action-connections")}</div>`);
  modal("Prepare an exact store text change",`<form id="provider-prepare-form" data-app="${esc(state.app)}"><div class="modal-content">${notice("Promotional text may become publicly visible without a new app submission. This reads the provider first; it does not send a change.")}<label class="field">Store evidence<select name="record_id">${records.map(r=>`<option value="${esc(r.id)}">${esc(r.title)}</option>`).join("")}</select></label><label class="field">App Store connection<select name="connection_id">${connections.map(r=>`<option value="${esc(r.id)}">${esc(r.title)} · ${esc(r.data.store_app_id)}</option>`).join("")}</select></label><label class="field">Exact promotional text<textarea name="promotional_text" maxlength="170" required>${esc(records[0].data.promotional_text || "")}</textarea><small>Maximum 170 characters. Edits are saved as versioned store evidence before preparing approval.</small></label><input name="localization_id" type="hidden"><div class="toolbar">${button("Read store destination","provider-action-destination")}</div><p id="provider-destination" class="description" role="status">Read the destination for this app's configured iOS release and language.</p><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit" disabled>Freeze exact provider change</button></div></form>`);
}

function providerActionOpen(id) {
  const row=(state.workspace.provider_actions || []).find(r=>r.id===id);if(!row)return;
  const user=reviewIdentity(),role=myReviewRole()?.role,current=row.availability==="CURRENT",signed=user.status==="AUTHENTICATED";
  const approve=signed&&current&&["CHECKER","OWNER"].includes(role)&&row.preparer!==user.principal&&row.status==="WAITING_APPROVAL";
  const execute=signed&&current&&row.preparer===user.principal&&row.status==="APPROVED";
  const cancel=signed&&row.preparer===user.principal&&["MAKER","OWNER"].includes(role)&&["WAITING_APPROVAL","APPROVED"].includes(row.status);
  const reconcile=signed&&role&&["DISPATCHING","NEEDS_RECONCILIATION"].includes(row.status);
  const confirmation=approve?"confirm_provider_change":execute?"confirm_send":null;
  const mutation=approve?"approve":"execute";
  const form=confirmation?`<form id="provider-confirm-form" data-app="${esc(state.app)}" data-id="${esc(id)}" data-operation="${mutation}"><label class="check-label"><input name="${confirmation}" type="checkbox" required> ${approve?"I authorize this exact provider text change, with zero ad spending.":"Send this exact approved text change to Apple now."}</label><div id="form-error" class="field-error" role="alert"></div><div class="modal-actions"><button type="submit" class="button">${approve?"Authorize exact provider change":"Send approved change now"}</button></div></form>`:"";
  modal("Inspect exact provider change",`<div class="modal-content">${status(row.status)}${status(row.availability)}${notice(row.unavailable_reason || "Review the exact before/after text, destination and source below.",current?"info":"warning")}<p><strong>Destination:</strong> App ${esc(row.packet.before.store_app_id)}, iOS ${esc(row.packet.before.release)}, ${esc(row.packet.before.locale)}</p><h3>Before</h3><p>${esc(row.packet.before.promotional_text??"No promotional text")}</p><h3>After</h3><p>${esc(row.packet.after.promotional_text)}</p>${notice("Apple may show promotional text publicly without a new submission. Preflight detects prior edits but cannot prevent a simultaneous edit by another Apple administrator. API readback does not verify the public listing.")}<p>Maker ${esc(row.preparer)} · checker ${esc(row.checker || "Not yet authorized")}<br>Expires ${esc(new Date(row.expires).toLocaleString())}</p><p class="app-mono">SHA256 ${esc(row.hash)}</p><details><summary>Exact packet and provider receipts</summary><pre>${json(row)}</pre></details>${["DISPATCHING","NEEDS_RECONCILIATION"].includes(row.status)?notice("No automatic resend. Read provider state to inspect this outcome. An active send retains ownership for up to 90 seconds.","warning"):""}${!form?'<div id="form-error" class="field-error" role="alert"></div>':""}${form}</div><div class="modal-actions">${button("Check public listing","public-store-open",`data-id="${esc(id)}"`)}${button("Download provider action receipt","provider-action-download",`data-id="${esc(id)}"`)}${cancel?button("Cancel unsent change","provider-action-cancel",`data-id="${esc(id)}"`):""}${reconcile?button("Read provider state","provider-action-reconcile",`data-id="${esc(id)}"`):""}</div>`);
}

async function providerDestination(node) {
  const form=node.closest("form"),app=form.dataset.app,data=Object.fromEntries(new FormData(form)),signature=data.record_id+"|"+data.connection_id;node.disabled=true;
  try {
    const result=await api(`/api/apps/${app}/provider-actions/destination`,{record_id:data.record_id,connection_id:data.connection_id});
    if(!form.isConnected||signature!==form.elements.record_id.value+"|"+form.elements.connection_id.value)return;
    form.elements.localization_id.value=result.localization_id;form.querySelector('[type="submit"]').disabled=false;
    form.querySelector("#provider-destination").textContent=`Verified destination: iOS ${result.release}, ${result.locale}. Exact baseline is reread when preparing approval.`;
    form.querySelector("#form-error").textContent="";
  } catch(error) {providerFormError(form,error);} finally {node.disabled=false;}
}

function providerFormError(form,error) {
  const field=form.querySelector("#form-error");if(form.isConnected&&field)field.textContent=error.message;else toast(error.message);
}

async function providerActionSubmit(event) {
  const form=event.target;if(!["provider-prepare-form","provider-confirm-form"].includes(form.id))return;
  event.preventDefault();const submit=form.querySelector('[type="submit"]');submit.disabled=true;
  const data=Object.fromEntries(new FormData(form)),app=form.dataset.app;
  try {
    let row;
    if(form.id==="provider-prepare-form") {
      const record=state.workspace.records.find(r=>r.id===data.record_id);if(!record||state.app!==app)throw new Error("Workspace changed; reopen this app's store change.");
      if(record.data.promotional_text!==data.promotional_text.trim()) {
        const saved=await api(`/api/apps/${app}/records`,{id:record.id,version:record.version,kind:record.kind,title:record.title,source:record.source,data:{...record.data,promotional_text:data.promotional_text.trim()}});Object.assign(record,saved);
      }
      row=await api(`/api/apps/${app}/provider-actions`,{record_id:data.record_id,connection_id:data.connection_id,localization_id:data.localization_id});
    } else {
      const original=state.workspace.provider_actions.find(r=>r.id===form.dataset.id);if(!original||state.app!==app)throw new Error("Workspace changed; reopen the exact provider action.");
      row=await api(`/api/apps/${app}/provider-actions/${original.id}/${form.dataset.operation}`,{hash:original.hash,[form.dataset.operation==="approve"?"confirm_provider_change":"confirm_send"]:true});
    }
    const active=form.isConnected&&$("#modal").open;if(active)$("#modal").close();await refresh();if(active&&state.app===app)providerActionOpen(row.id);
  } catch(error) {providerFormError(form,error);} finally {submit.disabled=false;}
}

async function providerActionClick(event) {
  const node=event.target.closest("[data-action]");if(!node)return;const action=node.dataset.action,id=node.dataset.id;
  if(action==="provider-action-prepare")return providerPrepareForm();
  if(action==="provider-action-open")return providerActionOpen(id);
  if(action==="provider-action-destination")return providerDestination(node);
  if(action==="provider-action-download")return download(`${state.app}-provider-action.json`,state.workspace.provider_actions.find(r=>r.id===id));
  if(["provider-action-evidence","provider-action-connections"].includes(action)) {$("#modal").close();state.view=action.endsWith("evidence")?"evidence":"connections";return render();}
  if(!["provider-action-cancel","provider-action-reconcile"].includes(action))return;
  const app=state.app;node.disabled=true;
  try {await api(`/api/apps/${app}/provider-actions/${id}/${action.endsWith("cancel")?"cancel":"reconcile"}`,{});const active=node.isConnected&&$("#modal").open;await refresh();if(active&&state.app===app)providerActionOpen(id);} catch(error) {const field=$("#form-error");if(field&&node.isConnected)field.textContent=error.message;else toast(error.message);} finally {node.disabled=false;}
}

document.addEventListener("submit",providerActionSubmit);
document.addEventListener("click",providerActionClick);
document.addEventListener("change",event=>{
  const form=event.target.closest("#provider-prepare-form");if(!form||!["record_id","connection_id"].includes(event.target.name))return;
  form.elements.localization_id.value="";form.querySelector('[type="submit"]').disabled=true;form.querySelector("#provider-destination").textContent="Read the selected destination before preparing this change.";
  if(event.target.name==="record_id")form.elements.promotional_text.value=state.workspace.records.find(r=>r.id===event.target.value)?.data.promotional_text || "";
});
