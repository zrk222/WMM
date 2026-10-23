/* Supplied public evidence -> narrow testable work. Never establishes demand or approval. */
(function(root,factory){
  "use strict";
  const value=factory();
  if(typeof module==="object"&&module.exports)module.exports=value;
  else root.WMMCustomerWorkflow=value;
})(typeof globalThis==="object"?globalThis:this,function(){
  "use strict";
  const MAX_HISTORY=1000,MAX_SOURCES=100,MAX_FEATURES=20,MAX_EXCLUSIONS=20;
  const escape=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const human=value=>String(value??"Unavailable").replaceAll("_"," ").toLowerCase();
  const button=(label,action,id="")=>`<button type="button" class="button outline" data-action="customer-${escape(action)}" data-id="${escape(id)}">${escape(label)}</button>`;
  const BASICS=["buyer","micro_behavior","desired_outcome","release","locale","currency","prototype_test"];
  const SOURCE_FIELDS=["url","content_sha256","observed_at","expires_at","availability","excerpt","evidence_type","frequency","impact"];

  function context(state){
    const app=state.workspace?.app,value=state.workspace?.subscription_growth;
    if(app?.id!==state.app||value?.app_id!==state.app||value.context.manifest_version!==app.version)throw new Error("Load the selected app and current customer evidence before continuing.");
    if(value.customer_workflows?.app_id!==state.app)throw new Error("Customer evidence is unavailable or belongs to another app.");
    return value.customer_workflows;
  }

  function history(state){
    return context(state).history.slice(0,MAX_HISTORY);
  }

  function selected(state,id){
    const row=history(state).find(item=>item.id===id);
    if(!row)throw new Error("This customer workflow is unavailable in the selected app.");
    return row;
  }

  function metrics(rows){
    const sources=rows.flatMap(row=>row.data.sources),features=rows.flatMap(row=>row.data.features);
    return [{label:"Saved workflow versions",value:rows.length,unit:"versions",source:"customer_workflows.history"},
      {label:"Supplied observations",value:sources.length,unit:"observations across saved versions",source:"customer_workflows.history; versions may reuse observations"},
      {label:"Proposed features",value:features.length,unit:"proposals across saved versions",source:"customer_workflows.history; proposals are not delivered features"},
      {label:"Sources needing review",value:rows.reduce((total,row)=>total+row.readout.unavailable_source_ids.length,0),unit:"source references across versions",source:"customer_workflows.history.readout; not unique people"}];
  }

  function panel(state){
    let rows;
    try{rows=history(state);}catch(error){return `<section class="panel"><h2>Customer evidence</h2><p role="status">${escape(error.message)}</p>${button("Retry workspace","refresh")}</section>`;}
    const counts=metrics(rows).map(item=>`<div><span>${escape(item.label)}</span><strong>${item.value}</strong><small>${escape(item.unit)}</small></div>`).join("");
    return `<section class="panel" id="customer-workflow-panel" aria-labelledby="customer-workflow-title"><p class="eyebrow">CUSTOMER EVIDENCE / A SMALLER USEFUL TEST</p><h2 id="customer-workflow-title">Start with a problem someone actually described</h2><p>Record who needs help and the small task they are trying to finish. Link each proposed feature to an inspected public observation. Say what you will leave out, then describe a test that could prove your idea wrong.</p><div class="page-metric-grid">${counts}</div><p class="description">${escape(state.workspace.app.data.name)} · evaluated ${escape(state.workspace.subscription_growth.observed_at)}. Counts include every saved version; they are not unique customers or verified demand.</p><div class="toolbar">${button("Record customer workflow","create")}${button("Report / Save PDF","report")}</div>${historyList(rows)}<p class="description">A quote, hash, stated willingness to pay or proposed feature cannot establish paid behavior, product demand or approval to execute.</p></section>`;
  }

  function historyList(rows){
    if(!rows.length)return "<p>No workflows saved yet. Begin with one inspected observation and one feature it supports.</p>";
    return `<h3>Saved customer workflows</h3><div class="record-list">${rows.map(row=>`<button type="button" class="record-row" data-action="customer-detail" data-id="${escape(row.id)}"><span class="record-main"><strong>${escape(row.data.micro_behavior)}</strong><small>${escape(row.created)} · ${row.imported?"imported assertion":"supplied local research"}</small></span><span>${escape(human(row.readout.status))}</span></button>`).join("")}</div>`;
  }

  function blankSource(uuid){
    return {id:uuid(),url:"",content_sha256:"",observed_at:"",expires_at:"",availability:"AVAILABLE",excerpt:"",evidence_type:"FIRSTHAND_COMPLAINT",frequency:"",impact:""};
  }

  function newDraft(state,uuid,id=""){
    if(id)return JSON.parse(JSON.stringify(selected(state,id).data));
    context(state);
    const app=state.workspace.app.data,source=blankSource(uuid);
    return {buyer:"",micro_behavior:"",desired_outcome:"",release:app.release||"",locale:app.locale||"",currency:app.currency||"",prototype_test:"",sources:[source],features:[{id:uuid(),description:"",source_ids:[source.id],validation:""}],excluded_features:[{feature:"",reason:""}]};
  }

  function field(name,label,value="",textarea=false,hint=""){
    const id="customer-"+name.replaceAll(".","-");
    const description=hint?`aria-describedby="${id}-hint"`:"";
    const control=textarea?`<textarea id="${id}" name="${escape(name)}" rows="3" required ${description}>${escape(value)}</textarea>`:`<input id="${id}" name="${escape(name)}" value="${escape(value)}" required ${description}>`;
    return `<div class="field"><label for="${id}">${escape(label)}</label>${control}${hint?`<small id="${id}-hint">${escape(hint)}</small>`:""}</div>`;
  }

  function choice(name,label,value,options){
    const id="customer-"+name.replaceAll(".","-");
    return `<div class="field"><label for="${id}">${escape(label)}</label><select id="${id}" name="${escape(name)}" required>${options.map(([key,text])=>`<option value="${escape(key)}" ${key===value?"selected":""}>${escape(text)}</option>`).join("")}</select></div>`;
  }

  function basics(draft){
    const labels={buyer:"Who needs help?",micro_behavior:"The small task they are trying to finish",desired_outcome:"The outcome they want",release:"App release",locale:"Locale",currency:"Currency",prototype_test:"How will you test this workflow?"};
    return `<fieldset><legend>One person, one useful task</legend><div class="form-grid">${BASICS.map(name=>field(name,labels[name],draft[name],["desired_outcome","prototype_test"].includes(name))).join("")}</div></fieldset>`;
  }

  function sourceRow(row,index){
    const prefix="sources."+index+".";
    return `<fieldset data-customer-source="${escape(row.id)}"><legend>Observation ${index+1}</legend><p>Use permitted public excerpts only, without contact details or private transcripts.</p><div class="form-grid">${field(prefix+"url","Original public source URL",row.url)}${field(prefix+"content_sha256","Inspected content SHA256",row.content_sha256)}${field(prefix+"observed_at","Inspected at (ISO timestamp)",row.observed_at)}${field(prefix+"expires_at","Review expires at (ISO timestamp)",row.expires_at)}${choice(prefix+"availability","Source availability",row.availability,[["AVAILABLE","Available"],["REMOVED","Removed"],["UNKNOWN","Unknown"]])}${choice(prefix+"evidence_type","What did you inspect?",row.evidence_type,[["FIRSTHAND_COMPLAINT","Firsthand complaint"],["OBSERVED_WORKFLOW","Observed workflow"],["STATED_WILLINGNESS_TO_PAY","Stated willingness to pay (unverified)"],["OBSERVED_PAID_BEHAVIOR","Supplied paid-behavior evidence (unverified)"]])}${field(prefix+"excerpt","Short public excerpt",row.excerpt,true,"Up to 500 characters. No email addresses or personal contact details.")}${field(prefix+"frequency","How often does the source describe this?",row.frequency)}${field(prefix+"impact","Observed impact and what remains unmeasured",row.impact,true)}</div>${button("Remove observation "+(index+1),"remove-source",row.id)}</fieldset>`;
  }

  function sourceLinks(row,index,sources){
    const id="customer-feature-sources-"+index,name="features."+index+".source_ids";
    return `<div class="field"><label for="${id}">Supporting observations for feature ${index+1}</label><select id="${id}" name="${name}" multiple required aria-describedby="${id}-hint">${sources.map((source,position)=>`<option value="${escape(source.id)}" ${row.source_ids.includes(source.id)?"selected":""}>Observation ${position+1}: ${escape(source.excerpt||"Excerpt not entered")}</option>`).join("")}</select><small id="${id}-hint">Select every supporting observation. On a desktop, use Ctrl or Command to select more than one. Removing an observation requires checking the remaining links.</small></div>`;
  }

  function featureRow(row,index,sources){
    const prefix="features."+index+".";
    return `<fieldset data-customer-feature="${escape(row.id)}"><legend>Proposed feature ${index+1}</legend><div class="form-grid">${field(prefix+"description","The smallest feature this evidence supports",row.description,true)}${sourceLinks(row,index,sources)}${field(prefix+"validation","What observation would support or reject this feature?",row.validation,true)}</div>${button("Remove feature "+(index+1),"remove-feature",row.id)}</fieldset>`;
  }

  function exclusionRow(row,index){
    const prefix="excluded_features."+index+".";
    return `<fieldset><legend>Excluded feature ${index+1}</legend><div class="form-grid">${field(prefix+"feature","What will you leave out?",row.feature)}${field(prefix+"reason","Why does it fall outside this workflow?",row.reason,true)}</div>${button("Remove exclusion "+(index+1),"remove-exclusion",String(index))}</fieldset>`;
  }

  function formHTML(draft){
    return `${basics(draft)}<h3>Inspected observations</h3>${draft.sources.map(sourceRow).join("")}${button("Add observation","add-source")}<h3>Features tied to evidence</h3>${draft.features.map((row,index)=>featureRow(row,index,draft.sources)).join("")}${button("Add proposed feature","add-feature")}<h3>Keep the scope small</h3>${draft.excluded_features.map(exclusionRow).join("")}${button("Add excluded feature","add-exclusion")}`;
  }

  function openForm(deps,id=""){
    const draft=newDraft(deps.state,deps.uuid,id);
    deps.modal(id?"Prepare a revised workflow":"Record a customer workflow",`<form id="customer-workflow-form" data-app="${escape(deps.state.app)}" data-version="${deps.state.workspace.app.version}" data-id="${escape(deps.uuid())}"><div class="modal-content"><p>Save a narrow, source-linked hypothesis. This records supplied research; it cannot verify demand or authorize a provider action. A revised version retains the original and needs its own current source review.</p><div id="customer-draft-fields">${formHTML(draft)}</div><p id="customer-draft-message" role="status"></p><div id="customer-form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button type="submit" class="button">Save customer workflow</button></div></form>`,"CUSTOMER EVIDENCE");
    deps.document.getElementById("customer-workflow-form").customerDraft=draft;
  }

  function capture(form,FormData){
    const values=new FormData(form),draft=form.customerDraft;
    const result=Object.fromEntries(BASICS.map(name=>[name,values.get(name)]));
    result.sources=draft.sources.map((row,index)=>({id:row.id,...Object.fromEntries(SOURCE_FIELDS.map(name=>[name,values.get("sources."+index+"."+name)]))}));
    result.features=draft.features.map((row,index)=>({id:row.id,description:values.get("features."+index+".description"),validation:values.get("features."+index+".validation"),source_ids:values.getAll("features."+index+".source_ids")}));
    result.excluded_features=draft.excluded_features.map((_,index)=>Object.fromEntries(["feature","reason"].map(name=>[name,values.get("excluded_features."+index+"."+name)])));
    return result;
  }

  function addRow(draft,kind,uuid){
    const lists={source:[draft.sources,MAX_SOURCES,()=>blankSource(uuid)],feature:[draft.features,MAX_FEATURES,()=>({id:uuid(),description:"",source_ids:[],validation:""})],exclusion:[draft.excluded_features,MAX_EXCLUSIONS,()=>({feature:"",reason:""})]};
    const rule=lists[kind];
    if(!rule)throw new Error("Unknown customer workflow row.");
    if(rule[0].length>=rule[1])throw new Error("This workflow allows at most "+rule[1]+" "+kind+" rows.");
    rule[0].push(rule[2]());
    return draft;
  }

  function removeRow(draft,kind,id){
    const list={source:draft.sources,feature:draft.features,exclusion:draft.excluded_features}[kind];
    if(!list)throw new Error("Unknown customer workflow row.");
    if(list.length<=1)throw new Error("Keep at least one "+kind+" row, or close the unsaved form.");
    const index=kind==="exclusion"?Number(id):list.findIndex(row=>row.id===id);
    if(!Number.isInteger(index)||index<0||index>=list.length)throw new Error("This row changed. Reopen the intended workflow.");
    list.splice(index,1);
    if(kind==="source")draft.features=draft.features.map(row=>({...row,source_ids:row.source_ids.filter(source=>source!==id)}));
    return draft;
  }

  function editRows(node,deps){
    const form=deps.document.getElementById("customer-workflow-form");
    if(!form||form.dataset.pending==="true")return;
    const message=form.querySelector("#customer-draft-message");
    try{
      const draft=capture(form,deps.FormData),parts=node.dataset.action.split("-");
      if(parts[1]==="add")addRow(draft,parts[2],deps.uuid);
      else removeRow(draft,parts[2],node.dataset.id);
      form.customerDraft=draft;
      form.querySelector("#customer-draft-fields").innerHTML=formHTML(draft);
      message.textContent="Draft updated. Original inputs are retained. Check the supporting observations for every feature before saving.";
      message.tabIndex=-1;
      message.focus();
    }catch(error){message.textContent=error.message+" Draft inputs are preserved.";}
  }

  function payload(form,FormData,state){
    context(state);
    if(form.dataset.app!==state.app||Number(form.dataset.version)!==state.workspace.app.version)throw new Error("App setup changed. Reopen this workflow in the intended app.");
    return {id:form.dataset.id,manifest_version:Number(form.dataset.version),data:capture(form,FormData)};
  }

  async function submit(form,deps){
    if(form.dataset.pending==="true")return;
    const submitButton=form.querySelector('[type="submit"]'),error=form.querySelector("#customer-form-error");
    const fields=form.querySelector("#customer-draft-fields");
    form.dataset.pending="true";submitButton.disabled=true;error.textContent="";
    fields.inert=true;
    try{
      const body=payload(form,deps.FormData,deps.state);
      await deps.api(`/api/apps/${encodeURIComponent(form.dataset.app)}/customer-workflows`,body);
      if(deps.state.app!==form.dataset.app)return;
      await deps.refresh();
      if(deps.state.app===form.dataset.app&&form.isConnected)deps.close();
      deps.toast("Customer workflow saved with exact source links. Demand remains unverified.");
    }catch(failure){if(form.isConnected)error.textContent=failure.message+" Inputs are preserved. Correct the issue and retry.";}
    finally{form.dataset.pending="false";submitButton.disabled=false;fields.inert=false;}
  }

  function sourceNotes(source){
    return [`Observation ${source.id}: ${source.url}; SHA256 ${source.content_sha256}. Inspected ${source.observed_at}; expires ${source.expires_at}; availability ${human(source.availability)}; supplied type ${human(source.evidence_type)}.`,`Public excerpt: ${source.excerpt}`,`Frequency: ${source.frequency}. Impact: ${source.impact}.`];
  }

  function entryNotes(row){
    const data=row.data,readout=row.readout;
    const notes=[`Workflow ${row.id}; saved ${row.created}; source hash ${row.hash}; ${row.imported?"imported assertion":"supplied local research"}; current state ${human(readout.status)}.`,
      `App release ${data.release}; locale ${data.locale}; currency ${data.currency}. Buyer: ${data.buyer}. Task: ${data.micro_behavior}. Desired outcome: ${data.desired_outcome}.`,
      ...data.sources.flatMap(sourceNotes),...readout.features.map(feature=>`Feature ${feature.id}: ${feature.description}. Supporting observations: ${feature.source_ids.join(", ")}. Validation: ${feature.validation}. Current state: ${human(feature.state)}.`),
      ...data.excluded_features.map(item=>`Excluded: ${item.feature}. Reason: ${item.reason}.`),`Prototype test: ${data.prototype_test}.`,
      `Sources needing review: ${readout.unavailable_source_ids.join(", ")||"None flagged"}. Demand verified: false. Paid behavior verified: false.`];
    return notes;
  }

  function report(state,pageReports,id=""){
    const rows=id?[selected(state,id)]:history(state),value=context(state);
    return {...pageReports.model({...state,view:"results"}),title:id?"Customer workflow: "+id:"Customer evidence review",purpose:"Review supplied observations, the features they support and the scope excluded from this workflow.",next_step:"Inspect source freshness, correct the evidence gaps and run the proposed prototype test. Demand and paid behavior remain unverified.",loaded_at:state.workspace.subscription_growth.observed_at,filters:{scope:id?"Exact saved workflow "+id:"All saved customer workflow versions",source_hash:value.source_hash},metrics:metrics(rows),cohorts:[],notes:[...rows.flatMap(entryNotes),"Counts include saved versions and repeated source references; they are not unique customers. Imported and supplied research grants no execution authority. Private state and unsaved form inputs are excluded."]};
  }

  function detail(id,deps){
    const row=selected(deps.state,id),counts=metrics([row]);
    deps.modal("Saved customer workflow",`<div class="modal-content"><p>Inspect the original source-to-feature links and current freshness. A correction creates a new saved version and retains this one.</p><dl>${counts.map(item=>`<div><dt>${escape(item.label)}</dt><dd>${item.value} ${escape(item.unit)}</dd></div>`).join("")}</dl>${entryNotes(row).map(note=>`<p>${escape(note)}</p>`).join("")}</div><div class="modal-actions">${button("Prepare revised version","revise",id)}${button("Report / Save PDF","report",id)}</div>`,"CUSTOMER EVIDENCE HISTORY");
  }

  function action(node,deps){
    const mode=node.dataset.action.slice("customer-".length),id=node.dataset.id;
    if(mode.startsWith("add-")||mode.startsWith("remove-"))return editRows(node,deps);
    const actions={create:()=>openForm(deps),revise:()=>openForm(deps,id),detail:()=>detail(id,deps),refresh:()=>deps.refresh(),report:()=>deps.pageReports.openReport(report(deps.state,deps.pageReports,id),deps.browser)};
    if(!actions[mode])throw new Error("Unknown customer workflow action.");
    return actions[mode]();
  }
  return {context,history,selected,metrics,panel,historyList,blankSource,newDraft,field,choice,basics,sourceRow,sourceLinks,featureRow,exclusionRow,formHTML,openForm,capture,addRow,removeRow,editRows,payload,submit,sourceNotes,entryNotes,report,detail,action};
});
