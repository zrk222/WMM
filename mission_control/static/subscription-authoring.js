/* Explicit supplied billing observations and immutable paywall/offer experiments. */
(function(root,factory){"use strict";const value=factory();if(typeof module==="object"&&module.exports)module.exports=value;else root.WMMSubscriptionAuthoring=value;})(globalThis,function(){
  "use strict";
  const escape=value=>String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const button=(text,mode,id="")=>`<button type="button" class="button outline" data-action="subscription-plan-${mode}" data-id="${escape(id)}">${escape(text)}</button>`;
  const CONFIG_TEXT=["product_id","offer_id","storefront","variant_id","renewal_terms"];
  const CONFIG_NUMBERS=["price_minor","renewal_price_minor","trial_days","intro_days","billing_period_days"];
  const PLAN_TEXT=["name","owner","hypothesis","analysis_at","assignment_source","stop_rule","rollback_plan"];
  const PLAN_NUMBERS=["baseline_rate","minimum_detectable_effect","treatment_allocation"];
  const GUARDRAILS=["min_retention_rate","max_refund_fraction","min_contribution_minor","max_acquisition_minor"];

  function current(state){
    if(state.workspace?.app?.id!==state.app)throw new Error("Load the selected app before authoring a subscription test.");
    return state.workspace.app;
  }
  function sources(state){
    current(state);
    return state.workspace.records.filter(row=>row.kind==="billing"&&row.data.subscription_configuration);
  }
  function source(state,id){
    const row=sources(state).find(item=>item.id===id);
    if(!row)throw new Error("Choose saved subscription billing evidence from this app.");
    return row;
  }
  function panel(state){
    const rows=sources(state);
    return `<section class="panel" id="subscription-plan-panel"><h2>Plan a paywall or offer test</h2><p>Record the exact subscription terms and purchase, restore and eligibility checks for each version. Select two observation cohorts, name the outcome and register the comparison before acquisition begins.</p><p>${rows.length} saved configuration records · source: this app’s billing evidence. These are supplied observations, not authenticated provider acceptance.</p><div class="toolbar">${button("Record tested subscription terms","billing")}${button("Plan paywall or offer experiment","experiment")}</div>${rows.map(row=>`<p>${button(row.title,"detail",row.id)} · ${escape(row.data.result)} · checked ${escape(row.data.checked_at)} · expires ${escape(row.data.expires_at)}</p>`).join("")}</section>`;
  }
  function fields(mode,state,ui){
    return mode==="billing"?billingFields(state,ui):experimentFields(state,ui);
  }
  function billingFields(state,ui){
    const app=current(state).data;
    const choices={experiment_type:[["PAYWALL","Paywall"],["OFFER","Offer"]],access_method:[["FREEMIUM","Freemium"],["HARD","Hard paywall"],["SOFT","Soft paywall"],["METERED","Metered"]],placement:[["AFTER_ONBOARDING","After onboarding"],["AFTER_VALUE","After first value"],["METERED_LIMIT","At metered limit"]],platform:[["iOS","iOS"],["Android","Android"]],result:[["PASS","Passed supplied checks"],["FAIL","Failed supplied checks"]],eligibility_status:[["ELIGIBLE","Observed eligible"],["INELIGIBLE","Observed ineligible"],["UNTESTED","Not tested"]]};
    const basic=[ui.input("title","Evidence title"),ui.input("source","Test receipt or source reference"),ui.input("release","App release",app.release||""),ui.input("locale","Locale",app.locale||""),ui.input("currency","Currency",app.currency||""),ui.input("checked_at","Checked at (ISO timestamp)"),ui.input("expires_at","Evidence expires at (ISO timestamp)")];
    return `<p>Enter the actual tested terms. Prices are in currency minor units; durations use whole days. Saving records these observations and does not change a live paywall.</p><div class="form-grid">${basic.join("")}${Object.entries(choices).map(([name,values])=>ui.select(name,name.replaceAll("_"," "),values)).join("")}${CONFIG_TEXT.map(name=>ui.input(name,name.replaceAll("_"," "),"",name==="renewal_terms"?"textarea":"text")).join("")}${CONFIG_NUMBERS.map(name=>ui.input(name,name.replaceAll("_"," "),"","number")).join("")}</div><label><input name="restore_tested" type="checkbox"> I recorded an actual restore test</label><label><input name="trial_eligibility_tested" type="checkbox"> I recorded an actual trial / offer eligibility test</label>`;
  }
  function experimentFields(state,ui){
    const rows=sources(state),cohorts=(state.workspace.ledger||[]).map(row=>[row.cohort.cohort_id,row.cohort.cohort_id+" · "+row.cohort.starts_at]);
    const text=PLAN_TEXT.map(name=>ui.input(name,name.replaceAll("_"," "),"",["hypothesis","stop_rule","rollback_plan"].includes(name)?"textarea":"text")).join("");
    const numbers=[...PLAN_NUMBERS,...GUARDRAILS].map(name=>ui.input(name,name.replaceAll("_"," "),"","number")).join("");
    return `<p>Choose exact saved billing configurations and two different cohorts with matching release, locale, currency and dates. The server checks source freshness, terms, future acquisition and follow-up maturity. No creative asset is required for this typed test.</p>${!rows.length||!cohorts.length?"<p role=\"status\">Record billing configurations and define two event cohorts in the ledger before registering.</p>":""}<div class="form-grid">${text}${ui.select("primary_metric","Primary outcome",[["activation_rate","Useful activation"],["paid_conversion","Paid conversion"],["retention_rate","Retained value"]])}${ui.select("assignment_method","Assignment evidence",[["RANDOMIZED","Supplied randomized assignment"],["OBSERVATIONAL","Observational comparison"]])}${numbers}${["control","treatment"].map(arm=>ui.select(arm+"_cohort",arm+" cohort",cohorts)+ui.select(arm+"_source",arm+" billing configuration",rows.map(row=>[row.id,row.title+" · "+row.data.subscription_configuration.variant_id]))).join("")}</div>`;
  }
  function open(mode,deps){
    const app=current(deps.state);
    if(!["billing","experiment"].includes(mode))throw new Error("Unknown subscription authoring form.");
    deps.modal(mode==="billing"?"Record tested subscription terms":"Plan a paywall or offer experiment",`<form id="subscription-plan-form" data-app="${escape(app.id)}" data-version="${app.version}" data-mode="${mode}" data-id="${escape(deps.uuid())}"><div class="modal-content">${fields(mode,deps.state,deps.ui)}<div id="subscription-plan-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button type="submit" class="button">${mode==="billing"?"Save billing observations":"Register subscription experiment"}</button></div></form>`,"SUBSCRIPTION TEST");
    const form=deps.document.getElementById("subscription-plan-form");
    form.subscriptionSourceHashes=Object.fromEntries(sources(deps.state).map(row=>[row.id,row.hash]));
  }
  function billingData(values){
    const configuration={version:1,experiment_type:values.experiment_type,access_method:values.access_method,placement:values.placement,currency:values.currency};
    CONFIG_TEXT.forEach(name=>configuration[name]=values[name]);
    CONFIG_NUMBERS.forEach(name=>configuration[name]=Number(values[name]));
    return {release:values.release,platform:values.platform,locale:values.locale,currency:values.currency,result:values.result,sku:configuration.product_id,price_minor:configuration.price_minor,restore_tested:values.restore_tested==="on",trial_eligibility_tested:values.trial_eligibility_tested==="on",eligibility_status:values.eligibility_status,checked_at:values.checked_at,expires_at:values.expires_at,subscription_configuration:configuration};
  }
  function variant(arm,values,state,hashes){
    const row=source(state,values[arm+"_source"]);
    if(hashes[row.id]!==row.hash)throw new Error("Billing source changed. Reopen the experiment before registering.");
    return {variant_type:"SUBSCRIPTION",cohort_id:values[arm+"_cohort"],source_record_id:row.id,configuration:JSON.parse(JSON.stringify(row.data.subscription_configuration))};
  }
  function planData(values,state,hashes){
    const data=Object.fromEntries(PLAN_TEXT.map(name=>[name,values[name]]));
    PLAN_NUMBERS.forEach(name=>data[name]=Number(values[name]));
    data.primary_metric=values.primary_metric;data.assignment_method=values.assignment_method;
    data.guardrails=Object.fromEntries(GUARDRAILS.map(name=>[name,Number(values[name])]));
    for(const arm of ["control","treatment"])data[arm]=variant(arm,values,state,hashes);
    return data;
  }
  function payload(form,values,state){
    const app=current(state);
    if(form.dataset.app!==app.id||Number(form.dataset.version)!==app.version)throw new Error("App setup changed. Reopen this form in the intended app.");
    if(form.dataset.mode==="billing")return {path:`/api/apps/${encodeURIComponent(app.id)}/records`,body:{id:form.dataset.id,manifest_version:app.version,kind:"billing",title:values.title,source:values.source,data:billingData(values)}};
    if(form.dataset.mode!=="experiment")throw new Error("Unknown subscription form mode.");
    return {path:`/api/apps/${encodeURIComponent(app.id)}/experiments`,body:{...planData(values,state,form.subscriptionSourceHashes),manifest_version:app.version}};
  }
  async function submit(form,deps){
    if(form.dataset.pending==="true")return;
    const save=form.querySelector('[type="submit"]'),error=form.querySelector("#subscription-plan-error");
    form.dataset.pending="true";save.disabled=true;error.textContent="";
    try{
      const request=payload(form,Object.fromEntries(new deps.FormData(form)),deps.state);
      await deps.api(request.path,request.body);
      if(deps.state.app!==form.dataset.app)return;
      await deps.refresh();
      if(deps.state.app===form.dataset.app&&form.isConnected)deps.close();
      deps.toast("Subscription evidence saved. Review the exact source and experiment history.");
    }catch(failure){if(form.isConnected)error.textContent=failure.message+" Inputs are preserved. Correct the issue and retry.";}
    finally{form.dataset.pending="false";save.disabled=false;}
  }
  function report(state,pages,id){
    const row=source(state,id),data=row.data;
    const facts=["release","platform","locale","currency","result","sku","price_minor","restore_tested","trial_eligibility_tested","eligibility_status","checked_at","expires_at"].map(key=>key+": "+data[key]);
    const terms=["version","experiment_type","access_method","placement","currency",...CONFIG_TEXT,...CONFIG_NUMBERS].map(key=>key+": "+data.subscription_configuration[key]);
    return {...pages.model({...state,view:"results"}),title:"Subscription billing observations",purpose:"Inspect supplied tested terms, eligibility and restore observations for this exact source.",next_step:"Verify the product, price, restore and eligibility observations against the named test receipt, then use current matching evidence to preregister a paywall or offer test.",cohorts:[],metrics:[{label:"Saved configuration",value:1,unit:"record",source:"workspace.records; exact selected source"}],filters:{source_id:row.id,source_hash:row.hash},notes:[row.title,"Source: "+row.source,...facts,...terms,"Verification status: operator-supplied checks; provider acceptance is unverified. No authenticated provider acceptance, live paywall change, purchase or spending authority."]};
  }
  function detail(id,deps){
    const model=report(deps.state,deps.pageReports,id);
    deps.modal("Saved subscription terms",`<div class="modal-content"><p>${escape(model.purpose)}</p>${model.notes.map(note=>`<p>${escape(note)}</p>`).join("")}</div><div class="modal-actions">${button("Report / Save PDF","report",id)}</div>`,"BILLING SOURCE");
  }
  function action(node,deps){
    const mode=node.dataset.action.slice("subscription-plan-".length),id=node.dataset.id;
    if(mode==="detail")return detail(id,deps);
    if(mode==="report")return deps.pageReports.openReport(report(deps.state,deps.pageReports,id),deps.browser);
    return open(mode,deps);
  }
  return {current,sources,source,panel,fields,billingFields,experimentFields,open,billingData,variant,planData,payload,submit,report,detail,action};
});
