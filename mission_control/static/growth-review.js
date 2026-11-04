/* App/version-bound founder review. Local evidence never grants execution authority. */
(function (root, factory) {
  "use strict";
  const value = factory();
  if (typeof module === "object" && module.exports) module.exports = value;
  else root.WMMGrowthReview = value;
})(typeof globalThis === "object" ? globalThis : this, function () {
  "use strict";
  const DENOMINATORS = {CPT_MINOR:"TAPS", CPI_MINOR:"INSTALLS", CR:"TAPS", TTR:"IMPRESSIONS"};
  const RULE_VERSION = "2026-10-27.v2";
  const MAX_ROWS = 1000;
  const MARKET_FILE_BYTES = 1048576;
  const escape = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const human = value => String(value ?? "Unavailable").replaceAll("_", " ").toLowerCase();
  const button = (label, action, id="") => `<button type="button" class="button outline" data-action="growth-${escape(action)}" data-id="${escape(id)}">${escape(label)}</button>`;

  function review(state) {
    if (state.workspace?.app?.id !== state.app) throw new Error("Load the selected app before opening growth review.");
    const value = state.workspace.subscription_growth;
    if (!value || value.app_id !== state.app || value.context?.manifest_version !== state.workspace.app.version) throw new Error("Growth review is unavailable or app setup changed. Refresh this workspace.");
    return value;
  }

  function history(state) {
    return review(state).history.history.slice(0, MAX_ROWS);
  }

  function selected(state, id) {
    const row = history(state).find(item => item.id === id);
    if (!row) throw new Error("This saved item is unavailable in the selected app. Reopen its history.");
    return row;
  }

  function metrics(value) {
    return [
      {label:"Saved review entries", value:value.history.history.length, unit:"entries", source:"subscription_growth.history"},
      {label:"Journey cohorts", value:value.journeys.length, unit:"cohorts", source:"subscription_growth.journeys; supplied observations"},
      {label:"Typed subscription tests", value:value.experiments.length, unit:"tests", source:"subscription_growth.experiments"},
      {label:"Items needing attention", value:value.issues.length, unit:"issues", source:"subscription_growth.issues"}
    ];
  }

  function panel(state) {
    let value;
    try { value = review(state); }
    catch (error) { return `<section class="panel"><h2>Subscription growth review</h2><p role="status">${escape(error.message)}</p>${button("Retry workspace", "refresh")}</section>`; }
    const counts = metrics(value).map(item => `<div><span>${escape(item.label)}</span><strong>${item.value}</strong><small>${escape(item.unit)}</small></div>`).join("");
    const issues = value.issues.map(item => `<li>${escape(item.next_action)}</li>`).join("");
    return `<section class="panel" id="growth-review-panel" aria-labelledby="growth-review-title"><p class="eyebrow">SUBSCRIPTION GROWTH / SAVED EVIDENCE</p><h2 id="growth-review-title">Find the next change worth testing</h2><p>Check your listing, subscription journey and experiment evidence in one place. Save a sourced benchmark to put an account report in context. Keep each decision tied to what you actually know.</p><p class="description">${escape(state.workspace.app.data.name)} · ${escape(value.observed_at)} · app setup ${escape(value.context.manifest_version)}. Counts below describe saved local evidence.</p><div class="page-metric-grid">${counts}</div>${evidenceStates(value)}<div class="toolbar"><button type="button" class="button outline" data-action="funnel-review">Review app-sales bottlenecks</button>${button("Save a listing", "listing")}${button("Import keyword research", "research")}${button("Add benchmark source", "reference")}${button("Compare saved report", "comparison")}${button("Report / Save PDF", "report")}</div>${issues?`<details><summary>${value.issues.length} next steps and repairs</summary><ul>${issues}</ul></details>`:"<p>No missing inputs were identified by this local review. Provider acceptance remains separate.</p>"}${historyList(value.history.history)}${journeyList(value.journeys)}${experimentList(value.experiments)}<p class="description">Editorial notes record your reasoning. Human approval, store acceptance and measured growth require their own evidence.</p></section>`;
  }

  function evidenceStates(value) {
    return `<dl class="details-list">${Object.entries(value.evidence_states).map(([name, item]) => `<div class="detail-item"><dt>${escape(human(name))}</dt><dd>${escape(human(item.state))}${item.reason?`<p>${escape(item.reason)}</p>`:""}</dd></div>`).join("")}</dl>`;
  }

  function historyList(rows) {
    if (!rows.length) return "<h3>Saved review history</h3><p>No saved entries yet. Begin with the original listing or an inspected benchmark source.</p>";
    return `<h3>Saved review history</h3><div class="record-list">${rows.map(row => `<button type="button" class="record-row" data-action="growth-detail" data-id="${escape(row.id)}"><span class="record-main"><strong>${escape(human(row.kind))} · ${escape(row.id)}</strong><small>${escape(row.created)} · ${escape(human(row.readout.availability))}</small></span><span>${escape(human(row.readout.analysis.status))}</span></button>`).join("")}</div>`;
  }

  function journeyList(rows) {
    return `<h3>Subscription journeys</h3>${rows.length?rows.map(row => `<details><summary>${escape(row.cohort_id)} · ${escape(row.currency)} · ${escape(human(row.status))}</summary><p>As of ${escape(row.as_of)}. Supplied events remain separate for this cohort and configuration.</p><pre>${escape(JSON.stringify(row.journey, null, 2))}</pre><p>Source hash: <span class="app-mono">${escape(row.source_hash)}</span></p></details>`).join(""):"<p>Define a cohort and import its permitted event export using the existing event ledger below.</p>"}`;
  }

  function experimentList(rows) {
    return `<h3>Paywall and offer experiments</h3>${rows.length?rows.map(row => `<article><h4>${escape(row.data.name)}</h4><p>${escape(human(row.review_state))}</p>${row.current_source_findings.map(issue => `<p>${escape(issue)}</p>`).join("")}${button("Inspect experiment", "experiment", row.id)}</article>`).join(""):"<p>No typed subscription experiment is registered. Billing configuration and eligibility must be supported by source evidence.</p>"}`;
  }

  function input(name, label, value="", type="text", hint="", required=true) {
    const id = "growth-" + name;
    const requirement = required ? "required" : "";
    const description = hint ? `aria-describedby="${id}-hint"` : "";
    const control = type === "textarea" ? `<textarea id="${id}" name="${name}" rows="4" ${requirement} ${description}>${escape(value)}</textarea>` : `<input id="${id}" name="${name}" type="${type}" value="${escape(value)}" ${requirement} ${description} step="any">`;
    return `<div class="field"><label for="${id}">${escape(label)}</label>${control}${hint?`<small id="${id}-hint">${escape(hint)}</small>`:""}</div>`;
  }

  function select(name, label, options) {
    return `<div class="field"><label for="growth-${name}">${escape(label)}</label><select id="growth-${name}" name="${name}" required><option value="">Choose ${escape(label.toLowerCase())}</option>${options.map(([value, text]) => `<option value="${escape(value)}">${escape(text)}</option>`).join("")}</select></div>`;
  }

  function listingFields(state) {
    const app = state.workspace.app.data;
    return `<p>Save the original text before editing it. Preflight checks length and the chosen test surface; it cannot approve claims or predict ranking.</p><div class="form-grid">${select("platform", "Store platform", [["iOS","Apple App Store"],["Android","Google Play"]])}${input("locale", "Listing locale", app.locale || "", "text", "Must match App setup, for example en-US.")}${input("release", "App release", app.release || "")}${select("surface", "Change or test surface", [["MANUAL_METADATA","Manual metadata edit"],["PRODUCT_PAGE_OPTIMIZATION","Apple product page optimization"],["LOCALIZED_LISTING_EXPERIMENT","Google localized listing experiment"],["DEFAULT_GRAPHICS_EXPERIMENT","Google default graphics experiment"]])}${input("title", "App title")}${input("subtitle", "Apple subtitle / Google short description")}${input("keywords", "Apple keywords", "", "text", "Apple docs differ: product-page guidance says 100 characters; an App Store Connect reference lists 100 bytes. The saved review shows both counts and asks you to check the current locale counter. Ignored for Google Play; enter a dash if not applicable.")}${input("description", "Full description", "", "textarea")}${input("test_fields", "Fields or assets being tested", "title", "text", "Comma-separated field names, such as title or screenshots. Unsupported combinations are flagged.")}</div>`;
  }

  function referenceFields(state) {
    const data = state.workspace.app.data;
    return `<p>Use an inspected source. Exact periods and segments must match before a comparison is shown. Values for CPT/CPI use currency minor units; rates use fractions.</p><fieldset><legend>Dataset and provenance</legend><div class="form-grid">${input("dataset_id","Dataset name or ID")}${input("source_url","Public source URL","","url")}${input("source_sha256","Inspected source SHA256")}${input("published_at","Published at (ISO timestamp)")}${input("retrieved_at","Inspected at (ISO timestamp)")}${input("expires_at","Review expires at (ISO timestamp)")}${input("limitations","Source limitations","","textarea")}</div></fieldset><fieldset><legend>Comparable scope</legend><div class="form-grid">${select("metric","Metric",Object.keys(DENOMINATORS).map(name=>[name,human(name)]))}${select("platform","Store platform",[["iOS","Apple App Store"],["Android","Google Play"]])}${input("currency","Currency",data.currency||"")}${segmentFields()}${input("period_start","Dataset period start (ISO, inclusive)")}${input("period_end","Dataset period end (ISO, exclusive)")}${input("value","Benchmark value","","number")}${input("percentile","Percentile","50","number")}${select("coverage","Source coverage",[["COMPLETE","Complete"],["PARTIAL","Partial"],["UNKNOWN","Unknown"]])}${input("release","App release",data.release||"")}</div></fieldset>`;
  }

  function segmentFields() {
    return input("category","Category") + input("territory","Territory") + input("placement","Ad placement") + input("campaign_type","Campaign type");
  }

  function comparisonFields(state) {
    const value = review(state);
    const refs = history(state).filter(row=>row.kind==="BENCHMARK_REFERENCE" && row.readout.availability==="CURRENT_LOCAL_EVIDENCE" && row.readout.analysis.status==="REFERENCE_AVAILABLE");
    const sources = value.ads_sources.filter(row=>row.state==="CURRENT_SAVED_SOURCE");
    return `<p>Totals come from the selected saved account read. You declare the classification below; it is not provider verified. Report dates are UTC and must match the benchmark period exactly.</p>${!refs.length||!sources.length?"<p role=\"status\">Save a current benchmark reference and read an Apple Ads campaign or keyword report in Connections before comparing.</p>":""}<div class="form-grid">${select("reference_id","Saved benchmark",refs.map(row=>[row.id,row.id+" · "+row.data.reference.dataset_id]))}${select("job_id","Saved account report",sources.map(row=>[row.job_id,row.operation+" · "+row.observed_at]))}${select("metric","Metric",Object.keys(DENOMINATORS).map(name=>[name,human(name)]))}${segmentFields()}</div>`;
  }

  function noteFields(row) {
    return `<p>Record reasoning about ${escape(row.id)}. A note cannot approve or execute a provider change.</p><div class="form-grid">${select("decision","Editorial choice",[["KEEP","Keep"],["REVISE","Revise"],["DEFER","Defer"]])}${input("rationale","Reason and next step","","textarea")}</div>`;
  }

  function openForm(mode, deps, id="") {
    review(deps.state);
    const builders = {research:()=>researchFields(deps.state),listing:()=>listingFields(deps.state)+input("promotional_text","Apple promotional text (optional)","","textarea","Ignored for Google Play.",false)+`<p>Preflight rules: ${RULE_VERSION}. Store counters and current provider rules remain authoritative.</p>`, reference:()=>referenceFields(deps.state), comparison:()=>comparisonFields(deps.state), note:()=>noteFields(selected(deps.state,id))};
    const titles = {research:"Find the words your app should test",listing:"Save a localized listing",reference:"Record a benchmark source",comparison:"Compare a saved account report",note:"Add an editorial note"};
    if (!builders[mode]) throw new Error("Unknown growth-review form.");
    deps.modal(titles[mode],`<form id="growth-review-form" data-mode="${mode}" data-app="${escape(deps.state.app)}" data-version="${deps.state.workspace.app.version}" data-id="${escape(deps.uuid())}" data-target="${escape(id)}"><div class="modal-content">${builders[mode]()}<p>New entries keep the original history. Save only permitted public evidence, with no credentials or personal identifiers.</p><div id="growth-form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button type="submit" class="button">${mode==="research"?"Review research file":"Save evidence"}</button></div></form>`,"GROWTH REVIEW");
  }

  function researchFields(state) {
    return `<p>Bring the keyword and competitor evidence your agent researched for ${escape(state.workspace.app.data.name)}. WMM shows which phrases appear in your listing, where competitors overlap and what to test next.</p><p id="market-file-help">Choose the agent's MARKET_RESEARCH data JSON, up to 1 MiB. It must use this app's release and locale, dated source excerpts and hashes. Search volume, rank and difficulty stay unknown unless a cited source supplies them; imported claims are not provider verified.</p><div class="field"><label for="market-research-file">Research evidence file</label><input id="market-research-file" name="research_file" type="file" accept=".json,application/json" required aria-describedby="market-file-help"></div><div id="market-research-preview" role="status" aria-live="polite"></div><details><summary>Instructions for your personal agent</summary><p>Read wmm_catalog → domain_contracts → market_research. Prepare growth.save with this app ID, current manifest version, kind MARKET_RESEARCH and the exact data object. Save that data object as a JSON file for review here. Never include credentials or personal data.</p></details>`;
  }

  function researchBody(form,raw,state) {
    review(state);
    if(form.dataset.app!==state.app || Number(form.dataset.version)!==state.workspace.app.version) throw new Error("App setup changed. Reopen research in the intended app; your selected file is preserved.");
    const data=JSON.parse(raw);
    if(!data || typeof data!=="object" || Array.isArray(data)) throw new Error("Choose the MARKET_RESEARCH data object, with release and snapshot.");
    const body=`{"id":${JSON.stringify(form.dataset.id)},"manifest_version":${Number(form.dataset.version)},"kind":"MARKET_RESEARCH","data":${raw}}`;
    if(new TextEncoder().encode(body).length>MARKET_FILE_BYTES) throw new Error("Research request exceeds 1 MiB. Use a smaller source snapshot.");
    return {body,data}; // Original JSON preserves duplicate fields for the server's strict decoder.
  }

  function researchPreview(data) {
    const s=data.snapshot;
    if(!s || !Array.isArray(s.sources) || !Array.isArray(s.phrases) || !Array.isArray(s.competitors)) throw new Error("Research needs snapshot sources, phrases and competitors. Ask your agent for the catalog format.");
    return `<h3>Review before saving</h3><p>${escape(s.platform)} · ${escape(s.locale)} · ${escape(s.territory)} · release ${escape(data.release)}</p><p>${s.sources.length} sources · ${s.phrases.length} keyword phrases · ${s.competitors.length} competitors. Observed ${escape(s.observed_at)}.</p><p>This saves local research. It approves no reuse, campaign, publication or spending. The server checks every field and source hash before saving.</p>`;
  }

  function listingData(values) {
    const fields={title:values.title,description:values.description};
    if (values.platform==="iOS") Object.assign(fields,{subtitle:values.subtitle,keywords:values.keywords,promotional_text:values.promotional_text||""});
    else fields.short_description=values.subtitle;
    return {release:values.release,listing:{platform:values.platform,locale:values.locale,fields,surface:values.surface,test_fields:values.test_fields.split(",").map(item=>item.trim()).filter(Boolean),rule_version:RULE_VERSION}};
  }

  function referenceData(values) {
    const keys=["dataset_id","source_url","source_sha256","published_at","retrieved_at","expires_at","limitations","metric","platform","currency","category","territory","placement","campaign_type","period_start","period_end","coverage"];
    const reference=Object.fromEntries(keys.map(key=>[key,values[key]]));
    return {release:values.release,reference:{...reference,denominator:DENOMINATORS[values.metric],value:Number(values.value),percentile:Number(values.percentile)}};
  }

  function comparisonData(values,state) {
    const reference=selected(state,values.reference_id);
    const source=review(state).ads_sources.find(row=>row.job_id===values.job_id && row.state==="CURRENT_SAVED_SOURCE");
    if (!source || reference.kind!=="BENCHMARK_REFERENCE") throw new Error("Saved source changed. Reopen this comparison.");
    return {reference_id:reference.id,reference_hash:reference.hash,job_id:source.job_id,report_hash:source.report_hash,metric:values.metric,segment:Object.fromEntries(["category","territory","placement","campaign_type"].map(key=>[key,values[key]]))};
  }

  function payload(form, values, state) {
    review(state);
    if (form.dataset.app!==state.app || Number(form.dataset.version)!==state.workspace.app.version) throw new Error("App setup changed. Your inputs are preserved; reopen this form in the intended app.");
    const modes={listing:["ASO_LISTING",()=>listingData(values)],reference:["BENCHMARK_REFERENCE",()=>referenceData(values)],comparison:["BENCHMARK_COMPARISON",()=>comparisonData(values,state)],note:["EDITORIAL_NOTE",()=>{const target=selected(state,form.dataset.target);return {target_id:target.id,target_hash:target.hash,decision:values.decision,rationale:values.rationale};}]};
    const mode=modes[form.dataset.mode];
    if (!mode) throw new Error("Unknown growth-review form.");
    return {id:form.dataset.id,manifest_version:Number(form.dataset.version),kind:mode[0],data:mode[1]()};
  }

  async function submit(form,deps) {
    if (form.dataset.pending==="true") return;
    const submitButton=form.querySelector('[type="submit"]'), error=form.querySelector("#growth-form-error");
    form.dataset.pending="true";submitButton.disabled=true;error.textContent="";
    try {
      if(form.dataset.mode==="research") {
        const file=new deps.FormData(form).get("research_file");
        if(!file || typeof file.text!=="function" || file.size===0) throw new Error("Choose a research JSON file first.");
        if(file.size>MARKET_FILE_BYTES) throw new Error("Research file exceeds 1 MiB. Use a smaller source snapshot.");
        const raw=await file.text();
        if(!form.isConnected) return;
        const packet=researchBody(form,raw,deps.state);
        if(form._researchRaw!==raw) {
          form.querySelector("#market-research-preview").innerHTML=researchPreview(packet.data);
          form._researchRaw=raw;submitButton.textContent="Save researched packet";return;
        }
        await deps.api(`/api/apps/${encodeURIComponent(form.dataset.app)}/subscription-growth/entries`,{}, {body:packet.body});
        if(deps.state.app!==form.dataset.app) return;
        await deps.refresh();
        if(deps.state.app===form.dataset.app && form.isConnected) deps.close();
        deps.toast("Research saved. Open its keyword coverage and next experiments in saved history.");return;
      }
      const body=payload(form,Object.fromEntries(new deps.FormData(form)),deps.state);
      await deps.api(`/api/apps/${encodeURIComponent(form.dataset.app)}/subscription-growth/entries`,body);
      if (deps.state.app!==form.dataset.app) return;
      await deps.refresh();
      if (deps.state.app===form.dataset.app && form.isConnected) deps.close();
      deps.toast("Evidence saved. Its original text and source history are retained.");
    } catch (failure) { if(form.isConnected) error.textContent=failure.message+" Inputs are preserved. Correct the issue and retry."; }
    finally {form.dataset.pending="false";submitButton.disabled=false;}
  }

  function entryNotes(row) {
    const analysis=row.readout.analysis;
    const notes=[`${human(row.kind)}: ${row.id}. Saved ${row.created}. ${human(row.readout.availability)}. Status: ${human(analysis.status)}. Source hash ${row.hash}.`];
    if(row.readout.scope_status) notes.push(`App context: ${human(row.readout.scope_status)}. Provenance: ${human(row.readout.import_provenance)}. Changed scope needs a new current-app review.`);
    if (row.kind==="ASO_LISTING") {
      notes.push(`Applied rule profile ${analysis.rule_version}; saved source profile ${analysis.source_rule_version}; rules reviewed ${analysis.rules_reviewed_at}.`);
      notes.push(...Object.entries(row.data.listing.fields).map(([name,value])=>`${human(name)}: ${value}`));
      notes.push(...analysis.fields.map(item=>item.field==="keywords"&&Number.isInteger(item.byte_reference)?`${human(item.field)}: ${item.characters} characters; limit ${item.maximum_characters}; ${item.bytes} UTF-8 bytes; App Store Connect reference: ${item.byte_reference} bytes.`:`${human(item.field)}: ${item.characters} characters; limit ${item.maximum_characters} characters.`));
      notes.push(...analysis.findings.map(item=>`${item.field}: ${item.correction}`));
    }
    if (row.kind==="BENCHMARK_REFERENCE") notes.push(...referenceNotes(row.data.reference));
    if (row.kind==="BENCHMARK_COMPARISON") notes.push(...comparisonNotes(row));
    if (row.kind==="MARKET_RESEARCH") notes.push(...researchNotes(row));
    if (row.kind==="EDITORIAL_NOTE") notes.push(`Editorial ${human(row.data.decision)}: ${row.data.rationale}. Target ${row.data.target_id}, hash ${row.data.target_hash}. No approval authority.`);
    return notes;
  }

  function referenceNotes(value) {
    return [`Dataset ${value.dataset_id}; ${value.source_url}; SHA256 ${value.source_sha256}. Published ${value.published_at}; inspected ${value.retrieved_at}; expires ${value.expires_at}.`,`${value.metric} / ${value.denominator}: ${value.value}; percentile ${value.percentile}; ${value.currency}; ${value.platform}; ${value.category}; ${value.territory}; ${value.placement}; ${value.campaign_type}. Period ${value.period_start} to ${value.period_end}, exclusive end; coverage ${value.coverage}.`,value.limitations];
  }

  function researchNotes(row) {
    const s=row.data.snapshot,a=row.readout.analysis;
    const notes=[`Market: ${s.platform}; ${s.locale}; ${s.territory}; observed ${s.observed_at}. ${a.next_action}.`,
      `${a.coverage.sourced_phrases} of ${a.coverage.phrases} supplied phrases have linked evidence. Phrase coverage is not search demand or ranking.`,
      `Own listing excerpt: ${s.own_listing.excerpt}. Source ${s.own_listing.source_id}.`,a.scope];
    for(const source of s.sources) notes.push(`Source ${source.id}: ${source.url}; SHA256 ${source.sha256}; inspected ${source.retrieved_at}; coverage ${source.coverage}. Operator-supplied excerpt: ${source.excerpt}`);
    for(const p of s.phrases) notes.push(`Keyword ${p.phrase}. Sources ${p.source_ids.join(", ")}. Supplied observations: ${p.observed.demand_signal??"Unknown"}; competitor position ${p.observed.competitor_position??"Unknown"}. Analyst intent ${p.inferred.intent??"Unknown"}; relevance ${p.inferred.relevance??"Unknown"}. `+Object.entries(p.metrics).map(([name,v])=>`${human(name)}: ${v===null?"Unknown":`${v.value} (operator assertion; source ${v.source_id})`}`).join("; "));
    for(const c of s.competitors) notes.push(`Competitor ${c.name} (${c.id}); source ${c.source_id}; supplied listing: ${c.listing_excerpt}`);
    for(const c of a.candidates) notes.push(`Test candidate ${c.phrase}: ${c.reason}. Own listing overlap ${c.own_listing_overlap}; competitor IDs ${c.competitor_ids.join(", ")||"None observed"}. ${c.suggested_test}.`);
    return notes;
  }

  function comparisonNotes(row) {
    const data=row.data,analysis=row.readout.analysis, projection=data.projection;
    const observed=projection.observed;
    return [`Reference ${data.reference_id} (${data.reference_hash}); saved report ${data.job_id} (${data.report_hash}).`, `Metric ${data.metric}; advisory difference ${analysis.difference??"Unavailable"}. Operator-declared classification; provider verification false.`, observed?`Numerator ${projection.numerator_exact}; denominator ${observed.denominator_count} ${observed.denominator}; currency ${observed.currency}; period ${observed.period_start} to ${observed.period_end}; coverage ${observed.coverage}.`:"Source metrics unavailable.", ...(analysis.reasons||[])];
  }

  function report(state,pageReports,id="") {
    const value=review(state),rows=id?[selected(state,id)]:history(state);
    const base=pageReports.model({...state,view:"results"});
    return {...base,title:id?"Saved growth review: "+id:"Subscription growth review",purpose:"Review saved listing, benchmark and subscription evidence for this selected app.",next_step:"Repair evidence gaps, then choose the next bounded test. Publishing and spending require separate approval.",loaded_at:value.observed_at,filters:{scope:id?"Exact saved item "+id:"All saved growth review history",source_hash:value.source_hash},metrics:metrics(value),cohorts:[],notes:[...rows.flatMap(entryNotes),...value.issues.map(item=>item.next_action),...Object.values(value.evidence_states).map(item=>human(item.state)+": "+(item.reason||"Local evidence only")),"No credentials, private form inputs, provider approval or growth guarantees are included."]};
  }

  function detail(id,deps) {
    const row=selected(deps.state,id);
    deps.modal("Saved growth review",`<div class="modal-content"><p>Inspect this saved source and its current readout. Corrections create a new version; the original remains unchanged.</p>${entryNotes(row).map(note=>`<p>${escape(note)}</p>`).join("")}</div><div class="modal-actions">${row.kind!=="EDITORIAL_NOTE"?button("Add editorial note","note",id):""}${button("Download report JSON","json",id)}${button("Report / Save PDF","report",id)}</div>`,"SOURCE-BOUND HISTORY");
  }

  function downloadReport(deps,id) {
    const value=report(deps.state,deps.pageReports,id);
    const url=deps.browser.URL.createObjectURL(new deps.browser.Blob([JSON.stringify(value,null,2)],{type:"application/json"}));
    const link=deps.document.createElement("a");link.href=url;link.download="wmm-growth-report.json";
    deps.document.body.append(link);link.click();link.remove();
    deps.browser.setTimeout(()=>deps.browser.URL.revokeObjectURL(url),0);
  }

  function action(node,deps) {
    const mode=node.dataset.action.slice("growth-".length),id=node.dataset.id;
    const actions={refresh:()=>deps.refresh(),detail:()=>detail(id,deps),json:()=>downloadReport(deps,id),report:()=>deps.pageReports.openReport(report(deps.state,deps.pageReports,id),deps.browser),experiment:()=>deps.openExperiment(id)};
    if (actions[mode]) return actions[mode]();
    return openForm(mode,deps,id);
  }
  return {DENOMINATORS,RULE_VERSION,review,history,selected,metrics,panel,evidenceStates,historyList,journeyList,experimentList,input,select,listingFields,referenceFields,segmentFields,comparisonFields,noteFields,openForm,listingData,referenceData,comparisonData,payload,submit,entryNotes,referenceNotes,comparisonNotes,researchFields,researchBody,researchPreview,researchNotes,report,detail,action};
});
