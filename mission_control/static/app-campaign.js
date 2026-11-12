'use strict';

function campaignPlanOpen() {
  const goal =
    state.goalChoice?.app === state.app
      ? state.goalChoice.id
      : typeof WMMGoalJourney !== 'undefined'
        ? WMMGoalJourney.read(WMMGoalJourney.browserStorage(), state.app)
        : '';
  const value = WMMCampaignPlan.build(state.workspace, { goal });
  state.campaignPlan = value;
  const missing = value.missing.length
    ? notice(`Missing before this plan is complete: ${value.missing.join(', ')}.`, 'warning')
    : notice(
        'Planner inputs are present. Saved evidence still needs current release, locale and rights review.',
      );
  modal(
    'Campaign plan',
    `<div class="modal-content"><div class="section-heading"><div><p class="eyebrow">MARKETING PLAN</p><h2>${esc(state.workspace?.app?.data?.name || state.app)}</h2></div>${status(value.status)}</div><p><strong>${esc(value.objective.metric)}</strong> for <strong>${esc(value.positioning.audience || 'your audience')}</strong>${value.channels.pilot ? ` via <strong>${esc(value.channels.pilot)}</strong>` : ''}.</p><p class="description">Agent-proposed draft. You edit and approve; this plan does not publish or spend.</p>${missing}<h3>Objective</h3><p><strong>${esc(value.objective.metric)}</strong> · baseline ${esc(value.objective.baseline)}</p><p class="description">${esc(value.objective.baseline_reason)}</p><h3>Audience and hypothesis</h3><p><strong>${esc(value.positioning.audience || 'Audience not supplied')}</strong> · ${esc(value.positioning.job || 'User job not supplied')}</p><p>${esc(value.positioning.hypothesis)}</p><h3>Pilot channel</h3><p><strong>${esc(value.channels.pilot || 'Not selected')}</strong>${value.channels.alternatives.length ? ` · alternatives ${esc(value.channels.alternatives.join(', '))}` : ''}</p><p class="description">${esc(value.channels.basis)}</p><h3>Proof to verify</h3><p>Saved claims ${value.proof.claims} · screens/assets ${value.proof.assets} · readiness ${value.proof.readiness} · store ${value.proof.store} · first-value routes ${value.proof.route}</p><p class="description">Counts are saved evidence, not current approval or public availability.</p><h3>Measurement and guardrails</h3><p><strong>Next:</strong> ${esc(value.measurement.next_action)}</p><p>Window: ${esc(value.measurement.window)}</p><p>Stop: ${esc(value.measurement.stop_rule)}</p><p>Rollback: ${esc(value.measurement.rollback)}</p><h3>Budget</h3><p>${esc(value.distribution.budget_minor)} ${esc(value.distribution.currency || '')} · ${esc(value.distribution.mode)} · no spend authorized</p><details><summary>Boundaries</summary><ul>${value.boundaries.map((item) => `<li>${esc(item)}</li>`).join('')}</ul></details><div class="modal-actions">${button('Download Markdown', 'campaign-plan-download-md')}${button('Download JSON', 'campaign-plan-download-json')}${button('Close', 'close')}</div></div>`,
    'CAMPAIGN PLAN',
  );
}

async function nextAnswer() {
  const app = state.app,
    workspace = state.workspace;
  if (!workspace) throw new Error('Wait for this app to load.');
  const next = workspace.workflow?.next_action ||
    workspace.automation?.next_action || { title: 'Review the saved workflow' };
  const analytics = WMMAnalyticsInventory.summary(workspace);
  const exceptions = workspace.workflow?.exceptions || [];
  const packets = (workspace.approvals || []).filter((row) => row.status === 'WAITING_REVIEW');
  let publications = { authorities: [], intents: [] },
    unavailable = false;
  try {
    publications = await api(`/api/apps/${encodeURIComponent(app)}/publications`);
  } catch {
    unavailable = true;
  }
  if (state.app !== app || !state.workspace) return;
  const authorities = (publications.authorities || []).filter((row) =>
    ['PREPARED', 'APPROVED'].includes(row.status),
  );
  const intents = publications.intents || [];
  const hashes = [...packets.map((row) => row.hash), ...authorities.map((row) => row.review_hash)]
    .filter(Boolean)
    .sort();
  const index = hashes.length ? await digestText(hashes.join('\n')) : null;
  if (state.app !== app || !state.workspace) return;
  const exceptionRows = exceptions
    .slice(0, 3)
    .map(
      (row) =>
        `<article class="next-step"><div><h3>${esc(row.headline)}</h3><p>${esc(row.reason)}</p><p><strong>Next:</strong> ${esc(row.action)}</p></div></article>`,
    )
    .join('');
  const approvalRows = [
    ...packets.map(
      (row) =>
        `<p><strong>Manual review packet</strong> ${esc(row.id)} · expires ${esc(row.expires || 'saved expiry')} · hash ${esc((row.hash || '').slice(0, 16))}…</p>`,
    ),
    ...authorities.map(
      (row) =>
        `<p><strong>${esc(row.status === 'APPROVED' ? 'Approved publication' : 'Prepared publication')}</strong> ${esc(row.id)} · hash ${esc((row.review_hash || '').slice(0, 16))}…</p>`,
    ),
    ...intents.map(
      (row) =>
        `<p><strong>Publication result</strong> ${esc(row.id || 'saved receipt')} · ${esc(row.status || 'unknown state')}</p>`,
    ),
  ].join('');
  modal(
    'What should I do next?',
    `<div class="modal-content"><p class="eyebrow">NEXT ACTION</p><h3>${esc(next.title)}</h3><p>This answer is read-only. It does not approve, publish or spend.</p><p><strong>Measurement next:</strong> ${esc(analytics.step.title)}. ${esc(analytics.step.detail)}</p>${exceptionRows ? `<h3>Needs attention</h3>${exceptionRows}` : ''}<h3>Pending approvals</h3>${approvalRows || notice('No prepared publication approval or manual review packet is waiting.')}${unavailable ? notice('Publication approvals could not be loaded; reload before relying on this list.', 'warning') : ''}${index ? `<details><summary>Review index</summary><p class="app-mono">${esc(index)}</p><p class="description">A display index of the listed review hashes only. Each item still needs its own exact review and approval.</p></details>` : ''}<div class="modal-actions">${button('Open guided workflow', 'next-answer-workflow')}${button('Open analytics', 'next-answer-results')}${button('Open organic publishing', 'next-answer-publishing')}${button('Close', 'close')}</div></div>`,
    'NEXT STEP',
  );
}

function measuredPostEvidence(link, destination, pubs, workspace, scopes = [], tracked = null) {
  if (!destination)
    return { delivery: false, ambiguous: false, queued: false, approved: false, coverage: null };
  const channel = link.study.source;
  const approvals = (pubs?.authorities || []).filter(
    (row) =>
      row.draft?.provider === channel &&
      row.draft.link === link.url &&
      row.draft.destination_id === destination,
  );
  const ids = new Set(approvals.map((row) => row.id));
  const intents = (pubs?.intents || []).filter((row) => ids.has(row.authority_id));
  const facebook =
    channel === 'facebook'
      ? (workspace.jobs || []).filter(
          (row) =>
            row.action === 'campaign_post' &&
            row.data?.request?.link === link.url &&
            (row.result?.page_id != null
              ? row.result.page_id === destination
              : scopes?.some(
                  (scope) => scope.scope_id === row.data.scope_id && scope.page_id === destination,
                )),
        )
      : [];
  const delivered = new Set([
    ...(channel === 'facebook' ? tracked?.records || [] : [])
      .filter((row) => row.page_id === destination && row.remote_id)
      .map((row) => row.remote_id),
    ...intents
      .filter(
        (row) => row.status === 'PUBLISHED' && (row.remote_id || row.asset_id) && row.receipt_hash,
      )
      .map((row) => row.remote_id || row.asset_id),
    ...facebook
      .filter(
        (row) =>
          row.status === 'SUCCEEDED' && row.result?.status === 'VERIFIED' && row.result.remote_id,
      )
      .map((row) => row.result.remote_id),
  ]).size;
  const queued =
    approvals.some((row) => ['QUEUED', 'RUNNING'].includes(row.schedule?.job_status)) ||
    intents.some((row) => !['FAILED', 'UNKNOWN', 'PUBLISHED'].includes(row.status)) ||
    facebook.some((row) => ['QUEUED', 'RUNNING'].includes(row.status));
  const installs = workspace.install_attribution?.campaigns?.find(
    (row) => row.campaign_token === link.study_id && row.study_status === 'LINKED',
  );
  const complete = channel !== 'facebook' || tracked?.complete !== false;
  return {
    delivery: delivered === 1 && complete,
    ambiguous: delivered > 1,
    queued,
    approved: approvals.some((row) => row.status === 'APPROVED'),
    coverage: installs?.coverage_status || null,
    historyAvailable:
      channel === 'facebook'
        ? Array.isArray(workspace.jobs) && Array.isArray(scopes) && tracked?.complete === true
        : Array.isArray(pubs?.authorities) && Array.isArray(pubs?.intents),
  };
}

function measuredPostContext() {
  const w = state.workspace,
    expiry = w?.identity?.expires_at_epoch;
  if (Number.isFinite(expiry) && expiry <= Date.now() / 1000) return null;
  return JSON.stringify([
    state.app,
    w?.app?.version,
    w?.identity?.principal,
    expiry,
    state.boot?.csrf,
  ]);
}

async function firstMeasuredPost(offset = 0) {
  state.measuredPost = null;
  const app = state.app,
    context = measuredPostContext();
  if (!context) throw new Error('Sign in again to review your study and its saved receipts.');
  modal(
    'Your first measured post',
    '<div class="modal-content" id="first-post-panel"><p role="status">Loading saved studies…</p></div>',
    'GUIDED PATH',
  );
  const panel = $('#first-post-panel');
  const current = () => panel.isConnected && $('#modal').open && measuredPostContext() === context;
  try {
    const history = await api(
      `/api/apps/${encodeURIComponent(app)}/observational-campaign/history`,
      { offset },
    );
    if (!current()) return;
    const studies = (history.records || []).filter(
      (row) => row.kind === 'REGISTERED' && row.data.app_version === state.workspace.app.version,
    );
    const page = (title, start) => button(title, 'first-post-page', 'data-offset=' + String(start));
    panel.innerHTML = `<p>Choose one study to track its own draft, delivery and evidence.</p>
      <label class="field">Registered study<select id="first-post-study"><option value="">Choose a study</option>${studies.map((row, i) => `<option value="${i}">${esc(row.data.study_id)}</option>`).join('')}</select></label>
      ${studies.length ? '' : '<p>No current study registrations on this page.</p>'}
      ${offset > 0 ? page('Newer activity', Math.max(0, offset - history.limit)) : ''}
      ${history.records?.length === history.limit && offset + history.limit <= 10000 ? page('Older activity', offset + history.limit) : ''}
      ${button('Register or browse studies', 'observational-campaign-open')}<div id="first-post-selection" role="status"></div>`;
    const select = panel.querySelector('select'),
      output = panel.querySelector('#first-post-selection');
    let generation = 0;
    select.addEventListener('change', async () => {
      const index = select.value,
        request = ++generation;
      state.measuredPost = null;
      const valid = () => current() && request === generation;
      if (index === '') {
        output.replaceChildren();
        return;
      }
      const row = studies[Number(index)]?.data;
      if (!row) return;
      const binding = {
        manifest_version: row.app_version,
        study_id: row.study_id,
        study_hash: row.study_hash,
      };
      output.textContent = 'Preparing the study link…';
      try {
        const url = `/api/apps/${encodeURIComponent(app)}`;
        const link = await api(url + '/observational-campaign/link', binding);
        if (!valid()) return;
        const linkHash = link.study.source === 'facebook' ? await campaignHash(link.url) : null;
        if (!valid()) return;
        const [pubs, report, campaigns] = await Promise.all([
          link.study.source === 'facebook'
            ? Promise.resolve(null)
            : api(url + '/publications').catch(() => null),
          api(url + '/observational-campaign/report', binding).catch(() => null),
          link.study.source === 'facebook'
            ? api(url + '/campaigns/history', { approved_link_sha256: linkHash }).catch(() => null)
            : Promise.resolve(null),
        ]);
        if (!valid()) return;
        const destinations = new Map();
        for (const a of pubs?.authorities || [])
          if (a.draft?.provider === link.study.source && a.draft.link === link.url)
            destinations.set(a.draft.destination_id, a.draft.destination_id);
        for (const receipt of campaigns?.tracked_posts?.records || [])
          destinations.set(receipt.page_id, receipt.page_id);
        const ready = new Set();
        for (const account of WMMPublicationUI.eligibleDestinations(
          link.study.source,
          state,
          pubs,
        )) {
          destinations.set(account.destination_id, account.name || account.destination_id);
          ready.add(account.destination_id);
        }
        const exactReport =
          report?.app_id === app &&
          report.study_id === link.study_id &&
          report.study_hash === link.study_hash
            ? report
            : null;
        const selected = (state.measuredPost = {
          app,
          context,
          link,
          binding,
          destination: '',
          report: exactReport,
        });
        output.innerHTML = `<h3>${esc(link.study.name)}</h3><p>${esc(link.study.hypothesis)}</p><p>Observation window: ${esc(savedWhen(link.study.starts_at))} to ${esc(savedWhen(link.study.ends_at))}</p>
          <label class="field">Exact tagged link<input readonly value="${esc(link.url)}"></label>
          <label class="field">Destination<select id="first-post-destination"><option value="">Choose where this post belongs</option>${[...destinations].map(([id, title]) => `<option value="${esc(id)}">${esc(title)}</option>`).join('')}</select></label>
          <p id="first-post-progress">Choose a destination to check delivery.</p>
          ${exactReport ? WMMObservationalCampaign.checkpointMarkup(exactReport) : '<p>Measurement report unavailable. Reopen this guide to retry.</p>'}
          ${exactReport ? button('Save study report as PDF', 'first-post-report-pdf') : ''}
          ${exactReport ? button('Review this study in Results', 'first-post-results') : ''}
          ${button('Prepare tagged draft', 'first-post-publishing')}${button('Prepare creative brief', 'first-post-brief')}${button('Import installs for this study', 'first-post-import')}`;
        const draftButton = output.querySelector('[data-action="first-post-publishing"]');
        draftButton.disabled = true;
        if (!destinations.size) {
          output.querySelector('#first-post-progress').textContent =
            'Connect a destination for this channel before preparing a post.';
        }
        if (!ready.size)
          output
            .querySelector('#first-post-progress')
            .insertAdjacentHTML(
              'afterend',
              button(
                link.study.source === 'instagram'
                  ? 'Verify the linked Instagram account'
                  : 'Review connections',
                link.study.source === 'instagram'
                  ? 'next-answer-publishing'
                  : 'measurement-connections',
              ),
            );
        output.querySelector('select').addEventListener('change', (event) => {
          if (!valid() || state.measuredPost !== selected) return;
          selected.destination = event.target.value;
          draftButton.disabled = !ready.has(selected.destination);
          const e = measuredPostEvidence(
            link,
            selected.destination,
            pubs,
            state.workspace,
            campaigns?.scopes ?? null,
            campaigns?.tracked_posts,
          );
          output.querySelector('#first-post-progress').textContent = !selected.destination
            ? 'Choose a destination to check delivery.'
            : `Publication: ${e.ambiguous ? 'Multiple delivered posts share this tag; keep results at study level' : e.delivery ? 'Delivered · provider verified' : e.queued ? 'Queued · delivery pending' : e.approved ? 'Approved · not queued' : e.historyAvailable ? 'No matching receipt in recent history' : 'Delivery history unavailable; reopen this guide to retry'}. Install export: ${e.coverage === 'COMPLETE' ? 'Matching window covered' : e.coverage ? 'Matching export · coverage incomplete' : 'Unknown'}.`;
        });
      } catch (error) {
        if (valid()) output.textContent = error.message;
      }
    });
  } catch (error) {
    if (current()) panel.textContent = error.message;
  }
}

function selectedMeasuredPost() {
  const current = state.measuredPost;
  if (!current || current.context !== measuredPostContext())
    throw new Error('Reopen Your first measured post and select a current study.');
  return current;
}

function savedWhen(value) {
  if (!value) return 'Not recorded';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'Not recorded' : date.toLocaleString();
}

function analyticsOverviewPanel() {
  const view = WMMAnalyticsInventory.summary(state.workspace || {});
  const counts = view.counts;
  const controls = {
    cohorts: counts.cohorts
      ? ''
      : button('Add cohort evidence', 'add-evidence', 'data-kind="cohort"'),
    ledger: '',
    retention: counts.retention
      ? ''
      : button('Add retention evidence', 'add-evidence', 'data-kind="retention"'),
    installs: button('Import install export', 'install-import-open'),
    payments:
      state.workspace?.measurement_integrity?.state === 'UNAVAILABLE'
        ? button('Review connections', 'measurement-connections')
        : button('Inspect comparison', 'measurement-inspect'),
    experiments: counts.experiments ? '' : button('Plan an experiment', 'experiment-create'),
  };
  const stepControls = {
    add_acquisition: button('Add cohort evidence', 'add-evidence', 'data-kind="cohort"'),
    repair_cohort: button('Add corrected cohort evidence', 'add-evidence', 'data-kind="cohort"'),
    import_installs: button('Import install export', 'install-import-open'),
    repair_payments: button('Review connections', 'measurement-connections'),
    add_retention: button('Add retention evidence', 'add-evidence', 'data-kind="retention"'),
    inspect_result: button('Inspect payment comparison', 'measurement-inspect'),
  };
  const rows = view.areas
    .map(
      (row) =>
        `<tr><td>${esc(row.name)}</td><td>${esc(row.saved)}</td><td>${esc(row.id === 'payments' && state.workspace?.measurement_integrity?.state !== 'UNAVAILABLE' ? 'Current comparison' : savedWhen(row.latest))}</td><td>${esc(row.next)}</td><td>${controls[row.id] || ''}</td></tr>`,
    )
    .join('');
  return `<section class="panel" aria-label="Analytics overview"><div class="section-heading"><div><p class="eyebrow">ANALYTICS</p><h2>What you can answer now</h2><p>Saved evidence in ${view.savedCount} of ${view.total} areas. Availability is not confidence, attribution completeness or causality.</p></div></div><div class="table-wrap"><table class="result-table"><caption>Saved analytics evidence and the next useful action</caption><thead><tr><th scope="col">Area</th><th scope="col">Saved evidence</th><th scope="col">Latest saved</th><th scope="col">Next</th><th scope="col">Action</th></tr></thead><tbody>${rows}</tbody></table></div><div class="next-step"><div><h3>${esc(view.step.title)}</h3><p>${esc(view.step.detail)}</p>${stepControls[view.step.id] || ''}</div></div><p class="description">A missing source stays unknown. WMM does not infer installs, revenue, retention or lift from unrelated counts.</p></section>`;
}

function automationRulesPanel() {
  const operator = experimentScheduleIdentity();
  if (operator.status !== 'AUTHENTICATED' || operator.role !== 'OWNER') return '';
  const sample = {
    schema: 'wmm.automation-rules.v1',
    mode: 'PROPOSE_ONLY',
    timezone: state.workspace?.app?.data?.timezone || 'UTC',
    rules: [
      {
        id: 'cohort-setup-review',
        enabled: true,
        priority: 5,
        when: { fact: 'metrics.cohort_count', op: 'eq', value: 0 },
        then: {
          propose: {
            action: 'review_measurement_setup',
            tool: 'reports.read',
            reason:
              'This app has no saved cohort metrics. Choose what to measure before starting a test.',
          },
          requires: ['OWNER_REVIEW'],
        },
      },
    ],
  };
  const selected = ruleStudySelection();
  return `<section class="panel" aria-label="Automation rule preview"><details ${selected ? 'open' : ''}><summary>Automation rules</summary><p class="description">See what WMM would suggest using saved evidence. A preview does not approve work, publish or spend.</p>
    ${selected ? `<p><strong>Example for ${esc(selected.link.study.name)}:</strong> If the observation window has ended and coverage is incomplete, suggest collecting the final evidence.</p>${button('Preview this example', 'automation-rules-run', 'data-example="study"')}` : button('Choose study evidence', 'first-post-open')}
    <details><summary>Advanced rule editor</summary><p>Saving adds an immutable version.</p><label class="field" for="automation-rules-json">Rule to preview (JSON)<textarea id="automation-rules-json" name="rules" rows="8" spellcheck="false">${esc(JSON.stringify(sample, null, 2))}</textarea></label><div class="toolbar">${button('Preview draft', 'automation-rules-run')}${button('Load latest into editor', 'automation-rules-load')}${button('Save rules', 'automation-rules-save')}</div></details>
    <details><summary>Saved rule versions</summary>${button('Show saved versions', 'automation-rules-history')}<div id="automation-rules-history" aria-live="polite"></div></details><p id="automation-rules-status" class="description" role="status"></p><div id="automation-rules-result" role="status" aria-live="polite"></div></details></section>`;
}

function automationRulesResult(value, example = false) {
  const labels = new Map([
    ['MATCH', 'Matched'],
    ['NO_MATCH', 'Did not match'],
    ['UNKNOWN', 'Missing or incompatible evidence'],
    ['EXPIRED', 'Expired'],
    ['DISABLED', 'Off'],
  ]);
  const approvals = new Map([
    ['OWNER_REVIEW', 'Owner review'],
    ['EXACT_APPROVAL', 'Approval for the exact action'],
  ]);
  const proposals = value.proposals
    .map(
      (row) =>
        `<article class="next-step"><div><h3>${esc(row.action.replaceAll('_', ' '))}</h3><p>${esc(row.reason)}</p><p><strong>Next:</strong> ${esc(row.requires.map((key) => approvals.get(key) || key).join(', '))}</p>${row.action === 'collect_study_evidence' && value.fact_snapshot?.values?.study ? button('Open study evidence', 'first-post-evidence') : ''}<details><summary>Evidence details</summary><p>Rule: ${esc(row.rule_id)}</p><p class="app-mono">${esc(row.fact_snapshot_sha256)}</p></details></div></article>`,
    )
    .join('');
  const results = value.results
    .map(
      (row) =>
        `<li>${esc(row.rule_id)}: <strong>${esc(labels.get(row.status) || row.status)}</strong>${row.missing?.length ? ` · Missing: ${esc(row.missing.join(', '))}` : ''}${row.incompatible?.length ? ` · Incompatible: ${esc(row.incompatible.join(', '))}` : ''}${row.proposal_status === 'SUPPRESSED_BY_HIGHER_PRIORITY' ? ' · A higher priority rule already suggested the same action.' : ''}</li>`,
    )
    .join('');
  const empty = value.results.some((row) => row.status === 'UNKNOWN')
    ? 'No suggestion yet. Open the rule details to see what evidence is missing.'
    : 'No rule matched the saved evidence.';
  const source = example
    ? 'Example rule (not saved)'
    : value.rule_binding
      ? `Saved version ${esc(value.rule_binding.version)}`
      : 'Draft (not a saved version)';
  const facts = value.fact_snapshot;
  const study = facts?.values?.study;
  const studyStatus = study
    ? `<p><strong>Observed:</strong> Window ${study.window.state === 'ENDED' ? 'ended' : 'still open'} · ${study.coverage === 'COMPLETE' ? 'collector coverage complete' : 'collector coverage incomplete'}.</p><p>Collector-reported evidence. A linked registration rate describes the recorded visits; it does not verify individual identities or establish lift.</p>`
    : '';
  const evidence = Object.entries(facts?.values || {})
    .flatMap(([group, fields]) =>
      Object.entries(fields).map(
        ([name, entry]) =>
          `<tr><th scope="row">${esc(group)}.${esc(name)}</th><td>${esc(JSON.stringify(entry))}</td><td>${esc(facts.sources[group] || 'Saved app evidence')}</td></tr>`,
      ),
    )
    .join('');
  return `<h3>Preview complete</h3><p>${source}${value.observed_at ? ` · ${esc(savedWhen(value.observed_at))}` : ''}</p>${studyStatus}${proposals || `<p>${empty}</p>`}
    <details><summary>Rule results</summary><ul>${results}</ul></details>
    ${
      evidence
        ? `<details><summary>Facts used for this preview</summary><div class="table-wrap"><table class="result-table"><caption>Observed facts; unlisted facts are unavailable</caption><thead><tr><th scope="col">Fact</th><th scope="col">Value</th><th scope="col">Source</th></tr></thead><tbody>${evidence}</tbody></table></div>
    <p>Rule fingerprint: <span class="app-mono">${esc(value.rules_sha256)}</span></p><p>Fact fingerprint: <span class="app-mono">${esc(value.facts_sha256)}</span></p><p>Preview fingerprint: <span class="app-mono">${esc(value.evaluation_sha256)}</span></p></details>`
        : ''
    }`;
}

function ruleStudySelection() {
  const selected = state.ruleStudy;
  return selected?.app === state.app && selected.context === measuredPostContext()
    ? selected
    : null;
}

function studyRuleExample() {
  return {
    schema: 'wmm.automation-rules.v1',
    mode: 'PROPOSE_ONLY',
    timezone: 'UTC',
    rules: [
      {
        id: 'collect-study-evidence',
        enabled: true,
        priority: 5,
        when: {
          all: [
            { fact: 'study.window.state', op: 'eq', value: 'ENDED' },
            { fact: 'study.coverage', op: 'ne', value: 'COMPLETE' },
          ],
        },
        then: {
          propose: {
            action: 'collect_study_evidence',
            tool: 'reports.read',
            reason:
              'The observation window ended. Review the declared collector and reconcile the final landing and registration counts.',
          },
          requires: ['OWNER_REVIEW'],
        },
      },
    ],
  };
}

async function runAutomationRulePreview(node) {
  const panel = node.closest('section'),
    target = panel.querySelector('#automation-rules-result');
  const input = panel.querySelector('#automation-rules-json'),
    binding = JSON.stringify(experimentScheduleIdentity());
  const app = state.app,
    original = input.value;
  const saved = node.dataset?.version
    ? { version: Number(node.dataset.version), hash: node.dataset.hash }
    : null;
  const example = node.dataset?.example === 'study',
    study = ruleStudySelection();
  let payload;
  if (example && !study) {
    target.textContent = 'Choose the study again to preview this example.';
    return;
  }
  try {
    payload = saved ? { saved } : { rules: example ? studyRuleExample() : JSON.parse(original) };
  } catch {
    target.textContent = 'Check the rule JSON and try again.';
    input.focus();
    return;
  }
  if (study) payload.study = study.binding;
  const request = {};
  target.previewRequest = request;
  const stillHere = () =>
    node.isConnected &&
    target.isConnected &&
    target.previewRequest === request &&
    state.app === app &&
    binding === JSON.stringify(experimentScheduleIdentity()) &&
    ruleStudySelection() === study;
  node.disabled = true;
  target.textContent = 'Checking saved evidence…';
  try {
    const result = await api(`/api/apps/${encodeURIComponent(app)}/automation/evaluate`, payload);
    if (!stillHere()) return;
    if (
      saved &&
      (result.rule_binding?.app_id !== app ||
        result.rule_binding.version !== saved.version ||
        result.rule_binding.hash !== saved.hash)
    ) {
      target.textContent = 'The returned preview did not match the selected saved version.';
      return;
    }
    const returnedStudy = result.fact_snapshot?.values?.study;
    if (
      study &&
      (returnedStudy?.id !== study.binding.study_id ||
        returnedStudy.definition_sha256 !== study.binding.study_hash ||
        returnedStudy.manifest_version !== study.binding.manifest_version)
    ) {
      target.textContent = 'The returned preview did not match the selected study.';
      return;
    }
    if (!saved && !example && input.value !== original) {
      target.textContent = 'Your draft changed while checking. Preview the current draft again.';
      return;
    }
    target.innerHTML = automationRulesResult(result, example);
  } catch (error) {
    if (stillHere()) target.textContent = `Could not preview this rule. ${error.message}`;
  } finally {
    if (node.isConnected) node.disabled = false;
  }
}

async function showAutomationVersions(node) {
  const panel = node.closest('section'),
    target = panel.querySelector('#automation-rules-history');
  const app = state.app,
    binding = JSON.stringify(experimentScheduleIdentity()),
    cursor = node.dataset.before;
  const request = {};
  target.historyRequest = request;
  const stillHere = () =>
    target.isConnected &&
    target.historyRequest === request &&
    app === state.app &&
    binding === JSON.stringify(experimentScheduleIdentity());
  node.disabled = true;
  try {
    const saved = await api(
      `/api/apps/${encodeURIComponent(app)}/automation/rules/history${cursor ? `?before=${encodeURIComponent(cursor)}` : ''}`,
    );
    if (!stillHere() || saved.app_id !== app) return;
    target.innerHTML = saved.versions.length
      ? `<ul>${saved.versions
          .map(
            (row) =>
              `<li>Version ${esc(row.version)} · ${esc(savedWhen(row.created))} · ${esc(row.hash.slice(0, 12))}…
      ${button(`Preview saved version ${row.version}`, 'automation-rules-run', `data-version="${esc(row.version)}" data-hash="${esc(row.hash)}"`)}</li>`,
          )
          .join('')}</ul>`
      : '<p>No saved rule versions yet.</p>';
    if (saved.next_before)
      target.insertAdjacentHTML(
        'beforeend',
        button(
          'Older versions',
          'automation-rules-history',
          `data-before="${esc(saved.next_before)}"`,
        ),
      );
    if (cursor)
      target.insertAdjacentHTML(
        'beforeend',
        button('Back to latest versions', 'automation-rules-history'),
      );
    if (cursor) target.querySelector('button')?.focus();
  } catch (error) {
    if (stillHere()) target.textContent = `Could not load saved versions. ${error.message}`;
  } finally {
    if (node.isConnected) node.disabled = false;
  }
}

async function manageAutomationRules(node, action) {
  const panel = node.closest('section'),
    input = panel.querySelector('#automation-rules-json');
  const status = panel.querySelector('#automation-rules-status'),
    app = state.app;
  const binding = JSON.stringify(experimentScheduleIdentity()),
    original = input.value;
  const saving = action === 'automation-rules-save';
  const stillHere = () =>
    input.isConnected &&
    status.isConnected &&
    state.app === app &&
    binding === JSON.stringify(experimentScheduleIdentity());
  let document;
  if (saving) {
    try {
      document = JSON.parse(original);
    } catch {
      status.textContent = 'Check the rule JSON and try again.';
      input.focus();
      return;
    }
  }
  const buttons = [
    ...panel.querySelectorAll(
      '[data-action="automation-rules-load"],[data-action="automation-rules-save"]',
    ),
  ];
  if (buttons.some((button) => button.disabled)) return;
  for (const button of buttons) button.disabled = true;
  try {
    const path = `/api/apps/${encodeURIComponent(app)}/automation/rules`;
    const saved = saving ? await api(path, { document }) : await api(path);
    if (!stillHere() || (saved && saved.app_id !== app)) return;
    if (!saved) {
      status.textContent = 'No saved rule set yet.';
      return;
    }
    if (!saving) {
      if (input.value !== original) {
        status.textContent =
          'Your draft changed while loading. Load again to replace it with the saved version.';
        return;
      }
      input.value = JSON.stringify(saved.document, null, 2);
    }
    status.textContent = `${saving ? 'Saved' : 'Loaded'} version ${saved.version} · ${saved.hash.slice(0, 16)}…${saving && input.value !== original ? ' Your newer draft has not been saved.' : ''}`;
  } catch (error) {
    if (stillHere())
      status.textContent = `Could not ${saving ? 'save' : 'load'} rules. ${error.message}`;
  } finally {
    for (const button of buttons) if (button.isConnected) button.disabled = false;
  }
}
