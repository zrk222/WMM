"use strict";

const spyTokDiscovery = Object.freeze({
  all: {title:"All categories",path:"/top-posts"},
  business: {title:"Business / productivity",path:"/top-posts/business"},
  lifestyle: {title:"Lifestyle",path:"/top-posts/lifestyle"},
  demo: {title:"App demonstrations",path:"/top-posts/app-demo"},
  business_demo: {title:"Business app demonstrations",path:"/top-posts/business-app-demo"},
  problem: {title:"Problem / solution",path:"/top-posts/problem-solution"}
});

function spyTokLink(key) {
  if(!Object.hasOwn(spyTokDiscovery,key))throw new Error("Unknown discovery destination.");
  return "https://spytok.com"+spyTokDiscovery[key].path;
}

function spyTokPanel() {
  return `<section class="panel" id="spytok-workflow"><div class="section-heading"><div><p class="eyebrow">CREATIVE DISCOVERY TO LAUNCH</p><h2>A clear path from reference to results</h2></div>${button("Open creative workflow","spytok-open")}</div><p>Review this app’s job and audience, find a feasible format, inspect the source, then connect an original brief to search and measured outcomes.</p><p class="description">SpyTok is optional public research. Imports use your permitted sources; supplier API access and performance claims remain unverified.</p></section>`;
}

function spyTokHandoff() {
  const w=state.workspace,a=w.app;
  if(a.id!==state.app)throw new Error("Workspace changed; reload before downloading.");
  const refs=(w.references||[]),analyses=(w.analyses||[]),briefs=(w.briefs||[]);
  if([...refs,...analyses,...briefs].some(r=>r.current?.app_id!==a.id||(r.app_id!==undefined&&r.app_id!==a.id)))throw new Error("Foreign app artifact rejected.");
  const identity=r=>({id:r.id,version:r.current.version,hash:r.current.hash});
  return {schema:"growth.creative-workflow-handoff.v1",status:"PREPARED_HANDOFF",app_id:a.id,
    app_version:a.version,profile:{name:a.data.name,job:a.data.job,audience:a.data.audience,activation:a.data.activation,release:a.data.release,locale:a.data.locale},
    source_binding:w.preparation?.source_hash||null,
    references:refs.map(identity),analyses:analyses.map(r=>({...identity(r),source_status:r.source_status})),
    briefs:briefs.map(r=>({...identity(r),evidence_status:r.evidence_status})),
    questions:{product:["What does the user do?","What useful output can be shown?","When is first value reached?"],
      audience:["Which real problem motivates use?","Which permitted source supports the wording?","What prevents trying or switching?"],
      production:["Which formats can the team make?","Which authentic screens and rights are available?","Which constraints exclude this format?"]},
    discovery:Object.keys(spyTokDiscovery).map(key=>({title:spyTokDiscovery[key].title,url:spyTokLink(key)})),
    evidence:{runtime:"ev_0e8bf958e7d2eef75e7a87993f55f78bdeb925d462e1a2ebf8d1434c67b0c6e9",client_schema:"ev_a56672b6d8c2fed54df1208ed32aa803e682c3b3331875bf1ec5dff0486e70fe"},
    supplier_api:"UNVERIFIED",external_execution:"NOT_RUN",growth_results:"NOT_RUN",authorized_spend_minor:0};
}

function openSpyTokWorkflow() {
  const refs=state.workspace.references||[];
  const step=(title,text,action,caption)=>`<section class="next-step"><div><h3>${esc(title)}</h3><p>${esc(text)}</p>${button(caption,"spytok-local",`data-next="${action}"`)}</div></section>`;
  modal("Creative discovery to measured outcomes",`<div class="modal-content">${notice("This guide uses your current app workspace. It does not contact SpyTok, generate evidence, connect a supplier account or publish anything.")}
    ${step("1. Review product and audience","Define the real user action, first useful result, audience and current release. Generated descriptions are hypotheses until checked.","profile","Review app setup")}
    <section class="next-step"><div><h3>2. Find a feasible mechanism</h3><p>Choose a category or narrative. Assess talent, editing ability, authentic output, rights and production cost before selecting a reference.</p><label class="field" for="spytok-discovery">Public discovery page<select id="spytok-discovery">${Object.keys(spyTokDiscovery).map(k=>`<option value="${k}">${esc(spyTokDiscovery[k].title)}</option>`).join("")}</select></label><a class="button outline" id="spytok-discovery-link" href="${spyTokLink("all")}" target="_blank" rel="noopener noreferrer">Open selected SpyTok page ↗</a></div></section>
    ${step("3. Capture permitted source facts","Save the original public post link, observation time, metric unit and rights. A category summary is not a creator baseline or an install count.","source","Add a permitted source")}${button("Preview a permitted export","spytok-local",'data-next="import"')}
    <label class="field" for="spytok-reference">Source to inspect<select id="spytok-reference"><option value="">Choose an existing source</option>${refs.map(r=>`<option value="${esc(r.id)}">${esc(r.current.data.title)}</option>`).join("")}</select></label>
    ${step("4. Inspect hook and mechanism","Record observed phases and actual timing; keep suggestions separate. If no source exists, the next control opens source setup.","inspect","Inspect selected source")}
    ${step("5. Review app fit and slate","Compare comparable attention and app relevance. Unknown baselines stay unknown. Review the rationale and production constraints.","ranking","Open ranking controls")}
    ${step("6. Prepare original work","Bind current approved claims, authentic screens and tested destinations. Prepare channel-specific hooks and beats; missing proof opens setup.","brief","Prepare an original brief")}
    ${step("7. Connect ASA and AEO","Carry the source problem into an app-specific query and answer-page chain. Views never become search demand, bids or citations.","acquisition","Map an acquisition intent")}
    ${step("8. Render and review","Inspect the original brief and its local rendering controls. Confirm legibility, authenticity and rights before a separate publication action.","render","Open production controls")}
    ${step("9. Measure useful outcomes","Register the cohort, cost and analysis plan. Observe activation, payers, retention and refunds; missing attribution remains unknown.","experiment","Open experiment setup")}
    <div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions">${button("Download current handoff","spytok-download")}${button("Close","close")}</div>`,"SOURCE → ORIGINAL WORK → MEASURED OUTCOME");
  $("#spytok-discovery").addEventListener("change",event=>{$("#spytok-discovery-link").href=spyTokLink(event.target.value);});
  $("#spytok-discovery-link").insertAdjacentHTML("afterend",button("Set up team capability","capability-profile"));
  $("#spytok-reference").closest("label").insertAdjacentHTML("afterend",button("Review selected source requirements","spytok-local",'data-next="requirements"'));
}

function spyTokAction(node) {
  const action=node.dataset.action;
  if(action==="spytok-open")return openSpyTokWorkflow();
  if(action==="spytok-download")return download(`${state.app}-creative-handoff.json`,spyTokHandoff());
  if(action!=="spytok-local")throw new Error("Unknown creative workflow action.");
  const research=()=>{$("#modal").close();state.view="research";render();};
  const handlers={profile:()=>appForm(false),source:referenceForm,import:referenceImportForm,requirements:()=>capabilityForm("requirement",$("#spytok-reference").value),
    inspect:()=>{const id=$("#spytok-reference").value;if(!id)return referenceForm();if(!state.workspace.references.some(r=>r.id===id))throw new Error("Source changed; reload.");return inspectionForm(id);},
    ranking:research,brief:briefForm,acquisition:acqIntentForm,render:research,experiment:experimentForm};
  if(!Object.hasOwn(handlers,node.dataset.next))throw new Error("Unknown creative workflow step.");
  return handlers[node.dataset.next]();
}
