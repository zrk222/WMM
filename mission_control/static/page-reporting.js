/* Typed, local page reports. Never capture form controls or arbitrary DOM/state. */
(function (root, factory) {
  "use strict";
  const value = factory();
  if (typeof module === "object" && module.exports) module.exports = value;
  else root.WMMPageReports = value;
})(typeof globalThis === "object" ? globalThis : this, function () {
  "use strict";
  const MAX_TEXT = 1000;
  const MAX_ROWS = 100;
  const PAGES = Object.freeze({
    weekly: ["Weekly review", "Review exceptions across the displayed portfolio page.", "Resolve the most important missing evidence before expanding work."],
    overview: ["Overview", "See this app's saved evidence and current readiness.", "Open the next stage that needs input; readiness is not permission to launch."],
    workflow: ["Guided workflow", "Follow the app's evidence, preparation and measurement steps.", "Complete the next missing prerequisite and review its evidence."],
    pipeline: ["Pipeline", "Inspect readiness across the app's growth stages.", "Prepare a stage, then verify its outputs before any external action."],
    evidence: ["Evidence & assets", "Find saved records and original assets for this app.", "Add current, sourced evidence; keep credentials out of records."],
    results: ["Results", "Review supplied cohort outcomes and measurement gaps.", "Check denominators, maturity and currency before interpreting an outcome."],
    connections: ["Connections", "Inspect this app's configured data-source connections.", "Connect or repair a source, then verify its current readback."],
    agents: ["Your agents", "Choose model connections and inspect their tested state.", "Test a connection, choose its route, then review the exact request."],
    activity: ["Activity & reviews", "Inspect loaded jobs and approval history for this app.", "Review exact current packets and investigate failed or uncertain work."],
    research: ["Research & playbook", "Turn sourced hypotheses into testable app-specific work.", "Keep evidence, assumptions and actual product outcomes separate."]
  });
  const escape = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"}[c]));
  const text = value => String(value ?? "").slice(0, MAX_TEXT);
  const rows = value => Array.isArray(value) ? value : null;
  const count = (value, predicate = () => true) => rows(value) ? value.filter(predicate).length : null;
  const metric = (label, value, source, unit = "count") => ({label, value, source, unit});
  const ready = stages => [metric("Stages with local inputs ready", count(stages, s => s.status === "READY"), "workspace.stages"), metric("Stages assessed", count(stages), "workspace.stages")];
  const statuses = value => value && typeof value === "object" && !Array.isArray(value) ? Object.values(value) : null;
  const SOURCE_LABELS = Object.freeze({"workspace.stages":"Saved stage assessments", "workspace.records":"Saved app evidence", "workspace.jobs; loaded history":"Loaded job history", "workspace.records; evidence search":"Saved evidence matching search", "workspace.records; all records":"All saved app evidence", "workspace.metrics.cohorts":"Supplied cohort summaries", "workspace.ledger":"Imported event-ledger cohorts", "workspace.connections":"Saved data-source status", "workspace.agent_access.profiles":"Saved model profiles", "workspace.verified_reviews; loaded history":"Loaded verified-review history", "research.ledger.other_notebooks; shared library":"Shared research-source library", "workspace.experiments":"Saved app experiments", "weekly_review.coverage":"Displayed portfolio coverage", "weekly_review.exceptions":"Displayed portfolio exceptions", "weekly_review.apps":"Displayed app source checks"});
  const sourceLabel = source => SOURCE_LABELS[source] || source;
  const scopeLabel = scope => scope === "PORTFOLIO_DISPLAYED_PAGE" ? "Displayed portfolio page" : "Selected app";

  /** Name the product purpose, actual inputs, operations and delivered artifacts. */
  function overviewStory() {
    return `<section class="panel wmm-overview-story" aria-labelledby="wmm-story-title"><p class="eyebrow">WHAT WMM DOES</p><h2 id="wmm-story-title">Your app marketing, from the brief to the results.</h2><p>Wize Marketing Machine is a workspace for preparing and measuring app marketing. It keeps your app facts, marketing work and performance records together, organized into twelve stages.</p><ol class="wmm-story-steps"><li><h3>1. Tell WMM about your app</h3><p>Enter the app’s purpose, audience, release and language. Define the first task a new user should complete. These facts guide the work for this app.</p></li><li><h3>2. Bring in the evidence</h3><p>Add screenshots, creative assets, public customer observations, listing text and test records. Import usage, purchase and refund events. Choose account connections to read store, advertising and payment reports.</p></li><li><h3>3. Prepare and check the work</h3><p>WMM checks each stage’s required inputs, prepares six creative briefs, checks listing fields, links feature proposals to customer sources, and calculates conversion, acquisition cost and contribution from your supplied records. Your chosen AI connection generates campaign drafts.</p></li><li><h3>4. Take the deliverables</h3><p>Run the pipeline to save twelve stage packets containing tasks, source evidence and missing-input checklists. Keep creative briefs, experiment plans, listing reviews and customer-workflow proposals in the same app workspace. Export results and evidence as PDF reports or downloadable data.</p></li></ol><div class="wmm-story-outcomes"><h3>Start here</h3><p>Open Guided workflow, complete App setup, add the requested evidence and run pipeline preparation. Review the saved work, complete the tasks and import the results of your next test.</p></div></section>`;
  }

  function pageMetrics(view, state) {
    const w = state.workspace;
    const builders = {
      overview: () => [...ready(w.stages), metric("Saved evidence records", count(w.records), "workspace.records")],
      workflow: () => [...ready(w.stages), metric("Stages needing inputs", count(w.stages, s => s.status !== "READY"), "workspace.stages")],
      pipeline: () => [...ready(w.stages), metric("Loaded preparation jobs", count(w.jobs, j => j.action === "pipeline"), "workspace.jobs; loaded history")],
      evidence: () => evidenceMetrics(state),
      results: () => [metric("Supplied cohort summaries", count(w.metrics?.cohorts), "workspace.metrics.cohorts"), metric("Mature measured summaries", count(w.metrics?.cohorts, c => c.status === "MEASURED"), "workspace.metrics.cohorts"), metric("Imported ledger cohorts", count(w.ledger), "workspace.ledger")],
      connections: () => [metric("Loaded data-source statuses", count(statuses(w.connections)), "workspace.connections"), metric("Disconnected data sources", count(statuses(w.connections), c => c.status === "DISCONNECTED"), "workspace.connections"), metric("Loaded provider synchronization jobs", count(w.jobs, j => j.action === "sync"), "workspace.jobs; loaded history")],
      agents: () => [metric("Configured model profiles", count(w.agent_access?.profiles, p => p.status !== "DISCONNECTED"), "workspace.agent_access.profiles"), metric("Disconnected profiles", count(w.agent_access?.profiles, p => p.status === "DISCONNECTED"), "workspace.agent_access.profiles"), metric("Loaded model request jobs", count(w.jobs, j => j.action === "agent_run"), "workspace.jobs; loaded history")],
      activity: () => [metric("Loaded saved jobs", count(w.jobs), "workspace.jobs; loaded history"), metric("Loaded failed jobs", count(w.jobs, j => j.status === "FAILED"), "workspace.jobs; loaded history"), metric("Verified-review packets", count(w.verified_reviews), "workspace.verified_reviews; loaded history")],
      research: () => [metric("Saved research-source entries", count(state.research?.ledger?.other_notebooks), "research.ledger.other_notebooks; shared library"), metric("App evidence records", count(w.records), "workspace.records"), metric("App experiment definitions", count(w.experiments), "workspace.experiments")],
      weekly: () => weeklyMetrics(state)
    };
    return builders[view]();
  }

  function evidenceMetrics(state) {
    const records = rows(state.workspace.records);
    const query = String(state.filter || "").toLowerCase();
    const selected = records?.filter(r => `${r.title} ${r.kind}`.toLowerCase().includes(query));
    return [metric("Matching evidence records", count(selected), "workspace.records; evidence search"), metric("Matching asset records", count(selected, r => r.kind === "asset"), "workspace.records; evidence search"), metric("All saved evidence records", count(records), "workspace.records; all records")];
  }

  function weeklyMetrics(state) {
    const review = state.weeklyError || state.weeklyLoading ? null : state.weeklyReview;
    return [metric("Apps evaluated on displayed page", Number.isSafeInteger(review?.coverage?.evaluated) ? review.coverage.evaluated : null, "weekly_review.coverage"), metric("Exceptions on displayed page", count(review?.exceptions), "weekly_review.exceptions"), metric("Unavailable app sources", count(review?.apps, a => a.exceptions?.some(e => e.state === "UNAVAILABLE")), "weekly_review.apps")];
  }

  function cohortRows(workspace) {
    const values = rows(workspace.metrics?.cohorts) || [];
    return values.slice(0, MAX_ROWS).map(c => {
      const measured = c.status === "MEASURED";
      const number = value => measured && Number.isFinite(value) ? value : null;
      return {id:text(c.cohort_id || "Unidentified supplied cohort"), status:text(c.status || "UNAVAILABLE"),
        horizon:text(c.horizon || "Not supplied"), currency:text(c.currency || "Not supplied"),
        installs:number(c.counts?.installs), activation_rate:number(c.activation_rate), paid_conversion:number(c.paid_conversion),
        paid_cac_minor:number(c.paid_cac_minor), contribution_minor:number(c.contribution_after_acquisition_minor)};
    });
  }

  /** Preserve only visible filter metadata, never draft or credential form inputs. */
  function reportFilters(state) {
    if (state.view === "evidence") return {evidence_search:text(state.filter || ""), reference_search:text(state.referenceFilter || ""), reference_platform:text(state.referencePlatform || "All"), reference_rights:text(state.referenceRights || "All")};
    if (state.view === "weekly") return {offset:state.weeklyReview?.coverage?.offset ?? "Not loaded", coverage:"Displayed review page only"};
    return {range:"All loaded saved history; no date filter"};
  }

  /** Distinguish portfolio coverage from the selected app and source-evaluation time. */
  function reportContext(state) {
    if (state.view === "weekly") return {scope:"PORTFOLIO_DISPLAYED_PAGE", app_id:null, app_name:"Portfolio review — displayed page", manifest_version:null, loaded_at:text(state.weeklyReview?.observed_at || "Not loaded")};
    const app = state.workspace.app;
    return {scope:"SELECTED_APP", app_id:text(app.id), app_name:text(app.data?.name || app.id), manifest_version:app.version, loaded_at:text(state.workspaceObservedAt || "Load time unavailable")};
  }

  /** Explain provenance, units and row truncation without claiming verified outcomes. */
  function reportNotes(state) {
    return ["Counts describe loaded local evidence and history, not verified growth. Missing sources stay unavailable.",
      "Loaded time is not provider freshness. Original source dates and completeness require review in the source panels.",
      "This report excludes credentials, credential and draft form inputs, raw records and detail-dialog contents. It grants no approval or execution authority.",
      state.view === "results" ? "Cohort values are supplied observations. Rates are fractions from 0 to 1 with eligible installs as denominator; currencies and horizons remain separate. Minor units are not whole currency units." : "No causal lift, permission to spend or provider approval is established.",
      count(state.workspace.metrics?.cohorts) > MAX_ROWS && state.view === "results" ? `Only the first ${MAX_ROWS} supplied cohort summaries are included.` : "Use the source page to inspect underlying evidence."];
  }

  /** Build a whitelisted snapshot, rejecting app drift and unsupported page identifiers. */
  function model(state, generatedAt) {
    const definition = PAGES[state.view];
    if (!Object.hasOwn(PAGES, state.view) || !state.workspace || state.workspace.app?.id !== state.app) throw new Error("Load the selected app before preparing this page report.");
    if (generatedAt === undefined) generatedAt = new Date().toISOString();
    return {schema:"growth.page-report.v1", page:state.view, title:definition[0], purpose:definition[1], next_step:definition[2],
      ...reportContext(state), generated_at:text(generatedAt), filters:reportFilters(state),
      metrics:pageMetrics(state.view, state), cohorts:state.view === "results" ? cohortRows(state.workspace) : [],
      notes:reportNotes(state)};
  }

  function metricTable(report) {
    return `<table><caption>Page analytics — ${escape(report.title)}</caption><thead><tr><th scope="col">Metric</th><th scope="col">Value</th><th scope="col">Source and coverage</th></tr></thead><tbody>${report.metrics.map(m => `<tr><th scope="row">${escape(m.label)}</th><td>${m.value === null ? "Unavailable" : escape(m.value)}${m.value === null ? "" : ` (${escape(m.unit)})`}</td><td>${escape(sourceLabel(m.source))}</td></tr>`).join("")}</tbody></table>`;
  }

  function panel(report) {
    return `<section class="panel page-reporting" aria-labelledby="page-reporting-title"><div class="section-heading"><h2 id="page-reporting-title">Page guide & analytics</h2><button type="button" class="button outline" data-report-page>Report / Save PDF</button></div><p>${escape(report.purpose)} <strong>Next:</strong> ${escape(report.next_step)}</p><p class="description">${escape(report.app_name)} · ${escape(scopeLabel(report.scope))} · Loaded: ${escape(report.loaded_at)}</p><div class="page-metric-grid">${report.metrics.map(m => `<div><span>${escape(m.label)}</span><strong>${m.value === null ? "Unavailable" : escape(m.value)}</strong><small>${escape(sourceLabel(m.source))}</small></div>`).join("")}</div><p class="description">Local operational counts; missing sources stay unavailable. Report opens a printable preview. Choose Print / Save as PDF there.</p></section>`;
  }

  function reportHTML(report, origin) {
    const cohorts = report.cohorts.map(c => `<section class="report-cohort"><h2>Cohort: ${escape(c.id)}</h2><p>Status: ${escape(c.status)} · Horizon: ${escape(c.horizon)} · Currency: ${escape(c.currency)}</p><dl>${Object.entries(c).filter(([key]) => !["id", "status", "horizon", "currency"].includes(key)).map(([key, value]) => `<div><dt>${escape(key.replaceAll("_", " "))}</dt><dd>${value === null ? "Unavailable" : escape(value)}</dd></div>`).join("")}</dl></section>`).join("");
    return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>${escape(report.title)} — WMM report</title><link rel="stylesheet" href="${escape(origin)}/page-reporting.css"></head><body class="wmm-print-report"><header><p>WMM · Evidence report</p><h1>${escape(report.title)}</h1><p>${escape(report.app_name)} · ${escape(report.app_id || report.scope)}</p></header><nav class="report-controls" aria-label="Report actions"><button type="button" id="print-page-report">Print / Save as PDF</button><button type="button" id="close-page-report">Close report</button><p>The browser print dialog lets you select Save as PDF. No file has been saved until you complete that step.</p></nav><main><p>${escape(report.purpose)}</p><p><strong>Next step:</strong> ${escape(report.next_step)}</p><dl><div><dt>Generated</dt><dd>${escape(report.generated_at)}</dd></div><div><dt>Loaded / evaluated</dt><dd>${escape(report.loaded_at)}</dd></div><div><dt>App setup version</dt><dd>${escape(report.manifest_version ?? "Portfolio scope")}</dd></div>${Object.entries(report.filters).map(([key, value]) => `<div><dt>${escape(key.replaceAll("_", " "))}</dt><dd>${escape(value || "None")}</dd></div>`).join("")}</dl>${metricTable(report)}${cohorts}<section><h2>Evidence boundaries</h2><ul>${report.notes.map(note => `<li>${escape(note)}</li>`).join("")}</ul></section></main><footer>Saved local evidence. No publication, spend or approval authority.</footer></body></html>`;
  }

  function openReport(report, browser) {
    const popup = browser.open("about:blank", "_blank");
    if (!popup) throw new Error("Allow a report window for this local app, then try Report / Save PDF again. Saved work is unchanged.");
    popup.document.open();
    popup.document.write(reportHTML(report, browser.location.origin));
    popup.document.close();
    popup.opener = null;
    popup.document.getElementById("print-page-report").addEventListener("click", () => popup.print());
    popup.document.getElementById("close-page-report").addEventListener("click", () => popup.close());
    popup.focus();
    return popup;
  }

  function decorate(state, document) {
    const main = document.getElementById("main");
    main.querySelector(".page-reporting")?.remove();
    const markup = panel(model(state));
    const anchor = main.querySelector(".wmm-overview-story") || main.querySelector(".page-heading, .hero");
    if (anchor) anchor.insertAdjacentHTML("afterend", markup);
    else main.insertAdjacentHTML("afterbegin", markup);
  }
  return {PAGES, overviewStory, model, pageMetrics, evidenceMetrics, weeklyMetrics, cohortRows, metricTable, panel, reportHTML, openReport, decorate};
});
