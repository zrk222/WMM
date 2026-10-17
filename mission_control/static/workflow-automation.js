"use strict";

function automationSelect(name,title,options,value) {
  return `<label class="field full" for="field-${name}">${esc(title)}<select id="field-${name}" name="${name}">${options.map(([key,label])=>`<option value="${esc(key)}" ${key===value?"selected":""}>${esc(label)}</option>`).join("")}</select></label>`;
}

function automationPreferenceFields(data) {
  const channels=data.growth_channels??(data.channel_hypotheses||[]).join("\n");
  return `<fieldset><legend>Workflow automation</legend><p>Choices stay editable. Missing proof stays blocked; provider changes keep their approvals.</p>${automationSelect("growth_mode","Preparation mode",[["AUTO","Automatic editable defaults"],["SUGGEST","Suggest; apply when requested"],["OFF","Manual forms"]],data.growth_mode||"AUTO")}${automationSelect("growth_metric","Primary outcome",[["activation_rate","Useful activation"],["paid_conversion","Paid conversion"],["retention_rate","Retained value"]],data.growth_metric||"activation_rate")}${field("growth_cadence",data.growth_cadence??data.retention??"","textarea","Useful-value cadence, e.g. a decision checkpoint; avoid generic daily opens",false)}${field("growth_channels",channels,"textarea","One pilot channel per line, in test priority order; up to 12. These are hypotheses, not measured winners.",false)}${field("growth_channel",data.growth_channel||"","text","Optional override: copy one channel from the list exactly",false)}</fieldset>`;
}

function automationPanel(identity="workflow-automation") {
  const a=state.workspace.automation;
  if(!a)return "";
  if(a.mode==="OFF")return `<section class="panel automation-panel" id="${esc(identity)}"><h2>Manual preparation</h2><p>Automatic form defaults are off for this app.</p>${button("Change automation preferences","automation-preferences")}</section>`;
  return `<section class="panel automation-panel" id="${esc(identity)}"><div class="section-heading"><div><p class="eyebrow">${a.mode==="AUTO"?"AUTOMATIC EDITABLE DEFAULTS":"SUGGESTED CHOICES"}</p><h2>Prepared for ${esc(state.workspace.app.data.name)}</h2></div>${button("Change automation preferences","automation-preferences")}</div><div class="automation-choices"><div><h3>Primary outcome</h3><p>${esc(a.metric.label)}</p><small>${esc(a.metric.activation||"Declare this app's useful activation")}</small></div><div><h3>Pilot channel</h3><p>${esc(a.channel.value||"Add channel candidates in app setup")}</p><small>${esc(a.channel.basis)}</small></div><div><h3>Retained value</h3><p>${esc(a.cadence||"Declare this app's useful-value cadence")}</p><small>Use meaningful outcomes, not generic app opens.</small></div></div><details><summary>Why these choices and what changes automatically</summary><p>${esc(a.metric.basis)}</p><p>${esc(a.baseline.reason)}${a.baseline.value!==null?` · supplied baseline ${esc(a.baseline.value)}`:""}</p><p>${esc(a.channel.next_test)}</p><p>Alternatives: ${esc(a.channel.alternatives.join(" · ")||"No additional candidates supplied")}</p><p>Choices refresh with saved app facts and evidence. ${a.mode==="AUTO"?"New planning forms receive editable defaults.":"Use Apply recommended defaults inside a planning form."} No form is submitted automatically.</p><p class="app-mono">Source ${esc(a.source_hash)}</p>${button("Download automatic choices","automation-download")}</details></section>`;
}

function automationStageChoice(stage) {
  const a=state.workspace.automation;
  if(!a||a.mode==="OFF")return "";
  const choice=a.choices.find(c=>c.stage===stage.id);
  return choice?`<p class="automation-stage-choice"><strong>Prepared choice:</strong> ${esc(choice.choice)}</p>`:"";
}

function automationDecorateWorkflow() {
  if(state.view!=="workflow")return;
  $("#guided-workflow").insertAdjacentHTML("beforebegin",automationPanel());
  for(const step of state.workspace.workflow.steps) {
    const article=$(`#workflow-step-${step.id}`);
    article.querySelector(".section-heading").insertAdjacentHTML("afterend",automationStageChoice(step));
  }
}

function automationCheckForm(form) {
  if(form.dataset.app!==state.app||form.dataset.manifestVersion!==String(state.workspace.app.version))
    throw new Error("App or setup changed. Close this form and reopen it in the selected workspace. Your input is preserved.");
}

function automationApply(form) {
  automationCheckForm(form);
  if(form.dataset.automationSource!==state.workspace.automation.source_hash)
    throw new Error("Recommendation sources changed. Close and reopen this form for current defaults; your input is preserved.");
  const applied=[];
  for(const [name,value] of Object.entries(form.automaticDefaults||{})) {
    const target=form.elements.namedItem(name);
    if(!target||form.automaticTouched.has(name))continue;
    if(target.value!==""&&name!=="primary_metric")continue;
    target.value=String(value);applied.push(label(name));
  }
  const message=form.querySelector(".automation-applied");
  if(message)message.textContent=applied.length?`Prepared: ${applied.join(", ")}. Review and edit before saving.`:"Your edits are preserved; no empty recommended fields remain.";
}

function automationAttach() {
  const form=$("#app-form")||$("#evidence-form")||$("#experiment-form");
  if(!form)return;
  form.dataset.app=state.app;form.dataset.manifestVersion=state.workspace.app.version;
  const a=state.workspace.automation;
  if(!a||a.mode==="OFF"||form.id==="app-form"||form.dataset.id)return;
  const kind=form.id==="experiment-form"?"registered_experiment":form.dataset.kind;
  const values=a.drafts[kind];if(!values)return;
  form.dataset.automationSource=a.source_hash;form.automaticDefaults=values;form.automaticTouched=new Set();
  for(const type of ["input","change"])form.addEventListener(type,e=>form.automaticTouched.add(e.target.name));
  const content=form.querySelector(".modal-content");
  content.insertAdjacentHTML("afterbegin",`<div class="notice automation-form-note"><div><strong>${esc(state.workspace.app.data.name)} · ${a.mode==="AUTO"?"Editable automatic defaults":"Recommended defaults"}</strong><p>Planning fields only. Baseline: ${esc(a.baseline.reason)}. Results, proof and analysis dates still need evidence.</p>${button("Apply recommended defaults","automation-apply")}<p class="automation-applied" role="status" aria-live="polite"></p></div></div>`);
  if(a.mode==="AUTO")automationApply(form);
}

function automationAction(node) {
  if(node.dataset.action==="automation-preferences")return appForm(false);
  if(node.dataset.action==="automation-download")return download(`${state.app}-automatic-choices.json`,state.workspace.automation);
  if(node.dataset.action==="automation-apply")return automationApply(node.closest("form"));
}
