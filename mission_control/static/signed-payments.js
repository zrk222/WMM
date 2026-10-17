"use strict";

function paymentWorkspace() {return state.workspace.payments || {sources:[],receipts:[],attempts:[],effects:[],cash:{known_subtotals:[],status:"NO_DATA"}};}
function paymentOwner() {return myReviewRole()?.role==="OWNER";}
function paymentMaker() {return ["OWNER","MAKER"].includes(myReviewRole()?.role);}
function paymentUrl(source) {return location.origin+"/api/payments/"+encodeURIComponent(state.app)+"/"+encodeURIComponent(source.id);}

function paymentSourcesPanel() {
  const sources=paymentWorkspace().sources;
  return `<section class="panel payment-panel"><p class="eyebrow">SIGNED PAYMENT SOURCES</p><div class="section-heading"><h2>Stripe payment receipts</h2>${button("Set up signed payments","payment-setup")}</div><p class="description">Protect an app-specific signing secret and read-only key locally. Setup checks actual account read access; it does not create a public webhook or process a payment.</p>${sources.map(s=>`<div class="record-row"><span class="record-main"><strong>${esc(s.data.account_id)} · ${s.data.livemode?"LIVE":"TEST"}</strong><small>${esc(s.data.api_version)}${s.imported?" · imported history only":""}</small></span>${status(s.status)}${button("Inspect payment source","payment-source",`data-id="${esc(s.id)}"`)}</div>`).join("") || notice("No source configured. An app owner can connect from this form; protected keys never enter exports.")}</section>`;
}

function paymentResultsPanel() {
  const w=paymentWorkspace(),rows=w.receipts;
  return `<section class="panel payment-panel"><p class="eyebrow">SIGNED INTAKE / ACTUAL CASH</p><div class="section-heading"><h2>Payment receipt reconciliation</h2>${button("Download payment history","payment-download")}</div>${status(w.cash.status)}<p class="description">Delivered records only: ${rows.length} receipts, ${w.cash.unresolved_receipts || 0} unresolved or imported. These are known net cash subtotals, not account totals, earned revenue, cohort contribution or acquisition lift.</p>${w.cash.known_subtotals.map(r=>`<div class="record-row"><span class="record-main"><strong>${r.livemode?"LIVE":"TEST"} · ${esc(r.currency)} · known net cash ${money(r.net_cash_minor,r.currency)}</strong><small>Charges ${money(r.gross_inflow_minor,r.currency)} · refund debits ${money(r.refund_outflow_minor,r.currency)} · failure credits ${money(r.refund_reversal_inflow_minor,r.currency)} · actual fees ${money(r.fees_minor,r.currency)}</small></span></div>`).join("")}${notice("Cohort and subject attribution remain unallocated. Shared-secret verification proves possession of the configured secret. Imported history carries no current verification authority.")}${rows.map(r=>`<button class="record-row" data-action="payment-receipt" data-id="${esc(r.event_id)}"><span class="record-main"><strong>${esc(r.data.event_type)}</strong><small>${esc(r.event_id)} · ${esc(new Date(r.created).toLocaleString())}${r.imported?" · history only":""}</small></span>${status(r.status)}</button>`).join("") || empty("Waiting for a signed delivery","Set up a source in Connections, then forward an authorized signed delivery to its exact loopback address. No test event or zero earnings is invented.",button("Open payment connections","payment-connections"))}</section>`;
}

function paymentSetup() {
  if(!paymentOwner()) return modal("App owner access required",`<div class="modal-content">${notice("Sign in and establish or obtain this app's owner role before connecting payment credentials.")}</div><div class="modal-actions">${button("Open app access","payment-access")}</div>`,"PAYMENTS / ACCESS");
  modal("Connect signed Stripe receipts",`<form id="payment-setup-form" data-app="${esc(state.app)}"><div class="modal-content"><p>Use the account's restricted read key and the exact signing secret for your authorized delivery source. Test and live sources are separate.</p><div class="form-grid">${field("account_id","","text","Stripe account ID, beginning acct_")}${field("livemode",false,"boolean","Yes for live payments; no for test data")}${field("api_version","","text","Exact snapshot endpoint API version")}<label class="field" for="payment-api-key">Restricted read key<input type="password" id="payment-api-key" name="api_key" autocomplete="off" required><small>Read-only access to account, charges, refunds and balance transactions.</small></label><label class="field" for="payment-secret">Endpoint signing secret<input type="password" id="payment-secret" name="endpoint_secret" autocomplete="off" required><small>The whsec_ secret from your authorized local forwarding source.</small></label></div><label class="choice"><input type="checkbox" name="confirm_read" required> I authorize transmitting this key to Stripe for the account read check and protecting both credentials locally.</label>${notice("No public receiver, tunnel, purchase, campaign or automatic provider write is created. Configure your own authorized forwarding source after setup.")}<div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit">Check account and protect source</button></div></form>`,"PAYMENTS / PROTECTED SETUP");
}

function paymentSourceOpen(id) {
  const source=paymentWorkspace().sources.find(s=>s.id===id);if(!source)return;
  const active=source.status==="ACTIVE"&&!source.imported,url=paymentUrl(source);
  modal("Payment source",`<div class="modal-content">${status(source.status)}<h3>${esc(source.data.account_id)} · ${source.data.livemode?"LIVE":"TEST"}</h3><p>Snapshot API version ${esc(source.data.api_version)}.</p>${active?`<label class="field" for="payment-address">Exact loopback forwarding address<input id="payment-address" readonly value="${esc(url)}"></label><p>Forward charge.succeeded, refund.created, refund.updated and refund.failed using your authorized Stripe tooling, with this source's exact signing secret. Keep Mission Control running. Signature age must be within 300 seconds.</p>${button("Copy delivery address","payment-copy",`data-id="${esc(id)}"`)}` : notice("This source cannot receive or reconcile new deliveries. Imported snapshots are history only.")}<details><summary>Inspect sanitized source</summary><pre>${json(source)}</pre></details><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions">${paymentOwner()&&!source.imported&&["ACTIVE","CLEANUP_REQUIRED"].includes(source.status)?button(source.status==="CLEANUP_REQUIRED"?"Retry protected key removal":"Disconnect payment source","payment-disconnect",`data-id="${esc(id)}"`):""}</div>`,"PAYMENTS / SOURCE");
}

function paymentReceiptOpen(id) {
  const w=paymentWorkspace(),row=w.receipts.find(r=>r.event_id===id);if(!row)return;
  const attempts=w.attempts.filter(a=>a.event_id===id),original=w.sources.find(s=>s.id===row.source_id),source=w.sources.find(s=>s.status==="ACTIVE"&&s.data.account_id===original?.data.account_id&&s.data.livemode===original?.data.livemode);
  const canRead=paymentMaker()&&!row.imported&&row.data.candidate&&source?.status==="ACTIVE";
  modal("Payment delivery receipt",`<div class="modal-content">${status(row.status)}<h3>${esc(row.data.event_type)}</h3><p>${esc(id)} · ${esc(row.data.object_id || "No supported cash object")}</p><p>Verification: ${row.imported?"IMPORTED HISTORY ONLY":"HMAC WITH CONFIGURED SHARED SECRET"}.</p>${notice("Reconciliation reads current source objects and actual fees. It never sends, refunds or retries a payment. Attribution stays unallocated.")}${attempts.map(a=>`<div class="record-row"><span class="record-main"><strong>Read attempt ${a.version} · ${esc(a.data.status)}</strong><small>${esc(a.data.error || new Date(a.created).toLocaleString())}</small></span></div>`).join("")}<details><summary>Inspect sanitized receipt and immutable attempts</summary><pre>${json({receipt:row,attempts})}</pre></details><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions">${canRead?button("Reconcile actual cash","payment-reconcile",`data-id="${esc(id)}"`):""}${button("Download exact receipt","payment-download-receipt",`data-id="${esc(id)}"`)}</div>`,"PAYMENTS / EVIDENCE");
}

function paymentConfirm(id,operation) {
  const w=paymentWorkspace(),row=operation==="reconcile"?w.receipts.find(r=>r.event_id===id):w.sources.find(s=>s.id===id);if(!row)return;
  const read=operation==="reconcile",original=w.sources.find(s=>s.id===row.source_id),source=read?w.sources.find(s=>s.status==="ACTIVE"&&s.data.account_id===original?.data.account_id&&s.data.livemode===original?.data.livemode):row;
  modal(read?"Read actual cash settlement":"Disconnect this payment source",`<form id="payment-action-form" data-app="${esc(state.app)}" data-id="${esc(id)}" data-operation="${operation}" data-hash="${esc(row.hash)}" data-source="${esc(source?.id || "")}" data-version="${row.version || 1}"><div class="modal-content"><p>${read?"Read the exact charge/refund and linked balance transactions from Stripe. A failed read keeps this receipt and a visible failure state. No payment is made.":"Intake stops before native keys are removed. Earlier receipts and cash history are retained. Provider-side webhook resources are not changed."}</p><label class="choice"><input type="checkbox" name="confirm" required> I confirm this ${read?"read-only reconciliation":"local disconnect"} for this app.</label><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit">${read?"Read and reconcile":"Disconnect locally"}</button></div></form>`,"PAYMENTS / EXPLICIT ACTION");
}

async function savePaymentSource(form) {
  const values=Object.fromEntries(new FormData(form)),app=form.dataset.app;
  const result=await api(`/api/apps/${encodeURIComponent(app)}/payments/sources`,{...values,livemode:values.livemode==="true",confirm_read:values.confirm_read==="on"});
  form.querySelectorAll('input[type="password"]').forEach(i=>i.value="");
  if(state.app===app){await refresh();paymentSourceOpen(result.id);}else $("#modal").close();
  toast("Account read checked; source protected. No delivery has been invented.");
}

async function savePaymentAction(form) {
  const app=form.dataset.app,id=form.dataset.id,operation=form.dataset.operation,confirmed=new FormData(form).get("confirm")==="on";
  const path=operation==="reconcile"?`receipts/${encodeURIComponent(id)}/reconcile`:`sources/${encodeURIComponent(id)}/disconnect`;
  const data=operation==="reconcile"?{receipt_hash:form.dataset.hash,source_id:form.dataset.source,confirm_read:confirmed}:{version:Number(form.dataset.version),confirm_disconnect:confirmed};
  const result=await api(`/api/apps/${encodeURIComponent(app)}/payments/${path}`,data);
  if(state.app===app){await refresh();operation==="reconcile"?paymentReceiptOpen(id):paymentSourceOpen(id);}else $("#modal").close();
  toast(result.status==="FAILED"?"Read failed; the receipt and retry path are preserved.":label(result.status));
}

async function paymentAction(node) {
  const id=node.dataset.id,action=node.dataset.action,w=paymentWorkspace();
  if(action==="payment-setup")return paymentSetup();
  if(action==="payment-source")return paymentSourceOpen(id);
  if(action==="payment-receipt")return paymentReceiptOpen(id);
  if(action==="payment-reconcile"||action==="payment-disconnect")return paymentConfirm(id,action==="payment-reconcile"?"reconcile":"disconnect");
  if(action==="payment-access"||action==="payment-connections"){state.view=action==="payment-access"?"activity":"connections";$("#modal").close();return render();}
  if(action==="payment-copy"){const source=w.sources.find(s=>s.id===id);await navigator.clipboard.writeText(paymentUrl(source));return toast("Delivery address copied.");}
  if(action==="payment-download")return download(state.app+"-payment-history.json",w);
  if(action==="payment-download-receipt")return download(state.app+"-"+id+"-receipt.json",{receipt:w.receipts.find(r=>r.event_id===id),attempts:w.attempts.filter(a=>a.event_id===id)});
}
