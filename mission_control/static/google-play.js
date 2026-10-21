"use strict";

function playBinding() {return state.workspace.records.find(r=>r.kind==='connection'&&r.data.provider==='google_play');}
function playFlows() {return state.workspace.play?.flows||[];}
function playReady(binding) {
  if(!binding)return false;
  const d=binding.data,a=state.workspace.app.data;
  return d.auth_mode==='managed_oauth'&&d.package_name===a.android_package&&d.track===a.android_track&&state.workspace.connections?.[binding.id]?.status==='PROTECTED_KEY_PRESENT';
}

function playLatest(binding) {
  if(!binding)return null;
  return state.workspace.jobs.find(j=>j.action==='sync'&&j.data.connection_id===binding.id&&j.data.connection_version===binding.version&&['play_releases','play_subscriptions'].includes(j.data.options?.operation));
}

function playInitial(binding) {
  return playFlows().find(f=>f.status==='CONNECTED'&&f.result?.connection_id===binding?.id&&f.result?.connection_version===binding?.version)?.result?.observation;
}

function playPending() {
  return playFlows().filter(f=>['PENDING','EXCHANGING'].includes(f.status)).map(f=>{
    const handoff=state.playHandoffs?.[state.app];
    const link=handoff?.flow_id===f.id?`<a class="button outline" href="${esc(handoff.url)}" target="_blank" rel="noopener noreferrer">Open Google consent ↗</a>`:'';
    return `<div class="panel"><strong>${esc(label(f.status))}</strong><p>${esc(f.config.package_name)} · ${esc(f.config.track)}. Expires ${esc(new Date(f.expires*1000).toLocaleTimeString())}.</p><p>After consent, refresh this connection. If the consent tab was closed, cancel this attempt and reconnect.</p>${link}${button('Cancel consent','play-cancel',`data-id="${esc(f.id)}"`)}</div>`;
  }).join('');
}

function googlePlayPanel() {
  const binding=playBinding(),ready=playReady(binding),latest=playLatest(binding),initial=playInitial(binding);
  const failed=latest&&['BLOCKED','FAILED'].includes(latest.status);
  const target=binding?`${binding.data.package_name} · ${binding.data.track}`:'Discover your Android package, review its track, then connect through Google.';
  const source=latest?.status==='SUCCEEDED'?latest.result:initial;
  const readControls=binding?`${button('Read releases','play-read',`data-operation="play_releases" ${ready?'':'disabled title="Reconnect or review the saved Android target first"'}`,'')}${button('Read subscription catalog','play-read',`data-operation="play_subscriptions" ${ready?'':'disabled title="Reconnect or review the saved Android target first"'}`)}`:'';
  const observed=source?`<p>Last verified ${esc(new Date(source.observed_at).toLocaleString())}. A saved observation does not guarantee current access.</p>${button('Inspect saved observation','play-observation')}`:'<p>No verified Google Play observation is saved for this connection version.</p>';
  const error=failed?notice(latest.result?.error||'The latest read did not complete. Reconnect or retry the current target.','error'):'';
  const key=binding&&!ready?notice('This login or Android target needs attention. Review app setup or reconnect before reading.','warning'):'';
  const pending=state.workspace.play?.cleanup_pending||0;
  return `<section class="panel" id="google-play-connector"><p class="eyebrow">ANDROID / GOOGLE PLAY</p><h2>Connect Google Play</h2><p>${esc(target)}</p><p>Read release and subscription catalog state for this app. Publishing, purchases and install attribution are separate workflows.</p>${status(ready?'CONFIGURED':binding?'RECONNECT_REQUIRED':'SETUP_NEEDED')}${key}${error}${observed}<div class="toolbar">${readControls}${button(binding?'Reconnect':'Set up Google Play','play-setup')}${binding?button('Disconnect locally','disconnect-connection',`data-id="${esc(binding.id)}"`):''}${button('Access and setup guide','play-guide')}</div>${playPending()}${pending?notice(`${pending} local cleanup item(s) remain. Retry cleanup when protected storage is available.`,'warning')+button('Retry local cleanup','play-cleanup'):''}</section>`;
}

function playGuide() {
  modal('Google Play access and setup',`<div class="modal-content"><ol><li>Use a Google account with access to this app in Play Console.</li><li>Enable the Google Play Developer API in an existing Google Cloud project and create a Desktop OAuth client.</li><li>Download that client’s JSON file. Select it here with your Android configuration, then review the exact package and track.</li><li>Approve Google’s official consent screen. WMM verifies a scoped read before saving the connection.</li></ol>${notice('The required androidpublisher scope covers Play Developer APIs. This integration implements release/catalog reads only. Limit app access through Play Console permissions.')}<p>The client configuration and refresh grant stay in Windows Credential Manager for this app and database. They are excluded from workspace exports.</p><p><a href="https://developers.google.com/android-publisher/getting_started" target="_blank" rel="noopener noreferrer">Official API access guide ↗</a></p><p><a href="https://console.cloud.google.com/apis/credentials" target="_blank" rel="noopener noreferrer">Google Cloud credentials ↗</a></p><p><a href="https://play.google.com/console/" target="_blank" rel="noopener noreferrer">Play Console permissions ↗</a></p></div>`);
}

function playSetup() {
  const binding=playBinding(),data=state.workspace.app.data;
  modal('Connect this Android app',`<form id="play-setup-form" data-app="${esc(state.app)}" data-manifest="${state.workspace.app.version}" data-connection="${esc(binding?.id||'')}" data-version="${binding?.version||0}"><div class="modal-content">${notice(`Review the Android target for ${data.name}. Your Apple Store ID remains separate. Existing access is retained until the replacement read succeeds.`)}<label class="field">Android project metadata<input id="play-metadata-file" type="file" accept=".json,.xml,.gradle,.kts"><small>Optional app.json, AndroidManifest.xml, build.gradle or build.gradle.kts, up to 128 KiB. Metadata is parsed locally by this service, never executed.</small></label><div id="play-discovery" role="status"></div><div class="form-grid">${field('package_name',data.android_package||binding?.data.package_name||'','text','Exact built Android application ID; review discovered variants')}${field('track',data.android_track||binding?.data.track||'production','text','Review the Play track, for example production or internal')}</div><p>If you are changing an already saved Android identity, review App setup first.</p>${button('Review app setup','play-app-setup')}<label class="field">Google Desktop client JSON<input name="client_file" type="file" accept=".json" ${binding?'':'required'} autocomplete="off"><small>Up to 8 KiB. ${binding?'Leave empty to reuse this app’s protected client, or select a replacement file.':'Download Desktop app credentials from Google Cloud.'} Secrets are cleared after submission.</small></label><label class="field"><span><input type="checkbox" name="confirm_read" required> I approve this app target, official Google consent, and a read to verify access.</span></label><div class="field-error" id="form-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit">Prepare Google consent</button></div></form>`,'GOOGLE PLAY / PROTECTED SETUP');
}

async function playFile(file,maximum) {
  if(!file?.size||file.size>maximum)throw new Error('Choose a nonempty configuration file within the displayed size limit.');
  return new TextDecoder('utf-8',{fatal:true}).decode(await file.arrayBuffer());
}

async function playDiscover(input) {
  const form=input.closest('form'),app=form.dataset.app,resultNode=form.querySelector('#play-discovery');
  try {
    const file=input.files[0],text=await playFile(file,131072);
    const value=await api(`/api/apps/${app}/play/discover`,{kind:file.name,text});
    if(state.app!==app||!form.isConnected)return;
    const choices=value.package_candidates;
    if(!choices.length){resultNode.textContent='No explicit package found. Confirm the built application ID from your Android project or Play Console.';return;}
    if(choices.length===1&&!value.requires_selection){form.elements.package_name.value=choices[0];resultNode.textContent='Package found. Review it before preparing consent.';return;}
    resultNode.innerHTML=`<label class="field">Choose an explicit candidate<select id="play-package-choice"><option value="">Review the built variant</option>${choices.map(v=>`<option value="${esc(v)}">${esc(v)}</option>`).join('')}</select></label><p>Computed suffixes and build variants are not resolved. Confirm the final application ID before connecting.</p>`;
  } catch(error) {if(form.isConnected&&state.app===app)resultNode.textContent=error.message;}
  finally {input.value='';}
}

function playConsentUrl(value) {
  const uri=new URL(value);
  if(uri.origin!=='https://accounts.google.com'||uri.pathname!=='/o/oauth2/v2/auth'||uri.username||uri.password||uri.hash)throw new Error('The consent destination could not be verified. Reconnect from Connections.');
  return uri.href;
}

async function playSubmit(form) {
  const app=form.dataset.app,submit=form.querySelector('[type="submit"]');submit.disabled=true;
  try {
    if(app!==state.app)throw new Error('App changed. Reopen this connection setup.');
    const file=new FormData(form).get('client_file');
    const body={package_name:form.elements.package_name.value.trim(),track:form.elements.track.value.trim(),
      client_json:file?.size?await playFile(file,8192):'',manifest_version:Number(form.dataset.manifest),
      connection_id:form.dataset.connection||null,connection_version:Number(form.dataset.version),confirm_read:form.elements.confirm_read.checked};
    const result=await api(`/api/apps/${app}/play/start`,body),url=playConsentUrl(result.authorization_url);
    state.playHandoffs=state.playHandoffs||{};state.playHandoffs[app]={flow_id:result.flow_id,url};
    if(state.app!==app||!form.isConnected||!$('#modal').open)return;
    await refresh();
    if(state.app!==app||!form.isConnected||!$('#modal').open)return;
    modal('Continue with Google',`<div class="modal-content"><p>${esc(result.package_name)} · ${esc(result.track)}</p><p>Open the official consent screen. Keep Mission Control running so Google can return to its exact local port.</p><p>No connection is saved until its read is verified.</p><a class="button" href="${esc(url)}" target="_blank" rel="noopener noreferrer">Open Google consent ↗</a></div>`);
  } catch(error) {if(form.isConnected&&state.app===app)form.querySelector('#form-error').textContent=error.message;}
  finally {form.querySelector('[name="client_file"]').value='';submit.disabled=false;}
}

function playOpenJob(job) {
  const pending=['RUNNING','QUEUED'].includes(job.status);
  let content=`${status(job.status)}<p>Saved ${esc(new Date(job.created).toLocaleString())}. This read cannot publish or change your app.</p>`;
  if(job.result?.error)content+=notice(job.result.error,'error');
  if(job.status==='SUCCEEDED')content+=`<p>${esc(job.result.package_name)} · ${esc(job.result.track)}</p>${playReportBody(job.result)}<details><summary>Inspect source and dated evidence</summary><pre>${json(job.result)}</pre></details>`;
  else if(pending)content+=notice('Reading the approved Android target. You may cancel this local run.');
  else content+=notice('This run did not produce a verified observation. Review the current target before retrying.','warning');
  const actions=pending?button('Cancel local run','cancel-job',`data-id="${esc(job.id)}"`):button('Review and retry','rerun-report',`data-id="${esc(job.id)}"`)+button('Close result','close');
  modal('Google Play read',`<div class="modal-content">${content}</div><div class="modal-actions">${actions}</div>`,'ANDROID / SAVED READ');
  $('#modal-body').dataset.job=job.id;
}

function playRetry(job) {
  const binding=playBinding();if(!playReady(binding))return playSetup();
  modal('Review the current Android target',`<div class="modal-content"><p>${esc(binding.data.package_name)} · ${esc(binding.data.track)}</p><p>This starts a new read against the current approved connection. The previous observation stays unchanged.</p>${button('Read current target','play-read',`data-operation="${esc(job.data.options.operation)}"`)}</div>`);
}

function playObservation() {
  const binding=playBinding(),latest=playLatest(binding),report=latest?.status==='SUCCEEDED'?latest.result:playInitial(binding);
  if(!report)return toast('No verified observation exists for this connection version. Read the current target first.');
  modal('Google Play observation',`<div class="modal-content"><p><strong>${esc(report.package_name)}</strong> · ${esc(report.track)}</p><p>Observed ${esc(new Date(report.observed_at).toLocaleString())}</p>${playReportBody(report)}<details><summary>Source and coverage</summary><p>${esc(label(report.coverage))}</p><p class="app-mono">${esc(report.source_hash)}</p><p>Account identity, global availability, install attribution, purchase and restore were not verified by this read.</p></details></div>`);
}

function playReportBody(report) {
  if(Array.isArray(report.releases))return report.releases.length?report.releases.map(r=>`<section class="panel"><h3>${esc(r.release_name||'Unnamed release')}</h3><p>Version codes: ${esc(r.version_codes.join(', ')||'Not reported')}</p><p>${esc(label(r.lifecycle.replace('RELEASE_LIFECYCLE_STATE_','')))}</p><p>Country availability and rollout fraction: not returned by this read.</p></section>`).join(''):notice('No non-obsolete releases were returned for this track. This is not a readiness or availability approval.');
  if(Array.isArray(report.subscriptions))return report.subscriptions.length?report.subscriptions.map(r=>`<section class="panel"><h3>${esc(r.product_id)}</h3>${r.base_plans.map(p=>`<p>${esc(p.base_plan_id)} · ${esc(label(p.state))}</p>`).join('')}<p>Listing languages: ${esc(r.locales.join(', ')||'Not reported')}. Localized prices and purchase/restore are not assessed here.</p></section>`).join(''):notice('No subscription products were returned. This does not verify billing behavior.');
  return notice('This observation needs review. Its original evidence remains in Activity.','warning');
}

async function playRead(operation) {
  const app=state.app,binding=playBinding();if(!playReady(binding))return playSetup();
  const job=await api(`/api/apps/${app}/play/read`,{connection_id:binding.id,connection_version:binding.version,
    manifest_version:state.workspace.app.version,operation,request_key:crypto.randomUUID()});
  if(state.app!==app)return;
  await refresh();if(state.app!==app)return;
  openJob(job.id);pollJob(job.id);
}

async function playAction(node) {
  const app=state.app,action=node.dataset.action;
  const local={'play-setup':playSetup,'play-guide':playGuide,'play-app-setup':()=>appForm(false),'play-observation':playObservation};
  if(local[action])return local[action]();
  if(action==='play-read')return playRead(node.dataset.operation);
  if(action==='play-refresh'){await refresh();return;}
  if(action==='play-cancel')await api(`/api/apps/${app}/play/cancel`,{flow_id:node.dataset.id});
  else if(action==='play-cleanup')await api(`/api/apps/${app}/play/cleanup`,{});
  else throw new Error('Unknown Google Play action. Refresh Connections.');
  if(state.app===app)await refresh();
}

document.addEventListener('change',event=>{
  if(event.target.id==='play-metadata-file')playDiscover(event.target);
  if(event.target.id==='play-package-choice')event.target.closest('form').elements.package_name.value=event.target.value;
});
