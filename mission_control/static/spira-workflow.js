"use strict";

const spiraRecipes=Object.freeze({
  screen_demo:{name:"Show first value",channel:"SHORT_VIDEO",execution:"SCREEN_RECORDING",objective:"demonstrate one current, approved first-value workflow with a fictional example"},
  evidence_slides:{name:"Explain with evidence",channel:"SHORT_VIDEO",execution:"SLIDES",objective:"explain one real user problem and demonstrate the exact approved behavior with readable evidence"},
  linkedin_proof:{name:"LinkedIn product walkthrough",channel:"LINKEDIN",execution:null,objective:"walk through a specific user scenario, the exact approved behavior and a tested next step"},
  x_proof:{name:"X concise proof",channel:"X",execution:null,objective:"share one exact approved behavior and the tested destination without unsupported outcome claims"}
});

function spiraPanel() {
  return `<section class="panel" id="guided-production"><div class="section-heading"><div><p class="eyebrow">BRIEF → RECIPE → REVIEW → LEARN</p><h2>Your app’s content workflow</h2></div>${button("Open guided production","spira-open")}</div><p>Start with your saved app brief, choose a runnable recipe, review current proof and connect results to the next iteration.</p><p class="description">Inspired by Spira’s public workflow. Runs in Mission Control; no Spira account or private API is connected.</p></section>`;
}

function spiraScope() {
  const w=state.workspace;
  if(w.app.id!==state.app)throw new Error("App changed; reload the workflow.");
  const groups=[w.references,w.analyses,w.briefs,capabilityState().profile,capabilityState().requirement];
  if(groups.flatMap(g=>g||[]).some(r=>r.current?.app_id!==state.app||(r.app_id!==undefined&&r.app_id!==state.app)))throw new Error("Foreign app artifact rejected.");
  if((w.records||[]).some(r=>r.app_id!==state.app))throw new Error("Foreign app evidence rejected.");
  return w;
}

function spiraBrandBrief() {
  const w=spiraScope(),a=w.app;
  return {schema:"growth.app-brand-brief.v1",status:"PREPARED_HANDOFF",app_id:a.id,app_version:a.version,
    manifest:{name:a.data.name,job:a.data.job,audience:a.data.audience,first_value:a.data.activation,release:a.data.release,locale:a.data.locale,website:a.data.website||null},
    brand:{voice:a.data.brand_voice||null,visual_direction:a.data.brand_visual||null,source:a.data.brand_source||null,boundaries:a.data.brand_boundaries||null,excluded_claims:a.data.excluded_claims||[],status:"OPERATOR_SUPPLIED"},
    provenance:{basis:"Operator-saved app manifest; audience and job remain hypotheses until independently researched",preparation_hash:w.preparation?.source_hash||null},
    claim_candidates:w.records.filter(r=>r.kind==="claim"&&r.data.result==="PASS").map(r=>({id:r.id,hash:r.hash,claim:r.data.claim,release:r.data.release,locale:r.data.locale,checked_at:r.data.checked_at,status:"REVALIDATE_BEFORE_USE"})),
    capabilities:capabilityState().profile.map(r=>({id:r.id,version:r.current.version,hash:r.current.hash})),
    recipes:Object.entries(spiraRecipes).map(([id,r])=>({id,...r,status:"REQUIRES_CURRENT_PROOF"})),
    external_execution:"NOT_RUN",social_scheduling:"MANUAL_HANDOFF",supplier_api:"UNVERIFIED",outcomes:"NOT_MEASURED",authorized_spend_minor:0};
}

function spiraStep(title,text,action,caption) {
  return `<section class="next-step"><div><h3>${esc(title)}</h3><p>${esc(text)}</p>${button(caption,"spira-local",`data-next="${action}"`)}</div></section>`;
}

function brandBriefGuidance() {
  const a=state.workspace.app.data;
  return `<details><summary>App brand guidance · operator supplied</summary><p>Voice: ${esc(a.brand_voice||"Not supplied")}</p><p>Visual direction: ${esc(a.brand_visual||"Not supplied")}</p><p>Source: ${esc(a.brand_source||"Not supplied")}</p><p>Boundaries: ${esc(a.brand_boundaries||"Not supplied")}</p></details>`;
}

function openSpiraWorkflow() {
  const w=spiraScope(),a=w.app.data;
  modal("App-specific production workflow",`<div class="modal-content">${notice("Your current app and saved evidence drive this flow. External generation and social publication are separate handoffs; scheduled analysis is local.")}<section class="panel"><h3>1. Brand brief · ${esc(a.name)}</h3><p><strong>Audience:</strong> ${esc(a.audience||"Not supplied")}<br><strong>User job:</strong> ${esc(a.job||"Not supplied")}<br><strong>First value:</strong> ${esc(a.activation||"Not supplied")}</p><p class="description">Saved by your operator; these descriptions are not verified customer research.</p>${button("Edit app brief","spira-local",'data-next="profile"')} ${button("Download sourced brand brief","spira-download")}</section>
    ${spiraStep("2. Check production limits","Set actual available formats, talent, audio, capture, time and cost. Review each source’s requirements before adapting it.","capability","Review production readiness")}
    <section class="panel"><h3>3. Choose a runnable recipe</h3><p>Each recipe opens the existing evidence-bound brief editor. It does not copy a creator’s script or generate unsupported proof.</p>${choiceField("spira_recipe",Object.entries(spiraRecipes).map(([id,r])=>({id,title:r.name})),"screen_demo")}${choiceField("spira_source",(w.references||[]).map(r=>({id:r.id,title:r.current.data.title})))}${button("Start selected recipe","spira-recipe")}<p class="description">Reference-only inspiration is kept in the source library until inspected and cleared.</p>${button("Add inspiration source","spira-local",'data-next="source"')}</section>
    ${spiraStep("4. Preview, quote and review","Prepare the original brief, inspect local render controls and declared cost. Generation quotes and social delivery are not confirmed supplier capabilities.","production","Open briefs and render controls")}
    ${spiraStep("5. Plan the measurement schedule","Register an experiment and record exposure. Enable, pause and inspect scheduled evidence analysis from that experiment. This does not schedule a social post.","experiments","Open experiments and schedules")}
    ${spiraStep("6. Learn from useful outcomes","Review actual activation, payers, retention, refunds and contribution after costs. Missing or immature data remains unavailable.","results","Open measured results")}
    <div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions">${button("Close","close")}</div>`,"NATIVE GUIDED WORKFLOW / SPIRA RESEARCH");
}

function spiraNavigate(view) {
  $("#modal").close();state.view=view;return render();
}

function startSpiraRecipe(key,referenceId) {
  spiraScope();
  if(!Object.hasOwn(spiraRecipes,key))throw new Error("Choose a known runnable recipe.");
  const source=state.workspace.references.find(r=>r.id===referenceId);
  if(!source)return referenceForm();
  const recipe=spiraRecipes[key],evaluation=capabilityEvaluation(referenceId);
  if(evaluation.status!=="READY")return capabilitySetup();
  const p=evaluation.evidence.profile.data,q=evaluation.evidence.requirement.data;
  if(!p.channels.includes(recipe.channel))throw new Error("Recipe channel is outside declared capability; revise production readiness.");
  if(recipe.execution&&q.execution!==recipe.execution)throw new Error("This source uses a different execution format; choose a matching source or recipe.");
  const analysis=analysisFor(referenceId);
  if(!analysis||analysis.source_status!=="CURRENT")return inspectionForm(referenceId);
  return briefForm(null,null,{channel:recipe.channel,analysis_id:analysis.id,objective:recipe.objective});
}

function spiraAction(node) {
  const handlers={"spira-open":openSpiraWorkflow,"spira-download":()=>download(`${state.app}-brand-brief.json`,spiraBrandBrief()),"spira-recipe":()=>startSpiraRecipe($("#field-spira_recipe").value,$("#field-spira_source").value),"spira-local":()=>{
    const routes={profile:()=>appForm(false),capability:capabilitySetup,source:referenceForm,production:()=>spiraNavigate("research"),experiments:()=>spiraNavigate("results"),results:()=>spiraNavigate("results")};
    if(!Object.hasOwn(routes,node.dataset.next))throw new Error("Unknown workflow step.");
    return routes[node.dataset.next]();
  }};
  if(!Object.hasOwn(handlers,node.dataset.action))throw new Error("Unknown production workflow action.");
  return handlers[node.dataset.action]();
}
