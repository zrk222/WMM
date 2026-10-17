"use strict";

function pmfOpen() {
  const p=state.workspace.pmf;
  modal("Find the next PMF test",`<div class="modal-content" id="pmf-workflow"><p class="eyebrow">${esc(state.workspace.app.data.name)} · CURRENT APP EVIDENCE</p><h2>${esc(p.next.title)}</h2>${notice("PMF is unproven. This is a research priority based on saved inputs, not a score, causal diagnosis or instruction to scale spending.")}<dl><dt>Problem</dt><dd>${esc(p.problem||"Define the user problem")}</dd><dt>Target segment hypothesis</dt><dd>${esc(p.segment_hypothesis||"Define a segment")}</dd><dt>Useful outcome</dt><dd>${esc(p.value_event||"Define first value")}</dd><dt>Return opportunity</dt><dd>${esc(p.value_cadence||"Define the natural return cycle")}</dd></dl>${p.core.failures.length?notice(p.core.failures.join("; "),"error"):""}<h3>Current observations</h3>${Object.entries(p.observations).map(([key,r])=>`<p><strong>${esc(label(key))}:</strong> ${r.value===null?"Unavailable":esc((r.value*100).toFixed(1)+"% supplied")}<br><small>${esc(r.reason)}</small></p>`).join("")}<h3>Saved PMF research</h3><p>${esc(p.research_next.title)}</p>${button("Open PMF evidence","research-open")}<h3>Research still needed</h3><ul>${p.missing_research.map(v=>`<li>${esc(v)}</li>`).join("")}</ul><h3>REA → ECC evidence workflow</h3>${button("Run installed REA / ECC","audit-open")}${p.tasks.map(t=>`<article><h4>${esc(t.engine)} · ${esc(label(t.execution))}</h4><p>${esc(t.task)}</p><small>${esc(t.constraint)}</small></article>`).join("")}<details><summary>Sources and limitations</summary><ul>${p.sources.map(s=>`<li>${esc(s.title)}: ${esc(s.url)}</li>`).join("")}</ul><ul>${p.limits.map(s=>`<li>${esc(s)}</li>`).join("")}</ul><p class="app-mono">Source ${esc(p.source_hash)}</p></details></div><div class="modal-actions">${button(p.next.title,"pmf-next",`data-source="${esc(p.source_hash)}" data-app="${esc(p.app_id)}"`)}${button("Download REA / ECC PMF tasks","pmf-download")}</div>`);
}

document.addEventListener("click",async event=>{
  const node=event.target.closest('[data-action^="pmf-"]');if(!node)return;
  if(node.dataset.action==="pmf-download")return download(`${state.app}-pmf-workflow.json`,state.workspace.pmf);
  const app=state.app;node.disabled=true;
  try {
    await refresh();
    if(state.app!==app||!node.isConnected||!$("#modal").open)return;
    if(node.dataset.app!==app||node.dataset.source!==state.workspace.pmf.source_hash)return pmfOpen();
    $("#modal").close();guidedOpenTool(state.workspace.pmf.next.tool);
  } catch(error) {if(state.app===app)toast(error.message);} finally {node.disabled=false;}
});
