"use strict";
const state = {boot:null, workspace:null, app:localStorage.getItem("growth-app"), view:"overview", filter:"", pending:false};
const $ = selector => document.querySelector(selector);
const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const json = value => esc(JSON.stringify(value,null,2));
const label = value => String(value).replaceAll("_"," ").replace(/\b\w/g,c=>c.toUpperCase());
const status = value => `<span class="status ${esc(String(value).toLowerCase())}">${esc(label(value))}</span>`;
const notice = (text,type="") => `<div class="notice ${esc(type)}"><span aria-hidden="true">ⓘ</span><span>${esc(text)}</span></div>`;
const button = (text,action,extra="",cls="outline") => `<button type="button" class="button ${esc(cls)}" data-action="${esc(action)}" ${extra}>${esc(text)}</button>`;
const heading = (title,description,action="") => `<div class="page-heading"><div><p class="eyebrow">${esc(state.workspace.app.data.name)} / APP GROWTH</p><h1>${esc(title)}</h1><p class="description">${esc(description)}</p></div>${action}</div>`;
const empty = (title,description,action="") => `<div class="empty-state"><div class="empty-icon" aria-hidden="true">↗</div><h3>${esc(title)}</h3><p>${esc(description)}</p>${action}</div>`;

async function api(path,body,options={}) {
  const headers = body ? {"Content-Type":"application/json","X-CSRF-Token":state.boot?.csrf} : {};
  const response = await fetch(path,{method:body?"POST":"GET",headers,body:body?JSON.stringify(body):undefined,...options});
  const result = await response.json();
  if(!response.ok) throw new Error(result.error || `Request failed (${response.status})`);
  return result;
}

function toast(message) {
  const node=$("#toast"); node.textContent=message;node.hidden=false;
  clearTimeout(toast.timer);toast.timer=setTimeout(()=>node.hidden=true,6000);
}

async function initialize() {
  try {
    state.boot=await api("/api/bootstrap");
    state.research=await api("/api/research");
    if(!state.boot.apps.some(a=>a.id===state.app)) state.app=state.boot.apps[0]?.id;
    $("#app-select").innerHTML=state.boot.apps.map(a=>`<option value="${esc(a.id)}">${esc(a.data.name)}</option>`).join("");
    $("#app-select").value=state.app;
    await refresh();
  } catch(error) {
    $("#main").innerHTML=`${notice(error.message,"error")}${empty("Your workspace could not load","Your saved records are preserved. Check the local server and retry.",button("Retry loading","reload"))}`;
  }
}

async function refresh() {
  if(!state.app) return;
  const app=state.app,generation=state.refreshGeneration=(state.refreshGeneration||0)+1;
  if(!currentWorkspace()) {
    state.workspace=null;state.workspaceError="";
    $("#app-name").textContent=state.boot.apps.find(item=>item.id===app)?.data.name||"Selected app";
    render();
  }
  let workspace;
  try {workspace=await api(`/api/apps/${encodeURIComponent(app)}`);} catch(error) {
    if(state.app!==app||state.refreshGeneration!==generation)return;
    if(currentWorkspace())throw error;
    state.workspaceError=error.message;render();return;
  }
  if(state.app!==app||state.refreshGeneration!==generation)return;
  state.workspace=workspace;state.workspaceError="";state.workspaceObservedAt=new Date().toISOString();
  localStorage.setItem("growth-app",app);
  $("#app-name").textContent=state.workspace.app.data.name;
  render();
}

function currentWorkspace() {
  return state.workspace?.app.id===state.app;
}

function render() {
  WMMTelemetry.clear();
  WMMAgentControl.invalidate(state);
  WMMCompleteAutomation.invalidate(state);
  $("#edit-app").disabled=!currentWorkspace();
  document.querySelectorAll(".nav-item").forEach(node=>{
    node.classList.toggle("active",node.dataset.view===state.view);
    if(node.dataset.view===state.view) node.setAttribute("aria-current","page"); else node.removeAttribute("aria-current");
  });
  if(!currentWorkspace()) {
    $("#main").setAttribute("aria-busy",state.workspaceError?"false":"true");
    $("#main").innerHTML=state.workspaceError
      ? `${notice(state.workspaceError,"error")}${empty("This app could not load","Your saved work is preserved. Retry loading this app.",button("Retry this app","retry-workspace"))}`
      : `<div role="status">${empty("Loading this app","Your workspace will appear here when it is ready.")}</div>`;
    return;
  }
  $("#main").setAttribute("aria-busy","false");
  const views={weekly:weeklyView,overview:overview,workflow:guidedView,pipeline:pipelineView,evidence:evidenceView,results:resultsView,connections:connectionsView,agents:agentAccessView,activity:activityView,research:researchView};
  $("#main").innerHTML=views[state.view]();
  if(["agents","activity"].includes(state.view))$("#main .page-heading").insertAdjacentHTML("afterend",WMMAgentControl.panel(state));
  if(["agents","activity"].includes(state.view))$("#main .page-heading").insertAdjacentHTML("afterend",WMMCompleteAutomation.panel(state));
  if(state.view==="overview")$("#main .hero").insertAdjacentHTML("afterend",WMMPageReports.overviewStory()+guidedOverviewPanel());
  automationDecorateWorkflow();
  WMMPageReports.decorate(state,document);
  if(["workflow","agents","activity"].includes(state.view)){
    $("#main .page-heading").insertAdjacentHTML("afterend",WMMTelemetry.panel());
    WMMTelemetry.mount(growthReviewServices());
  }
}

function summary() {
  const w=state.workspace, ready=w.stages.filter(s=>s.status==="READY").length;
  return `<div class="summary-grid"><div class="summary-card"><p class="metric-label">Stages with required evidence</p><div class="metric-value">${ready}<small> / 12</small></div><p class="metric-note">Local readiness, not publication</p></div><div class="summary-card"><p class="metric-label">Evidence & assets</p><div class="metric-value">${w.records.length}</div><p class="metric-note">Versioned and scoped to this app</p></div><div class="summary-card"><p class="metric-label">Authorized ad spending</p><div class="metric-value">0<small> authorized</small></div><p class="metric-note">Provider changes require exact approval</p></div></div>`;
}

function weeklyView() {
  const value=state.weeklyReview;
  const intro=heading("Your weekly exceptions","Review what needs attention across your apps. Saved local evidence; no campaign execution.",button("Refresh review","weekly-refresh"));
  if(state.weeklyLoading)return intro+'<p role="status">Reviewing saved app evidence…</p>';
  if(state.weeklyError)return intro+notice(state.weeklyError+" Refresh to retry; saved work is preserved.","error");
  if(!value)return intro+empty("Start your portfolio review","Gather saved evidence across up to five apps per page.",button("Review apps","weekly-refresh"));
  const cards=value.exceptions.map(c=>`<article class="panel"><p class="eyebrow">${esc(c.app_name)} / ${esc(c.category)}</p><h2>${esc(c.title)}</h2>${status(c.state)}<p>${esc(c.reason)}</p><p><strong>Recommended next step:</strong> ${esc(c.next_action)}</p><p class="description">Owner: ${esc(c.owner)} · Cost unknown · Change from prior review not assessed.</p>${button("Open recovery","weekly-recover",`data-app="${esc(c.app_id)}" data-tool="${esc(c.resolution_route)}"`)}<details><summary>Source and limits</summary><p>App ${esc(c.source_receipt.app_id)} · setup version ${esc(c.source_receipt.manifest_version)} · reviewed ${esc(c.source_receipt.observed_at)}</p><p class="app-mono">${esc(c.source_receipt.source_hash||"Source unavailable")}</p><p>Local input checks do not prove retained value, permission to spend or measured growth.</p></details></article>`).join('');
  const coverage=value.coverage;
  return intro+`<p role="status">Apps ${coverage.offset+1}–${coverage.offset+coverage.evaluated} of ${coverage.total_apps} reviewed · ${value.exceptions.length} exceptions on this page.</p>`+(cards||notice("No exceptions on this page. Local-ready inputs still require independent outcome and permission checks."))+`<details class="panel"><summary>Routine local-ready checks</summary>${value.apps.map(a=>`<p><strong>${esc(a.app_name)}</strong>: ${esc(a.local_ready.join(', ')||'No local-ready prerequisite checks')}</p>`).join('')}</details><div class="toolbar">${coverage.offset?button("First apps","weekly-page",'data-offset="0"'):''}${coverage.next_offset!==null?button("Next apps","weekly-page",`data-offset="${coverage.next_offset}"`):''}</div>`;
}

async function weeklyAction(node) {
  const generation=state.weeklyGeneration=(state.weeklyGeneration||0)+1;
  if(node.dataset.action==='weekly-recover') {
    const app=node.dataset.app,tool=node.dataset.tool;
    const allowed=new Set(['workspace','readiness','measurement','results','retention','findings']);
    if(!allowed.has(tool)||!state.boot.apps.some(a=>a.id===app))throw new Error('Refresh this review before opening recovery.');
    state.app=app;$('#app-select').value=app;
    await refresh();
    if(state.weeklyGeneration!==generation||state.view!=='weekly'||state.app!==app||!currentWorkspace())return;
    return tool==='workspace'?guidedNavigate('overview'):guidedOpenTool(tool);
  }
  const offset=node.dataset.action==='weekly-page'?Number(node.dataset.offset):0;
  state.weeklyLoading=true;state.weeklyError='';render();
  try {
    const result=await api('/api/weekly-review?offset='+offset);
    if(state.weeklyGeneration!==generation||state.view!=='weekly')return;
    state.weeklyReview=result;
  } catch(error) {
    if(state.weeklyGeneration!==generation||state.view!=='weekly')return;
    state.weeklyError=error.message;
  } finally {
    if(state.weeklyGeneration===generation){state.weeklyLoading=false;if(state.view==='weekly')render();}
  }
}

function stageCard(stage) {
  return `<button class="stage-card" data-action="stage" data-id="${stage.id}"><div class="stage-top"><span class="stage-number">${String(stage.id).padStart(2,"0")} / ${esc(stage.group.toUpperCase())}</span>${status(stage.status==="READY"?"READY":"NEEDS_INPUT")}</div><h3>${esc(stage.title)}</h3><p>${esc(stage.description)}</p><div class="stage-bottom"><span>${stage.missing.length?`${stage.missing.length} next checks`:"Ready to prepare"}</span><span aria-hidden="true">↗</span></div></button>`;
}

function flow() {
  return `<div class="flow-line">${["Plan","Launch","Learn"].map((name,i)=>`<div class="flow-phase"><span class="phase-number">${i+1}</span><span>${name}<small>${["Establish the truth","Prepare the experiment","Measure useful growth"][i]}</small></span></div>`).join("")}</div>`;
}

function overview() {
  const w=state.workspace, next=w.stages.find(s=>s.status!=="READY") || w.stages[10];
  const recent=w.jobs.slice(0,3);
  return `<section class="hero"><div><p class="eyebrow">WIZE MARKETING MACHINE</p><h1>Plan your app marketing.<br>Prepare the work.<br>Measure results.</h1><p>WMM organizes your app details, marketing evidence and results into a twelve-stage workflow. Create saved work packets, creative briefs, experiment plans and reports for each app.</p><button type="button" class="button light" data-view="workflow">Open Guided workflow →</button></div><div class="hero-art" aria-hidden="true"><div class="orbit"></div><div class="orbit second"></div><div class="orbit third">↗</div></div></section>${summary()}${automaticPreparationPanel()}<div class="two-column"><section class="panel"><p class="eyebrow">YOUR NEXT BEST ACTION</p><h2>${esc(next.title)}</h2><div class="next-step"><div class="step-icon" aria-hidden="true">${next.id}</div><div><h3>${esc(next.missing[0] || "Review a mature experiment")}</h3><p>${esc(next.description)}</p>${button("Open this stage","stage",`data-id="${next.id}"`)}</div></div></section><section class="panel"><p class="eyebrow">RECENT RUNS</p><h2>Work you can inspect</h2>${recent.length?recent.map(job=>`<div class="next-step"><div><h3>${job.action==="pipeline"?"Pipeline preparation":job.action==="experiment"?"Experiment analysis":"Provider read"}</h3><p>${esc(new Date(job.created).toLocaleString())}</p>${status(job.status)} <button class="text-button" data-action="job" data-id="${esc(job.id)}">View result ↗</button></div></div>`).join(""):`<p class="description">Your first run will create a saved packet for every stage, including the evidence still needed.</p><button class="text-button" data-view="pipeline">Explore the pipeline ↗</button>`}</section></div><div class="section-heading"><div><h2>A clear path from plan to learning</h2><p>Twelve connected stages. Each one has a purpose.</p></div><button class="text-button" data-view="pipeline">View all stages →</button></div>${flow()}<div class="stage-grid">${w.stages.slice(0,3).map(stageCard).join("")}</div>`;
}

function pipelineView() {
  return `${heading("Your growth pipeline","Prepare the work, inspect the evidence, and keep the next step visible.",button("Prepare all 12 stages","run-all","",""))}${summary()}${automaticPreparationPanel()}${flow()}<div class="stage-grid">${state.workspace.stages.map(stageCard).join("")}</div>`;
}

function evidenceView() {
  const records=state.workspace.records.filter(r=>`${r.title} ${r.kind}`.toLowerCase().includes(state.filter.toLowerCase()));
  return `${heading("Evidence before confidence","Keep your app facts, authentic captures and experiment data together.",button("＋ Add evidence","add-evidence","",""))}<div class="toolbar"><input id="evidence-search" aria-label="Search evidence" placeholder="Search titles or evidence types" value="${esc(state.filter)}">${button("Upload image","upload")}${button("Export workspace","export")}${button("Restore snapshot","restore")}</div>${notice("Records are operator-reported unless clearly labeled as a provider observation. No private conversations or credentials belong here.")}${spyTokPanel()}${spiraPanel()}${referenceLibrary()}${records.length?`<div class="record-list">${records.map(recordRow).join("")}</div>`:empty("Start with one useful proof","Add a current journey test, an approved claim, a screenshot or a mature cohort. Each item keeps its source and version.",button("Add your first evidence","add-evidence"))}`;
}

function recordRow(record) {
  return `<button class="record-row" data-action="record" data-id="${esc(record.id)}"><span class="record-icon" aria-hidden="true">${record.kind==="asset"?"▧":"▱"}</span><span class="record-main"><strong>${esc(record.title)}</strong><small>${esc(state.boot.labels[record.kind] || record.kind)} · ${esc(record.provenance)} · v${record.version}</small></span><span class="record-meta">${esc(new Date(record.updated).toLocaleDateString())}<br>Open ↗</span></button>`;
}

function referenceLibrary() {
  const filter=(state.referenceFilter||"").toLowerCase();
  const rows=(state.workspace.references||[]).filter(r=>{
    const d=r.current.data;
    return `${d.title} ${d.topic} ${d.relevance_note}`.toLowerCase().includes(filter)&&(!state.referencePlatform||d.platform===state.referencePlatform)&&(!state.referenceRights||d.rights===state.referenceRights);
  });
  return `<div class="section-heading"><h2>Creative source library</h2>${button("Add a reference","reference-add")}</div>${notice("Permitted sources are discovery evidence, not acquisition results or production assets. Unknown metrics and rights stay unknown; permission is operator supplied.")}<div class="toolbar"><input id="reference-search" aria-label="Search creative sources" placeholder="Search titles and topics" value="${esc(state.referenceFilter||"")}"><label class="field" for="reference-platform">Platform<select id="reference-platform"><option value="">All platforms</option>${["tiktok","youtube","instagram","linkedin","x","other"].map(p=>`<option value="${p}" ${state.referencePlatform===p?"selected":""}>${label(p)}</option>`).join("")}</select></label><label class="field" for="reference-rights">Usage rights<select id="reference-rights"><option value="">All rights states</option>${["UNKNOWN","REFERENCE_ONLY","LICENSED"].map(p=>`<option value="${p}" ${state.referenceRights===p?"selected":""}>${label(p)}</option>`).join("")}</select></label>${button("Preview source export","reference-import")}${button("Source CSV template","reference-template")}</div>${rows.length?`<div class="record-list">${rows.map(r=>`<button class="record-row" data-action="reference-open" data-id="${esc(r.id)}"><span class="record-main"><strong>${esc(r.current.data.title)}</strong><small>${esc(label(r.current.data.platform))} · ${esc(r.current.data.topic)} · ${r.captures.length} capture versions</small><small>${r.current.data.metric_value===null?"Observed count unavailable":`${r.current.data.metric_value} ${esc(label(r.current.data.metric_kind))}`} · ${esc(label(r.current.data.rights))}</small></span><span class="record-meta">Inspect source</span></button>`).join("")}</div>`:empty("No matching creative sources","Add a permitted public link or preview an approved export. Missing API access does not prevent an honest source library.",button("Add permitted source","reference-add"))}<div class="section-heading"><h2>Product evidence and authentic assets</h2></div>`;
}

function referenceForm(id=null) {
  const r=state.workspace.references?.find(r=>r.id===id),d=r?.current.data||{},data={...d,captured_at:new Date().toISOString()};
  const enums={platform:["tiktok","youtube","instagram","linkedin","x","other"],traffic_class:["UNKNOWN","ORGANIC","PAID"],rights:["UNKNOWN","REFERENCE_ONLY","LICENSED"],metric_kind:["UNKNOWN","VIEWS","LIKES","SHARES"]};
  const fields=[field("title",data.title),field("post_id",data.post_id,"text","Public opaque post ID; stable across refreshes"),field("url",data.url,"text","Public HTTPS source; no private tokens"),field("source",data.source,"text","Permitted export or collection receipt"),field("locale",data.locale||state.workspace.app.data.locale),field("creator_id",data.creator_id,"text","Public opaque ID, optional; no personal contacts",false),field("format",data.format,"text","Observed format, e.g. product demo"),field("topic",data.topic),field("relevance_note",data.relevance_note,"textarea","Why this is relevant to this app; supplied assessment, not measured lift"),field("captured_at",data.captured_at,"text","Actual ISO capture time with timezone"),field("published_at",data.published_at,"text","Optional observed publication time; blank stays unknown",false),field("metric_value",data.metric_value,"number","Optional observed count; blank stays unavailable",false),field("metric_at",data.metric_at,"text","Required if a count is supplied; ISO timestamp",false),field("permission_confirmed",false,"boolean","Confirm permission to store this reference. This does not grant rights to copy or render.")];
  for(const [name,choices] of Object.entries(enums)) fields.push(`<label class="field" for="field-${name}">${esc(label(name))}<select id="field-${name}" name="${name}" required>${choices.map(v=>`<option value="${v}" ${data[name]===v?"selected":""}>${esc(label(v))}</option>`).join("")}</select></label>`);
  modal(id?"Refresh source observations":"Add permitted reference",`<form id="reference-form" data-app="${esc(state.app)}" data-id="${esc(id||"")}" data-version="${r?.current.version||""}"><div class="modal-content">${notice("Enter facts you can inspect. This saves the link and supplied observations; it does not fetch media, invent a transcript, validate rights or estimate competitor installs.")}<div class="form-grid">${fields.join("")}</div><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button type="submit" class="button">Save source capture</button></div></form>`,"CREATIVE INTELLIGENCE / SOURCE");
  if(id){$("#field-platform").disabled=true;$("#field-post_id").readOnly=true;}
}

async function saveReference(form) {
  const data=Object.fromEntries(new FormData(form));
  if(form.dataset.id)data.platform=state.workspace.references.find(r=>r.id===form.dataset.id).current.data.platform;
  data.permission_confirmed=data.permission_confirmed==="true";
  for(const key of ["published_at","creator_id","metric_at"])if(!data[key])data[key]=null;
  data.metric_value=data.metric_value===""?null:Number(data.metric_value);
  const body={data};if(form.dataset.id)Object.assign(body,{id:form.dataset.id,version:Number(form.dataset.version)});
  await api(`/api/apps/${form.dataset.app}/references`,body);
}

function openReference(id) {
  const r=state.workspace.references.find(r=>r.id===id),d=r.current.data;
  modal(d.title,`<div class="modal-content">${notice("Operator-supplied source; no independent permission verification, transcript, outlier score or acquisition result is inferred.")}<p>${esc(d.relevance_note)}</p><p><a href="${esc(d.url)}" target="_blank" rel="noopener noreferrer">Open original source ↗</a></p><p>${esc(label(d.platform))} · ${esc(d.locale)} · ${esc(label(d.traffic_class))} · ${esc(label(d.rights))}</p><p>Observed count: ${d.metric_value===null?"Unavailable":`${d.metric_value} ${esc(label(d.metric_kind))}`}</p><p>Captured ${esc(d.captured_at)} · published ${esc(d.published_at||"Unknown")}</p><h3>Capture history</h3>${r.captures.map(c=>`<details><summary>Version ${c.version} · ${esc(c.data.captured_at)}</summary><p class="app-mono">${esc(c.hash)}</p><pre>${json(c.data)}</pre></details>`).join("")}<div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions">${button("Inspect source format","production-inspect",`data-id="${esc(id)}"`)} ${button("Refresh observations","reference-refresh",`data-id="${esc(id)}"`)}${button("Download source history","reference-download",`data-id="${esc(id)}"`)}</div>`,"CREATIVE INTELLIGENCE / EVIDENCE");
  $("#modal .modal-actions").insertAdjacentHTML("afterbegin",button("Review source requirements","capability-requirement",'data-id="'+esc(id)+'"')+button("Review app fit","ranking-relevance","data-id='"+esc(id)+"'"));
}

function referenceImportForm() {
  modal("Preview permitted source export",`<form id="reference-import-form" data-app="${esc(state.app)}"><div class="modal-content">${notice("Use the CSV template or an approved JSON row export, under 1 MB and at most 100 sources. Preview verifies columns, permission, dates and identities. Commit is all or none.")}<label class="field" for="reference-file">Source export<input type="file" id="reference-file" name="source_file" accept=".csv,.json" required></label><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button type="submit" class="button">Validate and preview sources</button></div></form>`);
}

async function previewReferences(form) {
  const file=new FormData(form).get("source_file");
  if(!file?.size||file.size>1048576)throw new Error("Choose a permitted export under 1 MB.");
  const raw=new TextDecoder("utf-8",{fatal:true}).decode(await file.arrayBuffer());
  const body=file.name.toLowerCase().endsWith(".csv")?{csv:raw}:{rows:JSON.parse(raw)};
  const preview=await api(`/api/apps/${form.dataset.app}/references/preview`,body);
  state.referencePreview={...preview,app:form.dataset.app};
  modal("Review source import",`<div class="modal-content">${notice(preview.provenance)}${preview.conflicts.map(v=>notice(`Conflict: ${v}. Inspect and refresh the existing source before retrying the batch.`,"warning")).join("")}<div class="table-wrap"><table class="result-table"><thead><tr><th>Source</th><th>Observation</th><th>Rights</th></tr></thead><tbody>${preview.rows.map(r=>`<tr><td>${esc(r.title)}<br>${esc(r.platform)} · ${esc(r.post_id)}</td><td>${r.metric_value===null?"Unavailable":`${r.metric_value} ${esc(r.metric_kind)}`}</td><td>${esc(r.rights)}</td></tr>`).join("")}</tbody></table></div><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions">${button("Import previewed sources","reference-commit",preview.conflicts.length?"disabled":"")}</div>`);
}

async function referenceAction(node) {
  const id=node.dataset.id,action=node.dataset.action;
  const handlers={"reference-add":()=>referenceForm(),"reference-open":()=>openReference(id),"reference-refresh":()=>referenceForm(id),"reference-download":()=>download(`${state.app}-source.json`,state.workspace.references.find(r=>r.id===id)),"reference-import":referenceImportForm,"reference-template":()=>download("creative-source-template.csv","platform,post_id,title,url,source,captured_at,published_at,locale,traffic_class,creator_id,format,metric_kind,metric_value,metric_at,rights,permission_confirmed,topic,relevance_note\n","text/csv")};
  if(handlers[action])return handlers[action]();
  if(action!=="reference-commit")throw new Error("Unknown source action.");
  const p=state.referencePreview;if(!p)throw new Error("Preview the source export first.");
  await api(`/api/apps/${p.app}/references/import`,{rows:p.rows,preview_hash:p.preview_hash});
  await refresh();$("#modal").close();state.referencePreview=null;toast("Permitted sources imported with immutable provenance.");
}

const phaseRoles=["HOOK","PROBLEM","STAKES","REVEAL","DEMO","PROOF","OBJECTION","CTA"];

function choiceField(name,options,value="",multiple=false) {
  const titles={analysis_id:"Inspected mechanism",claim_ids:"Approved claims",asset_ids:"Authentic screens",readiness_id:"Product readiness check",store_id:"Available destination",route_id:"Tested first-value route",duration_seconds:"Proposed scene duration"};
  return `<label class="field" for="field-${esc(name)}">${esc(titles[name]||label(name))}<select id="field-${esc(name)}" name="${esc(name)}" ${multiple?'multiple size="4"':""} required>${multiple?"":'<option value="">Choose…</option>'}${options.map(o=>`<option value="${esc(o.id)}" ${(Array.isArray(value)?value.includes(o.id):value===o.id)?"selected":""}>${esc(o.title)}</option>`).join("")}</select><small>${multiple?"Select the exact proof records; use Ctrl/Cmd for more than one.":""}</small></label>`;
}

function analysisFor(referenceId) {return (state.workspace.analyses||[]).find(a=>a.current.data.reference_id===referenceId);}

function inspectionForm(referenceId) {
  const source=state.workspace.references.find(r=>r.id===referenceId),old=analysisFor(referenceId),d=old?.current.data||{};
  const inputs=[choiceField("inspection_kind",["DIRECT_VIEW","PERMITTED_TRANSCRIPT"].map(id=>({id,title:label(id)})),d.inspection_kind),field("inspection_confirmed",false,"boolean","Confirm you actually inspected this permitted source"),field("inspected_at",new Date().toISOString()),field("analyst",d.analyst),field("format_family",d.format_family),field("duration_seconds",d.duration_seconds,"number","Only actual directly inspected media duration; optional",false),field("uncertainty",d.uncertainty,"textarea","What could not be observed or verified")];
  const phases=phaseRoles.map(role=>phaseFields(role,d.observations?.find(o=>o.role===role))).join("");
  modal(old?"Correct source inspection":"Inspect source format",`<form id="inspection-form" data-app="${esc(state.app)}" data-reference="${esc(referenceId)}" data-hash="${esc(source.current.hash)}" data-id="${esc(old?.id||"")}" data-version="${old?.current.version||""}"><div class="modal-content">${notice("Open and inspect the permitted original source first. Leave unseen phases blank. Suggestions are separate from facts; transcript-only evidence cannot establish timing.")}<a href="${esc(source.current.data.url)}" target="_blank" rel="noopener noreferrer">Open original source ↗</a><div class="form-grid">${inputs.join("")}</div>${phases}<div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button type="submit" class="button">Save inspected analysis</button></div></form>`,"CREATIVE INTELLIGENCE / INSPECTION");
}

function phaseFields(role,row={}) {
  return `<details ${role==="HOOK"?"open":""}><summary>${esc(label(role))} · optional unless observed</summary><div class="form-grid">${choiceField(role+"_basis",["OBSERVED","SUGGESTED"].map(id=>({id,title:label(id)})),row.basis).replace(" required","")}${field(role+"_detail",row.detail,"textarea","Blank excludes this phase",false)}${field(role+"_evidence_note",row.evidence_note,"textarea","Where this was observed, or why it is a suggestion",false)}${field(role+"_start_seconds",row.start_seconds,"number","Optional actual start seconds",false)}${field(role+"_end_seconds",row.end_seconds,"number","Optional actual end seconds",false)}</div></details>`;
}

async function saveInspection(form) {
  const values=Object.fromEntries(new FormData(form));
  const observations=phaseRoles.filter(role=>values[role+"_detail"]?.trim()).map(role=>({role,basis:values[role+"_basis"],detail:values[role+"_detail"],evidence_note:values[role+"_evidence_note"],start_seconds:values[role+"_start_seconds"]===""?null:Number(values[role+"_start_seconds"]),end_seconds:values[role+"_end_seconds"]===""?null:Number(values[role+"_end_seconds"])}));
  const data={reference_id:form.dataset.reference,capture_hash:form.dataset.hash,inspection_kind:values.inspection_kind,inspection_confirmed:values.inspection_confirmed==="true",inspected_at:values.inspected_at,analyst:values.analyst,format_family:values.format_family,duration_seconds:values.duration_seconds===""?null:Number(values.duration_seconds),observations,uncertainty:values.uncertainty};
  const body={data};if(form.dataset.id){body.id=form.dataset.id;body.version=Number(form.dataset.version);}
  await api(`/api/apps/${form.dataset.app}/production/analyses`,body);
}

function productionPanel() {
  const analyses=state.workspace.analyses||[],briefs=state.workspace.briefs||[];
  return `${capabilitiesPanel()}${learningGuidancePanel()}<div class="section-heading"><div><h2>From inspected source to original brief</h2><p>Inspect a permitted source, bind current app proof, then prepare channel-specific work.</p></div>${button("Prepare original brief","production-prepare")}</div>${notice("Preparation saves original copy and a real screen plan. Local videos can be rendered below; publication and spending remain unexecuted.")}<div class="two-column"><section class="panel"><h3>Inspected mechanisms</h3>${analyses.length?analyses.map(a=>`<div class="next-step"><div><strong>${esc(a.current.data.format_family)}</strong><p>${esc(a.source_status)} · ${a.current.data.observations.length} phases · version ${a.current.version}</p>${button("Inspect analysis","production-analysis",`data-id="${esc(a.id)}"`)} ${button("Correct inspection","production-inspect",`data-id="${esc(a.current.data.reference_id)}"`)}</div></div>`).join(""):"<p>Open a source in Evidence and choose Inspect source format. No transcript or timing is inferred.</p>"}</section><section class="panel"><h3>Original production briefs</h3>${briefs.length?briefs.map(b=>`<div class="next-step"><div><strong>${esc(label(b.current.data.definition.channel))} · ${esc(b.current.data.definition.objective)}</strong><p>${esc(b.evidence_status)} · version ${b.current.version} · ${esc(briefRenderState(b))}</p>${button("Open original brief","production-open",`data-id="${esc(b.id)}"`)}</div></div>`).join(""):"<p>Choose current approved claims, authentic screens and tested routes. Missing evidence has a recoverable setup path.</p>"}</section></div>`;
}

function briefForm(id=null,learningId=null,preset={}) {
  const old=state.workspace.briefs?.find(b=>b.id===id),d=old?.current.data.definition||preset,records=state.workspace.records;
  const analyses=(state.workspace.analyses||[]).filter(a=>a.source_status==="CURRENT");
  const missing=["claim","asset","readiness","store","route"].filter(kind=>!records.some(r=>r.kind===kind));
  if(!analyses.length||missing.length)return productionPrerequisites(missing,!analyses.length);
  if(!analyses.some(a=>capabilityEvaluation(a.current.data.reference_id).status==="READY"))return capabilitySetup();
  const selectors=[choiceField("analysis_id",analyses.map(a=>({id:a.id,title:a.current.data.format_family})),d.analysis_id),choiceField("channel",["SHORT_VIDEO","LINKEDIN","X"].map(id=>({id,title:label(id)})),d.channel)];
  for(const kind of ["claim","asset","readiness","store","route"]){const key=["claim","asset"].includes(kind)?kind+"_ids":kind+"_id";selectors.push(choiceField(key,records.filter(r=>r.kind===kind).map(r=>({id:r.id,title:r.title+" · "+r.data.release})),d[key],key.endsWith("_ids")));}
  const method=learningId?learningProgram(learningId):null;
  const guidance=method?notice("This new brief will explicitly include: "+method.data.definition.pattern+". Existing briefs remain unchanged."): "";
  const fields=[field("objective",d.objective,"textarea","Specific scenario to demonstrate; a hypothesis, not a benefit claim"),field("owner",d.owner),field("currency",d.currency||state.workspace.app.data.currency),field("budget_minor",d.budget_minor??0,"number","Declared production cost in minor units; this authorizes no spending"),choiceField("duration_seconds",[15,30,45,60].map(n=>({id:String(n),title:n+" seconds"})),String(d.duration_seconds||30))];
  modal(old?"Revise original brief":"Prepare original brief",`<form id="brief-form" data-app="${esc(state.app)}" data-id="${esc(id||"")}" data-version="${old?.current.version||""}" data-learning="${esc(learningId||"")}" data-learning-version="${method?.version||""}" data-learning-hash="${esc(method?.hash||"")}"><div class="modal-content">${guidance}${brandBriefGuidance()}${notice("Use current release/locale evidence checked within 14 days. A newer failed readiness result blocks preparation. Imported source copy is not reused. Missing proof can be added in Evidence.")}<div class="form-grid">${selectors.join("")}${fields.join("")}</div><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button type="submit" class="button">Prepare evidence-bound brief</button></div></form>`);
}

function productionPrerequisites(missing,needsAnalysis) {
  modal("Build the proof for your brief",`<div class="modal-content">${notice("Your work is preserved. Complete the missing setup below, then prepare a brief against current evidence. No developer configuration is required.")}${needsAnalysis?`<h3>Inspect a permitted source</h3><p>Add a source in Evidence, open it and choose Inspect source format. Correct a stale inspection against the latest capture.</p>${button("Open source library","production-sources")}`:""}${missing.map(kind=>`<div class="next-step"><div><h3>${esc(state.boot.labels[kind])}</h3><p>Add current release/locale proof. Screens require actual image upload and authenticity/rights review.</p>${kind==="asset"?button("Upload a real screen","upload"):button("Add "+state.boot.labels[kind],"production-evidence",`data-kind="${esc(kind)}"`)}</div></div>`).join("")}</div><div class="modal-actions">${button("Close setup guide","close")}</div>`);
}

async function saveBrief(form) {
  const fields=new FormData(form),data=Object.fromEntries(fields);
  for(const key of ["claim_ids","asset_ids"])data[key]=fields.getAll(key);
  data.budget_minor=Number(data.budget_minor);data.duration_seconds=Number(data.duration_seconds);
  data.analysis_hash=state.workspace.analyses.find(a=>a.id===data.analysis_id).current.hash;
  const body={data};if(form.dataset.id){body.id=form.dataset.id;body.version=Number(form.dataset.version);}
  if(form.dataset.learning) {
    const method=learningProgram(form.dataset.learning);
    if(!method?.active)throw new Error("Learning guidance is no longer available. Inspect current Results before using it.");
    await api(`/api/apps/${form.dataset.app}/learning/${method.id}/briefs`,{data,version:Number(form.dataset.learningVersion),hash:form.dataset.learningHash});
  } else await api(`/api/apps/${form.dataset.app}/production/briefs`,body);
}

function openProduction(id,type) {
  const item=state.workspace[type].find(v=>v.id===id),d=item.current.data;
  const contents=type==="briefs"?`<h3>Original copy</h3><p class="description">${esc(d.content.copy).replaceAll("\n","<br>")}</p><h3>Proposed scene plan</h3>${d.content.beats.map(b=>`<p><strong>${b.start_seconds}–${b.end_seconds}s · ${esc(b.scene)}</strong><br>${esc(b.script)}</p>`).join("")}<h3>Authentic screen plan</h3>${d.content.screens.map(s=>`<p>${esc(s.instruction)}</p><img class="asset-preview" src="/api/apps/${encodeURIComponent(state.app)}/files/${encodeURIComponent(s.file_id)}" alt="Selected current app screen for this proposed scene">`).join("")}<h3>Limitations</h3><ul>${d.content.limitations.map(t=>`<li>${esc(t)}</li>`).join("")}</ul>`:`<p>${esc(d.uncertainty)}</p>${d.observations.map(o=>`<p><strong>${esc(o.role)} · ${esc(o.basis)}</strong><br>${esc(o.detail)}<br>${esc(o.evidence_note)}<br>${o.start_seconds===null?"Timing unavailable":`${o.start_seconds}–${o.end_seconds}s`}</p>`).join("")}`;
  modal(type==="briefs"?"Original production brief":"Source inspection",`<div class="modal-content">${notice(type==="briefs"?`${item.evidence_status} · ${briefRenderState(item)} · Publication NOT_RUN`:item.source_status)}${(item.findings||[]).map(f=>notice(f,"warning")).join("")}${contents}<h3>Immutable history</h3>${item.versions.map(v=>`<details><summary>Version ${v.version} · ${esc(v.created)}</summary><pre>${json(v.data)}</pre><p class="app-mono">${esc(v.hash)}</p></details>`).join("")}<div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions">${button("Download production history","production-download",`data-id="${esc(id)}" data-type="${type}"`)} ${type==="briefs"?button("Revise brief","production-revise",`data-id="${esc(id)}"`):button("Correct inspection","production-inspect",`data-id="${esc(d.reference_id)}"`)}</div>`);
}

function productionAction(node) {
  if(node.dataset.action==="production-evidence")return evidenceForm(node.dataset.kind);
  if(node.dataset.action==="production-sources"){$("#modal").close();state.view="evidence";return render();}
  const id=node.dataset.id,handlers={"production-inspect":()=>inspectionForm(id),"production-analysis":()=>openProduction(id,"analyses"),"production-prepare":()=>briefForm(),"production-revise":()=>briefForm(id),"production-open":()=>openProduction(id,"briefs"),"production-download":()=>download(`${state.app}-production.json`,state.workspace[node.dataset.type].find(v=>v.id===id))};
  if(!handlers[node.dataset.action])throw new Error("Unknown production action");
  return handlers[node.dataset.action]();
}

function money(value,currency) {
  if(value===null || value===undefined) return "Unavailable";
  try {return new Intl.NumberFormat(undefined,{style:"currency",currency:currency || "USD"}).format(value/100);} catch {return `${value} minor units`;}
}
function percent(value) {return value===null || value===undefined?"Unavailable":`${(value*100).toFixed(1)}%`;}

function resultsView() {
  return WMMGrowthReview.panel(state)+WMMSubscriptionAuthoring.panel(state)+WMMCustomerWorkflow.panel(state)+measurementIntegrityPanel()+attributionPanel()+storekitPanel()+insightsPanel()+legacyResultsView();
}

function growthReviewServices() {
  return {state,modal,api,refresh,toast,openExperiment,uuid:()=>crypto.randomUUID(),FormData,document,
    close:()=>$("#modal").close(),pageReports:WMMPageReports,browser:window,ui:WMMGrowthReview};
}

function measurementIntegrityPanel() {
  const r=state.workspace.measurement_integrity||{state:"UNAVAILABLE",counts:null,rows:[],unallocated:[]};
  const counts=r.counts?Object.entries(r.counts).map(([name,count])=>`<span>${esc(label(name))}: <strong>${esc(count)}</strong></span>`).join(" · "):"Comparison unavailable";
  return `<section class="panel" aria-label="Financial evidence comparison"><h2>Do your payment records agree?</h2>${status(r.state)}<p>${counts}</p><p class="description">Compare imported cohort payments with current Stripe settlement evidence. Test payments stay separate. A financial match does not verify customer identity, cohort attribution or complete revenue.</p><div class="button-row">${button("Inspect payment comparison","measurement-inspect")}${r.sha256?button("Download comparison","measurement-download"):""}${button("Review connections","measurement-connections")}</div></section>`;
}

function measurementIntegrityInspect() {
  const r=state.workspace.measurement_integrity;
  const unavailable=!r || r.state==="UNAVAILABLE";
  const rows=(r?.rows||[]).map(row=>`<tr><td>${esc(row.cohort_id)}</td><td>${esc(row.type)}</td><td>${esc(row.currency)}</td><td>${esc(row.amount_minor)}</td><td>${esc(label(row.state))}</td></tr>`).join("");
  modal("Payment evidence comparison",`<div class="modal-content">${status(r?.state||"UNAVAILABLE")}<p>${esc(r?.scope||"Comparison unavailable. Refresh to retry.")}</p><p>${esc(r?.repair||"Review source connections.")}</p><p>Provider records without cohort counterparts: <strong>${esc(unavailable?"Unknown":r.unallocated.length)}</strong>. Withheld settlements: ${esc(r?.withheld_settlements??"Unknown")}. Pending receipts: ${esc(r?.pending_receipts??"Unknown")}.</p>${rows?`<div class="table-wrap"><table class="result-table"><thead><tr><th>Cohort</th><th>Event</th><th>Currency</th><th>Minor units</th><th>Comparison</th></tr></thead><tbody>${rows}</tbody></table></div>`:notice(unavailable?"Comparison unavailable; refresh or inspect the source history.":"No financial rows available for comparison.","warning")}<details><summary>Source fingerprints and financial identifiers</summary><pre>${json(r)}</pre></details></div><div class="modal-actions">${r?.sha256?button("Download comparison","measurement-download"):""}${button("Close comparison","close")}</div>`,"MEASUREMENT INTEGRITY");
}

function legacyResultsView() {
  const metrics=state.workspace.metrics;
  const cohort=metrics.cohorts.map(c=>c.status==="MEASURED"?`<section class="panel"><div class="section-heading"><h2>${esc(c.cohort_id)}</h2>${status(c.status)}</div><p class="description">${esc(c.horizon)} · ${esc(c.currency)} · supplied cohort evidence</p><div class="table-wrap"><table class="result-table"><thead><tr><th>Outcome</th><th>Observed value</th></tr></thead><tbody><tr><td>Eligible installs</td><td>${c.counts.installs}</td></tr><tr><td>Useful activation</td><td>${percent(c.activation_rate)}</td></tr><tr><td>Paid conversion</td><td>${percent(c.paid_conversion)}</td></tr><tr><td>Paid customer acquisition cost</td><td>${money(c.paid_cac_minor,c.currency)}</td></tr><tr><td>Contribution after acquisition</td><td>${money(c.contribution_after_acquisition_minor,c.currency)}</td></tr></tbody></table></div></section>`:notice(c.reason,"warning")).join("");
  return `${heading("Measure what matters","Useful activation, retained value and contribution—not manufactured growth.",button("Add a cohort","add-evidence",'data-kind="cohort"'))}${ledgerResults()}${notice("A zero denominator stays unavailable. Provider attribution and citation visibility are not proof of incremental revenue.")}${metrics.cohorts.length?cohort:state.workspace.ledger.length?notice("Event-derived acquisition results appear above. Manual summary worksheets are optional."):empty("No acquisition results yet","Import a mature cohort with its source, currency and complete costs. Until then, CAC and conversion remain unavailable.",button("Add cohort evidence","add-evidence",'data-kind="cohort"'))}<div class="section-heading"><h2>ASA & answer-engine visibility</h2>${button("Import worksheet","add-evidence",'data-kind="acquisition"')}</div>${metrics.acquisition.length?metrics.acquisition.map((result,i)=>`<section class="panel"><h3>Worksheet ${i+1}</h3>${result.asa?`<p>Advisory CPT ceiling: <strong>${money(result.asa.cpt_ceiling_minor,result.asa.currency)}</strong> · ${esc(result.asa.status)}</p>`:""}<details><summary>Inspect citation counts, inputs and scope</summary><pre>${json(result)}</pre></details></section>`).join(""):empty("Establish your search baseline","Capture app-specific query answers and source URLs, or supply mature Apple Ads counts. No keyword volume or citations are assumed.")}<div class="section-heading"><h2>Retained usefulness</h2></div>${metrics.retention.length?metrics.retention.map(r=>`<section class="panel"><h3>${esc(r.window)}</h3><p>${r.retained} / ${r.eligible} eligible · ${percent(r.rate)} ${r.mature?"":"— follow-up not mature"}</p></section>`).join(""):empty("Use the right value cadence","Choose a retention window that matches the useful outcome your app delivers.",button("Add retention evidence","add-evidence",'data-kind="retention"'))}`;
}

function ledgerResults() {
  const rows=state.workspace.ledger || [];
  const panels=rows.map(r=>`<section class="panel ledger-panel"><div class="section-heading"><h3>${esc(r.cohort.cohort_id)}</h3>${status(r.status)}</div><p class="description">${esc(r.cohort.release)} · ${esc(r.cohort.locale)} · ${r.events} imported events</p>${!r.mature?notice("Follow-up has not matured yet.","warning"):""}${!r.costs_complete?notice("Acquisition and delivery costs need explicit export rows, including zero-cost receipts.","warning"):""}${r.observability!=="OBSERVED"?notice("Attribution is partial or unknown; conversion and contribution remain inconclusive.","warning"):""}${r.issues.map(issue=>notice(issue,"warning")).join("")}<div class="table-wrap"><table class="result-table"><thead><tr><th>Event-derived outcome</th><th>Supplied result</th></tr></thead><tbody><tr><td>Eligible installs / activations / paid</td><td>${r.installs} / ${r.activated} / ${r.paid}</td></tr><tr><td>Paid conversion</td><td>${percent(r.paid_conversion)}</td></tr><tr><td>Net proceeds after refunds</td><td>${money(r.net_proceeds_minor,r.cohort.currency)}</td></tr><tr><td>Contribution after costs</td><td>${money(r.contribution_after_acquisition_minor,r.cohort.currency)}</td></tr></tbody></table></div><div class="toolbar">${button("Import event export","import-events",`data-id="${esc(r.cohort.cohort_id)}"`)}${button("CSV template","event-template")}${button("Download as-of report","ledger-report",`data-id="${esc(r.cohort.cohort_id)}"`)}${button("Earlier report","ledger-history",`data-id="${esc(r.cohort.cohort_id)}"`)}</div><details><summary>Observation contract, source and reconciliation details</summary><pre>${json(r)}</pre></details></section>`).join("");
  return `${paymentResultsPanel()}${outcomeLearningPanel()}${experimentResults()}<div class="section-heading"><h2>Reconciled event ledger</h2>${button("Define event cohort","define-cohort")}</div>${notice("Import permitted exports using opaque IDs only. Late refunds restate these cohorts. Imported files are not authenticated provider notifications.")}${rows.length?panels:empty("Start with a declared observation window","Define the app build, acquisition dates, follow-up maturity and attribution coverage. Then import a CSV or JSON export.",button("Set up event cohort","define-cohort"))}`;
}

function experimentResults() {
  const tests=state.workspace.experiments||[];
  const cards=tests.map(e=>{
    const latest=e.assessments.at(-1),decision=e.actions.filter(a=>a.data.operation==="decide").at(-1);
    return `<section class="panel experiment-panel"><div class="section-heading"><h3>${esc(e.data.name)}</h3>${status(e.state)}</div><p>${esc(e.data.hypothesis)}</p><p class="description">${esc(label(e.data.primary_metric))} · ${esc(e.data.assignment_method)} · analysis ${esc(new Date(e.data.analysis_at).toLocaleString())}</p><p>Approximate sample: ${e.data.sample_plan.control} control / ${e.data.sample_plan.treatment} treatment installs</p>${latest?`<p>Latest assessment: ${status(latest.data.status)} · decision ${status(e.decision_status)}</p>${latest.data.issues.map(i=>notice(i,"warning")).join("")}`:notice("No assessment recorded. Exposure and the fixed analysis date are required.")}${decision?`<p>Recorded decision: ${esc(label(decision.data.decision))}</p>`:""}${button("Inspect experiment","experiment-open",`data-id="${esc(e.id)}"`)}</section>`;
  }).join("");
  const worker=state.workspace.worker||{status:"NOT_STARTED"};
  return `<div class="section-heading"><h2>Experiments with a fixed learning window</h2>${button("Plan an experiment","experiment-create")}</div>${notice("Pre-register before acquisition begins. Compare supplied observations; launch, random assignment, publication and spending are separate actions.")}<p class="description">Local analysis worker: ${esc(label(worker.status))}${worker.last_success?` · last healthy poll ${esc(new Date(worker.last_success).toLocaleString())}`:""}</p>${worker.last_error?notice(worker.last_error,"error"):""}${tests.length?cards:empty("Turn a hypothesis into a bounded test","Choose two comparable event cohorts and reviewed creatives, declare the outcome, sample, dates and guardrails, then track exposure and decisions.",button("Register your first test","experiment-create"))}`;
}

function experimentSelect(name,title,choices) {
  return `<label class="field" for="field-${name}">${esc(title)}<select id="field-${name}" name="${name}" required><option value="">Choose…</option>${choices.map(([id,text])=>`<option value="${esc(id)}">${esc(text)}</option>`).join("")}</select></label>`;
}

function experimentForm() {
  const cohorts=(state.workspace.ledger||[]).map(r=>[r.cohort.cohort_id,`${r.cohort.cohort_id} · ${r.cohort.release} · ${r.cohort.locale}`]);
  const assets=state.workspace.records.filter(r=>r.kind==="asset"&&r.data.authentic&&r.data.rights_cleared).map(r=>[r.id,`${r.title} · ${r.data.release}`]);
  const fields=[field("name"),field("owner"),field("hypothesis","","textarea"),experimentSelect("primary_metric","Primary outcome",[["activation_rate","Useful activation"],["paid_conversion","Paid conversion"],["retention_rate","Retained value"]]),field("baseline_rate","","text","Fraction, e.g. 0.20; use a measured baseline"),field("minimum_detectable_effect","","text","Absolute fraction difference, e.g. 0.05"),field("treatment_allocation","0.50","text","Expected treatment fraction; between 0 and 1"),field("analysis_at","","text","Fixed ISO timestamp after both follow-up windows"),experimentSelect("assignment_method","Assignment evidence",[["RANDOMIZED","Supplied randomized assignment"],["OBSERVATIONAL","Observational comparison"]]),field("assignment_source","","text","Assignment receipt; randomization is not verified by this tool"),field("min_retention_rate","","text","Minimum retained-value fraction"),field("max_refund_fraction","","text","Maximum refund fraction; absent purchases stay unknown"),field("min_contribution_minor","","text","Minimum contribution in currency minor units; may be negative"),field("max_acquisition_minor","","number","Maximum acquisition cost per arm, minor units"),field("stop_rule","","textarea","When to stop collecting or repair; no automatic campaign action"),field("rollback_plan","","textarea","Exact prior creative/build and recovery path")];
  for(const arm of ["control","treatment"]) fields.push(experimentSelect(`${arm}_cohort`,`${label(arm)} event cohort`,cohorts),experimentSelect(`${arm}_asset`,`${label(arm)} reviewed creative`,assets));
  modal("Plan an experiment",`<form id="experiment-form" data-app="${esc(state.app)}"><div class="modal-content">${notice("Create both cohorts with identical release, locale, currency and dates. Acquisition must start in the future. Authentic, rights-cleared image files are verified again when registering.")}${!cohorts.length||!assets.length?notice("Define event cohorts and review creative assets before registering this test.","warning"):""}<div class="form-grid">${fields.join("")}</div><p id="sample-preview" role="status">Enter baseline, detectable effect and allocation to preview the approximate sample.</p><div class="field-error" id="form-error" role="alert"></div></div><div class="modal-actions"><button type="submit" class="button">Register immutable test</button></div></form>`,"EXPERIMENT PLANNING");
}

function samplePreview() {
  const form=$("#experiment-form");if(!form)return;
  const v=Object.fromEntries(new FormData(form)),b=Number(v.baseline_rate),d=Number(v.minimum_detectable_effect),f=Number(v.treatment_allocation);
  if(![b,d,f].every(x=>x>0&&x<1)||b+d>=1) {$("#sample-preview").textContent="Use valid fractions; baseline plus effect must be below 1.";return;}
  const p=b+d/2,n=p*(1-p)*(1/f+1/(1-f))*(1.96+0.841621)**2/d**2;
  $("#sample-preview").textContent=`Approximate minimum: ${Math.ceil(n*(1-f))} control / ${Math.ceil(n*f)} treatment installs. 95% interval, 80% power normal approximation; not proof of lift. Server validates the saved plan.`;
}

async function saveExperiment(form) {
  const data=Object.fromEntries(new FormData(form));
  data.manifest_version=Number(form.dataset.manifestVersion);
  for(const key of ["baseline_rate","minimum_detectable_effect","treatment_allocation"])data[key]=Number(data[key]);
  data.guardrails={};
  for(const key of ["min_retention_rate","max_refund_fraction","min_contribution_minor","max_acquisition_minor"]) {data.guardrails[key]=Number(data[key]);delete data[key];}
  for(const arm of ["control","treatment"]) {data[arm]={cohort_id:data[`${arm}_cohort`],asset_id:data[`${arm}_asset`]};delete data[`${arm}_cohort`];delete data[`${arm}_asset`];}
  await api(`/api/apps/${form.dataset.app}/experiments`,data);
}

function openExperiment(id) {
  const e=state.workspace.experiments.find(e=>e.id===id),latest=e.assessments.at(-1);
  const controls=e.state==="CANCELLED"?"":`${e.state==="PLANNED"?button("Record observed exposure","experiment-action",`data-id="${esc(id)}" data-operation="observe"`):button("Evaluate current evidence","experiment-evaluate",`data-id="${esc(id)}"`)}${latest?button("Record decision","experiment-action",`data-id="${esc(id)}" data-operation="decide"`):""}${e.state==="DECIDED"?button("Propose rollback","experiment-action",`data-id="${esc(id)}" data-operation="rollback"`):""}${button("Cancel test","experiment-action",`data-id="${esc(id)}" data-operation="cancel"`)}`;
  const effect=latest?.data.effect;
  const scheduled=experimentSchedulePanel(e);
  modal(e.data.name,`<div class="modal-content">${notice("Exposure receipts are operator reported. Rollback is a proposal, not a provider action. Re-evaluate after new imports: previous decisions may become stale.")}${status(e.state)} ${status(latest?.data.status||"NOT_EVALUATED")} ${status(e.decision_status)}<p>${esc(e.data.hypothesis)}</p>${effect?`<p>Descriptive difference: ${percent(effect.difference)} · 95% interval ${effect.interval.map(percent).join(" to ")}</p><p>${esc(effect.method)}</p>`:notice("No defensible comparison is available yet.","warning")}${latest?latest.data.issues.map(i=>notice(i,"warning")).join(""):""}${scheduled}<h3>Decision and recovery history</h3>${e.actions.map(a=>`<p><strong>${esc(label(a.data.operation))}</strong> · ${esc(a.data.reason||a.data.source)} · ${esc(a.created)}${a.data.operation==="rollback"?" · External rollback NOT RUN":""}</p>`).join("")||"<p>No lifecycle actions recorded.</p>"}<details><summary>Immutable plan, source hashes and all assessments</summary><pre>${json(e)}</pre></details><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions">${controls}${button("Download experiment","experiment-download",`data-id="${esc(id)}"`)}</div>`,"EXPERIMENT EVIDENCE");
}

function experimentActionForm(id,operation) {
  const e=state.workspace.experiments.find(e=>e.id===id);
  const fields={observe:[field("source","","text","Actual exposure receipt; no secrets"),field("observed_at","","text","Actual ISO timestamp inside the acquisition window")],decide:[experimentSelect("decision","Decision",[["COLLECT","Collect more evidence"],["REPAIR","Repair the identified cause"],["STOP","Stop this test"],["NEXT_TEST","Propose next bounded test"]]),field("reason","","textarea")],cancel:[field("reason","","textarea","Cancellation leaves all existing evidence intact")],rollback:[field("target","","text","Exact prior creative/build"),field("source","","text","Evidence supporting rollback"),field("reason","","textarea")]};
  modal(label(operation),`<form id="experiment-action-form" data-app="${esc(state.app)}" data-id="${esc(id)}" data-operation="${operation}" data-version="${e.version}" data-assessment="${esc(e.assessments.at(-1)?.hash||"")}"><div class="modal-content">${notice(operation==="rollback"?"This records a rollback proposal only. No build, campaign or store listing is changed.":"This records a local evidence-based action. No campaign, publication or spending will execute.")}<div class="form-grid">${fields[operation].join("")}</div><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button type="submit" class="button">Save ${esc(operation)}</button></div></form>`);
}

async function saveExperimentAction(form) {
  const data={...Object.fromEntries(new FormData(form)),operation:form.dataset.operation,version:Number(form.dataset.version)};
  if(data.operation==="decide")data.assessment_hash=form.dataset.assessment;
  await api(`/api/apps/${form.dataset.app}/experiments/${form.dataset.id}/actions`,data);
}

async function handleExperiment(node) {
  const id=node.dataset.id,action=node.dataset.action;
  if(action==="experiment-create")return experimentForm();
  if(action==="experiment-open")return openExperiment(id);
  if(action==="experiment-action")return experimentActionForm(id,node.dataset.operation);
  if(action==="experiment-schedule")return experimentScheduleForm(id);
  if(action==="experiment-download")return download(`${state.app}-experiment.json`,state.workspace.experiments.find(e=>e.id===id));
    const result=await api(`/api/apps/${state.app}/experiments/${id}/evaluate`,{});
  await refresh();openExperiment(id);
  if(result.status==="AWAITING_ANALYSIS")toast(`Analysis waits until ${new Date(result.analysis_at).toLocaleString()}. No early result recorded.`);
}

function experimentSchedulePanel(e) {
  const schedule=state.workspace.schedules?.find(s=>s.experiment_id===e.id);
  const active=e.state!=="PLANNED"&&e.state!=="CANCELLED";
  return `<section class="panel schedule-panel"><h3>Automatic evidence analysis</h3>${schedule?`<p>${status(schedule.status)} · every ${schedule.interval_hours} hours · failures ${schedule.failures} / 3</p><p class="description">Next due ${esc(new Date(schedule.next_due).toLocaleString())}${schedule.last_job_status?` · latest job ${esc(label(schedule.last_job_status))}`:""}</p>`:"<p>Disabled until you explicitly configure it.</p>"}${notice("Runs while this local Mission Control service is open. Pausing cancels queued analysis; running local assessment may finish. No campaign, publication or spending executes.")}${active?button(schedule?.enabled?"Configure or pause analysis":"Enable automatic analysis","experiment-schedule",`data-id="${esc(e.id)}"`):notice("Record exposure before scheduling; cancelled experiments remain stopped.")}${schedule?.last_job?button("Inspect scheduled run","job",`data-id="${esc(schedule.last_job)}"`):""}</section>`;
}

function experimentScheduleForm(id) {
  const schedule=state.workspace.schedules?.find(s=>s.experiment_id===id);
  modal("Automatic evidence analysis",`<form id="experiment-schedule-form" data-app="${esc(state.app)}" data-id="${esc(id)}" data-version="${schedule?.version||""}"><div class="modal-content">${notice("Enable local assessment only. The first run waits for the fixed analysis date. Three operational failures pause the schedule; resume after inspecting the cause. Restored snapshots require explicit enable.")}<div class="form-grid">${field("enabled",schedule?.enabled??false,"boolean")}${field("interval_hours",schedule?.interval_hours||24,"number","Whole hours, from 1 through 168")}</div><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button type="submit" class="button">Save analysis schedule</button></div></form>`);
}

async function saveExperimentSchedule(form) {
  const data=Object.fromEntries(new FormData(form));
  await api(`/api/apps/${form.dataset.app}/experiments/${form.dataset.id}/schedule`,{enabled:data.enabled==="true",interval_hours:Number(data.interval_hours),version:form.dataset.version?Number(form.dataset.version):null});
}

function cohortForm() {
  const app=state.workspace.app.data;
  const fields=[field("cohort_id","","text","New immutable cohort ID; corrections need a new ID"),field("release",app.release),field("platform"),field("locale",app.locale),field("currency",app.currency),field("starts_at","","text","Acquisition start, ISO timestamp with timezone"),field("ends_at","","text","Acquisition end, ISO timestamp with timezone"),field("matures_at","","text","Follow-up maturity, ISO timestamp with timezone"),field("attribution_method"),field("source","","text","Observation contract/export receipt; no secrets")];
  const observable=`<label class="field" for="field-observability">Observation coverage<select id="field-observability" name="observability"><option value="UNKNOWN">Unknown</option><option value="PARTIAL">Partial or privacy suppressed</option><option value="OBSERVED">Observed under the documented contract</option></select></label>`;
  modal("Define event cohort",`<form id="cohort-form"><div class="modal-content">${notice("Definitions and imported events are immutable. Use a fresh cohort for corrected boundaries; snapshots preserve the originals.")}<div class="form-grid">${fields.join("")}${observable}</div><div class="field-error" id="form-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit">Save event cohort</button></div></form>`);
}

function historicalForm(id) {
  modal("Reproduce an earlier report",`<form id="history-form" data-cohort="${esc(id)}"><div class="modal-content">${notice("Only events observed by this timestamp will count. Later refunds remain in the ledger and restate later reports.")}${field("as_of",new Date().toISOString(),"text","ISO timestamp with timezone; no future dates")}<div class="field-error" id="form-error" role="alert"></div></div><div class="modal-actions"><button type="submit" class="button">Inspect historical report</button></div></form>`);
}

function connectionsView() {
  return heading("Connect with clarity","Connect each app’s evidence, then verify actual access.")+googlePlayPanel()+socialPanel()+releaseInventoryPanel()+subscriptionPanel()+attributionPanel()+storekitPanel()+insightsPanel()+legacyConnectionsView();
}

function legacyConnectionsView() {
  return `${paymentSourcesPanel()}${notice("Protected keys stay with this Windows user and database. Exports contain connection metadata only. Publication and spending still require separate execution.")}<div class="connection-grid">${state.boot.providers.map(provider=>{
    const binding=state.workspace.records.find(r=>r.kind==="connection"&&r.data.provider===provider.id);
    const latest=binding?state.workspace.jobs.find(job=>job.action==="sync"&&job.data.connection_id===binding.id&&job.created>=binding.updated):null;
    const connectionInfo=state.workspace.connections?.[binding?.id];
    const protectedStatus=connectionInfo?.status;
    const cleanupNote=connectionInfo?.cleanup==="REMOVAL_PENDING"?notice("Protected key removal is still pending. Use Disconnect locally to finish cleanup; provider access remains disabled."):connectionInfo?.cleanup==="UNCONFIRMED"?notice("Local key cleanup could not be confirmed. Check protected storage, then use Disconnect locally; provider access remains disabled."):"";
    const unavailable=["DISCONNECTED","RECONNECT_REQUIRED","PROTECTED_STORAGE_UNAVAILABLE"].includes(protectedStatus);
    const connectionStatus=unavailable?protectedStatus:latest?.status==="SUCCEEDED"?"READ_SUCCEEDED":latest?.status==="BLOCKED"?"READ_BLOCKED":binding?"CONFIGURED_UNTESTED":"SETUP_NEEDED";
    return `<section class="connection-card"><span class="provider-mark" aria-hidden="true">${provider.id==="apple_ads"?"↗":provider.id==="app_store"?"A":"✦"}</span><h2>${esc(provider.name)}</h2><p>${esc(provider.description)}</p>${status(connectionStatus)}${cleanupNote}${button(binding&&!unavailable?"Test read access":"Set up connection",binding&&!unavailable?"sync":"provider",`data-id="${esc(binding&&!unavailable?binding.id:provider.id)}"`)}${binding?`<div class="toolbar">${button(provider.id==="app_store"?"Read customer reviews":"Get campaign report","provider-report",`data-id="${esc(binding.id)}" ${unavailable?"disabled":""}`)}</div>${button("Rotate or reconnect","provider",`data-id="${esc(provider.id)}"`)}${button("Disconnect locally","disconnect-connection",`data-id="${esc(binding.id)}"`)}`:""}${latest?button("Inspect latest read","job",`data-id="${esc(latest.id)}"`):""}</section>`;
  }).join("")}`;
}

function connectionSetup(providerId) {
  if(providerId==="aeo") return acquisitionForm("aeo");
  const binding=state.workspace.records.find(r=>r.kind==="connection"&&r.data.provider===providerId);
  const ads=providerId==="apple_ads";
  const guide=ads?"Register a P-256 public key in Apple Ads API settings. Copy the resulting team, client and key IDs, then upload the matching private PEM key here.":"In App Store Connect, open Users and Access → Integrations → App Store Connect API. Use a team API key, copy its issuer and key IDs, and upload the downloaded .p8 file. Individual keys use a different contract and are not accepted here.";
  const link=ads?"https://searchads.apple.com/":"https://appstoreconnect.apple.com/access/api";
  modal(ads?"Connect Apple Ads":"Connect App Store Connect",`<form id="connection-setup-form" data-provider="${esc(providerId)}" data-app="${esc(state.app)}" data-record="${esc(binding?.id||"")}" data-version="${binding?.version||""}"><div class="modal-content"><ol><li>${esc(guide)}</li><li>Enter the exact Store app ID${ads?" and ad account ID":""} for ${esc(state.workspace.app.data.name)}.</li><li>Save the protected key, then use Test read access. Saving does not prove provider access.</li></ol><p><a class="text-button" href="${link}" target="_blank" rel="noopener noreferrer">Open provider key settings ↗</a></p>${notice("The key is sent only to this local service and stored in Windows Credential Manager. It is excluded from exports and workspace records. Rotation retires the previous local key after the binding saves.")}<div class="form-grid">${field("store_app_id",binding?.data.store_app_id||state.workspace.app.data.store_app_id||"","text","Numeric App Store ID")}${ads?field("account_id",binding?.data.account_id||"","text","Numeric Apple Ads ad account ID; not the organization or team ID"):""}${field("issuer_id","","text",ads?"Team ID from Apple Ads":"Team issuer ID from App Store Connect")}${ads?field("client_id","","text","Client ID from Apple Ads"):""}${field("key_id","","text","ID of the uploaded private key")}<label class="field" for="private-key-file">Private key file<input id="private-key-file" name="key_file" type="file" accept=".p8,.pem" required autocomplete="off"><small>P-256 private key only. Upload again after an unsuccessful attempt; secret inputs are cleared.</small></label></div><div class="field-error" id="form-error" role="alert"></div></div><div class="modal-actions"><button type="submit" class="button">Save protected connection</button></div></form>`,"PROTECTED PROVIDER SETUP");
}

function disconnectForm(id) {
  const record=state.workspace.records.find(r=>r.id===id&&r.kind==="connection");
  modal("Disconnect this local connection",`<div class="modal-content">${notice("This removes the local protected key and disables new reads. It does not revoke the API key at Apple. Revoke it in provider settings if needed. Saved reports remain available.")}<div class="field-error" id="form-error" role="alert"></div></div><div class="modal-actions">${button("Keep connection","close")}${button("Remove local access","confirm-disconnect",`data-id="${esc(record.id)}" data-version="${record.version}"`)}</div>`);
}

async function saveConnection(form) {
  const values=Object.fromEntries(new FormData(form));
  const file=values.key_file;delete values.key_file;
  try {
    if(!file?.size||file.size>2000) throw new Error("Upload a private key file between 1 and 2000 bytes.");
    const data={...values,provider:form.dataset.provider,private_key:new TextDecoder("utf-8",{fatal:true}).decode(await file.arrayBuffer())};
    if(form.dataset.record) Object.assign(data,{id:form.dataset.record,version:Number(form.dataset.version)});
    const result=await api(`/api/apps/${form.dataset.app}/connections`,data);
    $("#modal").close();await refresh();toast(result.cleanup==="PRIOR_LOCAL_KEY_CLEANUP_REQUIRED"?"New connection saved; prior local key cleanup needs attention.":"Protected connection saved. Test read access to verify permissions.");
  } finally {form.querySelector('[name="key_file"]').value="";}
}

function researchView() {
  const ledger=state.research.ledger;
  const profile=state.research.acquisition.apps.find(app=>app.app_id===state.app);
  const sources=(ledger.other_notebooks || []).map(source=>`<section class="panel"><h3>${esc(source.title || source.name || source.artifact || "Saved research")}</h3><p class="description">${esc(source.review_scope || source.scope || "Selected saved artifact; review the evidence boundary.")}</p><details><summary>Inspect source and retained findings</summary><pre>${json(source)}</pre></details></section>`).join("");
  return `${heading("Research into useful action","Keep the source, question and actual product proof connected.")}${notice("Research findings are hypotheses, not product claims or guaranteed growth. The library records exactly what was reviewed.")}${spyTokPanel()}${spiraPanel()}${aeoPanel()}${acquisitionPanel()}${rankingPanel()}${productionPanel()}${renderingPanel()}<div class="section-heading"><h2>App-specific ASA / AEO intents</h2></div>${profile?`<div class="stage-grid">${profile.intent_clusters.map(cluster=>`<section class="panel"><p class="eyebrow">${esc(cluster.id)}</p><h3>${esc(cluster.aeo_seed)}</h3><p class="description">${esc(cluster.page_hypothesis)}</p><div class="details-list"><div class="detail-item"><strong>Apple Ads seed</strong>${esc(cluster.asa_seed)}</div><div class="detail-item"><strong>First-value event</strong>${esc(cluster.activation)}</div></div>${status("HYPOTHESIS")}</section>`).join("")}</div>`:empty("Define this app's first intent","Start with its researched user job, then map the search term, answer page, claim evidence and first-value event.")}<div class="section-heading"><h2>Source library</h2></div><section class="panel"><h3>Primary notebook</h3><p class="description">Your local source library starts empty. Add independently reviewed evidence for each app.</p><details><summary>Reviewed titles and coverage</summary><pre>${json(ledger.primary_notebook)}</pre></details></section><div class="section-heading"><h2>Additional saved research</h2></div><div class="stage-grid">${sources}</div>`;
}

function activityView() {
  const w=state.workspace;
  return `${heading("Every action leaves a trail","Inspect saved runs, review packets and the history of this app workspace.")}${verifiedReviewPanel()}${providerActionsPanel()}${notice("Legacy local-name packets below are manual bookkeeping. They cannot establish verified identity or authorize provider execution.")}<div class="section-heading"><h2>Manual review history</h2>${button("Prepare review packet","prepare-review")}</div>${w.approvals.length?`<div class="record-list">${w.approvals.map(r=>`<button class="record-row" data-action="review" data-id="${esc(r.id)}"><span class="record-icon" aria-hidden="true">✓</span><span class="record-main"><strong>${esc(r.packet.record.title)}</strong><small>Prepared by ${esc(r.preparer)} · expires ${esc(new Date(r.expires).toLocaleString())}</small></span>${status(r.status)}</button>`).join("")}</div>`:empty("Nothing waiting for review","Add a distribution, store or experiment record, then freeze its exact contents into a review packet.")}<div class="section-heading"><h2>Saved runs</h2></div>${w.jobs.length?`<div class="record-list">${w.jobs.map(job=>`<button class="record-row" data-action="job" data-id="${esc(job.id)}"><span class="record-icon" aria-hidden="true">↻</span><span class="record-main"><strong>${job.action==="agent_run"?"Agent campaign draft":job.action==="resolution"?"Agent evidence resolution":job.action==="pipeline"?"Pipeline preparation":job.action==="experiment"?"Experiment analysis":"Provider synchronization"}</strong><small>${esc(new Date(job.created).toLocaleString())} · attempt ${job.attempts}</small></span>${status(job.status)}</button>`).join("")}</div>`:empty("Your first run starts the trail","Prepare the pipeline to save app-scoped packets and exact missing-input checklists.",button("Prepare the pipeline","run-all"))}<div class="section-heading"><h2>Workspace history</h2></div>${w.audit.length?`<div class="record-list">${w.audit.slice(0,20).map(entry=>`<div class="record-row"><span class="record-main"><strong>${esc(label(entry.action.replaceAll("."," ")))}</strong><small>${esc(new Date(entry.created).toLocaleString())}</small></span><span class="app-mono">#${entry.id}</span></div>`).join("")}</div>`:notice("No workspace changes have been recorded yet.")}`;
}

function modal(title,html,eyebrow="WORKSPACE") {
  WMMAgentControl.clear();
  WMMCompleteAutomation.clear();
  $("#modal-title").textContent=title;$("#modal-eyebrow").textContent=eyebrow;$("#modal-body").innerHTML=html;
  $("#modal-body").insertAdjacentHTML("afterbegin",WMMStories.dialog(title,html));
  automationAttach();
  if(!$("#modal").open) $("#modal").showModal();
}

function openStage(id) {
  const s=state.workspace.stages.find(item=>item.id===Number(id));
  if(s.missing.length&&resolutionIssues(s.id).length)return openResolutionStage(s.id);
  const checklist=s.missing.length?s.missing.map(m=>`<div class="detail-item blocked-item">${esc(m)}</div>`).join(""):notice("The supplied inputs meet this local stage's checks. Review the packet before external action.");
  modal(s.title,`<div class="modal-content"><p class="description">${esc(s.description)}</p><div class="details-list">${checklist}</div><h3>What to do</h3><ol>${s.operations.tasks.map(task=>`<li>${esc(task)}</li>`).join("")}</ol><p><strong>Deliverable:</strong> ${esc(s.operations.deliverable)}</p><p><strong>How to verify:</strong> ${esc(s.operations.verify)}</p><h3>Evidence for this stage</h3><div class="toolbar">${s.inputs.filter(k=>k!=="manifest").map(k=>button(`＋ ${state.boot.labels[k]}`,"add-evidence",`data-kind="${esc(k)}"`)).join("")}${s.id===1?button("Edit app setup","edit-app"):""}</div><details><summary>Dependencies and evidence boundary</summary><p class="description">${s.dependencies.length?`Stages ${s.dependencies.join(", ")} must meet their input checks.`:"This is the starting stage."} Operator-reported readiness is separate from provider approval and public availability.</p></details></div><div class="modal-actions">${button("Prepare this stage","run-stage",`data-id="${s.id}"`,"")}</div>`,`STAGE ${String(s.id).padStart(2,"0")} / ${s.group.toUpperCase()}`);
}

function field(name,value="",type="text",hint="",mandatory=true) {
  const id=`field-${name}`, title=label(name);
  let input=`<input id="${id}" name="${esc(name)}" value="${esc(value)}" ${type==="number"?'type="number" min="0" step="1"':type==="date"?'type="date"':'type="text"'} required>`;
  if(type==="boolean") input=`<select id="${id}" name="${esc(name)}" required><option value="">Choose…</option><option value="true" ${value===true?"selected":""}>Yes</option><option value="false" ${value===false?"selected":""}>No</option></select>`;
  if(type==="textarea"||type==="json") input=`<textarea id="${id}" name="${esc(name)}" class="${type==="json"?"json-field":""}" required>${esc(type==="json"&&typeof value==="object"?JSON.stringify(value,null,2):value)}</textarea>`;
  if(!mandatory) input=input.replaceAll(" required","");
  return `<label class="field ${type==="textarea"||type==="json"?"full":""}" for="${id}">${esc(title)}${input}${hint?`<small>${esc(hint)}</small>`:""}</label>`;
}

function appForm(isNew=false) {
  if(!isNew&&!currentWorkspace())return toast("Wait for this app to load, then reopen setup.");
  const app=isNew?{id:"",data:{},version:null}:state.workspace.app;
  const fields=[field("id",app.id,"text","Lowercase, unique workspace ID; cannot be renamed"),field("name",app.data.name),field("job",app.data.job,"textarea"),field("audience",app.data.audience),field("activation",app.data.activation),field("release",app.data.release,"text","Exact version/build being promoted"),field("locale",app.data.locale,"text","For example en-US; only use a tested locale"),field("currency",app.data.currency,"text","Optional until economics are supplied",false),field("website",app.data.website,"text","Optional public app website",false)];
  fields.push(...["brand_voice","brand_visual","brand_source","brand_boundaries"].map(key=>field(key,app.data[key]||"","textarea","Optional operator-supplied brand guidance; use a source and avoid unsupported promises",false)));
  fields.push(automationPreferenceFields(app.data));
  fields.push(field("store_app_id",app.data.store_app_id||"","text","Optional numeric App Store app ID; required for subscription catalog reads",false));
  fields.push(field("android_package",app.data.android_package||"","text","Optional Android application ID. Google Play setup can discover it from your project metadata.",false));
  fields.push(field("android_track",app.data.android_track||"","text","Set with the Android package, for example production or internal. Changes invalidate prior read scope.",false));
  fields.push(field("social_callback_base_url",app.data.social_callback_base_url||"","text","Optional verified HTTPS relay origin. Prefills official social callbacks; Mission Control stays private.",false));
  modal(isNew?"Add your app":"App setup",`<form id="app-form" data-new="${isNew}"><div class="modal-content">${notice("This creates an isolated growth workspace. It does not change your app, pricing or production accounts.")}<div class="form-grid">${fields.join("")}</div><div class="field-error" id="form-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit">Save app setup</button></div></form>`);
  if(!isNew) $("#field-id").readOnly=true;
  if(!isNew) $("#app-form .modal-content").insertAdjacentHTML("afterbegin",`<section class="panel"><h3>Let the agent collect app details</h3><p>Read the saved public website, compare its suggestions and approve only the fields you want to change.</p>${button("Discover app details","setup-open")}</section>`);
}

const booleanFields=new Set(["authentic","rights_cleared","consent_review","refund_reconciliation","installed","fresh_install","signed_out","restore_tested","trial_eligibility_tested","mature","confirmed"]);
const numberFields=new Set(["p0_count","price_minor","budget_minor","daily_cap_minor","eligible","retained","installs","activated","paid","acquisition_cost_minor","net_proceeds_minor","delivery_cost_minor","refunds_minor","amount_minor","rating"]);
const longFields=new Set(["claim","hypothesis","guardrails","change","heldout_test","rollback","fallback"]);

function evidenceForm(kind="readiness",record=null,preset={}) {
  if(kind==="acquisition"&&!record) return acquisitionForm("asa");
  const data=record?.data || preset;
  const options=Object.entries(state.boot.labels).map(([key,value])=>`<option value="${esc(key)}" ${key===kind?"selected":""}>${esc(value)}</option>`).join("");
  const fields=state.boot.fields[kind].filter(name=>kind!=="readiness"||name!=="result").map(name=>{
    const type=name==="analysis"?"json":booleanFields.has(name)?"boolean":numberFields.has(name)?"number":longFields.has(name)?"textarea":"text";
    let value=data[name] ?? "";
    if(name==="release"&&!value) value=state.workspace.app.data.release || "";
    if(name==="locale"&&!value) value=state.workspace.app.data.locale || "";
    if(name==="checked_at"&&!value) value=new Date().toISOString();
    const hint=name==="result"?"Use PASS only after the stated checks pass; otherwise FAIL or NOT_RUN":name==="availability"?"AVAILABLE requires a current public readback":name==="env_ref"?"Variable name only. Never paste a token.":"";
    return field(name,value,type,hint);
  });
  modal(record?"Inspect and update evidence":"Add evidence",`<form id="evidence-form" data-kind="${esc(kind)}" data-id="${esc(record?.id || "")}"><div class="modal-content"><div class="form-grid"><label class="field full" for="evidence-kind">Evidence type<select id="evidence-kind">${options}</select></label>${field("title",record?.title || "")}${field("source",record?.source || "","text","Receipt, report, test path or public URL; no secrets")}${fields.join("")}</div>${record?`<details><summary>Source hash and version</summary><p class="app-mono">${esc(record.hash)} · version ${record.version}</p></details>`:""}<div class="field-error" id="form-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit">Save evidence</button></div></form>`);
  if(kind==="readiness") {
    $("#form-error").insertAdjacentHTML("beforebegin",journeyFields(data));
    wireJourneys(data);
  }
  if(record) $("#evidence-kind").disabled=true;
  if(kind==="asset") $("#modal-body .modal-content").insertAdjacentHTML("afterbegin",notice("Upload the actual PNG/JPEG first. Authenticity and rights are human review assertions; a file hash alone does not prove either."));
}

function acquisitionForm(mode) {
  const types=`<label class="field full" for="worksheet-mode">Worksheet type<select id="worksheet-mode"><option value="asa" ${mode==="asa"?"selected":""}>Apple Ads bid worksheet</option><option value="aeo" ${mode==="aeo"?"selected":""}>Answer-engine observation</option></select></label>`;
  const asa=[field("cohort_id"),field("currency",state.workspace.app.data.currency),field("taps","","number"),field("paid","","number"),field("contribution_per_payer_minor","","number","Refund-adjusted contribution in cents or the currency's minor units"),field("contribution_horizon","","text","For example D30; use a mature measured horizon"),field("acquisition_share","","text","Fraction 0 to 1 for acquisition allocation"),field("non_media_cost_per_tap_minor","","number"),field("owner_cpt_cap_minor","","number","Planning ceiling; this does not authorize spending"),field("mature","","boolean"),field("counts_verified","","boolean"),field("contribution_verified","","boolean")];
  const aeo=[field("engine","","text","Record the actual engine/API and search mode"),field("locale",state.workspace.app.data.locale),field("query_id"),field("observation_id",crypto.randomUUID()),field("observed_at",new Date().toISOString()),field("mention","","boolean"),field("citation","","boolean"),field("correct_citation","","boolean","Yes only after inspecting whether the cited source backs the claim"),field("citation_url","","text","Public HTTPS source when a citation exists",false)];
  modal("Add ASA / AEO evidence",`<form id="evidence-form" data-kind="acquisition" data-worksheet="${mode}" data-id=""><div class="modal-content">${notice("This worksheet uses your supplied evidence. It does not verify the provider, authorize bids or claim rankings.")}<div class="form-grid">${types}${field("title")}${field("source","","text","Report or captured-answer receipt; no secrets")}${(mode==="asa"?asa:aeo).join("")}</div><div class="field-error" id="form-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit">Save and calculate worksheet</button></div></form>`);
}

function openRecord(id) {
  const record=state.workspace.records.find(r=>r.id===id);
  evidenceForm(record.kind,record);
  if(record.kind==="asset"&&record.data.file_id) $("#modal-body .modal-content").insertAdjacentHTML("afterbegin",`<img class="asset-preview" src="/api/apps/${encodeURIComponent(state.app)}/files/${encodeURIComponent(record.data.file_id)}" alt="Uploaded asset: ${esc(record.title)}">`);
}

function openProvider(id) {
  const provider=state.boot.providers.find(p=>p.id===id);
  if(id==="aeo") return acquisitionForm("aeo");
  modal(`Connect ${provider.name}`,`<div class="modal-content">${notice("Connection tests only read data; no campaign or metadata writes occur.")}<p class="description">${esc(provider.setup)}</p><div class="details-list"><div class="detail-item"><strong>1. Prepare the credential on your server</strong><p>Use an app-specific environment variable beginning GROWTH_${esc(state.app.toUpperCase().replaceAll("-","_"))}_ . Restart Mission Control after changing its environment.</p></div><div class="detail-item"><strong>2. Save the binding</strong><p>Enter the variable name, the exact organization/account ID and this app's Store ID.</p></div><div class="detail-item"><strong>3. Test read access</strong><p>Inspect the saved provider response. A configured binding alone is not a working connection.</p></div></div></div><div class="modal-actions">${button("Enter connection details","add-connection",`data-id="${esc(id)}"`,"")}</div>`);
}

async function queue(action,data) {
  const app=state.app;
  const job=await api(`/api/apps/${app}/jobs`,{action,data,request_key:crypto.randomUUID()});
  if(state.app!==app)return;
  toast("Run saved. Its result will appear in Activity.");await refresh();
  if(state.app!==app)return;
  openJob(job.id);
  pollJob(job.id);
}

async function pollJob(id) {
  const app=state.app;
  for(let attempt=0;attempt<40;attempt++) {
    await new Promise(resolve=>setTimeout(resolve,750));
    if(!state.workspace.jobs.some(j=>j.id===id)) return;
    await refresh();
    if(state.app!==app)return;
    const job=state.workspace.jobs.find(j=>j.id===id);
    if(!job)return;
    if($("#modal").open && $("#modal-body").dataset.job===id) openJob(id);
    if(!["QUEUED","RUNNING"].includes(job.status)) {toast(job.status==="SUCCEEDED"?"Run finished. Inspect each stage's result.":"Run needs attention. Its reason is saved.");return;}
  }
  toast("Run is still pending. Check Activity for its saved state.");
}

function currentInventoryRun(job,binding) {
  return job.status==="SUCCEEDED"&&job.action==="sync"&&!job.data.options&&job.app_id===state.app&&job.data.connection_id===binding.id&&job.data.connection_version===binding.version;
}

function verifiedCampaignInventory(binding) {
  const job=state.workspace.jobs.find(item=>currentInventoryRun(item,binding));
  const result=job?.result;
  if(result?.api_version!=="PLATFORM_V1"||result.app_id!==state.app||result.store_app_id!==binding.data.store_app_id||result.account_id!==binding.data.account_id)return null;
  const rows=result.payload?.data;
  if(!Array.isArray(rows)||rows.length>100)return null;
  if(rows.some(row=>!row||row.promotedObjectType!=="APPSTORE_APP"||String(row.promotedObjectId)!==binding.data.store_app_id||String(row.adAccountId)!==binding.data.account_id||!/^\d{1,30}$/.test(String(row.id))))return null;
  if(!Number.isInteger(result.payload.total_count)||result.payload.total_count<rows.length)return null;
  if(!["COMPLETE","PARTIAL"].includes(result.coverage))return null;
  if((result.coverage==="COMPLETE")!==(result.payload.total_count===rows.length))return null;
  return result;
}

function campaignPicker(binding) {
  const inventory=verifiedCampaignInventory(binding);
  if(!inventory)return notice("Use Test read access to load a saved campaign list, or enter known IDs below. Every report checks current app and account scope again.");
  const rows=inventory.payload.data;
  if(!rows.length)return notice("The saved access check found no campaigns for this app. This does not prove ad eligibility or delivery. You can enter a known ID for a fresh scoped read.");
  const options=rows.map(row=>`<option value="${esc(String(row.id))}">${esc(String(row.id))} — ${esc(typeof row.name==="string"?row.name:"Campaign "+row.id)}</option>`).join("");
  return `<section class="notice"><p>Saved access check: ${esc(inventory.observed_at)}. Showing ${rows.length} of ${esc(String(inventory.payload.total_count))} campaigns. ${inventory.coverage==="PARTIAL"?"This is a partial list; use known IDs for other campaigns.":"The saved page was complete."} A report rechecks current scope.</p><label class="field" for="verified-campaign">Choose a saved campaign<select id="verified-campaign"><option value="">Choose a campaign…</option>${options}</select></label><button type="button" class="button secondary" id="add-verified-campaign" disabled>Add campaign to report</button></section>`;
}

function wireCampaignPicker() {
  const picker=$("#verified-campaign"),add=$("#add-verified-campaign");
  if(!picker||!add)return;
  picker.addEventListener("change",()=>{add.disabled=!picker.value;});
  add.addEventListener("click",()=>{
    const input=$("#field-campaign_ids");
    const ids=[...new Set(input.value.split(",").map(value=>value.trim()).filter(Boolean))];
    if(!ids.includes(picker.value))ids.push(picker.value);
    if(ids.length>20){$("#form-error").textContent="Choose at most 20 distinct campaign IDs per report.";return;}
    input.value=ids.join(",");$("#form-error").textContent="";
  });
}

function releaseInventoryPanel() {
  const release=state.workspace.release_inventory;
  const binding=state.workspace.records.find(r=>r.kind==="connection"&&r.data.provider==="app_store"&&r.data.auth_mode!=="disconnected");
  if(!release||release.state==="NOT_APPLICABLE")return "";
  const selected=release.selection;
  const action=binding?button("Inspect App Store release","release-inventory",`data-id="${esc(binding.id)}"`):button("Connect App Store Connect","provider",'data-id="app_store"');
  return `<section class="panel" id="release-inventory-panel" aria-labelledby="release-inventory-heading"><h2 id="release-inventory-heading">Release being promoted</h2>${status(release.state)}<p>${esc(release.reason)}</p>${selected?`<p>Apple ${esc(selected.version)} · build ${esc(selected.build_number||"not selected")} · ${esc(selected.locale)}<br><small>Local release: ${esc(selected.local_release)}</small></p>`:""}<p class="description">A complete inventory is one prerequisite. Public availability, screenshot authenticity and billing need separate proof.</p><div class="toolbar">${action}${release.job_id?button("Inspect selected-release read","job",`data-id="${esc(release.job_id)}"`):""}</div></section>`;
}

function releaseForm(id,saved=null) {
  const binding=state.workspace.records.find(r=>r.id===id&&r.kind==="connection"&&r.data.provider==="app_store");
  if(!binding||binding.data.auth_mode==="disconnected")throw new Error("Reconnect this app's App Store connection first.");
  const job=state.workspace.jobs.find(j=>currentInventoryRun(j,binding)),result=job?.result;
  const owned=result?.provider==="app_store"&&result.app_id===state.app&&String(result.payload?.data?.id)===binding.data.store_app_id;
  const versions=owned&&Array.isArray(result.payload.included)?result.payload.included.filter(r=>r.type==="appStoreVersions"&&/^[A-Za-z0-9-]{1,80}$/.test(r.id)&&r.attributes):[];
  const choices=versions.map(r=>`<option value="${esc(r.id)}" ${saved?.version_id===r.id?"selected":""}>${esc(r.attributes.versionString)} · ${esc(r.attributes.platform)} · ${esc(label(r.attributes.appStoreState))}</option>`).join("");
  modal("Inspect App Store release",`<form id="release-inventory-form" data-app="${esc(state.app)}" data-connection="${esc(id)}" data-version="${binding.version}"><div class="modal-content">${notice("Read-only inspection of metadata and screenshot file inventory. This does not submit, approve or change your app.")}${owned?`<p>Version list observed ${esc(result.observed_at)}. The read will verify ownership again.</p>`:notice("Test read access to load this app's version list, or enter a known release ID below.")}<label class="field" for="release-version">Select a release<select id="release-version" name="version_id"><option value="">Choose a version</option>${choices}</select></label><details><summary>Use a known release ID</summary><label class="field" for="release-manual">App Store version resource ID<input id="release-manual" name="manual_version_id" autocomplete="off" maxlength="80" value="${esc(saved?.version_id&&!versions.some(r=>r.id===saved.version_id)?saved.version_id:"")}"></label></details><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit">Read release inventory</button></div></form>`);
}

function releaseResult(report) {
  const job=state.workspace.jobs.find(row=>row.status==="SUCCEEDED"&&row.result===report);
  const select=job?button("Use this release for promotion","release-select",`data-id="${esc(job.id)}"`):"";
  const locales=report.locales.map(row=>`<details><summary>${esc(row.locale||"Locale not supplied")} · ${esc(row.coverage)} · ${row.screenshot_sets.reduce((n,s)=>n+s.screenshots.length,0)} files observed</summary>${row.missing_fields.length?notice("Missing metadata: "+row.missing_fields.join(", "),"warning"):""}${row.screenshot_sets.length?row.screenshot_sets.map(set=>`<h3>${esc(set.display_type||"Display type not supplied")} · ${esc(set.coverage)}</h3><ol>${set.screenshots.map(file=>`<li><strong>${esc(file.filename||"Filename unavailable")}</strong> · ${esc(file.delivery_state||"Delivery not supplied")} · ${esc(file.width??"?")} × ${esc(file.height??"?")}<small>Checksum: ${esc(file.checksum||"Unavailable")}</small></li>`).join("")}</ol>`).join(""):notice("No screenshot sets observed; partial coverage does not prove there are none.")}<details><summary>Observed metadata</summary><pre>${json(row.metadata)}</pre></details></details>`).join("");
  return `${status(report.coverage)}<h3>Version ${esc(report.version)} · ${esc(report.platform)}</h3><p>${esc(label(report.review_state||"Not supplied"))} · Build ${esc(report.build?.number||"not selected / unavailable")}</p><p>Observed ${esc(report.observed_at)} · ${report.requests} source requests</p>${notice(report.interpretation)}${select}${report.coverage==="PARTIAL"?notice("Some resources were not inspected. Do not treat this as a complete release check.","warning"):""}${locales||notice("No localizations were returned.","warning")}<details><summary>Exact inventory and source hashes</summary><pre>${json(report)}</pre></details>`;
}

async function selectPromotionRelease(node) {
  const app=state.app,job=state.workspace.jobs.find(row=>row.id===node.dataset.id),report=job?.result;
  if(!job||!report||report.operation!=="release_inventory")throw new Error("Reopen a current saved release inventory.");
  const body={manifest_version:state.workspace.app.version,connection_id:job.data.connection_id,connection_version:job.data.connection_version,job_id:job.id,report_hash:report.source_hash};
  node.disabled=true;
  try {
    await api(`/api/apps/${encodeURIComponent(app)}/release-selection`,body);
    if(state.app!==app)return;
    await refresh();$("#modal").close();state.view="connections";render();
    $("#release-inventory-panel").scrollIntoView({block:"start"});toast("Promotion release saved locally. Review the current prerequisites.");
  }finally{node.disabled=false;}
}

function reportForm(id,saved=null) {
  const binding=state.workspace.records.find(r=>r.id===id);
  if(!binding)throw new Error("This connection is unavailable. Reconnect from this app workspace.");
  if(binding.data.provider==="app_store"&&saved?.operation==="release_inventory")return releaseForm(id,saved);
  if(binding.data.provider==="app_store") return queue("sync",{connection_id:id,options:{operation:saved?.operation==="subscription_catalog"?"subscription_catalog":"reviews"}});
  const end=new Date(),start=new Date(end);start.setUTCDate(start.getUTCDate()-7);
  const reports={campaign_report:"Campaign report",keyword_report:"Keyword report",search_term_report:"Search-term report"};
  const choices=`<label class="field" for="field-operation">Report type<select id="field-operation" name="operation">${Object.entries(reports).map(([key,title])=>`<option value="${key}" ${saved?.operation===key?"selected":""}>${title}</option>`).join("")}</select></label>`;
  modal("Read Apple Ads report",`<form id="provider-report-form" data-app="${esc(state.app)}" data-connection="${esc(id)}" data-version="${binding.version}"><div class="modal-content">${notice("Selected campaigns must belong to this exact app and ad account. This read cannot change a campaign or spend money.")}<p id="report-timezone" role="status"></p>${campaignPicker(binding)}<div class="form-grid">${choices}${field("campaign_ids",saved?.campaign_ids?.join(",")||"","text","Separate 1–20 numeric IDs with commas")}${field("start",saved?.start||start.toISOString().slice(0,10),"date","Calendar date in the selected reporting timezone; last 90 days")}${field("end",saved?.end||end.toISOString().slice(0,10),"date","Calendar date in the selected reporting timezone; no future dates")}</div><div class="field-error" id="form-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit">Read campaign report</button></div></form>`);
  const update=()=>{const name=$("#field-operation").value;$("#provider-report-form [type=submit]").textContent="Read "+reports[name].toLowerCase();$("#report-timezone").textContent=name==="search_term_report"?"Account reporting timezone (ORTZ). Low-volume terms may be suppressed or aggregated; fetched rows are not total demand.":"UTC reporting window. Provider-attributed installs do not prove paid customers.";};
  $("#field-operation").addEventListener("change",update);update();wireCampaignPicker();
}

function providerResult(result) {
  if(result.operation==="release_inventory")return releaseResult(result);
  if(result.operation==="subscription_catalog")return subscriptionResult(result);
  if(!Array.isArray(result.rows)) return `<pre>${json(result)}</pre>`;
  const review=result.operation==="reviews";
  const keyword=result.operation==="keyword_report",search=result.operation==="search_term_report";
  const rows=result.rows.map(r=>review?`<tr><td>${esc(r.rating)} / 5</td><td><strong>${esc(r.title)}</strong><p>${esc(r.body)}</p><small>${esc(r.createdDate)} · ${esc(r.territory)}</small></td></tr>`:`<tr><td>${esc(search?r.metadata.searchTermText:keyword?r.metadata.text:r.metadata.name || r.metadata.id)}${keyword||search?`<small>Campaign ${esc(r.metadata.campaignId)} · ${esc(keyword?r.metadata.matchType:r.metadata.keyword?.text||"No targeting keyword supplied")}</small>`:""}</td><td>${esc(r.totalMetrics.taps ?? "Unavailable")}</td><td>${esc(r.totalMetrics.totalInstalls ?? "Unavailable")}</td><td>${esc(r.totalMetrics.localSpend?.amount ?? "Unavailable")} ${esc(r.totalMetrics.localSpend?.currency || "")}</td></tr>`).join("");
  return `${status(result.coverage)}${notice(result.interpretation,result.coverage==="PARTIAL"?"warning":"info")}<p>${result.rows.length} observed rows · ${result.pages} fetched pages${result.reporting_timezone?` · ${esc(result.reporting_timezone)}`:""}</p>${result.rows.length?`<div class="table-wrap"><table class="result-table"><thead><tr>${review?"<th>Rating</th><th>Unverified public complaint</th>":`<th>${search?"Observed search term":keyword?"Targeting keyword":"Campaign"}</th><th>Taps</th><th>Provider-attributed installs</th><th>Reported spend</th>`}</tr></thead><tbody>${rows}</tbody></table></div>`:notice("No matching provider rows were returned. This does not prove that the product is healthy or the campaign effective.")}<details><summary>Inspect dates, source hashes and exact observed data</summary><pre>${json(result)}</pre></details>`;
}

function openJob(id) {
  if(state.workspace.jobs.some(j=>j.id===id&&j.action==='agent_run'))return agentOpenRun(id);
  if(state.workspace.resolutions?.history.some(r=>r.job_id===id))return openResolutionRun(id);
  const job=state.workspace.jobs.find(j=>j.id===id);
  if(!job)return toast("This run is outside the current history. Refresh the selected app.");
  if(job.action==='sync'&&['play_releases','play_subscriptions'].includes(job.data.options?.operation))return playOpenJob(job);
  const outputs=job.result?.outputs || [];
  let content=notice("This run is saved locally. Prepared packets are not provider publication or measured acquisition.");
  if(job.result?.error) content+=notice(job.result.error,"error");
  content+=outputs.map(output=>stagePacketCard(output,id)).join("");
  if(job.result&&!outputs.length) content+=providerResult(job.result)+button("Download observed result","download-report",`data-id="${esc(id)}"`);
  if(job.action==="sync"&&job.data.options&&!["RUNNING","QUEUED"].includes(job.status))content+=button("Run report again","rerun-report",`data-id="${esc(id)}"`);
  const runState=outputs.length?`<p>Saved preparation · ${esc(new Date(job.created).toLocaleString())}. Buttons open the current workflow; the drafts below retain this run's saved inputs.</p><details><summary>Run reference</summary>${status(job.status)}<p class="app-mono">${esc(id)}</p></details>`:`${status(job.status)}<p class="app-mono">${esc(id)}</p>`;
  modal(outputs.length?"Your prepared workflow":"Saved run",`<div class="modal-content">${runState}${content}</div><div class="modal-actions">${["RUNNING","QUEUED"].includes(job.status)?button("Cancel local run","cancel-job",`data-id="${esc(id)}"`):button("Close result","close")}</div>`,outputs.length?"SAVED WORKFLOW":"RUN HISTORY");
  $("#modal-body").dataset.job=id;
}

function prepareReview() {
  const records=state.workspace.records.filter(r=>["distribution","store","experiment"].includes(r.kind));
  if(!records.length) return toast("Add a distribution, store or experiment record first.");
  modal("Prepare an immutable review",`<form id="review-form"><div class="modal-content">${notice("The packet freezes exact source contents for 24 hours. External execution remains manual.")}<label class="field" for="review-record">Source record<select name="record_id" id="review-record">${records.map(r=>`<option value="${esc(r.id)}">${esc(r.title)}</option>`).join("")}</select></label><div class="field-error" id="form-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit">Prepare review packet</button></div></form>`);
}

function openReview(id) {
  const review=state.workspace.approvals.find(r=>r.id===id);
  modal("Review exact contents",`<div class="modal-content">${status(review.status)}${notice(`Prepared by ${review.preparer}. Current local operator: ${state.boot.operator}. A different reviewer must inspect this packet before recording review.`)}<pre>${json(review.packet)}</pre><p class="app-mono">SHA256 ${esc(review.hash)}</p><div class="field-error" id="form-error" role="alert"></div></div><div class="modal-actions">${button("Download handoff","download-review",`data-id="${esc(id)}"`)}${review.status==="WAITING_REVIEW"?button("Record independent review","record-review",`data-id="${esc(id)}"`,""):""}</div>`);
}

function download(name,data,contentType="application/json") {
  const url=URL.createObjectURL(new Blob([typeof data==="string"?data:JSON.stringify(data,null,2)],{type:contentType}));
  const a=document.createElement("a");a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
function serverDownload(path,name) {
  const link=document.createElement("a");link.href=path;link.download=name;
  document.body.appendChild(link);link.click();link.remove();
}

async function formSubmit(event) {
  const form=event.target;
  if(!form.isConnected||(!currentWorkspace()&&!(form.id==="app-form"&&form.dataset.new==="true"))) {
    event.preventDefault();toast("App changed. Wait for this app to load and reopen the form.");return;
  }
  const formId=form.getAttribute("id");
  if(formId==='standing-scope-form'){event.preventDefault();return WMMCompleteAutomation.submit(form,growthReviewServices());}
  if((formId||"").startsWith("control-")) {event.preventDefault();return WMMAgentControl.submit(form,growthReviewServices());}
  if(formId==="subscription-plan-form") {event.preventDefault();return WMMSubscriptionAuthoring.submit(form,growthReviewServices());}
  if(formId==="customer-workflow-form") {event.preventDefault();return WMMCustomerWorkflow.submit(form,growthReviewServices());}
  if(formId==="growth-review-form") {event.preventDefault();return WMMGrowthReview.submit(form,growthReviewServices());}
  if((formId||'').startsWith('agent-')) {event.preventDefault();return agentSubmit(form);}
  if((formId||'').startsWith('social-')) {event.preventDefault();return socialSubmit(form);}
  if(formId==='play-setup-form') {event.preventDefault();return playSubmit(form);}
  if(formId==="aeo-form") {event.preventDefault();return aeoSubmit(form);}
  if(["storekit-setup-form","storekit-intake-form","storekit-disconnect-form"].includes(formId)) {
    event.preventDefault();
    return storekitSubmit(form);
  }
  if((formId||"").startsWith("attribution-")) {
    event.preventDefault();
    return attributionSubmit(form);
  }
  if(formId==="insights-setup-form") {
    event.preventDefault();
    return saveInsights(form);
  }
  if(formId==="insights-events-form") {
    event.preventDefault();return saveInsightsEvents(form);
  }
  if(!["app-form","evidence-form","review-form","cohort-form","history-form","provider-report-form","release-inventory-form","connection-setup-form","experiment-form","experiment-action-form","experiment-schedule-form","reference-form","reference-import-form","inspection-form","brief-form","payment-setup-form","payment-action-form"].includes(formId)) return;
  event.preventDefault();const submit=form.querySelector('[type="submit"]');submit.disabled=true;
  try {
    if(formId==="release-inventory-form") {
      if(form.dataset.app!==state.app)throw new Error("App changed. Reopen this release in the selected workspace.");
      const values=Object.fromEntries(new FormData(form)),version=values.manual_version_id.trim()||values.version_id;
      if(!/^[A-Za-z0-9-]{1,80}$/.test(version))throw new Error("Choose a release or enter its App Store version ID.");
      return await queue("sync",{connection_id:form.dataset.connection,connection_version:Number(form.dataset.version),options:{operation:"release_inventory",version_id:version}});
    }
    if(formId==="payment-setup-form")return await savePaymentSource(form);
    if(formId==="payment-action-form")return await savePaymentAction(form);
    if(formId==="connection-setup-form") return await saveConnection(form);
    if(formId==="reference-import-form")return await previewReferences(form);
    const data=Object.fromEntries(new FormData(form));
    if(["app-form","evidence-form","experiment-form"].includes(formId))automationCheckForm(form);
    if(formId==="provider-report-form") {
      if(form.dataset.app!==state.app)throw new Error("App changed. Close this form and reopen the report in the selected workspace.");
      await queue("sync",{connection_id:form.dataset.connection,connection_version:Number(form.dataset.version),options:{operation:data.operation,start:data.start,end:data.end,campaign_ids:data.campaign_ids.split(",").map(v=>v.trim()).filter(Boolean)}});
      return;
    }
    if(formId==="history-form") {
      const reports=await api(`/api/apps/${encodeURIComponent(state.app)}/measurement?as_of=${encodeURIComponent(data.as_of)}`);
      const report=reports.find(r=>r.cohort.cohort_id===form.dataset.cohort);
      modal("Historical cohort report",`<div class="modal-content">${status(report.status)}<p>As of ${esc(report.as_of)}</p><p>Contribution after costs: <strong>${money(report.contribution_after_acquisition_minor,report.cohort.currency)}</strong></p><pre>${json(report)}</pre></div><div class="modal-actions">${button("Close report","close")}</div>`);
      return;
    }
    if(formId==="app-form") await saveApp(data,form.dataset.new==="true",form);
    if(formId==="evidence-form") await saveEvidence(data,form);
    if(formId==="review-form") await api(`/api/apps/${state.app}/reviews`,data);
    if(formId==="cohort-form") await api(`/api/apps/${state.app}/cohorts`,data);
    if(formId==="experiment-form")await saveExperiment(form);
    if(formId==="experiment-action-form")await saveExperimentAction(form);
    if(formId==="experiment-schedule-form")await saveExperimentSchedule(form);
    if(formId==="reference-form")await saveReference(form);
    if(formId==="inspection-form")await saveInspection(form);
    if(formId==="brief-form")await saveBrief(form);
    await initialize();$("#modal").close();toast("Saved with source and workspace history.");
  } catch(error) {$("#form-error").textContent=error.message;} finally {submit.disabled=false;}
}

async function saveApp(data,isNew,form) {
  const id=data.id;delete data.id;
  const previous=isNew?{}:state.workspace.app.data;
  await api("/api/apps",{id,data:{...previous,...data},version:isNew?null:Number(form.dataset.manifestVersion)});
  state.app=id;
  if(isNew)state.view="workflow";
}

async function saveEvidence(data,form) {
  const id=form.dataset.id, previous=state.workspace.records.find(r=>r.id===id);
  const title=data.title,source=data.source;delete data.title;delete data.source;
  if(form.dataset.kind==="readiness")saveJourneyFields(data);
  if(form.dataset.worksheet) {
    const mode=form.dataset.worksheet;
    if(mode==="asa") {
      for(const key of ["taps","paid","contribution_per_payer_minor","non_media_cost_per_tap_minor","owner_cpt_cap_minor","acquisition_share"]) data[key]=Number(data[key]);
      for(const key of ["mature","counts_verified","contribution_verified"]) data[key]=data[key]==="true";
    } else {
      for(const key of ["mention","citation","correct_citation"]) data[key]=data[key]==="true";
      data.status="ok";
    }
    data.app_id=state.app;data.source_ref=source;
    const analysis={app_id:state.app,as_of:new Date().toISOString(),[mode]:mode==="asa"?data:[data]};
    return api(`/api/apps/${state.app}/records`,{kind:"acquisition",title,source,data:{analysis}});
  }
  for(const key of Object.keys(data)) {
    if(booleanFields.has(key)) data[key]=data[key]==="true";
    if(numberFields.has(key)) data[key]=Number(data[key]);
    if(key==="analysis") data[key]=JSON.parse(data[key]);
  }
  await api(`/api/apps/${form.dataset.app}/records`,{id:id || undefined,version:previous?.version,manifest_version:Number(form.dataset.manifestVersion),kind:form.dataset.kind,title,source,data:{...previous?.data,...data}});
}

async function handleAction(node) {
  if(node.dataset.action.startsWith('standing-'))return WMMCompleteAutomation.action(node,growthReviewServices());
  if(node.dataset.action==="retry-workspace")return refresh();
  if(!currentWorkspace()&&!["reload","close","add-app"].includes(node.dataset.action))return toast("Wait for this app to load, then try again.");
  if(node.dataset.action.startsWith("control-"))return WMMAgentControl.action(node,growthReviewServices());
  if(node.dataset.action.startsWith("growth-"))return WMMGrowthReview.action(node,growthReviewServices());
  if(node.dataset.action.startsWith("subscription-plan-"))return WMMSubscriptionAuthoring.action(node,growthReviewServices());
  if(node.dataset.action.startsWith("customer-"))return WMMCustomerWorkflow.action(node,growthReviewServices());
  if(node.dataset.action.startsWith('agent-'))return agentAction(node);
  if(node.dataset.action.startsWith('social-'))return socialAction(node);
  if(node.dataset.action.startsWith('play-'))return playAction(node);
  if(node.dataset.action.startsWith('setup-'))return setupAction(node);
  if(node.dataset.action.startsWith("subscriptions-"))return subscriptionAction(node);
  if(node.dataset.action.startsWith("followup-"))return followupAction(node);
  if(node.dataset.action==="rerun-report"){const job=state.workspace.jobs.find(j=>j.id===node.dataset.id);if(!job)throw new Error("Reload this app's saved reports.");if(['play_releases','play_subscriptions'].includes(job.data.options?.operation))return playRetry(job);return reportForm(job.data.connection_id,job.data.options);}
  const action=node.dataset.action,id=node.dataset.id;
  if(action==="measurement-inspect")return measurementIntegrityInspect();
  if(action==="measurement-download")return download(`${state.app}-payment-comparison.json`,state.workspace.measurement_integrity);
  if(action==="measurement-connections"){$("#modal").close();state.view="connections";return render();}
  if(action.startsWith("guided-"))return guidedAction(node);
  if(action.startsWith("automation-"))return automationAction(node);
  if(action.startsWith("spira-"))return spiraAction(node);
  if(action.startsWith("capability-"))return capabilityAction(node);
  if(action.startsWith("spytok-"))return spyTokAction(node);
  if(action.startsWith("automatic-"))return automaticPreparationAction(node);
  if(action.startsWith("storekit-"))return storekitAction(node);
  if(action.startsWith("attribution-"))return attributionAction(node);
  if(action.startsWith("insights-"))return insightsAction(node);
  if(action.startsWith("payment-"))return paymentAction(node);
  if(action.startsWith("experiment-"))return handleExperiment(node);
  if(action.startsWith("ranking-"))return rankingAction(node);
  if(action.startsWith("production-"))return productionAction(node);
  if(action.startsWith("render-"))return renderingAction(node);
  if(action.startsWith("acq-"))return acquisitionAction(node);
  if(action.startsWith("aeo-"))return aeoAction(node);
  if(action.startsWith("reference-"))return referenceAction(node);
  const simple={reload:initialize,close:()=>$("#modal").close(),"edit-app":()=>appForm(false),"add-app":()=>appForm(true),"run-all":()=>queue("pipeline",{stage:0}),"run-stage":()=>queue("pipeline",{stage:Number(id)}),stage:()=>openStage(id),record:()=>openRecord(id),job:()=>openJob(id),provider:()=>connectionSetup(id),upload:()=>$("#asset-file").click(),restore:()=>$("#restore-file").click(),"add-evidence":()=>evidenceForm(node.dataset.kind || "readiness"),"add-connection":()=>evidenceForm("connection",null,{provider:id,env_ref:`GROWTH_${state.app.toUpperCase().replaceAll("-","_")}_${id.toUpperCase()}_TOKEN`}),sync:()=>queue("sync",{connection_id:id}),"prepare-review":prepareReview,review:()=>openReview(id)};
  if(simple[action]) return simple[action]();
  if(action==="disconnect-connection") return disconnectForm(id);
  if(action==="confirm-disconnect") {const result=await api(`/api/apps/${state.app}/connections/${id}/disconnect`,{version:Number(node.dataset.version)});$("#modal").close();await refresh();return toast(result.cleanup==="PRIOR_LOCAL_KEY_CLEANUP_REQUIRED"?"Connection disabled; protected key cleanup needs attention. Use Disconnect locally again to remove it. Provider revocation was not performed.":"Local access removed. Provider key revocation was not performed.");}
  if(action==="release-select")return selectPromotionRelease(node);
  if(action==="release-inventory")return releaseForm(id);
  if(action==="provider-report") return reportForm(id);
  if(action==="download-report") return download(`${state.app}-provider-report.json`,state.workspace.jobs.find(j=>j.id===id).result);
  if(action==="define-cohort") return cohortForm();
  if(action==="import-events") {$("#event-file").dataset.cohort=id;$("#event-file").dataset.app=state.app;return $("#event-file").click();}
  if(action==="event-template") return download("event-import-template.csv","provider,event_id,type,subject_id,occurred_at,amount_minor,currency,related_event_id,source\n","text/csv");
  if(action==="ledger-report") return download(`${state.app}-${id}-report.json`,state.workspace.ledger.find(r=>r.cohort.cohort_id===id));
  if(action==="ledger-history") return historicalForm(id);
  if(action==="export") return serverDownload(`/api/apps/${encodeURIComponent(state.app)}/export`,`${state.app}-snapshot.json`);
  if(action==="cancel-job") {await api(`/api/apps/${state.app}/jobs/${id}/cancel`,{});await refresh();return openJob(id);}
  if(action==="download-packet") {const job=state.workspace.jobs.find(j=>j.id===node.dataset.job);return download(`${state.app}-stage-${node.dataset.stage}.json`,job.result.outputs.find(o=>o.stage===Number(node.dataset.stage)).packet);}
  if(action==="download-review") return download(`${state.app}-review.json`,state.workspace.approvals.find(r=>r.id===id));
  if(action==="record-review") {const review=state.workspace.approvals.find(r=>r.id===id);await api(`/api/apps/${state.app}/reviews/${id}/record`,{hash:review.hash});await refresh();return openReview(id);}
}

document.addEventListener("click",async event=>{
  const node=event.target.closest("[data-action],[data-view],[data-report-page]");if(!node) return;
  if(node.hasAttribute("data-report-page")) {
    try{WMMPageReports.openReport(WMMPageReports.model(state),window);}catch(error){toast(error.message);}return;
  }
  if(node.dataset.view) {state.weeklyGeneration=(state.weeklyGeneration||0)+1;state.weeklyLoading=false;state.view=node.dataset.view;render();$("#main").focus();return;}
  if(node.dataset.action?.startsWith('weekly-')){try{await weeklyAction(node);}catch(error){toast(error.message);}return;}
  try {await handleAction(node);} catch(error) {if($("#form-error")) $("#form-error").textContent=error.message;else toast(error.message);}
});
document.addEventListener("submit",formSubmit);
document.addEventListener("change",event=>{
  if(event.target.id==="reference-platform"){state.referencePlatform=event.target.value;render();}
  if(event.target.id==="reference-rights"){state.referenceRights=event.target.value;render();}
  if(event.target.id==="evidence-kind") evidenceForm(event.target.value);
  if(event.target.id==="worksheet-mode") acquisitionForm(event.target.value);
});
$("#app-select").addEventListener("change",async event=>{state.app=event.target.value;state.filter="";$("#modal").close();$("#modal-body").replaceChildren();try{await refresh();}catch(error){toast(error.message);}});
$("#add-app").addEventListener("click",()=>appForm(true));
$("#edit-app").addEventListener("click",()=>appForm(false));
$("#close-modal").addEventListener("click",()=>$("#modal").close());
$("#modal").addEventListener("close",()=>{WMMAgentControl.clear();WMMCompleteAutomation.clear();delete $("#modal-body").dataset.job;});
document.addEventListener("input",event=>{
  if(event.target.id==="reference-search"){const position=event.target.selectionStart;state.referenceFilter=event.target.value;render();$("#reference-search").focus();$("#reference-search").setSelectionRange(position,position);return;}
  if(event.target.closest("#experiment-form"))return samplePreview();
  if(event.target.id!=="evidence-search")return;
  const position=event.target.selectionStart;state.filter=event.target.value;render();$("#evidence-search").focus();$("#evidence-search").setSelectionRange(position,position);
});
$("#asset-file").addEventListener("change",async event=>{
  const file=event.target.files[0];if(!file)return;
  try {
    if(file.size>8388608) throw new Error("Choose an image smaller than 8 MB.");
    const response=await fetch(`/api/apps/${state.app}/files`,{method:"POST",headers:{"X-CSRF-Token":state.boot.csrf,"X-Filename":encodeURIComponent(file.name)},body:file});
    const result=await response.json();if(!response.ok)throw new Error(result.error);
    await refresh();openRecord(result.id);toast("Image saved. Review authenticity, rights, device and release before use.");
  }catch(error){toast(error.message);}finally{event.target.value="";}
});
$("#restore-file").addEventListener("change",async event=>{
  const file=event.target.files[0];if(!file)return;
  try {
    if(file.size>33554432)throw new Error("Snapshot exceeds 32 MB; use a filesystem backup for larger workspaces.");
    const text=new TextDecoder("utf-8",{fatal:true}).decode(await file.arrayBuffer());
    const result=await api("/api/restore",{}, {body:text});state.app=result.id;await initialize();toast("Snapshot restored. Existing workspaces were preserved.");
  }catch(error){toast(error.message);}finally{event.target.value="";}
});
$("#event-file").addEventListener("change",async event=>{
  const input=event.target,file=input.files[0];if(!file)return;
  const app=input.dataset.app,cohort=input.dataset.cohort;
  try {
    if(file.size>1048576)throw new Error("Use a smaller export under 1 MB and 500 rows per batch.");
    const text=new TextDecoder("utf-8",{fatal:true}).decode(await file.arrayBuffer());let body={cohort_id:cohort};
    if(file.name.toLowerCase().endsWith(".csv")) body.csv=text;
    else {
      const decoded=JSON.parse(text);
      if(decoded.cohort_id&&decoded.cohort_id!==cohort)throw new Error("This file names a different cohort. Select the matching cohort first.");
      body.events=Array.isArray(decoded)?decoded:decoded.events;
    }
    const result=await api(`/api/apps/${encodeURIComponent(app)}/events`,body);
    if(state.app===app)await refresh();
    toast(`${result.inserted} events imported; ${result.duplicates} unchanged duplicates. Inspect reconciliation before drawing conclusions.`);
  }catch(error){toast(error.message);}finally{input.value="";}
});
initialize();
