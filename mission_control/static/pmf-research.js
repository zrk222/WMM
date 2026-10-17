"use strict";

function researchPercent(value) { return value===null?"Unavailable":(value*100).toFixed(1)+"%"; }
function researchReadout(r) {
  if(r.status==="MISSING_SNAPSHOT")return notice("No observations imported. Download the CSV template, then preview your consented export.");
  return `<p><strong>${esc(label(r.status))}</strong> · ${esc(r.provenance)} · ${esc(r.registration)}</p><p>Population ${r.population} / ${r.expected_population===null?"unknown":r.expected_population}; eligible ${r.eligible}; invited ${r.invited}; responded ${r.responded}; nonresponse ${r.nonresponse}.</p><p>First value: yes ${r.first_value.yes}, no ${r.first_value.no}, unknown ${r.first_value.unknown}. Return opportunity: yes ${r.opportunity.yes}, no ${r.opportunity.no}, unknown ${r.opportunity.unknown}.</p><p>Repeat value: ${r.repeat.yes} / ${r.repeat_denominator} verified first-value users with an opportunity (${researchPercent(r.repeat_rate)}); unknown ${r.repeat.unknown}. All supplied users: ${researchPercent(r.all_acquired_repeat_lower_bound)} lower bound.</p><p>Very disappointed: ${r.survey.very} / ${r.survey_answered} answered (${researchPercent(r.very_disappointed_rate)}); unanswered disappointment ${r.survey.unknown}.${r.survey_wilson95?" Descriptive 95% interval "+r.survey_wilson95.map(researchPercent).join(" to "):""}</p><ul>${r.pending.map(s=>`<li>${esc(s)}</li>`).join("")}</ul>`;
}
function pmfResearchOpen() {
  const p=state.workspace.pmf,w=p.research;
  const studies=w.studies.map(s=>`<section class="panel"><h3>${esc(s.study.id)} · ${esc(s.study.data.segment)}</h3><p>${esc(s.study.data.release)} · ${esc(s.study.data.locale)} · ${esc(s.study.data.arm)} · ${esc(s.study.data.cadence)}</p>${researchReadout(s.readout)}${button("Import observations","research-import",`data-study="${esc(s.study.id)}"`)}</section>`).join("");
  const receipts=w.history.filter(r=>r.kind==="receipt").map(r=>`<article><h4>${esc(r.id)} · ${esc(r.data.engine)}</h4><p>${esc(r.data.summary)}</p><p>${esc(r.imported?"IMPORTED_ASSERTION":"SUPPLIED_RESULT_NOT_AUTHENTICATED")} · ${r.data.source_hash===p.tasks[0].source_hash?"Current task source":"Stale task source"}</p><details><summary>Coverage and unknowns</summary><p>${esc(r.data.coverage)}</p><p>${esc(r.data.unknowns)}</p></details></article>`).join("");
  modal("PMF evidence",`<div class="modal-content" id="pmf-research"><p class="eyebrow">${esc(state.workspace.app.data.name)} · PRIVATE RESEARCH</p>${notice("Use consented pseudonymous observations only. No names, contacts or private conversations. Complete supplied research still does not prove PMF; receipts do not authenticate plugin execution.")}<p><strong>Next research step:</strong> ${esc(p.research_next.title)}</p><div class="toolbar">${button("New study","research-study")}${button("Download CSV template","research-template")}</div>${studies||"<p>No studies yet. Declare the problem, segment, alternative and natural return cycle.</p>"}<h3>REA → ECC supplied results</h3><div class="toolbar">${button("Add REA result","research-result",'data-engine="REA"')}${button("Add ECC review","research-result",'data-engine="ECC"')}${button("Download evidence","research-download")}</div>${receipts||"<p>No supplied results. Task execution remains Not run.</p>"}</div><div class="modal-actions">${button("Back to PMF","research-back")}${button("Close","close")}</div>`);
}
function researchForm(kind,studyId=null,engine=null) {
  const app=state.workspace.app,p=state.workspace.pmf;
  const locale=/^[a-z]{2,3}(?:-[a-zA-Z0-9]{2,8}){0,3}$/;
  if(kind==="study"&&(!app.data.release||!locale.test(app.data.locale)||!/^[A-Z]{3}$/.test(app.data.currency))) {
    return modal("Choose the app and market first",`<div class="modal-content">${notice("Set the exact release, one language/region such as en-US, and a three-letter settlement currency before declaring a study. MULTIPLE cannot identify a research cohort.")}<p>Your existing research is preserved.</p></div><div class="modal-actions">${button("Open app setup","edit-app")}${button("Back to evidence","research-open")}</div>`);
  }
  const currentRea=p.research.history.filter(r=>r.kind==="receipt"&&r.data.engine==="REA"&&r.data.source_hash===p.tasks[0].source_hash);
  if(engine==="ECC"&&!currentRea.length) {
    return modal("REA evidence is needed first",`<div class="modal-content">${notice("ECC reviews the current REA evidence. Add a source-bound REA result before recording its critique; stale results remain in history.")}</div><div class="modal-actions">${button("Add REA result","research-result",'data-engine="REA"')}${button("Back to evidence","research-open")}</div>`);
  }
  let fields=[field("id","","text","Immutable lowercase ID; use a new ID for a new observation")];
  if(kind==="study") {
    fields.push(...["segment","problem","alternative","switching_cost","value_event","cadence"].map(k=>field(k,({problem:p.problem,segment:p.segment_hypothesis,value_event:p.value_event,cadence:p.value_cadence})[k]||"","text","Research hypothesis; no personal data")));
    fields.push(experimentSelect("arm","Study arm",[["discovery","Discovery"],["holdout","Holdout"]],"discovery"));
    fields.push(...["starts_at","ends_at","matures_at"].map(k=>field(k,"","text","ISO timestamp with timezone, e.g. 2026-10-12T09:00:00Z")));
    fields.push(field("target_responses",30,"number","Declared sampling target, not a guarantee of statistical power"));
  } else if(kind==="snapshot") {
    fields.push(experimentSelect("study_id","Study",p.research.studies.map(s=>[s.study.id,s.study.id]),studyId));
    fields.push(field("source_id","","text","Unique source export ID"),field("observed_at",new Date().toISOString(),"text","Observation timestamp with timezone"),field("expected_population","","number","All acquired cohort members; leave blank if unknown",false));
    fields.push('<label class="field">Consented observations CSV<input type="file" name="csv_file" accept=".csv,text/csv" required><small>Exact template columns; up to 1000 pseudonymous rows and 1 MiB.</small></label>');
  } else {
    fields.push(field("observed_at",new Date().toISOString(),"text","Actual result observation time"),field("evidence_ids","","textarea","Native ev_ SHA256 references, one per line"),field("artifact_hashes","","textarea","Artifact SHA256 hashes, one per line"));
    fields.push(...["summary","coverage","unknowns"].map(k=>field(k,"","textarea","Supplied observations; no secrets or personal data")));
    if(engine==="ECC")fields.push(experimentSelect("rea_id","Current REA result",p.research.history.filter(r=>r.kind==="receipt"&&r.data.engine==="REA"&&r.data.source_hash===p.tasks[0].source_hash).map(r=>[r.id,r.id]),null));
  }
  modal(kind==="study"?"Declare a PMF study":kind==="snapshot"?"Preview cohort observations":`Add supplied ${engine} result`,`<form id="research-form" data-kind="${kind}" data-engine="${engine||""}" data-app="${esc(app.id)}" data-manifest="${app.version}" data-source="${p.tasks[0].source_hash}"><div class="modal-content">${notice(kind==="snapshot"?"Preview does not save. Imports are complete snapshots; later observations replace the current readout without deleting history.":"Saved entries are immutable. These are supplied research assertions, not native tool execution or provider permission.")}<div class="form-grid">${fields.join("")}</div><div id="research-preview" aria-live="polite"></div><p id="form-error" class="field-error" role="alert"></p></div><div class="modal-actions"><button type="submit" class="button" name="operation" value="preview">${kind==="snapshot"?"Preview CSV":"Save "+(kind==="study"?"study":"supplied result")}</button>${kind==="snapshot"?'<button type="submit" class="button secondary" name="operation" value="commit" disabled>Save previewed observations</button>':""}${button("Back to evidence","research-open")}</div></form>`);
  if(kind==="snapshot"&&studyId)$("#research-form [name=study_id]").value=studyId;
  if(kind==="study")$("#research-form [name=arm]").value="discovery";
  if(engine==="ECC")$("#research-form [name=rea_id]").value=currentRea[currentRea.length-1].id;
}
async function researchPayload(form) {
  const raw=Object.fromEntries(new FormData(form)),kind=form.dataset.kind;
  const body={id:raw.id,manifest_version:Number(form.dataset.manifest),data:{}};
  delete raw.id;delete raw.operation;
  if(kind==="study")body.data={...raw,release:state.workspace.app.data.release,locale:state.workspace.app.data.locale,currency:state.workspace.app.data.currency,target_responses:Number(raw.target_responses)};
  if(kind==="snapshot") {
    const file=form.querySelector("[name=csv_file]").files[0];
    if(!file||file.size>1048576)throw new Error("Choose a CSV file up to 1 MiB.");
    body.data={study_id:raw.study_id,source_id:raw.source_id,observed_at:raw.observed_at,expected_population:raw.expected_population===""?null:Number(raw.expected_population),csv:await file.text()};
  }
  if(kind==="receipt")body.data={...raw,engine:form.dataset.engine,source_hash:form.dataset.source,evidence_ids:raw.evidence_ids.trim().split(/\s+/),artifact_hashes:raw.artifact_hashes.trim().split(/\s+/),rea_id:raw.rea_id||null};
  return body;
}
document.addEventListener("input",event=>{
  const form=event.target.closest("#research-form");if(!form)return;
  delete form.previewHash;const commit=form.querySelector('[value="commit"]');if(commit)commit.disabled=true;
  $("#research-preview").innerHTML="";
});
document.addEventListener("submit",async event=>{
  const form=event.target;if(form.getAttribute("id")!=="research-form")return;event.preventDefault();
  const operation=event.submitter?.value,controls=[...form.querySelectorAll('[type="submit"]')];controls.forEach(n=>n.disabled=true);
  try {
    if(state.app!==form.dataset.app||state.workspace.app.version!==Number(form.dataset.manifest))throw new Error("App setup changed. Reopen the form; input is retained.");
    const body=await researchPayload(form),kind=form.dataset.kind,app=form.dataset.app;
    if(operation==="commit")body.preview_hash=form.previewHash;
    const route=kind==="snapshot"&&operation!=="commit"?"preview":kind;
    const result=await api(`/api/apps/${encodeURIComponent(app)}/pmf-research/${route}`,body);
    if(state.app!==app||!form.isConnected)return;
    if(route==="preview") {
      form.previewHash=result.preview_hash;$("#research-preview").innerHTML=`<h3>Preview · ${result.rows} supplied rows</h3>${researchReadout(result.readout)}`;
    } else {await refresh();if(state.app===app&&form.isConnected)pmfResearchOpen();}
  } catch(error) {if(form.isConnected)form.querySelector("#form-error").textContent=error.message;}
  finally {controls.forEach(n=>n.disabled=n.value==="commit"&&!form.previewHash);}
});
document.addEventListener("click",event=>{
  const node=event.target.closest('[data-action^="research-"]');if(!node)return;
  const action=node.dataset.action;
  if(action==="research-open")pmfResearchOpen();
  if(action==="research-back")pmfOpen();
  if(action==="research-study")researchForm("study");
  if(action==="research-import")researchForm("snapshot",node.dataset.study);
  if(action==="research-result")researchForm("receipt",null,node.dataset.engine);
  if(action==="research-download")download(`${state.app}-pmf-evidence.json`,state.workspace.pmf.research);
  if(action==="research-template") {
    const text="subject_id,consent,eligible,invited,responded,first_value,return_opportunity,repeat_value,disappointment,barrier\n";
    const url=URL.createObjectURL(new Blob([text],{type:"text/csv;charset=utf-8"})),a=document.createElement("a");
    a.href=url;a.download="pmf-observations-template.csv";a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
});
