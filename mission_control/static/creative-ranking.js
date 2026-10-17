"use strict";
function rankingPanel() {
  const ranking=state.workspace.rankings||{policy:[],relevance:[],report:[]};
  return `<div class="section-heading"><h2>Explainable source ranking</h2><div>${button(ranking.policy.length?"Revise ranking policy":"Declare ranking policy","ranking-policy")} ${button("Rank selected sources","ranking-run")}</div></div>${notice("Attention and app fit are independent. Weights are proposed, not calibrated; downstream superiority has not been evaluated. Unknown baselines remain unavailable.")}${ranking.report.length?`<div class="record-list">${ranking.report.map(r=>`<button class="record-row" data-action="ranking-open" data-id="${esc(r.id)}"><span class="record-main"><strong>Source ranking · ${esc(new Date(r.current.created).toLocaleString())}</strong><small>${r.current.data.coverage.eligible} reviewed / ${r.current.data.coverage.sources} selected posts · ${r.current.data.coverage.comparable_attention} comparable attention values</small></span>${status(r.input_status)}</button>`).join("")}</div>`:empty("Review app fit before ranking","Open a source in Evidence, record its fit to this app, then declare your selection policy.",button("Review source relevance","ranking-sources"))}`;
}

function rankForm(title,kind,fields,old=null,extra="") {
  modal(title,`<form id="ranking-form" data-kind="${kind}" data-app="${esc(state.app)}" data-id="${esc(old?.id||"")}" data-version="${old?.current.version||""}" ${extra}><div class="modal-content">${notice("This is supplied research and a proposed selection method. Saving does not authorize publication, prove rights or establish growth.")}<div class="form-grid">${fields}</div><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit">${kind==="run"?"Save source ranking":"Save "+kind}</button></div></form>`,"CREATIVE INTELLIGENCE / RANKING");
}

function rankingPolicyForm() {
  const old=state.workspace.rankings.policy[0],d=old?.current.data||{mode:"SIMPLE_RELEVANCE",weights:{relevance:1,attention:0,freshness:0,cost:0},max_per_creator:2,max_per_format:3,slate_size:6,holdout_after:new Date().toISOString()};
  const weights=Object.entries(d.weights).map(([key,value])=>field(key+"_weight",value,"text","Fraction 0–1; all four sum to 1. Relevance at least 0.5.")).join("");
  rankForm("Declare your selection policy","policy",choiceField("mode",["SIMPLE_RELEVANCE","EXPLORATORY"].map(id=>({id,title:label(id)})),d.mode)+weights+field("max_per_creator",d.max_per_creator,"number","1–3; unknown creator cap is always 1")+field("max_per_format",d.max_per_format,"number","1–12 maximum posts using the same format")+field("slate_size",d.slate_size,"number","1–12")+field("holdout_after",d.holdout_after,"text","Source publication partition only; not a downstream holdout test")+field("rationale",d.rationale,"textarea","Why these proposed weights and constraints?"),old);
}

function rankingRelevanceForm(referenceId) {
  const source=state.workspace.references.find(r=>r.id===referenceId),old=state.workspace.rankings.relevance.find(r=>r.current.data.reference_id===referenceId),d=old?.current.data||{};
  const app=state.workspace.app.data;
  const fits=["job_fit","audience_fit","proof_fit"].map(key=>choiceField(key,[0,1,2,3].map(value=>({id:String(value),title:["0 · No fit","1 · Weak fit","2 · Plausible fit","3 · Direct fit"][value]})),d[key]===undefined?"":String(d[key]))).join("");
  rankForm("Review app fit · "+source.current.data.title,"relevance",`<div class="notice"><span>Job: ${esc(app.job)}<br>Audience: ${esc(app.audience)}<br>Source: ${esc(source.current.data.relevance_note)}</span></div>`+fits+field("cost_minor",d.cost_minor??0,"number",`Proposed production cost in ${app.currency} minor units, not authorized spending`)+field("rationale",d.rationale,"textarea","Specific evidence for the three ratings; uncertainty and limits"),old,`data-reference="${esc(referenceId)}" data-capture="${esc(source.current.hash)}" data-app-hash="${esc(state.workspace.rankings.app_hash)}"`);
}

function rankingRunForm() {
  if(!state.workspace.rankings.policy.length)return rankingPolicyForm();
  const sources=state.workspace.references;
  if(!sources.length){state.view="evidence";render();return referenceForm();}
  const fields=`<fieldset><legend>Selected source pool · 1–100 distinct posts</legend><p>Only these posts supply comparable peers. This is not a representative market sample.</p>${sources.map((r,i)=>`<label class="check-row"><input type="checkbox" name="reference_ids" value="${esc(r.id)}" ${sources.length<=100?"checked":""}> ${esc(r.current.data.title)} · ${esc(r.current.data.platform)}</label>`).join("")}</fieldset>`;
  rankForm("Choose the ranking denominator","run",capabilityState().evaluations.map(capabilityRow).join("")+fields);
}

function rankingRow(row) {
  const signal=s=>s.score===null?`Unavailable · ${esc(s.reason)} (${s.n} peers)`:`${s.score.toFixed(3)} exploratory value · ${s.n} comparable peers`;
  return `<details><summary>${esc(row.title)} · ${row.eligible?"Reviewed fit "+row.relevance.value.toFixed(2):"Excluded"}</summary><p>${esc(row.exclusion||row.relevance.rationale)}</p><p>App fit is operator supplied. ${esc(row.partition)} source partition.</p><p>Cumulative attention: ${signal(row.attention)}</p><p>Observed velocity: ${signal(row.velocity)}</p><details><summary>Inspect denominators, hashes and components</summary><pre>${json(row)}</pre></details></details>`;
}

function openRanking(id) {
  const item=state.workspace.rankings.report.find(r=>r.id===id),data=item.current.data;
  const title=ref=>data.rows.find(r=>r.reference_id===ref)?.title||ref;
  modal("Source ranking rationale",`<div class="modal-content">${status(item.input_status)}${notice(data.limits)}<h3>Proposed slate</h3><ol>${data.slate.selected.map(ref=>`<li>${esc(title(ref))}</li>`).join("")}</ol><h3>Simple relevance baseline</h3><ol>${data.simple_baseline.selected.map(ref=>`<li>${esc(title(ref))}</li>`).join("")}</ol><p>Downstream comparison: ${esc(data.evaluation)} · outcomes ${esc(data.outcomes)}</p><p>${data.coverage.eligible}/${data.coverage.sources} current relevance reviews · ${data.coverage.comparable_attention}/${data.coverage.sources} comparable cumulative attention values</p><h3>Independent axes and exclusions</h3>${data.rows.map(rankingRow).join("")}<details><summary>Frozen policy and selection exclusions</summary><pre>${json({policy:data.inputs.policy,selection:data.slate})}</pre></details><h3>Saved report history</h3>${item.versions.map(r=>`<p>Version ${r.version} · ${esc(r.created)} · <span class="app-mono">${esc(r.hash)}</span></p>`).join("")}</div><div class="modal-actions">${button("Download ranking evidence","ranking-download",`data-id="${esc(id)}"`)} ${button("Run with current evidence","ranking-run")}</div>`);
}

function rankingAction(node) {
  const action=node.dataset.action,id=node.dataset.id;
  const handlers={"ranking-policy":rankingPolicyForm,"ranking-run":rankingRunForm,"ranking-relevance":()=>rankingRelevanceForm(id),"ranking-open":()=>openRanking(id),"ranking-download":()=>download(`${state.app}-source-ranking.json`,state.workspace.rankings.report.find(r=>r.id===id)),"ranking-sources":()=>{state.view="evidence";render();}};
  if(!handlers[action])throw new Error("Unknown ranking action");
  return handlers[action]();
}

async function rankingSubmit(event) {
  const form=event.target;if(form.id!=="ranking-form")return;
  event.preventDefault();const submit=form.querySelector('[type="submit"]');submit.disabled=true;
  try {
    const fd=new FormData(form),kind=form.dataset.kind;let data=Object.fromEntries(fd),body;
    if(kind==="run")body={reference_ids:fd.getAll("reference_ids")};
    else {
      if(kind==="policy"){
        data.weights={};for(const key of ["relevance","attention","freshness","cost"]){data.weights[key]=Number(data[key+"_weight"]);delete data[key+"_weight"];}
        for(const key of ["max_per_creator","max_per_format","slate_size"])data[key]=Number(data[key]);
      } else {
        for(const key of ["job_fit","audience_fit","proof_fit","cost_minor"])data[key]=Number(data[key]);
        Object.assign(data,{reference_id:form.dataset.reference,capture_hash:form.dataset.capture,app_hash:form.dataset.appHash});
      }
      body={data};if(form.dataset.id)Object.assign(body,{id:form.dataset.id,version:Number(form.dataset.version)});
    }
    const result=await api(`/api/apps/${form.dataset.app}/rankings/${kind}`,body);await refresh();$("#modal").close();
    if(kind==="run")openRanking(result.id);else toast("Saved "+kind+" with source-bound history.");
  } catch(error){$("#form-error").textContent=error.message;}finally{submit.disabled=false;}
}
document.addEventListener("submit",rankingSubmit);
