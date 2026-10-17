"use strict";

function publicStoreEvents(id) {return state.workspace.public_store_checks?.[id]||[];}

function publicStoreResult(event) {
  const d=event.detail,r=d.report;
  return `<article class="panel"><h3>${esc(label(r.status))}</h3><p>${esc(d.binding.country.toUpperCase())} · ${esc(r.language||"Language unknown")} · ${esc(r.version||"Version unknown")} · ${esc(label(event.evidence_status))}</p><p>${esc(new Date(event.observed_at).toLocaleString())}</p>${r.reasons.length?notice(r.reasons.map(label).join("; "),"warning"):""}<ul>${Object.entries(r.checks).map(([k,v])=>`<li>${esc(label(k))}: ${v?"Matched":"Not matched"}</li>`).join("")}</ul><details><summary>Observation receipt</summary><pre>${json(event)}</pre></details></article>`;
}

function publicStoreOpen(id=null,country="") {
  const rows=state.workspace.provider_actions||[];
  if(!rows.length)return modal("Check public App Store listing",`<div class="modal-content">${notice("Prepare an exact store text action in Activity first. The public check needs its app ID, release, language and frozen copy. No provider change is sent by this check.")}</div><div class="modal-actions">${button("Open Activity","public-store-activity")}</div>`);
  const row=rows.find(r=>r.id===id)||rows[0];
  const localeCountry=row.packet.after.locale.split("-").at(-1);
  const suggested=/^[a-zA-Z]{2}$/.test(localeCountry)?localeCountry.toLowerCase():"";
  modal("Check public App Store listing",`<form id="public-store-form" data-app="${esc(state.app)}" data-version="${state.workspace.app.version}" data-id="${esc(row.id)}" data-hash="${esc(row.hash)}"><div class="modal-content">${notice("This reads Apple’s public page without credentials. A match is a server-rendered HTTP observation, not proof of App Review approval, device rendering or growth.")}<label class="field">Exact store action<select name="action_id">${rows.map(r=>`<option value="${esc(r.id)}" ${r.id===row.id?"selected":""}>${esc(r.packet.record.title)} · ${esc(r.packet.after.locale)} · ${esc(r.packet.after.release)}</option>`).join("")}</select></label><label class="field">Storefront country<input name="country" value="${esc(country||suggested)}" pattern="[a-z]{2}" minlength="2" maxlength="2" required autocomplete="off"><small>Two lowercase letters, such as us, ca or gb. Suggested from this action’s language; confirm your intended storefront.</small></label><p>App ${esc(row.packet.after.store_app_id)} · iOS ${esc(row.packet.after.release)} · ${esc(row.packet.after.locale)}</p><p>${esc(row.packet.after.promotional_text)}</p><p class="app-mono">SHA256 ${esc(row.hash)}</p><div id="form-error" class="field-error" role="alert"></div><div id="public-store-history" aria-live="polite">${publicStoreEvents(row.id).slice().reverse().map(publicStoreResult).join("")||"<p>No public checks recorded for this action.</p>"}</div></div><div class="modal-actions"><button type="submit" class="button">Check public listing</button>${button("Download public checks","public-store-download",`data-id="${esc(row.id)}"`)}</div></form>`);
}

async function publicStoreSubmit(event) {
  const form=event.target;if(form.getAttribute("id")!=="public-store-form")return;
  event.preventDefault();const app=form.dataset.app,submit=form.querySelector('[type="submit"]');submit.disabled=true;
  const country=form.elements.country.value;
  try {
    if(state.app!==app)throw new Error("Workspace changed; reopen the public check for this app.");
    const result=await api(`/api/apps/${app}/provider-actions/${form.dataset.id}/public-listing`,{manifest_version:Number(form.dataset.version),action_hash:form.dataset.hash,country});
    if(!form.isConnected||state.app!==app||!$("#modal").open)return;
    await refresh();
    if(form.isConnected&&state.app===app&&$("#modal").open)publicStoreOpen(form.dataset.id,country);
    if(state.app===app)toast(label(result.detail.report.status));
  } catch(error) {
    if(form.isConnected&&state.app===app)form.querySelector("#form-error").textContent=error.message;
  } finally {submit.disabled=false;}
}

document.addEventListener("submit",publicStoreSubmit);
document.addEventListener("change",event=>{
  const form=event.target.closest("#public-store-form");
  if(form&&event.target.name==="action_id")publicStoreOpen(event.target.value,form.elements.country.value);
});
document.addEventListener("click",event=>{
  const node=event.target.closest("[data-action]");if(!node)return;
  if(node.dataset.action==="public-store-open")publicStoreOpen(node.dataset.id);
  if(node.dataset.action==="public-store-download")download(`${state.app}-public-store-checks.json`,{app_id:state.app,action_id:node.dataset.id,checks:publicStoreEvents(node.dataset.id),classification:"PASSIVE_OBSERVATION_HISTORY"});
  if(node.dataset.action==="public-store-activity"){$("#modal").close();guidedNavigate("activity");}
});
