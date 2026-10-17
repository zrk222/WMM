"use strict";
const aeoPending = new Set();

function aeoPanel() {
  const a = state.workspace.aeo || {checks:[],website:""};
  const rows = a.checks.map(row => `<button class="record-row" data-action="aeo-inspect" data-id="${esc(row.id)}"><span class="record-main"><strong>${esc(row.data.binding.target)}</strong><small>${esc(row.data.report.state)} · ${esc(new Date(row.created).toLocaleString())}</small></span>${status(row.evidence_status)}</button>`).join("");
  return `<section class="panel aeo-panel"><p class="eyebrow">PUBLIC PAGE EVIDENCE</p><h2>Can search crawlers read your answer page?</h2><p>Check robots rules, source metadata and one sitemap. Each run belongs to this app. Indexing is unverified; citations and growth are unmeasured.</p><div class="toolbar">${button(a.website?"Check a public page":"Set up public website",a.website?"aeo-run":"edit-app")}${button("Download check history","aeo-download")}</div>${rows||"<p>No checks yet. Save your public HTTPS website in App setup, then check a page.</p>"}</section>`;
}

function aeoForm(previous=null) {
  const a=state.workspace.aeo;
  if(!a?.website) return appForm(false);
  const intents=(state.workspace.acquisition?.intents||[]).filter(i=>i.evidence_status==="CURRENT");
  const selected=previous?.intent?.id||"";
  const options='<option value="">Website diagnostic only · no acquisition intent</option>'+intents.map(i=>`<option value="${esc(i.id)}" ${selected===i.id?"selected":""}>${esc(i.current.data.definition.problem)}</option>`).join("");
  const pending=aeoPending.has(state.app);
  modal("Check this app's public page",`<form id="aeo-form" data-app="${esc(state.app)}" data-version="${a.app_version}" data-hash="${esc(a.app_hash)}"><div class="modal-content"><p>Read-only public HTTPS check, limited to 30 seconds. No provider key is needed. Closing this dialog leaves the bounded read running; reopen and reload to inspect its outcome.</p>${field("page_url",previous?.target||a.website,"text","Use an exact page on this app's declared website.")}<label class="field" for="aeo-intent">Acquisition intent<select id="aeo-intent" name="intent_id">${options}</select><small>A current intent uses its exact page. Website-only diagnostics make no acquisition claim.</small></label><div id="form-error" role="alert" class="field-error"></div><p id="aeo-progress" role="status" aria-live="polite">${pending?"A check is already running for this app. Reload after it finishes.":""}</p></div><div class="modal-actions"><button type="submit" class="button" ${pending?"disabled":""}>Run public page check</button>${button("Reload history","aeo-reload")}</div></form>`,"READ-ONLY AEO CHECK");
  $("#aeo-intent").addEventListener("change",event=>{
    const intent=intents.find(i=>i.id===event.target.value);
    if(intent) $("#field-page_url").value=intent.current.data.definition.page_url;
  });
}

function aeoInspect(id) {
  const row=state.workspace.aeo.checks.find(item=>item.id===id);
  if(!row) return toast("This check is not in the selected app.");
  const data=row.data;
  modal("Public page source evidence",`<div class="modal-content aeo-detail">${status(row.evidence_status)}<h3>${esc(data.report.state)}</h3><p class="aeo-url">${esc(data.binding.target)}</p><p>Observed ${esc(row.created)}. Freshness limit: seven days. Imported history is never a current native check.</p><p><strong>What to repair</strong></p>${data.repairs.length?`<ol>${data.repairs.map(item=>`<li><strong>${esc(item.code)}</strong><p>${esc(item.instruction)}</p></li>`).join("")}</ol>`:"<p>No listed technical repair was observed. This does not prove indexing, visibility or content quality.</p>"}<details><summary>Inspect hashes, budget and exact source facts</summary><pre>${json(row)}</pre></details><p>Indexing: not verified. Citations and growth: not measured. No publication or spending occurred.</p></div><div class="modal-actions">${button("Run a new check","aeo-retry",`data-id="${esc(id)}"`)}${button("Download check history","aeo-download")}</div>`,"IMMUTABLE OBSERVATION");
}

async function aeoSubmit(form) {
  const app=form.dataset.app;
  if(app!==state.app || aeoPending.has(app)) return;
  const data=new FormData(form), selected=(state.workspace.acquisition?.intents||[]).find(i=>i.id===data.get("intent_id"));
  const body={app_version:Number(form.dataset.version),app_hash:form.dataset.hash,url:data.get("page_url"),intent_id:selected?.id||null,intent_hash:selected?.current.hash||null};
  const submit=form.querySelector('[type="submit"]');submit.disabled=true;aeoPending.add(app);
  form.querySelector("#aeo-progress").textContent="Reading robots, page and sitemap… no automatic retries.";
  form.querySelector("#form-error").textContent="";
  try {
    const saved=await api(`/api/apps/${encodeURIComponent(app)}/aeo/run`,body);
    if(state.app!==app) return;
    await refresh();
    if(form.isConnected && $("#modal").open) aeoInspect(saved.id);
    else toast("Public page check saved. Open its history to inspect.");
  } catch(error) {
    if(state.app===app && form.isConnected) {
      form.querySelector("#form-error").textContent=error.message+" Reload history before retrying if the connection was interrupted.";
      form.querySelector("#aeo-progress").textContent="Check did not confirm completion.";
    }
  } finally {
    aeoPending.delete(app);
    if(form.isConnected) submit.disabled=false;
  }
}

async function aeoAction(node) {
  const action=node.dataset.action;
  if(action==="aeo-run") return aeoForm();
  if(action==="aeo-inspect") return aeoInspect(node.dataset.id);
  if(action==="aeo-retry") return aeoForm(state.workspace.aeo.checks.find(i=>i.id===node.dataset.id)?.data.binding);
  if(action==="aeo-download") return serverDownload(`/api/apps/${encodeURIComponent(state.app)}/aeo/history`,state.app+"-aeo-history.json");
  if(action==="aeo-reload") {$("#modal").close();await refresh();}
}
