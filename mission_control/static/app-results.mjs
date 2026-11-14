import { status } from './app.mjs';
import { connectionSetup } from './app-connections.mjs';
import { openJob } from './app-ui.mjs';
import {
  $,
  api,
  button,
  empty,
  esc,
  heading,
  json,
  label,
  notice,
  refresh,
  render,
  state,
  toast,
} from './app.mjs';
import { WMMObservationalCampaign } from './observational-campaign.mjs';
import {
  analyticsOverviewPanel,
  automationRulesPanel,
  ruleStudySelection,
  savedWhen,
} from './app-campaign.mjs';
import { attributionPanel } from './attribution.mjs';
import { briefForm } from './app-production.mjs';
import { download, field, modal, money, percent } from './app-ui.mjs';
import { guidedEvidenceStates } from './guided-workflow.mjs';
import { insightsPanel } from './insights.mjs';
import { installAttributionPanel } from './app-install.mjs';
import { openRender, renderForm } from './creative-rendering.mjs';
import { outcomeLearningPanel } from './outcome-learning.mjs';
import { paymentResultsPanel } from './signed-payments.mjs';
import { storekitPanel } from './storekit.mjs';
import {
  WMMCustomerWorkflow,
  WMMFunnels,
  WMMGrowthReview,
  WMMPageReports,
  WMMSubscriptionAuthoring,
} from './feature-apis.mjs';
('use strict');

function kpiGapPanel() {
  const gaps = state.workspace?.metrics?.kpi_gaps || [];
  if (!gaps.length) return '';
  return `<section class="panel" aria-label="KPI gaps"><h2>KPI gaps remain explicit</h2><p class="description">These metrics are not collected; no value, zero or provider proxy is inferred.</p><div class="table-wrap"><table class="result-table"><thead><tr><th>Metric</th><th>Status</th><th>Reason</th></tr></thead><tbody>${gaps.map((gap) => `<tr><td>${esc(gap.metric)}</td><td>${status(gap.status)}</td><td>${esc(gap.reason)}</td></tr>`).join('')}</tbody></table></div></section>`;
}

function launchGatePanel() {
  const gate = state.workspace?.launch_gate;
  if (!gate || gate.status === 'NOT_CONFIGURED') return '';
  const blockers = gate.blockers || [];
  return `<section class="panel" aria-label="Launch measurement gate"><h2>Launch measurement gate</h2><p>Status: ${status(gate.status)}</p>${blockers.length ? `<ul>${blockers.map((item) => `<li>${esc(item.name)}: ${esc(item.detail)}</li>`).join('')}</ul>` : '<p>All measurement checks passed for the newest saved campaign scope.</p>'}<p class="description">A READY gate does not publish, spend or prove an outcome.</p></section>`;
}

function reconciliationPanel() {
  const groups = state.workspace?.reconciliation?.groups || [];
  if (!groups.length) return '';
  return `<section class="panel" aria-label="Cross-source reconciliation"><h2>Cross-source reconciliation</h2><p class="description">Source values stay separate. No average is computed.</p><div class="table-wrap"><table class="result-table"><thead><tr><th>Metric</th><th>Period</th><th>Status</th><th>Sources</th><th>Values</th></tr></thead><tbody>${groups
    .slice(0, 50)
    .map(
      (group) =>
        `<tr><td>${esc(group.metric)}</td><td>${esc(group.period)}</td><td>${status(group.status)}</td><td>${esc(group.sources.join(', '))}</td><td>${group.values.map((item) => `${esc(item.source)}: ${esc(String(item.value))}`).join('; ')}</td></tr>`,
    )
    .join('')}</tbody></table></div></section>`;
}

function creativeLearningPanel() {
  const cycle = state.workspace?.creative_learning;
  if (!cycle) return '';
  return `<section class="panel" aria-label="Creative learning loop"><h2>Creative learning loop</h2><p>Status: ${status(cycle.status)}</p><p>${esc(cycle.next_brief?.seed || '')}</p>${cycle.gaps?.length ? `<ul>${cycle.gaps.map((gap) => `<li>${esc(gap)}</li>`).join('')}</ul>` : '<p>No stage gaps detected in saved evidence.</p>'}<p class="description">Read-only composition; no new authority or publication.</p></section>`;
}

function resultsView() {
  const study = ruleStudySelection();
  const decision = `<section class="panel" aria-labelledby="results-decision-heading"><h2 id="results-decision-heading" tabindex="-1">What should you do next?</h2>
    ${study ? `<h3>${esc(study.link.study.name)}</h3><p>Saved view checked ${esc(savedWhen(study.report.as_of))}.</p>${WMMObservationalCampaign.checkpointMarkup(study.report)}` : '<p>Choose a tracked study to see the result it supports or what you need to collect next.</p>'}
    ${study ? button('Open study evidence', 'first-post-evidence') : ''}${button(study ? 'Change tracked study' : 'Choose a tracked study', 'first-post-open')}</section>`;
  return (
    decision +
    kpiGapPanel() +
    launchGatePanel() +
    reconciliationPanel() +
    creativeLearningPanel() +
    analyticsOverviewPanel() +
    automationRulesPanel() +
    WMMFunnels.panel() +
    installAttributionPanel() +
    WMMGrowthReview.panel(state) +
    WMMSubscriptionAuthoring.panel(state) +
    WMMCustomerWorkflow.panel(state) +
    measurementIntegrityPanel() +
    attributionPanel() +
    storekitPanel() +
    insightsPanel() +
    legacyResultsView()
  );
}

function growthReviewServices() {
  return {
    state,
    modal,
    api,
    refresh,
    toast,
    openExperiment,
    openJob,
    connectionSetup,
    openAccess: () => {
      state.view = 'activity';
      render();
    },
    uuid: () => crypto.randomUUID(),
    FormData,
    document,
    close: () => $('#modal').close(),
    openResearchBrief: (preset) => briefForm(null, null, preset),
    openResearchRender: openRender,
    openResearchHypit: (briefIds) => renderForm(briefIds),
    pageReports: WMMPageReports,
    download,
    browser: window,
    ui: WMMGrowthReview,
  };
}

function measurementIntegrityPanel() {
  const r = state.workspace.measurement_integrity || {
    state: 'UNAVAILABLE',
    counts: null,
    rows: [],
    unallocated: [],
  };
  const counts = r.counts
    ? Object.entries(r.counts)
        .map(([name, count]) => `<span>${esc(label(name))}: <strong>${esc(count)}</strong></span>`)
        .join(' Â· ')
    : 'Comparison unavailable';
  return `<section class="panel" aria-label="Financial evidence comparison"><h2>Do your payment records agree?</h2>${status(r.state)}<p>${counts}</p><p class="description">Compare imported cohort payments with current Stripe settlement evidence. Test payments stay separate. A financial match does not verify customer identity, cohort attribution or complete revenue.</p><div class="button-row">${button('Inspect payment comparison', 'measurement-inspect')}${r.sha256 ? button('Download comparison', 'measurement-download') : ''}${button('Review connections', 'measurement-connections')}</div></section>`;
}

function measurementIntegrityInspect() {
  const r = state.workspace.measurement_integrity;
  const unavailable = !r || r.state === 'UNAVAILABLE';
  const rows = (r?.rows || [])
    .map(
      (row) =>
        `<tr><td>${esc(row.cohort_id)}</td><td>${esc(row.type)}</td><td>${esc(row.currency)}</td><td>${esc(row.amount_minor)}</td><td>${esc(label(row.state))}</td></tr>`,
    )
    .join('');
  modal(
    'Payment evidence comparison',
    `<div class="modal-content">${status(r?.state || 'UNAVAILABLE')}<p>${esc(r?.scope || 'Comparison unavailable. Refresh to retry.')}</p><p>${esc(r?.repair || 'Review source connections.')}</p><p>Provider records without cohort counterparts: <strong>${esc(unavailable ? 'Unknown' : r.unallocated.length)}</strong>. Withheld settlements: ${esc(r?.withheld_settlements ?? 'Unknown')}. Pending receipts: ${esc(r?.pending_receipts ?? 'Unknown')}.</p>${rows ? `<div class="table-wrap"><table class="result-table"><thead><tr><th>Cohort</th><th>Event</th><th>Currency</th><th>Minor units</th><th>Comparison</th></tr></thead><tbody>${rows}</tbody></table></div>` : notice(unavailable ? 'Comparison unavailable; refresh or inspect the source history.' : 'No financial rows available for comparison.', 'warning')}<details><summary>Source fingerprints and financial identifiers</summary><pre>${json(r)}</pre></details></div><div class="modal-actions">${r?.sha256 ? button('Download comparison', 'measurement-download') : ''}${button('Close comparison', 'close')}</div>`,
    'MEASUREMENT INTEGRITY',
  );
}

function legacyResultsView() {
  const metrics = state.workspace.metrics;
  const cohort = metrics.cohorts
    .map((c) =>
      c.status === 'MEASURED'
        ? `<section class="panel"><div class="section-heading"><h2>${esc(c.cohort_id)}</h2>${status(c.status)}</div><p class="description">${esc(c.horizon)} Â· ${esc(c.currency)} Â· supplied cohort evidence</p><div class="table-wrap"><table class="result-table"><thead><tr><th>Outcome</th><th>Observed value</th></tr></thead><tbody><tr><td>Eligible installs</td><td>${c.counts.installs}</td></tr><tr><td>Useful activation</td><td>${percent(c.activation_rate)}</td></tr><tr><td>Paid conversion</td><td>${percent(c.paid_conversion)}</td></tr><tr><td>Paid customer acquisition cost</td><td>${money(c.paid_cac_minor, c.currency)}</td></tr><tr><td>Contribution after acquisition</td><td>${money(c.contribution_after_acquisition_minor, c.currency)}</td></tr></tbody></table></div></section>`
        : notice(c.reason, 'warning'),
    )
    .join('');
  return `${heading('Measure what matters', 'Useful activation, retained value and contributionâ€”not manufactured growth.', button('Add a cohort', 'add-evidence', 'data-kind="cohort"'))}${guidedEvidenceStates()}${ledgerResults()}${notice('A zero denominator stays unavailable. Provider attribution and citation visibility are not proof of incremental revenue.')}${metrics.cohorts.length ? cohort : state.workspace.ledger.length ? notice('Event-derived acquisition results appear above. Manual summary worksheets are optional.') : empty('No acquisition results yet', 'Import a mature cohort with its source, currency and complete costs. Until then, CAC and conversion remain unavailable.', button('Add cohort evidence', 'add-evidence', 'data-kind="cohort"'))}<div class="section-heading"><h2>ASA & answer-engine visibility</h2>${button('Import worksheet', 'add-evidence', 'data-kind="acquisition"')}</div>${metrics.acquisition.length ? metrics.acquisition.map((result, i) => `<section class="panel"><h3>Worksheet ${i + 1}</h3>${result.asa ? `<p>Advisory CPT ceiling: <strong>${money(result.asa.cpt_ceiling_minor, result.asa.currency)}</strong> Â· ${esc(result.asa.status)}</p>` : ''}<details><summary>Inspect citation counts, inputs and scope</summary><pre>${json(result)}</pre></details></section>`).join('') : empty('Establish your search baseline', 'Capture app-specific query answers and source URLs, or supply mature Apple Ads counts. No keyword volume or citations are assumed.')}<div class="section-heading"><h2>Retained usefulness</h2></div>${metrics.retention.length ? metrics.retention.map((r) => `<section class="panel"><h3>${esc(r.window)}</h3><p>${r.retained} / ${r.eligible} eligible Â· ${percent(r.rate)} ${r.mature ? '' : 'â€” follow-up not mature'}</p></section>`).join('') : empty('Use the right value cadence', 'Choose a retention window that matches the useful outcome your app delivers.', button('Add retention evidence', 'add-evidence', 'data-kind="retention"'))}`;
}

function ledgerResults() {
  const rows = state.workspace.ledger || [];
  const panels = rows
    .map(
      (r) =>
        `<section class="panel ledger-panel"><div class="section-heading"><h3>${esc(r.cohort.cohort_id)}</h3>${status(r.status)}</div><p class="description">${esc(r.cohort.release)} Â· ${esc(r.cohort.locale)} Â· ${r.events} imported events · Evidence as of ${esc(r.as_of)}</p>${!r.mature ? notice('Follow-up has not matured yet.', 'warning') : ''}${!r.costs_complete ? notice('Acquisition and delivery costs need explicit export rows, including zero-cost receipts.', 'warning') : ''}${r.observability !== 'OBSERVED' ? notice('Attribution is partial or unknown; conversion and contribution remain inconclusive.', 'warning') : ''}${r.issues.map((issue) => notice(issue, 'warning')).join('')}<div class="table-wrap"><table class="result-table"><thead><tr><th>Event-derived outcome</th><th>Supplied result</th></tr></thead><tbody><tr><td>Eligible installs / activations / paid</td><td>${r.installs} / ${r.activated} / ${r.paid}</td></tr><tr><td>Paid conversion</td><td>${percent(r.paid_conversion)}</td></tr><tr><td>Net proceeds after refunds</td><td>${money(r.net_proceeds_minor, r.cohort.currency)}</td></tr><tr><td>Contribution after costs</td><td>${money(r.contribution_after_acquisition_minor, r.cohort.currency)}</td></tr></tbody></table></div><div class="toolbar">${button('Import event export', 'import-events', `data-id="${esc(r.cohort.cohort_id)}"`)}${button('CSV template', 'event-template')}${button('Download as-of report', 'ledger-report', `data-id="${esc(r.cohort.cohort_id)}"`)}${button('Earlier report', 'ledger-history', `data-id="${esc(r.cohort.cohort_id)}"`)}${r.cohort.economics?.coverage_through ? button('Use covered economics snapshot', 'ledger-covered', `data-id="${esc(r.cohort.cohort_id)}"`) : ''}</div><details><summary>Observation contract, source and reconciliation details</summary><pre>${json(r)}</pre></details></section>`,
    )
    .join('');
  return `${paymentResultsPanel()}${outcomeLearningPanel()}${experimentResults()}<div class="section-heading"><h2>Reconciled event ledger</h2>${button('Define event cohort', 'define-cohort')}</div>${notice('Import permitted exports using opaque IDs only. Late refunds restate these cohorts. Imported files are not authenticated provider notifications.')}${rows.length ? panels + WMMPageReports.sectionsHTML(WMMPageReports.measurementSections({ ledger: rows }), 3) : empty('Start with a declared observation window', 'Define the app build, acquisition dates, follow-up maturity and attribution coverage. Then import a CSV or JSON export.', button('Set up event cohort', 'define-cohort'))}`;
}

function experimentIterationPanel(e) {
  const plan = e.iteration,
    assessment = e.assessments.at(-1)?.data;
  if (!plan || !assessment) return '';
  const samples = Object.entries(assessment.reports || {})
    .map(([arm, row]) => `${esc(label(arm))}: ${esc(row.installs ?? 'unknown')} installs`)
    .join(' · ');
  return `<section class="next-step"><h4>Suggested next decision: ${esc(label(plan.decision))}</h4>
    <p>${esc(plan.reason)}</p><p>Analysis date: ${esc(savedWhen(e.data.analysis_at))}${samples ? ' · ' + samples : ''}</p>
    ${
      plan.draft
        ? `<details><summary>Review one-variable draft</summary><p>${esc(plan.draft.proposed_change)}</p>
      <p>Keep fixed: ${esc(plan.draft.keep_fixed.join(', '))}.</p><p>${esc(plan.draft.next_step)}</p></details>`
        : ''
    }
    <p class="description">This recommendation does not approve, publish, or spend.</p></section>`;
}

function experimentResults() {
  const tests = state.workspace.experiments || [];
  const cards = tests
    .map((e) => {
      const latest = e.assessments.at(-1),
        decision = e.actions.filter((a) => a.data.operation === 'decide').at(-1);
      return `<section class="panel experiment-panel"><div class="section-heading"><h3>${esc(e.data.name)}</h3>${status(e.state)}</div><p>${esc(e.data.hypothesis)}</p><p class="description">${esc(label(e.data.primary_metric))} Â· ${esc(e.data.assignment_method)} Â· analysis ${esc(new Date(e.data.analysis_at).toLocaleString())}</p><p>Approximate sample: ${e.data.sample_plan.control} control / ${e.data.sample_plan.treatment} treatment installs</p>${latest ? `<p>Latest assessment: ${status(latest.data.status)} Â· decision ${status(e.decision_status)}</p>${latest.data.issues.map((i) => notice(i, 'warning')).join('')}` : notice('No assessment recorded. Exposure and the fixed analysis date are required.')}${decision ? `<p>Recorded decision: ${esc(label(decision.data.decision))}</p>` : ''}${WMMPageReports.sectionsHTML(WMMPageReports.measurementSections({ experiments: [e] }), 3)}${experimentIterationPanel(e)}${button('Inspect experiment', 'experiment-open', `data-id="${esc(e.id)}"`)}</section>`;
    })
    .join('');
  const worker = state.workspace.worker || { status: 'NOT_STARTED' };
  return `<div class="section-heading"><h2>Experiments with a fixed learning window</h2>${button('Plan an experiment', 'experiment-create')}</div>${notice('Pre-register before acquisition begins. Compare supplied observations; launch, random assignment, publication and spending are separate actions.')}<p class="description">Local analysis worker: ${esc(label(worker.status))}${worker.last_success ? ` Â· last healthy poll ${esc(new Date(worker.last_success).toLocaleString())}` : ''}</p>${worker.last_error ? notice(worker.last_error, 'error') : ''}${tests.length ? cards : empty('Turn a hypothesis into a bounded test', 'Choose two comparable event cohorts and reviewed creatives, declare the outcome, sample, dates and guardrails, then track exposure and decisions.', button('Register your first test', 'experiment-create'))}`;
}

function experimentSelect(name, title, choices) {
  return `<label class="field" for="field-${name}">${esc(title)}<select id="field-${name}" name="${name}" required><option value="">Chooseâ€¦</option>${choices.map(([id, text]) => `<option value="${esc(id)}">${esc(text)}</option>`).join('')}</select></label>`;
}

function experimentForm() {
  const cohorts = (state.workspace.ledger || []).map((r) => [
    r.cohort.cohort_id,
    `${r.cohort.cohort_id} Â· ${r.cohort.release} Â· ${r.cohort.locale}`,
  ]);
  const assets = state.workspace.records
    .filter((r) => r.kind === 'asset' && r.data.authentic && r.data.rights_cleared)
    .map((r) => [r.id, `${r.title} Â· ${r.data.release}`]);
  const fields = [
    field('name'),
    field('owner'),
    field('hypothesis', '', 'textarea'),
    experimentSelect('primary_metric', 'Primary outcome', [
      ['activation_rate', 'Useful activation'],
      ['paid_conversion', 'Paid conversion'],
      ['retention_rate', 'Retained value'],
    ]),
    field('baseline_rate', '', 'text', 'Fraction, e.g. 0.20; use a measured baseline'),
    field('minimum_detectable_effect', '', 'text', 'Absolute fraction difference, e.g. 0.05'),
    field('treatment_allocation', '0.50', 'text', 'Expected treatment fraction; between 0 and 1'),
    field('analysis_at', '', 'text', 'Fixed ISO timestamp after both follow-up windows'),
    experimentSelect('assignment_method', 'Assignment evidence', [
      ['RANDOMIZED', 'Supplied randomized assignment'],
      ['OBSERVATIONAL', 'Observational comparison'],
    ]),
    field(
      'assignment_source',
      '',
      'text',
      'Assignment receipt; randomization is not verified by this tool',
    ),
    field('min_retention_rate', '', 'text', 'Minimum retained-value fraction'),
    field(
      'max_refund_fraction',
      '',
      'text',
      'Maximum refund fraction; absent purchases stay unknown',
    ),
    field(
      'min_contribution_minor',
      '',
      'text',
      'Minimum contribution in currency minor units; may be negative',
    ),
    field('max_acquisition_minor', '', 'number', 'Maximum acquisition cost per arm, minor units'),
    field(
      'stop_rule',
      '',
      'textarea',
      'When to stop collecting or repair; no automatic campaign action',
    ),
    field('rollback_plan', '', 'textarea', 'Exact prior creative/build and recovery path'),
  ];
  for (const arm of ['control', 'treatment'])
    fields.push(
      experimentSelect(`${arm}_cohort`, `${label(arm)} event cohort`, cohorts),
      experimentSelect(`${arm}_asset`, `${label(arm)} reviewed creative`, assets),
    );
  modal(
    'Plan an experiment',
    `<form id="experiment-form" data-app="${esc(state.app)}"><div class="modal-content">${notice('Create both cohorts with identical release, locale, currency and dates. Acquisition must start in the future. Authentic, rights-cleared image files are verified again when registering.')}${!cohorts.length || !assets.length ? notice('Define event cohorts and review creative assets before registering this test.', 'warning') : ''}<div class="form-grid">${fields.join('')}</div><p id="sample-preview" role="status">Enter baseline, detectable effect and allocation to preview the approximate sample.</p><div class="field-error" id="form-error" role="alert"></div></div><div class="modal-actions"><button type="submit" class="button">Register immutable test</button></div></form>`,
    'EXPERIMENT PLANNING',
  );
}

function samplePreview() {
  const form = $('#experiment-form');
  if (!form) return;
  const v = Object.fromEntries(new FormData(form)),
    b = Number(v.baseline_rate),
    d = Number(v.minimum_detectable_effect),
    f = Number(v.treatment_allocation);
  if (![b, d, f].every((x) => x > 0 && x < 1) || b + d >= 1) {
    $('#sample-preview').textContent = 'Use valid fractions; baseline plus effect must be below 1.';
    return;
  }
  const p = b + d / 2,
    n = (p * (1 - p) * (1 / f + 1 / (1 - f)) * (1.96 + 0.841621) ** 2) / d ** 2;
  $('#sample-preview').textContent =
    `Approximate minimum: ${Math.ceil(n * (1 - f))} control / ${Math.ceil(n * f)} treatment installs. 95% interval, 80% power normal approximation; not proof of lift. Server validates the saved plan.`;
}

async function saveExperiment(form) {
  const data = Object.fromEntries(new FormData(form));
  data.manifest_version = Number(form.dataset.manifestVersion);
  for (const key of ['baseline_rate', 'minimum_detectable_effect', 'treatment_allocation'])
    data[key] = Number(data[key]);
  data.guardrails = {};
  for (const key of [
    'min_retention_rate',
    'max_refund_fraction',
    'min_contribution_minor',
    'max_acquisition_minor',
  ]) {
    data.guardrails[key] = Number(data[key]);
    delete data[key];
  }
  for (const arm of ['control', 'treatment']) {
    data[arm] = { cohort_id: data[`${arm}_cohort`], asset_id: data[`${arm}_asset`] };
    delete data[`${arm}_cohort`];
    delete data[`${arm}_asset`];
  }
  await api(`/api/apps/${form.dataset.app}/experiments`, data);
}

function openExperiment(id) {
  const e = state.workspace.experiments.find((e) => e.id === id),
    latest = e.assessments.at(-1);
  const controls =
    e.state === 'CANCELLED'
      ? ''
      : `${e.state === 'PLANNED' ? button('Record observed exposure', 'experiment-action', `data-id="${esc(id)}" data-operation="observe"`) : button('Evaluate current evidence', 'experiment-evaluate', `data-id="${esc(id)}"`)}${latest ? button('Record decision', 'experiment-action', `data-id="${esc(id)}" data-operation="decide"`) : ''}${e.state === 'DECIDED' ? button('Propose rollback', 'experiment-action', `data-id="${esc(id)}" data-operation="rollback"`) : ''}${button('Record decision note', 'experiment-action', `data-id="${esc(id)}" data-operation="note"`)}${button('Cancel test', 'experiment-action', `data-id="${esc(id)}" data-operation="cancel"`)}`;
  const effect = latest?.data.effect;
  const scheduled = experimentSchedulePanel(e);
  modal(
    e.data.name,
    `<div class="modal-content">${notice('Exposure receipts are operator reported. Rollback is a proposal, not a provider action. Re-evaluate after new imports: previous decisions may become stale.')}${status(e.state)} ${status(latest?.data.status || 'NOT_EVALUATED')} ${status(e.decision_status)}<p>${esc(e.data.hypothesis)}</p>${effect ? `<p>Descriptive difference: ${percent(effect.difference)} Â· 95% interval ${effect.interval.map(percent).join(' to ')}</p><p>${esc(effect.method)}</p>` : notice('No defensible comparison is available yet.', 'warning')}${latest ? latest.data.issues.map((i) => notice(i, 'warning')).join('') : ''}${experimentIterationPanel(e)}${scheduled}<h3>Decision and recovery history</h3>${e.actions.map((a) => `<p><strong>${esc(label(a.data.operation))}</strong> Â· ${esc(a.data.operation === 'note' ? a.data.note || '' : a.data.reason || a.data.source)} Â· ${esc(a.created)}${a.data.operation === 'rollback' ? ' Â· External rollback NOT RUN' : ''}${a.data.operation === 'note' ? ' Â· Human note, not provider verification' : ''}</p>`).join('') || '<p>No lifecycle actions recorded.</p>'}<details><summary>Immutable plan, source hashes and all assessments</summary><pre>${json(e)}</pre></details><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions">${controls}${button('Download experiment', 'experiment-download', `data-id="${esc(id)}"`)}</div>`,
    'EXPERIMENT EVIDENCE',
  );
}

function experimentActionForm(id, operation) {
  const e = state.workspace.experiments.find((e) => e.id === id);
  const fields = {
    observe: [
      field('source', '', 'text', 'Actual exposure receipt; no secrets'),
      field('observed_at', '', 'text', 'Actual ISO timestamp inside the acquisition window'),
    ],
    decide: [
      experimentSelect('decision', 'Decision', [
        ['COLLECT', 'Collect more evidence'],
        ['REPAIR', 'Repair the identified cause'],
        ['STOP', 'Stop this test'],
        ['NEXT_TEST', 'Propose next bounded test'],
      ]),
      field('reason', '', 'textarea'),
    ],
    note: [
      field(
        'note',
        '',
        'textarea',
        'Human note bound to this experiment; not a decision or provider verification',
      ),
    ],
    cancel: [field('reason', '', 'textarea', 'Cancellation leaves all existing evidence intact')],
    rollback: [
      field('target', '', 'text', 'Exact prior creative/build'),
      field('source', '', 'text', 'Evidence supporting rollback'),
      field('reason', '', 'textarea'),
    ],
  };
  modal(
    label(operation),
    `<form id="experiment-action-form" data-app="${esc(state.app)}" data-id="${esc(id)}" data-operation="${operation}" data-version="${e.version}" data-assessment="${esc(e.assessments.at(-1)?.hash || '')}"><div class="modal-content">${notice(operation === 'rollback' ? 'This records a rollback proposal only. No build, campaign or store listing is changed.' : 'This records a local evidence-based action. No campaign, publication or spending will execute.')}<div class="form-grid">${fields[operation].join('')}</div><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button type="submit" class="button">Save ${esc(operation)}</button></div></form>`,
  );
}

async function saveExperimentAction(form) {
  const data = {
    ...Object.fromEntries(new FormData(form)),
    operation: form.dataset.operation,
    version: Number(form.dataset.version),
  };
  if (data.operation === 'decide') data.assessment_hash = form.dataset.assessment;
  await api(`/api/apps/${form.dataset.app}/experiments/${form.dataset.id}/actions`, data);
}

async function handleExperiment(node) {
  const id = node.dataset.id,
    action = node.dataset.action;
  if (action === 'experiment-create') return experimentForm();
  if (action === 'experiment-open') return openExperiment(id);
  if (action === 'experiment-action') return experimentActionForm(id, node.dataset.operation);
  if (action === 'experiment-schedule') return experimentScheduleForm(id);
  if (action === 'experiment-download')
    return download(
      `${state.app}-experiment.json`,
      state.workspace.experiments.find((e) => e.id === id),
    );
  const result = await api(`/api/apps/${state.app}/experiments/${id}/evaluate`, {});
  await refresh();
  openExperiment(id);
  if (result.status === 'AWAITING_ANALYSIS')
    toast(
      `Analysis waits until ${new Date(result.analysis_at).toLocaleString()}. No early result recorded.`,
    );
}

function experimentSchedulePanel(e) {
  const schedule = state.workspace.schedules?.find((s) => s.experiment_id === e.id);
  const active = e.state !== 'PLANNED' && e.state !== 'CANCELLED';
  const limit = schedule?.finite_limit;
  return `<section class="panel schedule-panel"><h3>Automatic evidence analysis</h3>${schedule ? `<p>${status(schedule.status)} Â· every ${schedule.interval_hours} hours Â· failures ${schedule.failures} / 3</p><p class="description">Next due ${esc(new Date(schedule.next_due).toLocaleString())}${schedule.last_job_status ? ` Â· latest job ${esc(label(schedule.last_job_status))}` : ''}</p>${limit ? `<p>${esc(limit.remaining)} of ${esc(limit.max_observations)} observations remaining Â· expires ${esc(new Date(limit.expires_at).toLocaleString())}</p>` : notice('This older schedule needs a new owner authorization before it can run.', 'warning')}` : '<p>Disabled until you explicitly configure it.</p>'}${notice('Runs while this local service is open. Pausing cancels queued analysis and blocks an assessment that has not yet committed. No campaign, publication or spending executes.')}${active ? button(schedule?.enabled ? 'Configure or pause analysis' : 'Enable automatic analysis', 'experiment-schedule', `data-id="${esc(e.id)}"`) : notice('Record exposure before scheduling; cancelled experiments remain stopped.')}${schedule?.last_job ? button('Inspect scheduled run', 'job', `data-id="${esc(schedule.last_job)}"`) : ''}</section>`;
}

function experimentScheduleIdentity() {
  const w = state.workspace || {},
    identity = w.identity || {},
    role = (w.access?.members || []).find(
      (m) => m.principal === identity.principal && m.status === 'ACTIVE',
    );
  return {
    app: state.app,
    manifest: w.app?.version,
    principal: identity.principal,
    status: identity.status,
    expires: identity.expires_at_epoch,
    role: role?.role,
    roleVersion: role?.version,
    csrf: state.boot?.csrf,
  };
}

function experimentScheduleForm(id) {
  const schedule = state.workspace.schedules?.find((s) => s.experiment_id === id);
  const identity = experimentScheduleIdentity(),
    experiment = state.workspace.experiments.find((e) => e.id === id);
  if (identity.status !== 'AUTHENTICATED' || identity.role !== 'OWNER')
    return modal(
      'Owner access required',
      `<div class="modal-content">${notice('Sign in as the current app owner to authorize or pause local monitoring.', 'warning')}${identity.status !== 'AUTHENTICATED' ? button('Sign in', 'identity-login') : !state.workspace.access?.configured ? button('Establish app owner', 'access-bootstrap') : ''}</div>`,
    );
  const expires =
    schedule?.finite_limit?.expires_at || new Date(Date.now() + 7 * 86400000).toISOString();
  modal(
    'Automatic evidence analysis',
    `<form id="experiment-schedule-form" data-app="${esc(identity.app)}" data-id="${esc(id)}" data-version="${schedule?.version || ''}" data-binding="${esc(JSON.stringify(identity))}" data-source="${esc(experiment.hash)}"><div class="modal-content">${notice('Enable a finite local assessment. The first run waits for the fixed analysis date; choose an expiry after that date and within 90 days. Saving an enabled schedule creates a new finite allowance. Failed or interrupted runs use a reservation. Three operational failures pause the schedule. Restored snapshots need fresh owner authorization.')}<div class="form-grid">${field('enabled', schedule?.enabled ?? false, 'boolean')}${field('interval_hours', schedule?.interval_hours || 24, 'number', 'Whole hours, from 1 through 168')}${field('max_observations', schedule?.finite_limit?.max_observations || 7, 'number', 'Maximum 1 through 30 local observations')}${field('expires_at', expires, 'text', 'ISO timestamp with timezone; at most 90 days')}</div><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button type="submit" class="button">Save analysis schedule</button></div></form>`,
  );
}

async function saveExperimentSchedule(form) {
  if (form.dataset.submitting === 'true') throw new Error('This schedule is already being saved.');
  const data = Object.fromEntries(new FormData(form));
  const binding = form.dataset.binding,
    valid = () =>
      form.isConnected &&
      JSON.stringify(experimentScheduleIdentity()) === binding &&
      state.workspace.experiments.some(
        (e) => e.id === form.dataset.id && e.hash === form.dataset.source,
      );
  if (!valid()) throw new Error('App or owner session changed. Reopen this schedule.');
  const body = {
    enabled: data.enabled === 'true',
    interval_hours: Number(data.interval_hours),
    version: form.dataset.version ? Number(form.dataset.version) : null,
  };
  if (body.enabled)
    Object.assign(body, {
      manifest_version: state.workspace.app.version,
      expires_at: data.expires_at,
      max_observations: Number(data.max_observations),
    });
  form.dataset.submitting = 'true';
  try {
    await api(`/api/apps/${form.dataset.app}/experiments/${form.dataset.id}/schedule`, body);
    if (!valid())
      throw new Error('App or owner session changed. Refresh to inspect the saved schedule.');
  } finally {
    delete form.dataset.submitting;
  }
}

function cohortEconomicsFields() {
  const choice = (name, title, choices) =>
    `<label class="field" for="${name}">${esc(title)}<select id="${name}" name="${name}">${choices.map(([value, caption]) => `<option value="${value}">${esc(caption)}</option>`).join('')}</select></label>`;
  return `<fieldset><legend>Optional acquisition economics</legend><p>Leave cost basis unselected to keep the original cohort definition. If selected, supply all six fields. These declarations are not provider verification.</p><div class="form-grid">${choice(
    'economics_cost_basis',
    'Cost basis (optional)',
    [
      ['', 'Not supplied'],
      ['MEDIA_SPEND', 'Media spend'],
      ['TOTAL_ACQUISITION_COST', 'Total acquisition cost'],
    ],
  )}${choice('economics_revenue_basis', 'Revenue basis', [
    ['', 'Choose when supplying economics'],
    ['NET_PROCEEDS', 'Net proceeds'],
    ['GROSS_REVENUE', 'Gross revenue'],
  ])}${choice('economics_attribution_status', 'Attribution coverage', [
    ['', 'Choose when supplying economics'],
    ['DECLARED_MATCHED', 'Declared matched'],
    ['PARTIAL', 'Partial'],
    ['UNAVAILABLE', 'Unavailable'],
  ])}${field('economics_spend_source', '', 'text', 'Spend export / receipt reference; no credentials', false, 'Spend source')}${field('economics_currency', '', 'text', 'Must match the cohort and imported costs', false, 'Economics currency')}${field('economics_coverage_through', '', 'text', 'ISO timestamp with timezone through which coverage is complete', false, 'Coverage through')}</div></fieldset>`;
}

function cohortForm() {
  const app = state.workspace.app.data;
  const fields = [
    field('cohort_id', '', 'text', 'New immutable cohort ID; corrections need a new ID'),
    field('release', app.release),
    field('platform'),
    field('locale', app.locale),
    field('currency', app.currency),
    field('starts_at', '', 'text', 'Acquisition start, ISO timestamp with timezone'),
    field('ends_at', '', 'text', 'Acquisition end, ISO timestamp with timezone'),
    field('matures_at', '', 'text', 'Follow-up maturity, ISO timestamp with timezone'),
    field('attribution_method'),
    field('source', '', 'text', 'Observation contract/export receipt; no secrets'),
  ];
  const observable = `<label class="field" for="field-observability">Observation coverage<select id="field-observability" name="observability"><option value="UNKNOWN">Unknown</option><option value="PARTIAL">Partial or privacy suppressed</option><option value="OBSERVED">Observed under the documented contract</option></select></label>`;
  modal(
    'Define event cohort',
    `<form id="cohort-form"><div class="modal-content">${notice('Definitions and imported events are immutable. Use a fresh cohort for corrected boundaries; snapshots preserve the originals.')}<div class="form-grid">${fields.join('')}${observable}</div>${cohortEconomicsFields()}<div class="field-error" id="form-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit">Save event cohort</button></div></form>`,
  );
}

function historicalForm(id) {
  modal(
    'Reproduce an earlier report',
    `<form id="history-form" data-cohort="${esc(id)}"><div class="modal-content">${notice('Only events observed by this timestamp will count. Later refunds remain in the ledger and restate later reports.')}${field('as_of', new Date().toISOString(), 'text', 'ISO timestamp with timezone; no future dates')}<div class="field-error" id="form-error" role="alert"></div></div><div class="modal-actions"><button type="submit" class="button">Inspect historical report</button></div></form>`,
  );
}

export {
  resultsView,
  growthReviewServices,
  measurementIntegrityPanel,
  measurementIntegrityInspect,
  legacyResultsView,
  ledgerResults,
  experimentIterationPanel,
  experimentResults,
  experimentSelect,
  experimentForm,
  samplePreview,
  saveExperiment,
  openExperiment,
  experimentActionForm,
  saveExperimentAction,
  handleExperiment,
  experimentSchedulePanel,
  experimentScheduleIdentity,
  experimentScheduleForm,
  saveExperimentSchedule,
  cohortForm,
  historicalForm,
};
