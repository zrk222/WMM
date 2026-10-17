/* Guided project analytics; keys never enter browser persistence. */
function insightsState() {
  return state.workspace.insights || {sources:[],reports:[],providers:{}};
}
function insightsEventFields(source) {
  const w=insightsState(),events=source?.data.event_map||w.event_defaults||{};
  return `<fieldset><legend>Match this app's event names</legend><p class="description">Use names from your app instrumentation. Leave unknown roles empty. Examples are not verified events; saving does not install tracking or establish user consent.</p><div class="form-grid">${Object.entries(w.event_roles||{}).map(([role,label])=>`<label class="field">${esc(label)}<input name="event_${esc(role)}" value="${esc(events[role]||"")}" maxlength="80" pattern="[A-Za-z_$][A-Za-z0-9_$.\\-]{0,79}" autocomplete="off"><span class="description">${esc(role==="activation"?"The app's promised first useful result.":role==="value"?"Useful completion on a later opportunity.":role==="purchase"?"Activity only; reconcile actual receipts separately.":role==="exposure"?"Assignment or exposure to a declared experiment.":"Exact event name; no personal data.")}</span></label>`).join("")}</div></fieldset>`;
}
function insightsCoverage(source) {
  const c=source?.event_coverage;if(!c)return "";
  return `<section aria-label="Event coverage"><h3>App event coverage</h3>${status(c.state)}<p>${esc(c.reason)}</p><p class="description">Dedicated project · last seven days · events, not unique people. Build, consent, retention and payments require separate evidence.</p><div class="table-wrap"><table class="result-table"><thead><tr><th>Outcome role</th><th>Configured event</th><th>Observed events</th><th>Coverage</th></tr></thead><tbody>${c.roles.map(r=>`<tr><td>${esc(r.label)}</td><td>${esc(r.event||"Not mapped")}</td><td>${r.count===null?"Not measured":esc(r.count)}</td><td>${esc(r.state.replaceAll("_"," "))}</td></tr>`).join("")}</tbody></table></div>${c.observation?`<p class="description">Current observation: ${esc(c.observation.observed_at)} · ${esc(c.observation.sha256.slice(0,12))}</p>`:""}</section>`;
}
function insightsEvents(id) {
  const s=insightsState().sources.find(row=>row.id===id);if(!s||s.provider!=="posthog")return;
  modal("Match your app's events",`<form id="insights-events-form" data-app="${esc(state.app)}" data-id="${esc(id)}" data-version="${s.version}"><div class="modal-content">${notice("This reuses the existing protected key and tests the new mapping. It changes only Mission Control's read configuration.")}${insightsEventFields(s)}<label class="choice"><input name="confirm_read" type="checkbox" required> Read the mapped event counts from this app's dedicated project.</label><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button type="submit" class="button">Save event names & test</button></div></form>`,"APP MEASUREMENT SETUP");
}
function insightsFormEvents(values) {
  return Object.fromEntries(Object.keys(insightsState().event_roles||{}).map(role=>[role,(values["event_"+role]||"").trim()]));
}
async function saveInsightsEvents(form) {
  const submit=form.querySelector('[type="submit"]'),values=Object.fromEntries(new FormData(form)),app=form.dataset.app;
  const body={version:Number(form.dataset.version),event_map:insightsFormEvents(values),confirm_read:values.confirm_read==="on"};
  submit.disabled=true;
  try {
    const result=await api(`/api/apps/${encodeURIComponent(app)}/insights/${encodeURIComponent(form.dataset.id)}/events`,body);
    if(state.app===app){await refresh();insightsInspect(result.source_id);}else $("#modal").close();
    toast(result.read.status==="CONNECTED"?"Event mapping tested. Review coverage gaps.":"Mapping saved; provider access needs attention.");
  }catch(error){const target=form.querySelector("#form-error");if(target)target.textContent=error.message;}
  finally{submit.disabled=false;}
}
function insightsPanel() {
  const w=insightsState();
  const cards=Object.entries(w.providers).map(([id,p])=>{
    const source=w.sources.find(s=>s.provider===id),report=source?w.reports.find(r=>r.source_id===source.id):null;
    return `<section class="connection-card"><h3>${esc(p.name)}</h3>${status(source?.status||"NOT_CONNECTED")}<p>${esc(id==="posthog"?"Map real app events and inspect outcome coverage.":id==="clarity"?"Aggregate friction and engagement. No recordings.":"Subscription overview with provider units and periods.")}</p>${source?.last_error?notice(source.last_error,"warning"):""}${source?`<p class="description">Project ${esc(source.data.project_id)} · ${source.data.automatic?"Six-hour automatic refresh":"Manual refresh"}<br>${report?"Last saved observation: "+esc(report.created):"No successful observation yet."}</p>`:""}${source?.event_coverage?`<p>${status(source.event_coverage.state)} ${esc(source.event_coverage.reason)}</p>`:""}${button(source?"Reconnect / change setup":"Connect "+p.name,"insights-setup",`data-provider="${esc(id)}"`)}${source?button("Inspect / refresh","insights-inspect",`data-id="${esc(source.id)}"`):""}${source?.provider==="posthog"&&!["DISCONNECTED","CLEANUP_REQUIRED"].includes(source.status)?button("Match app events","insights-events",`data-id="${esc(source.id)}"`):""}</section>`;
  }).join("");
  return `<section aria-label="Product and revenue connections"><div class="section-heading"><h2>Product, experience & subscription insights</h2></div><p class="description">Connect once. Saving tests access automatically. Optional refresh runs every six hours while this workstation runs.</p><div class="connection-grid">${cards}</div></section>`;
}
function insightsSetup(provider) {
  const w=insightsState(),p=w.providers[provider],source=w.sources.find(s=>s.provider===provider);if(!p)return;
  const region=provider==="posthog"?`<label class="field">Cloud region<select name="region"><option value="us">US Cloud</option><option value="eu" ${source?.data.region==="eu"?"selected":""}>EU Cloud</option></select></label>`:'<input type="hidden" name="region" value="global">';
  const caveats={posthog:"Map the exact event names your app emits. Generic names below are examples, not installation proof. Absent events are not fabricated.",clarity:"Ten requests per project per day; latest three days only. The export token determines scope; the API does not verify the entered project ID.",revenuecat:"Overview includes every app in its project. Use a dedicated project. Provider metrics are never added to payment cash totals."};
  modal("Connect "+p.name,`<form id="insights-setup-form" data-app="${esc(state.app)}" data-provider="${esc(provider)}" data-version="${source?.version||""}"><div class="modal-content"><p>${esc(p.guide)}</p><p><a class="text-button" href="${esc(p.link)}" target="_blank" rel="noopener noreferrer">Open official setup instructions ↗</a></p>${notice("Your key stays in Windows Credential Manager. Saving performs a permitted read immediately; it does not install an SDK or change your app.")}<div class="form-grid"><label class="field">Project ID<input name="project_id" value="${esc(source?.data.project_id||"")}" required autocomplete="off"></label>${region}<label class="field">Read API key / export token<input name="api_key" type="password" required autocomplete="new-password" maxlength="1800"></label></div>${provider==="posthog"?insightsEventFields(source):""}<label class="choice"><input name="automatic" type="checkbox" ${source?.data.automatic===false?"":"checked"}> Automatically refresh every six hours while Mission Control runs.</label><label class="choice"><input name="dedicated_project" type="checkbox" required> This project contains only this app's permitted data.</label><label class="choice"><input name="confirm_read" type="checkbox" required> I authorize read-only access and the selected refresh schedule.</label>${notice(caveats[provider])}<div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button type="submit" class="button">Connect & test automatically</button></div></form>`,"PERMITTED PROJECT CONNECTION");
}
async function saveInsights(form) {
  const submit=form.querySelector('[type="submit"]'),values=Object.fromEntries(new FormData(form)),app=form.dataset.app;
  submit.disabled=true;
  const body={provider:form.dataset.provider,project_id:values.project_id.trim(),region:values.region,api_key:values.api_key.trim(),automatic:values.automatic==="on",dedicated_project:values.dedicated_project==="on",confirm_read:values.confirm_read==="on"};
  if(form.dataset.version)body.version=Number(form.dataset.version);
  if(body.provider==="posthog")body.event_map=insightsFormEvents(values);
  form.querySelector('[name="api_key"]').value="";
  try {
    const result=await api(`/api/apps/${encodeURIComponent(app)}/insights/setup`,body);
    if(state.app===app){await refresh();insightsInspect(result.source_id);}else $("#modal").close();
    toast(result.read.status==="CONNECTED"?"Connection tested. Review observed coverage.":"Setup saved; provider access needs attention.");
  }catch(error){const target=form.querySelector("#form-error");if(target){const message=String(error.message||"Setup failed");const hasState=message.includes("Replacement not activated")||message.includes("SOURCE_NOT_SAVED");const rotating=!!form.dataset.version;target.textContent=hasState?message:(rotating?"Replacement not activated. The existing connection, schedule, and reports remain in use. ":"No source was saved. Enter the key again to retry. ")+message;}}
  finally{submit.disabled=false;}
}
function insightsInspect(id) {
  const w=insightsState(),s=w.sources.find(row=>row.id===id);if(!s)return;
  const report=w.reports.find(r=>r.source_id===id),p=w.providers[s.provider];
  const controls=(s.provider==="posthog"&&!["DISCONNECTED","CLEANUP_REQUIRED"].includes(s.status)?button("Match app events","insights-events",`data-id="${esc(id)}"`):"")+(!["DISCONNECTED","CLEANUP_REQUIRED"].includes(s.status)?button("Refresh now","insights-read",`data-id="${esc(id)}"`):"")+button("Change setup","insights-setup",`data-provider="${esc(s.provider)}"`)+(report?button("Download report","insights-download",`data-id="${esc(id)}"`):"")+button(s.status==="CLEANUP_REQUIRED"?"Retry local key cleanup":"Disconnect locally","insights-disconnect",`data-id="${esc(id)}" data-version="${s.version}"`);
  modal(p.name+" · "+s.data.project_id,`<div class="modal-content">${status(s.status)}${s.last_error?notice(s.last_error,"warning"):""}<p>${s.data.automatic?"Six-hour automatic refresh while the worker runs.":"Automatic refresh disabled."} ${s.next_due?"Next due: "+esc(new Date(s.next_due*1000).toLocaleString()):""}</p>${insightsCoverage(s)}${report?`<details><summary>Last saved observation (historical if current coverage is unavailable)</summary><p>Observed ${esc(report.created)} · ${esc(report.data.scope)}</p><pre>${json(report.data)}</pre></details>`:notice("No successful observation yet. Check project and key permissions, then reconnect or retry.","warning")}${notice("Provider observations remain separate from transaction evidence. Disconnect removes local access; reports remain available. Revoke the key at the provider if needed.")}<div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions insights-actions">${controls}</div>`,"PROJECT MEASUREMENT");
}
async function insightsAction(node) {
  const action=node.dataset.action,id=node.dataset.id,app=state.app,w=insightsState();
  if(action==="insights-setup")return insightsSetup(node.dataset.provider);
  if(action==="insights-inspect")return insightsInspect(id);
  if(action==="insights-events")return insightsEvents(id);
  if(action==="insights-download")return download(app+"-analytics-report.json",w.reports.find(r=>r.source_id===id));
  if(action==="insights-read"||action==="insights-disconnect"){
    node.disabled=true;
    try{
      const body=action==="insights-read"?{confirm_read:true}:{version:Number(node.dataset.version),confirm_disconnect:true};
      await api(`/api/apps/${encodeURIComponent(app)}/insights/${encodeURIComponent(id)}/${action==="insights-read"?"read":"disconnect"}`,body);
      if(state.app===app){await refresh();insightsInspect(id);}else $("#modal").close();
    }catch(error){$("#form-error").textContent=error.message;}finally{node.disabled=false;}
  }
}
