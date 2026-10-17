"use strict";

function learningWorkspace() {return state.workspace.learning || {programs:[],links:[],cost_options:[],uses:[],active_id:null};}
function learningProgram(id) {return learningWorkspace().programs.find(p=>p.id===id);}
function learningRole(kind) {const role=myReviewRole();return role&&[kind,"OWNER"].includes(role.role);}

function outcomeLearningPanel() {
  const w=learningWorkspace(),identity=reviewIdentity();
  const links=w.links.map(r=>`<div class="record-row"><span class="record-main"><strong>${esc(state.workspace.experiments.find(e=>e.id===r.experiment_id)?.data.name || "Retained experiment")} · ${esc(r.arm)}</strong><small>${esc(r.data.brief.data.content.hooks?.[0] || r.data.brief.data.definition.objective)} · production allocation ${money(r.data.production_cost_minor,r.data.variant.cohort.currency)}</small><small>Publication receipt supplied by operator · already included in delivery costs</small></span>${status(r.availability)}${button("Inspect creative link","learning-link-open",`data-experiment="${esc(r.experiment_id)}" data-arm="${esc(r.arm)}"`)}</div>`).join("");
  const programs=w.programs.map(p=>`<button class="record-row" data-action="learning-open" data-id="${esc(p.id)}"><span class="record-main"><strong>${esc(p.data.definition.name)}</strong><small>${p.active?"Active local guidance · ":p.restored?"Imported history; authority not transferred · ":""}version ${p.version} · ${esc(p.availability)}</small></span>${status(p.state)}</button>`).join("");
  return `<section class="panel" id="outcome-learning-panel"><p class="eyebrow">CREATIVE OUTCOMES / LEARNING</p><h2>Learn from useful outcomes</h2><p class="description">Join original creative, supplied publication receipts and costs to the fixed experiment. Test an original method on a new untouched holdout before local adoption.</p>${notice("Supplied publication and imported cohort data are not authenticated delivery or causal lift. Creative costs are allocated from existing delivery rows and are never subtracted twice.")}<div class="toolbar">${button("Link creative outcomes","learning-link")}${button("Propose a creative method","learning-propose")}${identity.status!=="AUTHENTICATED"?button("Sign in for local guidance","identity-login"):""}</div>${links?'<div class="record-list">'+links+'</div>':notice("No creative outcome links yet. Register an experiment, prepare source-bound briefs and import explicit delivery-cost rows, including zero-cost evidence when appropriate.")}${programs?'<h3>Versioned creative methods</h3><div class="record-list">'+programs+'</div>':notice("No learned guidance yet. Complete a mature experiment and record a next-test decision before proposing a method.")}</section>`;
}

function learningGuidancePanel() {
  const active=learningWorkspace().programs.find(p=>p.active);
  const blocked=learningWorkspace().active_id&&!active;
  if(!active)return blocked?notice("Previously active learning is unavailable because its source or authorization changed. Inspect it in Results and roll back or prepare a new proposal.","warning"):"";
  return `<section class="panel"><p class="eyebrow">ACTIVE LOCAL GUIDANCE</p><h3>${esc(active.data.definition.name)}</h3><p>${esc(active.data.definition.pattern)}</p>${notice("Optional method for a new original brief. Supplied holdout conditions passed; this is not a causal performance promise or permission to publish.")}${button("Use method in a new brief","learning-use-brief",`data-id="${esc(active.id)}"`)}</section>`;
}

function learningSetup(title,message) {
  modal(title,`<div class="modal-content">${notice(message,"warning")}<div class="toolbar">${button("Open experiments","learning-results")}${button("Prepare an original brief","production-prepare")}${button("Open app review access","learning-access")}</div></div>`);
}

function learningLinkForm(experimentId=null,arm="control") {
  const experiments=state.workspace.experiments || [],briefs=state.workspace.briefs || [],costs=learningWorkspace().cost_options;
  if(!experiments.length||!briefs.length)return learningSetup("Set up creative outcome evidence","Register an experiment and prepare original briefs first. The selected brief must include the exact variant asset. Import delivery-cost rows through the event ledger.");
  const e=experiments.find(e=>e.id===experimentId)||experiments[0],old=learningWorkspace().links.find(r=>r.experiment_id===e.id&&r.arm===arm);
  const d=old?.data.request||{};
  modal("Link creative to observed outcomes",`<form id="learning-link-form" data-app="${esc(state.app)}" data-options="${esc(JSON.stringify(costs))}"><div class="modal-content">${notice("Choose an actually observed publication receipt and exact incurred creative cost rows. These are operator-supplied records, not verified provider delivery.")}<div class="form-grid">${choiceField("experiment_id",experiments.map(e=>({id:e.id,title:e.data.name})),e.id)}${choiceField("arm",["control","treatment"].map(id=>({id,title:label(id)})),arm)}<div id="learning-link-choices"></div>${field("publication_url",d.publication_url||"","url","HTTPS publication receipt for this exact creative")}${field("published_at",d.published_at||"","text","Observed timezone timestamp within this acquisition window")}</div><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit">Save exact outcome link</button></div></form>`,"OUTCOMES / SOURCE LINK");
  learningLinkChoices($("#learning-link-form"));
}

function learningLinkChoices(form) {
  const e=state.workspace.experiments.find(e=>e.id===form.elements.experiment_id.value),arm=form.elements.arm.value;
  const old=learningWorkspace().links.find(r=>r.experiment_id===e.id&&r.arm===arm),costs=JSON.parse(form.dataset.options);
  form.dataset.version=old?.version||"";
  const briefs=(state.workspace.briefs||[]).filter(b=>b.current.data.records.some(r=>r.kind==="asset"&&r.id===e.data[arm].asset_id&&r.hash===e.data[arm].asset_hash));
  const choices=costs.map((c,i)=>({c,i})).filter(({c})=>c.cohort_id===e.data[arm].cohort_id);
  $("#learning-link-choices").innerHTML=choiceField("brief_id",briefs.map(b=>({id:b.id,title:b.current.data.definition.objective})),old?.data.request.brief_id)+choiceField("cost_events",choices.map(({c,i})=>({id:String(i),title:`${money(c.amount_minor,c.currency)} · ${c.source} · ${c.event_id}`})),old?.data.request.cost_events.map(c=>String(costs.findIndex(v=>v.provider===c.provider&&v.event_id===c.event_id))),true)+notice("Acquisition window: "+e.data[arm].cohort.starts_at+" to "+e.data[arm].cohort.ends_at);
}

function learningProposalForm() {
  if(!learningRole("MAKER"))return learningSetup("Verified maker access required","Sign in with your own GitHub account and establish or request this app's maker role in Activity.");
  const tests=(state.workspace.experiments||[]).filter(e=>e.state==="DECIDED");
  if(!tests.length)return learningSetup("Complete a training experiment","Observe and evaluate a mature experiment, link both creative arms, then record a current next-test decision. No learning is inferred from views.");
  modal("Propose an original creative method",`<form id="learning-propose-form" data-app="${esc(state.app)}"><div class="modal-content">${notice("Write your original method as a hypothesis. Choose the practical holdout threshold now, before seeing the future test's outcomes.")}<div class="form-grid">${choiceField("training_experiment_id",tests.map(e=>({id:e.id,title:e.data.name})))}${field("name","","text","Short name for this original method")}${field("pattern","","textarea","Specific creative method to test; no unsupported product claims")}${field("minimum_holdout_difference",.1,"number","Minimum lower-bound improvement in the primary rate, as a fraction").replace('step="1"','step="any" max="1"')}</div><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit">Freeze proposal and training evidence</button></div></form>`,"LEARNING / DECLARATION");
}

function learningLinkOpen(experiment,arm) {
  const row=learningWorkspace().links.find(r=>r.experiment_id===experiment&&r.arm===arm);if(!row)return;
  modal("Creative outcome source",`<div class="modal-content"><p>${esc(row.data.brief.data.definition.objective)}</p><p><a href="${esc(row.data.request.publication_url)}" target="_blank" rel="noopener noreferrer">Open supplied publication receipt ↗</a></p>${notice("Publication authenticity: OPERATOR SUPPLIED. Production cost allocation is already included in the delivery ledger.")}<p>Allocated creative cost: ${money(row.data.production_cost_minor,row.data.variant.cohort.currency)}</p>${row.findings.map(i=>notice(i,"warning")).join("")}<details><summary>Inspect exact creative, cohort and cost provenance</summary><pre>${json(row)}</pre></details></div><div class="modal-actions">${button("Correct outcome link","learning-link",`data-experiment="${esc(experiment)}" data-arm="${esc(arm)}"`)}</div>`,"OUTCOMES / EVIDENCE");
}

function learningOpen(id) {
  const row=learningProgram(id);if(!row)return;
  const mine=reviewIdentity().principal===row.preparer,role=myReviewRole(),current=row.availability==="CURRENT",actions=[];
  if(mine&&current&&row.state==="PROPOSED")actions.push(button("Reserve untouched holdout","learning-action",`data-id="${esc(id)}" data-operation="reserve"`));
  if(mine&&["RESERVED","READY","REJECTED"].includes(row.state))actions.push(button("Evaluate current holdout","learning-action",`data-id="${esc(id)}" data-operation="evaluate"`));
  if(!mine&&current&&learningRole("CHECKER")&&row.state==="READY")actions.push(button("Review exact local adoption","learning-action",`data-id="${esc(id)}" data-operation="approve"`));
  if(mine&&current&&row.state==="APPROVED")actions.push(button("Activate local guidance","learning-action",`data-id="${esc(id)}" data-operation="activate"`));
  if(row.active)actions.push(button("Use in a new brief","learning-use-brief",`data-id="${esc(id)}"`));
  if(learningWorkspace().active_id===id&&(mine||role?.role==="OWNER"))actions.push(button("Roll back local guidance","learning-action",`data-id="${esc(id)}" data-operation="rollback"`));
  const result=row.data.evaluation,source=result?.holdout?.assessment;
  modal(row.data.definition.name,`<div class="modal-content"><p class="eyebrow">${esc(row.state)} · VERSION ${row.version}</p><h3>Original method</h3><p>${esc(row.data.definition.pattern)}</p><p>Predeclared minimum lower-bound difference: ${percent(row.data.definition.minimum_holdout_difference)}</p><p class="description">Maker ${esc(row.preparer)} · exact hash ${esc(row.hash)}</p>${notice("Adoption influences only explicitly requested new local briefs. It does not authorize publication, spending, product claims or policy changes.")}${row.restored?notice("Imported history only. Authenticated approval was not transferred and this version cannot become active.","warning"):""}${row.findings.map(i=>notice(i,"warning")).join("")}${result?'<h3>Current saved holdout result</h3>'+status(result.outcome)+(result.issues||[]).map(i=>notice(i,"warning")).join(""):""}${source?'<p>Control primary rate '+percent(source.effect.control_rate)+' · treatment '+percent(source.effect.treatment_rate)+'</p><p>Lower 95% difference bound '+percent(source.effect.interval[0])+'</p><p>Contribution per install: control '+money(result.contribution_per_install.control,row.data.training.experiment.data.control.cohort.currency)+' · treatment '+money(result.contribution_per_install.treatment,row.data.training.experiment.data.control.cohort.currency)+'</p>':""}${mine&&row.state==="READY"?notice("A different current checker must approve this exact version before you activate it."):""}<details><summary>Inspect source links, fixed analysis, approvals and history</summary><pre>${json(row)}</pre></details><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions">${actions.join("")}${button("Download exact history","learning-download",`data-id="${esc(id)}"`)}</div>`,"LEARNING / SOURCE-BOUND REVIEW");
}

function learningActionForm(id,operation) {
  const row=learningProgram(id);if(!row)return;
  let controls="",confirmation="";
  if(operation==="reserve") {
    const tests=(state.workspace.experiments||[]).filter(e=>e.state==="PLANNED"&&new Date(e.created)>new Date(row.created)&&new Date(e.data.control.cohort.starts_at)>new Date());
    if(!tests.length)return learningSetup("Register a new holdout first","Create new future event cohorts and a planned experiment after this proposal. Do not import any exposure or outcome events before reservation.");
    controls=choiceField("experiment_id",tests.map(e=>({id:e.id,title:e.data.name})))+["control","treatment"].map(arm=>choiceField(arm+"_brief_id",(state.workspace.briefs||[]).map(b=>({id:b.id,title:label(arm)+": "+b.current.data.definition.objective})))).join("");
    confirmation="I confirm the treatment tests this exact original method and this holdout has no observed events.";
  }
  if(operation==="approve")confirmation="I independently reviewed this exact method, source links, predeclared threshold and supplied holdout result. I approve local guidance only.";
  if(operation==="activate")confirmation="Activate this exact approved method for optional new local briefs. No external publication or spending.";
  if(operation==="rollback"){controls=field("reason","","textarea","Why local guidance should be rolled back");confirmation="Roll back the actual active local guidance, restoring an eligible previous method or ordinary preparation.";}
  const confirm=confirmation?`<label class="check-row"><input type="checkbox" name="confirm" value="true" required> ${esc(confirmation)}</label>`:notice("Recompute against current supplied outcomes and sources. Missing proof is recorded as rejected; it cannot become a winner.");
  modal(label(operation)+" local learning",`<form id="learning-action-form" data-app="${esc(state.app)}" data-id="${esc(id)}" data-operation="${esc(operation)}" data-version="${row.version}" data-hash="${esc(row.hash)}"><div class="modal-content"><p>${esc(row.data.definition.pattern)}</p><div class="form-grid">${controls}</div>${confirm}<div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit">${esc(label(operation))}</button></div></form>`,"LEARNING / EXPLICIT ACTION");
}

async function learningSubmit(event) {
  const form=event.target;
  if(!["learning-link-form","learning-propose-form","learning-action-form"].includes(form.id))return;
  event.preventDefault();const app=form.dataset.app,values=Object.fromEntries(new FormData(form)),submit=form.querySelector('[type="submit"]');
  submit.disabled=true;form.querySelector("#form-error").textContent="";
  try {
    let path=`/api/apps/${app}/learning`,body=values;
    if(form.id==="learning-link-form") {
      const options=JSON.parse(form.dataset.options);values.cost_events=new FormData(form).getAll("cost_events").map(i=>({provider:options[Number(i)].provider,event_id:options[Number(i)].event_id}));
      body={data:values,version:form.dataset.version?Number(form.dataset.version):null};path+="/links";
    } else if(form.id==="learning-propose-form")body.minimum_holdout_difference=Number(body.minimum_holdout_difference);
    else {
      path+=`/${form.dataset.id}/${form.dataset.operation}`;body={version:Number(form.dataset.version),hash:form.dataset.hash,...values};delete body.confirm;
      const names={reserve:"confirm_pattern_test",approve:"confirm_local_guidance",activate:"confirm_activate",rollback:"confirm_rollback"};
      if(names[form.dataset.operation])body[names[form.dataset.operation]]=values.confirm==="true";
    }
    const result=await api(path,body),active=form.isConnected&&$("#modal").open;
    if(state.app===app) {await refresh();if(active&&form.isConnected){if(form.id==="learning-link-form")learningLinkOpen(result.experiment_id,result.arm);else learningOpen(result.id);}}
  } catch(error) {if(form.isConnected)form.querySelector("#form-error").textContent=error.message;else toast(error.message);}
  finally{submit.disabled=false;}
}

async function learningClick(event) {
  const node=event.target.closest('[data-action^="learning-"]');if(!node)return;
  const action=node.dataset.action,id=node.dataset.id;
  if(action==="learning-link")return learningLinkForm(node.dataset.experiment,node.dataset.arm||"control");
  if(action==="learning-link-open")return learningLinkOpen(node.dataset.experiment,node.dataset.arm);
  if(action==="learning-propose")return learningProposalForm();
  if(action==="learning-open")return learningOpen(id);
  if(action==="learning-action")return learningActionForm(id,node.dataset.operation);
  if(action==="learning-download")return download(`${state.app}-learning-history.json`,learningProgram(id));
  if(action==="learning-use-brief")return briefForm(null,id);
  if(["learning-results","learning-access"].includes(action)){$("#modal").close();state.view=action.endsWith("access")?"activity":"results";render();}
}

document.addEventListener("submit",learningSubmit);
document.addEventListener("click",learningClick);
document.addEventListener("change",event=>{
  const form=event.target.closest("#learning-link-form");
  if(form&&["experiment_id","arm"].includes(event.target.name))learningLinkChoices(form);
});
