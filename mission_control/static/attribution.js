/* Apple attribution: app-scoped setup, explicit maps, one-shot reads, honest history. */
function attributionState() {return state.workspace.attribution||{sources:[],maps:[],receipts:[],failures:[],reads:[],report:{channels:[],records:[]}};}
function attributionButton(text,action,extra="") {
  return button(text,action,extra).replace("<button ","<button type=\"button\" ");
}
function attributionPanel() {
  const w=attributionState();
  return `<section class="panel attribution-panel"><p class="eyebrow">APPLE ATTRIBUTION</p><div class="section-heading"><h2>Understand acquisition evidence</h2>${attributionButton("Add Apple source","attribution-setup")}</div><p class="description">Verify signed SKAdNetwork and AdAttributionKit files, or read a fresh AdServices token. Each app, channel and environment stays separate.</p>${w.sources.map(s=>`<div class="record-row"><span class="record-main"><strong>${esc(s.data.channel)} · ${esc(s.data.environment)}</strong><small>Apple app ${esc(s.data.app_apple_id)} · ${s.imported?"History only":"Declared scope"}</small></span>${status(s.status)}${attributionButton("Open source","attribution-source",`data-id="${esc(s.id)}"`)}</div>`).join("")}${notice("No public delivery endpoint is configured. Conversion labels are unsigned observations; channel overlap, attributed revenue and actual device delivery remain unverified.")}<div class="insights-actions">${attributionButton("Conversion maps","attribution-maps")}${attributionButton("Inspect observations","attribution-results")}</div>${w.failures.length?notice(`${w.failures.length} input failures retained. Open the affected source for recovery.`,"warning"):""}</section>`;
}
function attributionAccess() {
  modal("App access required",`<div class="modal-content">${notice("Use this app's owner role to add or disconnect sources. Owner or maker access is required for maps and verified intake.")}</div><div class="modal-actions">${attributionButton("Open app access","payment-access")}</div>`,"ATTRIBUTION / ACCESS");
}
function attributionSetup() {
  if(!paymentOwner())return attributionAccess();
  modal("Add Apple attribution source",`<form id="attribution-setup-form" data-app="${esc(state.app)}"><div class="modal-content"><ol><li>Choose the protocol this app uses.</li><li>Copy its numeric Apple app ID from App Store Connect.</li><li>For AdServices only, enter the Apple Ads organization ID.</li></ol><div class="form-grid"><label class="field">Channel<select name="channel"><option>SKAdNetwork</option><option>AdAttributionKit</option><option>AdServices</option></select></label><label class="field">Environment<select name="environment"><option>Production</option><option>Development</option></select></label><label class="field">Apple app ID<input name="app_apple_id" inputmode="numeric" pattern="[1-9][0-9]*" maxlength="19" required autocomplete="off"></label><label class="field">Apple Ads organization ID<small>Required only for AdServices; leave blank for signed postbacks.</small><input name="org_id" inputmode="numeric" pattern="[1-9][0-9]*" maxlength="19" autocomplete="off"></label></div><label class="choice"><input name="confirm_read" type="checkbox" required> Enable local verification or explicitly requested one-shot reads for this declared source.</label>${notice("This declaration does not prove account ownership. AdServices tokens must come from this app's SDK; the response itself does not identify the app. No token is retained.")}<div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit">Save source & continue</button></div></form>`,"ATTRIBUTION / SETUP");
}
function attributionSource(id) {
  const w=attributionState(),s=w.sources.find(r=>r.id===id);if(!s)return;
  const active=s.status==="ACTIVE"&&!s.imported,ads=s.data.channel==="AdServices",fails=w.failures.filter(r=>r.source_id===id);
  modal("Apple attribution source",`<div class="modal-content">${status(s.status)}<h3>${esc(s.data.channel)} · ${esc(s.data.environment)}</h3><p>Declared Apple app ${esc(s.data.app_apple_id)}${ads?" · organization "+esc(s.data.org_id):""}</p>${!active?notice("This source cannot accept new observations. Imported history carries no current read or signature authority."):""}${active&&!ads?notice("Next: create or select a release/locale/sequence map, then verify the original signed JSON. Signature verification runs locally with pinned Apple public keys."):""}${active&&ads?notice("Request a new attributionToken from this app's iOS AdServices SDK. Submit it here once, within 24 hours. The fixed Apple API endpoint receives the token only after your consent."):""}${fails.length?notice(`${fails.length} failed attempts. Check app/environment and the selected sequence map. For AdServices, check organization ID and request a fresh SDK token. Reselect original input to retry; no background retry occurs.`,"warning"):""}<details><summary>Inspect sanitized declaration and errors</summary><pre>${json({source:s,failures:fails})}</pre></details></div><div class="modal-actions insights-actions">${active?button(ads?"Read fresh AdServices token":"Verify signed postback",ads?"attribution-token":"attribution-intake",`data-id="${esc(id)}"`):""}${!ads?button("Manage conversion maps","attribution-maps"):""}${attributionButton("Inspect observations","attribution-results")}${active&&paymentOwner()?button("Disconnect locally","attribution-disconnect",`data-id="${esc(id)}"`):""}</div>`,"ATTRIBUTION / SOURCE");
}
function attributionMaps() {
  const w=attributionState();
  modal("Immutable conversion maps",`<div class="modal-content"><p>Label only values your app actually emits. Keep release, locale, sequence and original mapping source explicit. New versions never reinterpret saved receipts.</p>${w.maps.map(m=>`<div class="record-row"><span class="record-main"><strong>${esc(m.data.release)} · ${esc(m.data.locale)} · v${m.version}</strong><small>${esc(m.data.channel)} · sequence ${m.data.sequence}${m.imported?" · history only":""}</small></span>${!m.imported?button("Create revision","attribution-map",`data-id="${esc(m.id)}"`):""}</div>`).join("")||notice("No maps yet. Create the mapping used by your app before importing a signed postback.")}<details><summary>Inspect map versions</summary><pre>${json(w.maps)}</pre></details></div><div class="modal-actions">${attributionButton("Create conversion map","attribution-map")}</div>`,"ATTRIBUTION / MAPS");
}
function attributionMapRow(row={},coarse=false) {
  const control=coarse?`<select name="map_value"><option value="">Choose coarse value</option>${["low","medium","high"].map(v=>`<option ${v===row.value?"selected":""}>${v}</option>`).join("")}</select>`:`<input name="map_value" type="number" min="0" max="63" step="1" value="${row.value??""}">`;
  return `<div class="form-grid attribution-map-row" data-kind="${coarse?"coarse":"fine"}"><label class="field">${coarse?"Coarse value":"Fine value (0–63)"}${control}</label><label class="field">Symbolic meaning<input name="map_label" maxlength="180" value="${esc(row.label||"")}"></label>${attributionButton("Remove row","attribution-remove-row")}</div>`;
}
function attributionMap(id) {
  if(!paymentMaker())return attributionAccess();
  const rows=attributionState().maps.filter(m=>m.id===id),m=rows.sort((a,b)=>b.version-a.version)[0],d=m?.data||{};
  modal(m?"Create map revision":"Create conversion map",`<form id="attribution-map-form" data-app="${esc(state.app)}" data-id="${esc(m?.id||"")}" data-version="${m?.version||0}"><div class="modal-content">${notice("Use symbolic event names, not inferred revenue. Fine values apply only to sequence zero. Blank rows are ignored; duplicate values are rejected.")}<div class="form-grid"><label class="field">App release<input name="release" required maxlength="120" value="${esc(d.release||state.workspace.app.data.release||"")}"></label><label class="field">Locale<input name="locale" required maxlength="35" value="${esc(d.locale||state.workspace.app.data.locale||"en-US")}"></label><label class="field">Channel<select name="channel">${["SKAdNetwork","AdAttributionKit"].map(v=>`<option ${v===d.channel?"selected":""}>${v}</option>`).join("")}</select></label><label class="field">Postback sequence<select name="sequence">${[0,1,2].map(v=>`<option value="${v}" ${v===(d.sequence||0)?"selected":""}>${v}</option>`).join("")}</select></label><label class="field">Effective at (with timezone)<input name="effective_at" required value="${esc(d.effective_at||new Date().toISOString())}"></label><label class="field">Original mapping source<input name="original_source" required maxlength="1000" value="${esc(d.original_source||"")}" placeholder="Release configuration or inspected source path"></label></div><div id="attribution-map-rows">${(d.fine||[{}]).map(row=>attributionMapRow(row)).join("")}${(d.coarse||[{}]).map(row=>attributionMapRow(row,true)).join("")}</div><div class="insights-actions">${attributionButton("Add fine value","attribution-add-row",'data-kind="fine"')}${attributionButton("Add coarse value","attribution-add-row",'data-kind="coarse"')}</div><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit">Save immutable map version</button></div></form>`,"ATTRIBUTION / MAP VERSION");
}
function attributionIntake(id) {
  if(!paymentMaker())return attributionAccess();
  const s=attributionState().sources.find(r=>r.id===id);if(!s)return;
  const maps=attributionState().maps.filter(m=>!m.imported&&m.data.channel===s.data.channel);
  if(!maps.length)return attributionMaps();
  modal("Verify original signed postback",`<form id="attribution-intake-form" data-app="${esc(state.app)}" data-id="${esc(id)}"><div class="modal-content"><label class="field">Exact conversion-map version<select name="mapping" required>${maps.map(m=>`<option value="${esc(m.id)}:${m.version}:${esc(m.hash)}">${esc(m.data.release)} · ${esc(m.data.locale)} · sequence ${m.data.sequence} · v${m.version}</option>`).join("")}</select></label><label class="field">Original signed JSON<input name="postback" type="file" required accept=".json,application/json"></label><label class="choice"><input name="confirm_read" type="checkbox" required> Verify this original file and bind its observations to this exact map.</label>${notice("No provider JSON editing is needed. Duplicates do not count twice. Conflicting unsigned values stay visible as unknown. Raw signatures and file contents are discarded.")}<details><summary>Authorized local forwarding</summary><p>Use the selected map's exact ID/version in /api/attribution/APP/SOURCE/MAP/VERSION and its hash in X-Attribution-Map-SHA256. Send original JSON with Content-Type application/json to this workstation only. No public Apple URL is configured.</p></details><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit">Verify & save observations</button></div></form>`,"ATTRIBUTION / SIGNED FILE");
}
function attributionToken(id) {
  if(!paymentMaker())return attributionAccess();
  modal("Read fresh AdServices token",`<form id="attribution-token-form" data-app="${esc(state.app)}" data-id="${esc(id)}"><div class="modal-content"><label class="field">Fresh app SDK token<input type="password" name="token" required maxlength="16384" autocomplete="off" spellcheck="false"></label><label class="field">Token obtained at (with timezone)<input name="obtained_at" required value="${esc(new Date().toISOString())}"></label><label class="choice"><input type="checkbox" name="confirm_read" required> Send this token once to Apple's AdServices API for this declared app and organization.</label>${notice("The token must be less than 24 hours old and cannot be reused here. It is cleared after the attempt and never stored or exported. A response with no attribution does not prove organic acquisition. No cross-channel install total is calculated.")}<div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit">Read once & save sanitized facts</button></div></form>`,"ATTRIBUTION / EXPLICIT API READ");
}
function attributionResults() {
  const w=attributionState();
  modal("Apple attribution observations",`<div class="modal-content">${notice("Keep channels separate: their audiences may overlap. Download candidates are provider observations, not verified new customers. Historical imports are assertions only. Mapping labels remain unsigned; revenue is unknown.")}<div class="table-wrap"><table class="result-table"><thead><tr><th>Channel / environment</th><th>Unique observations</th><th>Current download candidates</th><th>History / conflicts</th></tr></thead><tbody>${w.report.channels.map(r=>`<tr><td>${esc(r.channel)}<br>${esc(r.environment)}</td><td>${r.unique_observations}</td><td>${r.current_download_candidates}</td><td>${r.historical_observations} / ${r.unsigned_conflicts}</td></tr>`).join("")}</tbody></table></div>${w.report.records.map(r=>`<details><summary>${esc(r.channel)} · ${esc(r.conversion_type||"unknown")} · ${esc(label(r.verification))}${r.unsigned_conflict?" · conversion conflict":""}</summary><pre>${json(r)}</pre></details>`).join("")}${w.reads.length?`<h3>One-shot API read history</h3>${notice("A pending read has an unknown outcome; it never resumes automatically. Request a new SDK token after checking the cause.")}<pre>${json(w.reads)}</pre>`:""}</div><div class="modal-actions">${attributionButton("Download sanitized history","attribution-download")}</div>`,"ATTRIBUTION / SEPARATE CHANNELS");
}
function attributionDisconnect(id) {
  const s=attributionState().sources.find(r=>r.id===id);if(!s||!paymentOwner())return attributionAccess();
  modal("Disconnect source locally",`<form id="attribution-disconnect-form" data-app="${esc(state.app)}" data-id="${esc(id)}" data-version="${s.version}"><div class="modal-content"><p>Disable new intake and in-flight reads for this source. Saved history remains. This does not change Apple settings.</p><label class="choice"><input name="confirm_disconnect" type="checkbox" required> Disconnect this app's attribution source locally.</label><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit">Disconnect locally</button></div></form>`,"ATTRIBUTION / DISCONNECT");
}
function attributionMapValues(form,kind) {
  return Array.from(form.querySelectorAll(`[data-kind="${kind}"].attribution-map-row`)).flatMap(row=>{
    const value=row.querySelector('[name="map_value"]').value,text=row.querySelector('[name="map_label"]').value.trim();
    if(!value&&!text)return [];
    if(value===""||!text)throw Error("Each mapping row needs both a value and a symbolic meaning.");
    return [{value:kind==="fine"?Number(value):value,label:text}];
  });
}
async function attributionSubmit(form) {
  const submit=form.querySelector('[type="submit"]'),v=new FormData(form),app=form.dataset.app,id=form.dataset.id;
  submit.disabled=true;
  try {
    let path="sources",body;
    if(form.id==="attribution-setup-form")body={channel:v.get("channel"),environment:v.get("environment"),app_apple_id:v.get("app_apple_id").trim(),org_id:v.get("org_id").trim()||null,confirm_read:v.get("confirm_read")==="on"};
    else if(form.id==="attribution-map-form") {
      path="maps";body={id:id||null,expected_version:Number(form.dataset.version),data:{release:v.get("release").trim(),locale:v.get("locale").trim(),channel:v.get("channel"),sequence:Number(v.get("sequence")),effective_at:v.get("effective_at").trim(),fine:attributionMapValues(form,"fine"),coarse:attributionMapValues(form,"coarse"),original_source:v.get("original_source").trim()}};
    } else if(form.id==="attribution-intake-form") {
      const file=v.get("postback");if(!file||!file.size||file.size>262144)throw Error("Choose original JSON of 1 through 262144 bytes.");
      const [mid,version,hash]=v.get("mapping").split(":");
      path=`sources/${encodeURIComponent(id)}/postbacks`;body={raw_json:await file.text(),map_id:mid,map_version:Number(version),map_hash:hash,confirm_read:v.get("confirm_read")==="on"};
    } else if(form.id==="attribution-token-form") {
      path=`sources/${encodeURIComponent(id)}/adservices`;body={token:v.get("token"),obtained_at:v.get("obtained_at").trim(),confirm_read:v.get("confirm_read")==="on"};
    } else {path=`sources/${encodeURIComponent(id)}/disconnect`;body={version:Number(form.dataset.version),confirm_disconnect:v.get("confirm_disconnect")==="on"};}
    if(state.app!==app)throw Error("The selected app changed. Reopen setup for that app.");
    const result=await api(`/api/apps/${encodeURIComponent(app)}/attribution/${path}`,body);
    if(state.app===app){await refresh();if(path==="maps")attributionMaps();else attributionSource(id||result.id);}else $("#modal").close();
    toast(result.duplicate?"Already verified; no duplicate counted.":"Attribution evidence updated.");
  } catch(error) {
    if(state.app===app)await refresh();
    const target=form.querySelector("#form-error");
    if(target){target.textContent=error.message;target.scrollIntoView({block:"nearest"});}
  } finally {
    form.querySelectorAll('[name="token"],[type="file"]').forEach(input=>{input.value="";});
    submit.disabled=false;
  }
}
function attributionAction(node) {
  const action=node.dataset.action,id=node.dataset.id;
  if(action==="attribution-setup")return attributionSetup();
  if(action==="attribution-source")return attributionSource(id);
  if(action==="attribution-maps")return attributionMaps();
  if(action==="attribution-map")return attributionMap(id);
  if(action==="attribution-intake")return attributionIntake(id);
  if(action==="attribution-token")return attributionToken(id);
  if(action==="attribution-results")return attributionResults();
  if(action==="attribution-disconnect")return attributionDisconnect(id);
  if(action==="attribution-add-row")return $("#attribution-map-rows").insertAdjacentHTML("beforeend",attributionMapRow({},node.dataset.kind==="coarse"));
  if(action==="attribution-remove-row")return node.closest(".attribution-map-row").remove();
  if(action==="attribution-download") {
    return serverDownload("/api/apps/"+encodeURIComponent(state.app)+"/attribution/history",state.app+"-attribution-history.json");
  }
}
