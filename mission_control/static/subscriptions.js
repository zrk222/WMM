/* App-owned catalog observations; no product submission or purchase authority. */
function subscriptionRows(products) {
  const periods={ONE_WEEK:"Weekly",ONE_MONTH:"Monthly",TWO_MONTHS:"Every two months",THREE_MONTHS:"Every three months",SIX_MONTHS:"Every six months",ONE_YEAR:"Annual"};
  return `<div class="table-wrap"><table class="result-table"><caption>Observed Apple subscriptions and next steps</caption><thead><tr><th scope="col">Product</th><th scope="col">Apple status</th><th scope="col">Next step</th></tr></thead><tbody>${products.map(row=>`<tr><th scope="row"><strong>${esc(row.name)}</strong><p class="app-mono">${esc(row.product_id)}</p><small>${esc(periods[row.period]||row.period||"Period not supplied")}</small></th><td>${esc(label(row.state))}</td><td>${esc(row.next_step)}</td></tr>`).join("")}</tbody></table></div>`;
}

function subscriptionResult(report) {
  const products=report.rows.map(row=>({...row,next_step:"Inspect the current billing readiness panel for next steps."}));
  return `${status(report.coverage)}${notice(report.interpretation)}<p>${products.length} products observed · ${report.pages} fetched pages</p>${products.length?subscriptionRows(products):notice("Apple returned no subscriptions. This does not establish the app’s billing model.")}<details><summary>Inspect exact observed data and source hashes</summary><pre>${json(report)}</pre></details>`;
}

function subscriptionPanel() {
  const catalog=state.workspace.subscription_catalog;
  if(!catalog)return "";
  const unavailable=["SETUP_NEEDED","CONNECTION_BLOCKED","NOT_APPLICABLE"].includes(catalog.state);
  const read=catalog.connection_id&&!unavailable?button("Read subscription catalog","subscriptions-read",`data-connection="${esc(catalog.connection_id)}" data-version="${catalog.connection_version}"`):button(catalog.state==="NOT_APPLICABLE"?"Set Store app identity":"Set up App Store connection",catalog.state==="NOT_APPLICABLE"?"edit-app":"provider",'data-id="app_store"');
  const provider=/^\d+$/.test(String(catalog.store_app_id||""))?`<a class="text-button" href="https://appstoreconnect.apple.com/apps/${esc(catalog.store_app_id)}" target="_blank" rel="noopener noreferrer">Open this app in App Store Connect ↗</a>`:"";
  return `<section class="panel" id="subscription-catalog-panel" aria-labelledby="subscription-catalog-heading"><p class="eyebrow">BILLING / APP STORE</p><h2 id="subscription-catalog-heading">Subscription readiness</h2>${status(catalog.state)}<p>${esc(catalog.reason)}</p><p class="description">Product status is one prerequisite. Localized prices, in-app purchase, entitlements and restore still need separate proof.</p><div class="toolbar">${read}${catalog.job_id?button("Inspect catalog read","job",`data-id="${esc(catalog.job_id)}"`):""}${button("Record purchase and restore test","subscriptions-billing")}${provider}</div>${catalog.report?`<p class="description">Observed ${esc(catalog.report.observed_at)} · ${esc(catalog.report.coverage)} coverage · ${catalog.products.length} products. Price verification: not completed.</p>`:""}${catalog.products.length?subscriptionRows(catalog.products):""}<p role="status" id="subscription-message" class="field-error"></p></section>`;
}

async function subscriptionAction(node) {
  if(node.dataset.action==="subscriptions-billing")return evidenceForm("billing");
  if(state.subscriptionPending)return;
  const app=state.app,connection=node.dataset.connection,version=Number(node.dataset.version);
  state.subscriptionPending=true;node.disabled=true;
  try {
    await refresh();
    if(state.app!==app)return;
    const catalog=state.workspace.subscription_catalog;
    if(catalog.connection_id!==connection||catalog.connection_version!==version||catalog.state==="CONNECTION_BLOCKED")throw new Error("Connection changed. Reopen the catalog in this app workspace.");
    return await queue("sync",{connection_id:connection,connection_version:version,options:{operation:"subscription_catalog"}});
  } catch(error) {
    if(state.app!==app)return;
    const message=$("#subscription-message");
    if(message)message.textContent=error.message+" Saved work is preserved. Retry the catalog read.";
    else toast(error.message);
  } finally {state.subscriptionPending=false;node.disabled=false;}
}
