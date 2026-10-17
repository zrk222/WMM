/* StoreKit intake: declared app, actual signatures, passive historical replay. */
function storekitState() {return state.workspace.storekit||{sources:[],receipts:[],failures:[],report:{transactions:[]}};}
function storekitPanel() {
  const w=storekitState(),active=w.sources.find(s=>s.status==="ACTIVE"&&!s.imported);
  return `<section class="panel storekit-panel"><p class="eyebrow">APPLE SIGNED NOTIFICATIONS</p><div class="section-heading"><h2>StoreKit transaction observations</h2>${button(active?"Open StoreKit source":"Connect StoreKit","storekit-setup")}</div><p class="description">Verify once per delivery; refund and reversal history updates automatically. Configured prices are separate from payment cash and proceeds.</p>${w.sources.map(s=>`<div class="record-row"><span class="record-main"><strong>${esc(s.data.bundle_id)} · ${esc(s.data.environment)}</strong><small>${s.imported?"Imported history only":"Declared app identity"}</small></span>${status(s.status)}${button("Inspect source","storekit-source",`data-id="${esc(s.id)}"`)}</div>`).join("")}${notice("This workstation accepts authorized local forwarding only. No public Apple endpoint is configured. Original signed JSON can also be imported below.")}${w.failures.length?notice(`${w.failures.length} verification failures retained. Open the source for recovery steps.`,"warning"):""}${w.receipts.length?button("Inspect transactions & download history","storekit-results"):""}</section>`;
}
function storekitSetup() {
  const active=storekitState().sources.find(s=>s.status==="ACTIVE"&&!s.imported);
  if(active)return storekitSource(active.id);
  if(!paymentOwner())return storekitAccess();
  modal("Connect StoreKit",`<form id="storekit-setup-form" data-app="${esc(state.app)}"><div class="modal-content"><p>Enter this app's identity from App Store Connect. No private signing key is required for incoming Apple signatures.</p><div class="form-grid"><label class="field">Bundle ID<input name="bundle_id" required maxlength="255" autocomplete="off"></label><label class="field">Numeric Apple app ID<input name="app_apple_id" required inputmode="numeric" pattern="[0-9]+" maxlength="30" autocomplete="off"></label><label class="field">Environment<select name="environment"><option>Sandbox</option><option>Production</option></select></label></div><label class="choice"><input name="confirm_read" type="checkbox" required> Allow online certificate revocation checks for deliveries to this source.</label>${notice("Setup declares an app identity; it does not verify Apple account ownership or configure a public notification URL. Once connected, signature checks and ordered lifecycle reconciliation run for every received delivery.")}<div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button type="submit" class="button">Save source & enable verification</button></div></form>`,"STOREKIT / SETUP");
}
function storekitAccess() {
  modal("App access required",`<div class="modal-content">${notice("Use this app's owner role for setup/disconnect, or owner/maker role for signed file intake.")}</div><div class="modal-actions">${button("Open app access","payment-access")}</div>`,"STOREKIT / ACCESS");
}
function storekitSource(id) {
  const w=storekitState(),s=w.sources.find(r=>r.id===id);if(!s)return;
  const active=s.status==="ACTIVE"&&!s.imported;
  const url=location.origin+"/api/storekit/"+encodeURIComponent(state.app)+"/"+encodeURIComponent(id);
  const failures=w.failures.filter(r=>r.source_id===id);
  modal("StoreKit source",`<div class="modal-content">${status(s.status)}<h3>${esc(s.data.bundle_id)} · ${esc(s.data.environment)}</h3>${active?`<label class="field">Local forwarding address<input readonly value="${esc(url)}"></label><p>Forward the original JSON with only signedPayload using authorized local tooling. Keep this workstation running. Never put this loopback address in App Store Connect or expose the server publicly.</p>`:notice("This source cannot ingest new deliveries. Imported snapshots carry no current signing authority.")}${failures.length?`<h3>Verification recovery</h3>${notice("Check the declared app/environment, original signed file, system clock and certificate network access. Reselect the original file after fixing the cause. No silent retry or unsigned fallback occurs.","warning")}<p>${failures.length} redacted failures retained; unverified claims were not saved.</p>`:""}<details><summary>Inspect sanitized source and failures</summary><pre>${json({source:s,failures})}</pre></details><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions insights-actions">${active?button("Import original signed JSON","storekit-intake",`data-id="${esc(id)}"`):""}${button("Inspect transactions","storekit-results")}${active&&paymentOwner()?button("Disconnect locally","storekit-disconnect",`data-id="${esc(id)}"`):""}</div>`,"STOREKIT / SOURCE");
}
function storekitIntake(id) {
  if(!paymentMaker())return storekitAccess();
  modal("Verify signed StoreKit JSON",`<form id="storekit-intake-form" data-app="${esc(state.app)}" data-id="${esc(id)}"><div class="modal-content"><label class="field">Original signed notification file<input name="notification" type="file" required accept="application/json,.json"></label><label class="choice"><input name="confirm_read" type="checkbox" required> Verify the outer and nested Apple signatures with online certificate checks.</label>${notice("One verification attempt per submission. Signed payload and private fields are discarded; only sanitized facts and body hash are retained. Failed verification stays visible for recovery.")}<div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button type="submit" class="button">Verify & reconcile automatically</button></div></form>`,"STOREKIT / ORIGINAL FILE");
}
function storekitResults() {
  const w=storekitState();
  modal("StoreKit observations",`<div class="modal-content"><p>${w.receipts.length} sanitized receipts · ${w.report.transactions.length} unique transactions.</p>${notice("Prices are provider-configured milliunits, not cash receipts or proceeds. Refund amounts, fees and attribution remain unknown. History imports are assertions only; no product entitlement is changed.")}<div class="table-wrap"><table class="result-table"><thead><tr><th>Transaction</th><th>Observed lifecycle</th><th>Configured price</th></tr></thead><tbody>${w.report.transactions.map(r=>`<tr><td>${esc(r.transaction_id)}<br>${esc(r.environment)}</td><td>${esc(label(r.status))}${r.conflict?"<br>"+esc(r.conflict):""}<br>${esc(label(r.verification_scope))}</td><td>${r.configured_price_milliunits===null?"Unknown":esc(r.configured_price_milliunits)+" milliunits "+esc(r.currency)}</td></tr>`).join("")}</tbody></table></div>${w.receipts.map(r=>`<details><summary>${esc(r.data.notification.notification_type)} · ${esc(r.id)}${r.imported?" · history only":""}</summary><pre>${json(r)}</pre></details>`).join("")}</div><div class="modal-actions insights-actions">${button("Download sanitized history","storekit-download")}</div>`,"STOREKIT / OBSERVED FACTS");
}
function storekitDisconnect(id) {
  const s=storekitState().sources.find(r=>r.id===id);if(!s)return;
  modal("Disconnect StoreKit locally",`<form id="storekit-disconnect-form" data-app="${esc(state.app)}" data-id="${esc(id)}" data-version="${s.version}"><div class="modal-content"><p>This disables new intake and in-flight verification. Existing history stays available; no Apple configuration is changed.</p><label class="choice"><input type="checkbox" name="confirm_disconnect" required> Disconnect this app's source locally.</label><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit">Disconnect locally</button></div></form>`,"STOREKIT / DISCONNECT");
}
async function storekitSubmit(form) {
  const submit=form.querySelector('[type="submit"]'),values=new FormData(form),app=form.dataset.app,id=form.dataset.id;
  submit.disabled=true;
  try {
    let path="sources",body;
    if(form.id==="storekit-setup-form")body={bundle_id:values.get("bundle_id").trim(),app_apple_id:values.get("app_apple_id").trim(),environment:values.get("environment"),confirm_read:values.get("confirm_read")==="on"};
    else if(form.id==="storekit-intake-form") {
      const file=values.get("notification");if(!file||!file.size||file.size>262144)throw Error("Choose an original JSON file of 1 through 262144 bytes.");
      const parsed=JSON.parse(await file.text());
      if(!parsed||typeof parsed!=="object"||Array.isArray(parsed)||Object.keys(parsed).length!==1||typeof parsed.signedPayload!=="string")throw Error("The file must contain only signedPayload.");
      path=`sources/${encodeURIComponent(id)}/notifications`;body={signedPayload:parsed.signedPayload,confirm_read:values.get("confirm_read")==="on"};
      form.querySelector('[type="file"]').value="";
    } else {path=`sources/${encodeURIComponent(id)}/disconnect`;body={version:Number(form.dataset.version),confirm_disconnect:values.get("confirm_disconnect")==="on"};}
    const result=await api(`/api/apps/${encodeURIComponent(app)}/storekit/${path}`,body);
    if(state.app===app){await refresh();storekitSource(id||result.id);}else $("#modal").close();
    toast(result.duplicate?"Already verified; no duplicate transaction counted.":"StoreKit history updated.");
  } catch(error) {
    if(state.app===app)await refresh();
    const target=form.querySelector("#form-error");if(target)target.textContent=error.message;
  } finally {submit.disabled=false;}
}
async function storekitAction(node) {
  const action=node.dataset.action,id=node.dataset.id;
  if(action==="storekit-setup")return storekitSetup();
  if(action==="storekit-source")return storekitSource(id);
  if(action==="storekit-intake")return storekitIntake(id);
  if(action==="storekit-results")return storekitResults();
  if(action==="storekit-disconnect")return storekitDisconnect(id);
  if(action==="storekit-download") {
    const w=storekitState();
    return download(state.app+"-storekit-history.json",{schema:"growth.storekit-history.v1",app_id:state.app,sources:w.sources,receipts:w.receipts,failures:w.failures});
  }
}
