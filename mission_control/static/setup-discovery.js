"use strict";

// Public metadata is a suggestion, never an instruction or proof of readiness.
let setupReview = null;
const setupFields = ['name','job','audience','locale','store_app_id','android_package','android_track'];

function setupCurrent(node, app) {
  return node.isConnected && $('#modal').open && state.app === app && currentWorkspace();
}

function appendSetupReviewLinks(target, row) {
  for(const artifact of row.artifacts.filter(item=>item.kind==='setup_proposal')) target.insertAdjacentHTML('beforeend',button('Review collected app details','setup-review',`data-id="${esc(artifact.id)}"`));
}

function setupHome() {
  setupReview = null;
  const setup = state.workspace.setup_discovery;
  const rows = setup.proposals.map(row => `<div class="next-step"><div><h3>${esc(label(row.currentness))}</h3><p>${esc(new Date(row.created).toLocaleString())} · ${row.suggested_fields.length} suggested fields</p></div>${button('Review draft','setup-review',`data-id="${esc(row.id)}"`)}</div>`).join('');
  modal('Discover app details',`<div class="modal-content" id="setup-home"><p>Use the saved website to collect explicit app metadata and official store links. Nothing changes until you approve selected fields.</p><p><strong>Saved source:</strong> ${esc(setup.website || 'No public website saved')}</p>${notice('Website claims and page language do not prove product behavior, ownership or a tested locale. Credentials and private pages are not requested.')}<div class="toolbar">${button('Read saved website','setup-read',setup.website && setup.proposals.length < setup.capacity ? '' : 'disabled')}${button('Edit saved website','setup-edit')}</div><p>Up to ${setup.capacity} local drafts. Remove a reviewed draft if storage is full.</p><h3>Saved discovery drafts</h3>${rows || '<p>No drafts yet. Read the saved website to begin.</p>'}<p id="setup-error" class="field-error" role="alert"></p></div>`,'SOURCE → REVIEW → APPROVE');
}

async function setupRead(node) {
  const app = state.app, setup = state.workspace.setup_discovery;
  const anchor = $('#setup-home') || $('#setup-review');
  if(!anchor) return;
  node.disabled = true;
  const error = anchor.querySelector('.field-error');
  error.textContent = 'Reading the public source…';
  try {
    const row = await api(`/api/apps/${encodeURIComponent(app)}/setup-discovery/discover`,{app_id:app,app_version:setup.app_version,app_hash:setup.app_hash,confirm_read:true});
    if(!setupCurrent(anchor,app)) return;
    await refresh();
    if(setupCurrent(anchor,app)) setupShow(row);
  } catch(failure) {
    if(setupCurrent(anchor,app)) error.textContent = failure.message + ' Review the saved website or retry the current source.';
  } finally {if(node.isConnected) node.disabled = false;}
}

function setupField(key, candidates, current, editable) {
  const id = `setup-${key}`;
  const options = candidates.map((candidate,index) => `<option value="${index}">${esc(candidate.value)}</option>`).join('');
  const choose = candidates.length ? `<label class="field" for="${id}-candidate">Source suggestions<select id="${id}-candidate" data-field="${key}"><option value="">Choose or edit below</option>${options}</select></label>` : '<p>No explicit source value found. Supply a value only after reviewing its source.</p>';
  const sources = candidates.map(candidate => `<li>${esc(candidate.basis)}${candidate.reference ? ` · <a href="${esc(candidate.reference)}" target="_blank" rel="noopener noreferrer">Official store source ↗</a>` : ''}</li>`).join('');
  return `<fieldset class="panel" ${editable?'':'disabled'}><legend>${esc(label(key))}</legend><p>Saved: ${esc(current || 'Not set')}</p>${choose}<label class="field" for="${id}">Reviewed value<input id="${id}" name="${key}" maxlength="600" value="${esc(current || '')}"></label>${key==='android_track'?'<p>No track is inferred from a store link. Production is a review default; confirm the intended track.</p>':''}<label class="check-row"><input type="checkbox" name="select-${key}"> Apply this field</label>${sources?`<details><summary>Source basis</summary><ul>${sources}</ul></details>`:''}</fieldset>`;
}

function setupShow(row) {
  setupReview = row;
  const data = row.data, projection = data.projection, current = state.workspace.app.data;
  const editable = row.currentness === 'PENDING';
  const fields = setupFields.map(key => setupField(key, projection?.fields[key] || [], key==='android_track' ? current[key] || 'production' : current[key], editable)).join('');
  const warnings = [...(projection?.ambiguous_fields || []).map(key=>`Conflicting ${label(key)} suggestions: choose explicitly.`),...(projection?.limited_fields || []).map(key=>`${label(key)} exceeded the collection limit; review independently.`)];
  if(projection?.link_limit_reached) warnings.push('The link inspection limit was reached; this source may be incomplete.');
  modal('Review collected app details',`<form id="setup-review" data-app="${esc(row.app_id)}"><div class="modal-content">${status(row.currentness)}<p>Source: ${esc(data.source_url || 'No website saved')} · ${esc(label(data.state))}</p><p>Expires ${esc(new Date(row.expires).toLocaleString())}. Only checked fields will change; existing connections and evidence remain intact.</p>${notice('These are unverified public suggestions. Release, activation and readiness still require their own evidence.')} ${warnings.map(text=>notice(text,'warning')).join('')}${editable?fields:'<p>This draft cannot be applied. Read the current source again, or edit app setup.</p>'}<h3>Resolve missing evidence</h3><p>${esc((projection?.missing_fields || ['Public source unavailable']).map(label).join(', '))}</p><div class="toolbar">${button('Read current source again','setup-read')}${button('Edit app setup','setup-edit')}${button('Connect evidence sources','setup-connections')}${button('Review evidence','setup-evidence')}</div><details><summary>Source fingerprints</summary><p>Page SHA256: ${esc(data.source_sha256 || 'Unavailable')}</p><p>Draft SHA256: ${esc(row.hash)}</p></details><p class="field-error" role="alert"></p></div><div class="modal-actions">${button('Remove this local draft','setup-delete')}${editable?'<button class="button" type="submit">Approve selected changes</button>':''}</div></form>`,'HUMAN REVIEW · NO AUTOMATIC APPLY');
  const form = $('#setup-review');
  if(data.source_url) form.querySelector('.modal-content').insertAdjacentHTML('afterbegin',`<a href="${esc(data.source_url)}" target="_blank" rel="noopener noreferrer">Open inspected public page ↗</a>`);
  form.addEventListener('change',event=>{
    const key=event.target.dataset.field;
    if(!setupFields.includes(key) || event.target.value==='') return;
    form.elements[key].value=projection.fields[key][Number(event.target.value)].value;
  });
  form.addEventListener('submit',setupApply);
}

async function setupApply(event) {
  event.preventDefault();event.stopPropagation();
  const form=event.currentTarget, app=state.app, row=setupReview;
  if(!setupCurrent(form,app) || row?.app_id!==app || form.dataset.busy) return;
  const changes={};
  for(const key of setupFields) if(form.elements[`select-${key}`]?.checked) changes[key]=form.elements[key].value;
  const error=form.querySelector('.field-error');
  if(!Object.keys(changes).length) {error.textContent='Select at least one field to apply.';return;}
  form.dataset.busy='true';const submit=form.querySelector('[type="submit"]');submit.disabled=true;
  try {
    const binding=row.data.binding;
    await api(`/api/apps/${encodeURIComponent(app)}/setup-discovery/apply`,{app_id:app,id:row.id,proposal_hash:row.hash,app_version:binding.app_version,app_hash:binding.app_hash,changes,confirm_apply:true});
    if(!setupCurrent(form,app)) return;
    await refresh();
    if(setupCurrent(form,app)) {setupHome();toast('Selected app details saved. Readiness and ownership remain unverified.');}
  } catch(failure) {if(setupCurrent(form,app)) error.textContent=failure.message;}
  finally {delete form.dataset.busy;if(submit.isConnected)submit.disabled=false;}
}

async function setupOpenDraft(id) {
  const app=state.app;
  modal('Loading discovery draft','<div class="modal-content" id="setup-loading"><p role="status">Loading the saved source and review…</p><p class="field-error" role="alert"></p></div>');
  const anchor=$('#setup-loading');
  try {
    const row=await api(`/api/apps/${encodeURIComponent(app)}/setup-discovery/${encodeURIComponent(id)}`);
    if(setupCurrent(anchor,app))setupShow(row);
  } catch(failure) {if(setupCurrent(anchor,app))anchor.innerHTML=`${notice(failure.message,'error')}${button('Return to discovery','setup-open')}`;}
}

async function setupDelete(node) {
  const row=setupReview, app=state.app;
  if(!row || row.app_id!==app)return;
  modal('Remove this discovery draft?',`<div class="modal-content" id="setup-delete"><p>Remove only this local draft. Saved app details, provider connections and the audit history remain.</p><p class="field-error" role="alert"></p></div><div class="modal-actions">${button('Keep draft','setup-review',`data-id="${esc(row.id)}"`)}${button('Remove draft','setup-confirm-delete')}</div>`);
}

async function setupConfirmDelete(node) {
  const row=setupReview, app=state.app, anchor=$('#setup-delete');
  if(!row || row.app_id!==app || !anchor)return;
  node.disabled=true;
  try {
    await api(`/api/apps/${encodeURIComponent(app)}/setup-discovery/delete`,{id:row.id,hash:row.hash,confirm_delete:true});
    if(!setupCurrent(anchor,app))return;
    await refresh();if(setupCurrent(anchor,app))setupHome();
  } catch(failure) {if(setupCurrent(anchor,app))anchor.querySelector('.field-error').textContent=failure.message;}
  finally {if(node.isConnected)node.disabled=false;}
}

function setupAction(node) {
  const action=node.dataset.action;
  if(action==='setup-open')return setupHome();
  if(action==='setup-read')return setupRead(node);
  if(action==='setup-review')return setupOpenDraft(node.dataset.id);
  if(action==='setup-edit')return appForm(false);
  if(action==='setup-delete')return setupDelete(node);
  if(action==='setup-confirm-delete')return setupConfirmDelete(node);
  if(['setup-connections','setup-evidence'].includes(action)) {$('#modal').close();state.view=action==='setup-connections'?'connections':'evidence';return render();}
}
