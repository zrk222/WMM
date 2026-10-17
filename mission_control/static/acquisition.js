"use strict";
function acquisitionPanel() {
  const a=state.workspace.acquisition||{intents:[],panels:[],reports:[]};
  const rows=(items,kind,title)=>items.map(i=>`<button class="record-row" data-action="acq-open" data-kind="${kind}" data-id="${esc(i.id)}"><span class="record-main"><strong>${esc(title(i))}</strong><small>${esc(i.evidence_status)} · version ${i.current.version}</small></span>${status(i.evidence_status)}</button>`).join("");
  return `<div class="section-heading"><div><h2>Acquisition intent to measured evidence</h2><p>Connect source, claim, page, first value and a fixed observation panel.</p></div>${button("Map an acquisition intent","acq-intent")}</div>${notice("Search demand remains unknown until measured. Source popularity is not search volume. API answers do not establish consumer-interface visibility.")}<div class="two-column"><section class="panel"><h3>Reviewed intent chains</h3>${rows(a.intents,"intents",i=>i.current.data.definition.problem)||"<p>Start with inspected research and current product checks. Future apps use the same guided workflow.</p>"}</section><section class="panel"><h3>Fixed answer-engine panels</h3>${rows(a.panels,"panels",i=>i.current.data.definition.engine+" / "+i.current.data.definition.surface)||"<p>Declare questions, conditions, repetitions and holdouts before recording answers.</p>"}</section></div><section class="panel"><h3>Saved panel reports</h3>${rows(a.reports,"reports",i=>"Panel report · "+new Date(i.current.created).toLocaleString())||"<p>Missing slots, errors and unreviewed citations remain visible in every report.</p>"}</section>`;
}

function acqForm(title,kind,fields,extra="",old=null) {
  modal(title,`<form id="acq-form" data-kind="${kind}" data-app="${esc(state.app)}" data-id="${esc(old?.id||"")}" data-version="${old?.current.version||""}" ${extra}><div class="modal-content">${notice("This saves an app-specific research contract. No provider request, publication or spending is performed.")}<div class="form-grid">${fields}</div><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit">${({intents:"Save intent chain",panels:"Declare fixed panel",observations:"Save immutable observation"})[kind]}</button></div></form>`,"ASA / AEO WORKFLOW");
}

function acqIntentForm(id=null) {
  const old=state.workspace.acquisition.intents.find(i=>i.id===id),d=old?.current.data.definition||{},records=state.workspace.records;
  const analyses=state.workspace.analyses.filter(a=>a.source_status==="CURRENT"),missing=["claim","readiness","route"].filter(k=>!records.some(r=>r.kind===k));
  if(!analyses.length||missing.length)return productionPrerequisites(missing,!analyses.length);
  let fields=["owner","problem","asa_seed","aeo_question","territory","native_reviewer","page_url"].map(k=>field(k,d[k]||"",k==="problem"?"textarea":"text",({territory:"Two-letter country code; language and territory are independent",native_reviewer:"Name of the native-language reviewer; supplied attestation",page_url:"Proposed public HTTPS answer page; crawl/index/publication remain unverified",asa_seed:"Proposed keyword, not measured volume"})[k]||"")).join("");
  fields+=choiceField("analysis_id",analyses.map(i=>({id:i.id,title:i.current.data.format_family})),d.analysis_id);
  for(const kind of ["claim","readiness","route","store"])fields+=choiceField(kind+"_id",[...(kind==="store"?[{id:"NONE",title:"Educational page only; no Store destination"}]:[]),...records.filter(r=>r.kind===kind).map(r=>({id:r.id,title:r.title}))],d[kind+"_id"]||"NONE");
  fields+=choiceField("brief_id",[{id:"NONE",title:"No creative linked yet"},...state.workspace.briefs.filter(b=>b.evidence_status==="CURRENT").map(b=>({id:b.id,title:b.current.data.definition.objective}))],d.brief_id||"NONE");
  acqForm("Map a source-linked acquisition intent","intents",fields,"",old);
}

function acqQueryFields(index,partition="CALIBRATION") {
  return `<fieldset class="full acq-query"><legend>Question ${index+1}</legend>${field("query_"+index,"","text","Exact question; avoid including private information")}${choiceField("partition_"+index,[{id:"CALIBRATION",title:"Calibration"},{id:"HOLDOUT",title:"Holdout"}],partition)}</fieldset>`;
}

function acqPanelForm(intentId) {
  const intent=state.workspace.acquisition.intents.find(i=>i.id===intentId);
  const fields=field("owner")+field("engine","","text","Actual answer engine or API name")+choiceField("surface",["API","CONSUMER_UI"].map(id=>({id,title:label(id)})))+field("search_mode","","text","Actual search setting used in every attempt")+field("model","NOT_EXPOSED","text","Exact visible model/version or NOT_EXPOSED")+field("account_context","","text","Plan, account state, personalization; no account secrets")+field("geography","","text","Actual test location, independent of app territory")+field("repetitions",1,"number","1–5 attempts per exact query")+field("rubric","","textarea","How to judge mention, source support and misinformation")+`<div class="full" id="acq-queries">${acqQueryFields(0)}${acqQueryFields(1,"HOLDOUT")}</div><div class="full">${button("Add panel question","acq-add-query")}</div>`;
  acqForm("Declare questions before observations","panels",fields,`data-intent="${esc(intentId)}" data-hash="${esc(intent.current.hash)}"`);
}

function acqObservationForm(panelId) {
  const panel=state.workspace.acquisition.panels.find(p=>p.id===panelId),d=panel.current.data.definition,observed=state.workspace.acquisition.observations;
  const slots=[];for(const q of d.queries)for(let r=1;r<=d.repetitions;r++)if(!observed.some(o=>o.current.data.panel_id===panelId&&o.current.data.query_id===q.id&&o.current.data.repetition===r))slots.push({id:JSON.stringify([q.id,r]),title:`${q.partition} · ${q.text} · attempt ${r}`});
  if(!slots.length)return toast("Every fixed panel slot already has a saved attempt. Generate its report.");
  const fields=choiceField("slot",slots)+choiceField("status",[{id:"OK",title:"Answer returned"},{id:"ERROR",title:"Failed attempt"}])+field("observed_at",new Date().toISOString())+field("raw_response","","textarea","Exact public/synthetic answer or error, maximum 20000 characters; no private conversations")+field("source_ref","","text","Retained capture or authorized API response receipt")+field("reviewer")+field("mention","","boolean","Whether the app was explicitly mentioned")+field("citation_url","","text","Exact public HTTPS citation, or leave empty",false)+choiceField("correct_citation",[{id:"UNKNOWN",title:"Unreviewed / no citation"},{id:"true",title:"Source supports the specific claim"},{id:"false",title:"Source does not support the claim"}])+field("misinformation","","boolean","Does the answer misstate the app or its capabilities?")+field("review_note","","textarea","Explain source support, uncertainty or failure. Failed attempts ignore answer outcomes.");
  acqForm("Record a fixed-panel attempt","observations",fields,`data-panel="${esc(panelId)}" data-hash="${esc(panel.current.hash)}"`);
}

function acqReportBody(d) {
  return `${notice(d.limits)}<div class="two-column">${Object.entries(d.partitions).map(([key,p])=>`<section class="panel"><h3>${esc(label(key))}</h3><p>${p.attempted}/${p.expected} attempts · ${p.missing} missing · ${p.errors} errors</p><p>${p.successful} answers · ${p.mentions} mentions · ${p.citations} citations · ${p.pending_review} unreviewed</p><p>${p.correct_exact_destination} correct citations to the exact destination · ${p.misinformation} misinformation findings</p><p>Reviewed citation accuracy: ${p.reviewed_citation_accuracy===null?"Unknown":(100*p.reviewed_citation_accuracy).toFixed(1)+"%"}</p></section>`).join("")}</div><details><summary>Exact frozen panel, raw responses and hashes</summary><pre>${json(d)}</pre></details>`;
}

function acqChainBody(d,kind) {
  if(kind==="intents"){
    const claim=d.records.find(r=>r.kind==="claim"),definition=d.definition;
    return `<h3>${esc(definition.problem)}</h3><div class="details-list"><div class="detail-item"><strong>1. Inspected source</strong><a href="${esc(d.source.data.url)}" target="_blank" rel="noopener noreferrer">${esc(d.source.data.title)}</a><p>${esc(d.analysis.data.format_family)}</p></div><div class="detail-item"><strong>2. Search intent</strong><p>Apple Ads hypothesis: ${esc(definition.asa_seed)}</p><p>Answer-engine question: ${esc(definition.aeo_question)}</p></div><div class="detail-item"><strong>3. Demonstrated claim</strong><p>${esc(claim.data.claim)}</p></div><div class="detail-item"><strong>4. Answer page to first value</strong><p>${esc(definition.page_url)}</p><p>${esc(d.first_value)}</p></div><div class="detail-item"><strong>5. Language and market</strong><p>${esc(d.locale)} / ${esc(definition.territory)} · reviewer ${esc(definition.native_reviewer)}</p><p>Search demand: UNKNOWN · Apple Ads: ${esc(d.asa_status)}</p></div></div><details><summary>Exact source chain and hashes</summary><pre>${json(d)}</pre></details>`;
  }
  const p=d.definition;
  return `<h3>${esc(p.engine)} / ${esc(p.surface)}</h3><p>${esc(p.search_mode)} · model ${esc(p.model)} · ${esc(p.geography)}</p><p>${esc(p.account_context)}</p><p>${p.repetitions} attempts per question. Rubric: ${esc(p.rubric)}</p><ol>${p.queries.map(q=>`<li>${esc(q.text)} <strong>${esc(q.partition)}</strong></li>`).join("")}</ol><details><summary>Exact frozen conditions and intent chain</summary><pre>${json(d)}</pre></details>`;
}

function acqOpen(id,kind) {
  const item=state.workspace.acquisition[kind].find(i=>i.id===id),d=item.current.data;
  let actions=button("Download acquisition history","acq-download",`data-id="${esc(id)}" data-kind="${kind}"`);
  if(kind==="intents")actions+=button("Declare answer-engine panel","acq-panel",`data-id="${esc(id)}"`)+button("Revise intent chain","acq-intent",`data-id="${esc(id)}"`);
  if(kind==="panels")actions+=button("Record panel attempt","acq-observe",`data-id="${esc(id)}"`)+button("Generate panel report","acq-report",`data-id="${esc(id)}"`);
  if(kind==="reports")actions+=button("Attach as pipeline evidence","acq-attach",`data-id="${esc(id)}"`);
  modal(kind==="reports"?"Fixed panel results":"Acquisition source chain",`<div class="modal-content">${status(item.evidence_status)}${kind==="reports"?acqReportBody(d):acqChainBody(d,kind)}<div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions">${actions}</div>`);
}

async function acquisitionAction(node) {
  const action=node.dataset.action,id=node.dataset.id;
  if(action==="acq-intent")return acqIntentForm(id);
  if(action==="acq-panel")return acqPanelForm(id);
  if(action==="acq-observe")return acqObservationForm(id);
  if(action==="acq-open")return acqOpen(id,node.dataset.kind);
  if(action==="acq-download")return download(`${state.app}-acquisition.json`,state.workspace.acquisition[node.dataset.kind].find(i=>i.id===id));
  if(action==="acq-add-query"){
    const count=document.querySelectorAll(".acq-query").length;
    if(count>=20)return toast("Panels allow at most twenty questions.");
    return $("#acq-queries").insertAdjacentHTML("beforeend",acqQueryFields(count));
  }
  if(action==="acq-report"||action==="acq-attach"){
    const result=await api(`/api/apps/${state.app}/acquisition/${action==="acq-report"?"reports":"attach"}`,action==="acq-report"?{panel_id:id}:{report_id:id});
    await refresh();if(action==="acq-report")acqOpen(result.id,"reports");else toast("Saved source-bound observation evidence in the pipeline.");
  }
}

async function acquisitionSubmit(event) {
  const form=event.target;if(form.id!=="acq-form")return;
  event.preventDefault();const submit=form.querySelector('[type="submit"]');submit.disabled=true;
  try {
    const values=Object.fromEntries(new FormData(form)),kind=form.dataset.kind;let data={...values};
    if(kind==="intents"){
      for(const key of ["store_id","brief_id"])if(data[key]==="NONE")data[key]=null;
      data.analysis_hash=state.workspace.analyses.find(a=>a.id===data.analysis_id).current.hash;
    } else if(kind==="panels"){
      for(const key of Object.keys(data))if(key.startsWith("query_")||key.startsWith("partition_"))delete data[key];
      Object.assign(data,{intent_id:form.dataset.intent,intent_hash:form.dataset.hash,repetitions:Number(values.repetitions),queries:[...form.querySelectorAll(".acq-query")].map((_,i)=>({id:"q"+(i+1),text:values["query_"+i],partition:values["partition_"+i]}))});
    } else {
      const [query_id,repetition]=JSON.parse(data.slot);delete data.slot;
      Object.assign(data,{panel_id:form.dataset.panel,panel_hash:form.dataset.hash,query_id,repetition,mention:values.mention==="true",misinformation:values.misinformation==="true",citation_url:values.citation_url||null,correct_citation:values.correct_citation==="UNKNOWN"?null:values.correct_citation==="true"});
      if(data.status==="ERROR")for(const key of ["mention","misinformation","citation_url","correct_citation"])data[key]=null;
    }
    const body={data};if(form.dataset.id)Object.assign(body,{id:form.dataset.id,version:Number(form.dataset.version)});
    const result=await api(`/api/apps/${form.dataset.app}/acquisition/${kind}`,body);await refresh();$("#modal").close();
    if(kind!=="observations")acqOpen(result.id,kind);else toast("Saved immutable panel attempt.");
  } catch(error){$("#form-error").textContent=error.message;}finally{submit.disabled=false;}
}

document.addEventListener("submit",acquisitionSubmit);
document.addEventListener("change",event=>{
  if(event.target.name!=="status"||event.target.form?.id!=="acq-form")return;
  for(const key of ["mention","citation_url","correct_citation","misinformation"]){
    const control=event.target.form.elements.namedItem(key);control.disabled=event.target.value==="ERROR";
  }
});
