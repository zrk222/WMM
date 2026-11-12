import { $, api, button, esc, json, label, notice, refresh, state, toast } from './app.mjs';
import { WMMGoalJourney, goalAction, guidedButton } from './guided-workflow.mjs';
import { appendSetupReviewLinks } from './setup-discovery.mjs';
import { automationPanel } from './workflow-automation.mjs';
import { download, field, modal, openStage } from './app-ui.mjs';
import { sequenceAction, sequencePanel } from './campaign-sequence.mjs';
import { trackingAction, trackingPanel } from './experiment-tracking.mjs';
import { WMMPageReports } from './feature-apis.mjs';
('use strict');

function packetNeed(message) {
  const match = String(message).match(/^Add current ([a-z_]+) evidence/);
  const steps = {
    readiness: 'Run and record the core journey tests.',
    measurement: 'Connect measurement and record its verified setup.',
    cohort: 'Add source-backed economics for a mature cohort.',
    claim: 'Add a claim supported by current app evidence.',
    asset: 'Add a rights-cleared screenshot of this release.',
    store: 'Verify the store or web destination.',
    experiment: 'Set the hypothesis, primary metric and stopping rules.',
    distribution: 'Choose a channel, destination and approved limits.',
    route: 'Test the first-value entry routes.',
    billing: 'Test plans, purchase and restore.',
    retention: 'Add observed retained-value cohort data.',
    evaluation: 'Record an evidence-based experiment decision.',
    learning: 'Review a learning proposal and its holdout.',
  };
  if (match)
    return (
      steps[match[1]] ||
      `Add ${String(state.boot.labels[match[1]] || label(match[1])).toLowerCase()} for this release.`
    );
  return String(message).replace(/^Finish stage (\d+): /, 'First complete step $1: ');
}

function stagePacketCard(output, jobId = null) {
  const packet = output.packet,
    missing = output.missing || [];
  const step = state.workspace.workflow.steps.find((s) => s.id === Number(output.stage));
  const needs = missing.length > 0 || output.status === 'BLOCKED';
  const tasks = packet.operations?.tasks || [];
  const action = needs
    ? resolutionButton(Number(output.stage))
    : step
      ? guidedButton(step.primary)
      : '';
  const tools = step ? step.tools.map((t) => guidedButton(t)).join('') : '';
  const downloadButton = jobId
    ? button(
        'Download packet',
        'download-packet',
        `data-job="${esc(jobId)}" data-stage="${esc(output.stage)}"`,
      )
    : button('Download packet', 'automatic-packet', `data-stage="${esc(output.stage)}"`);
  return `<article class="panel packet-stage" data-packet-stage="${esc(output.stage)}"><div class="section-heading"><h3>Step ${esc(output.stage)} · ${esc(packet.title)}</h3><span class="status ${needs ? 'needs_input' : 'ready'}">${needs ? 'Needs input' : 'Draft prepared'}</span></div><p>${esc(packet.operations?.deliverable || "Review this stage's prepared work.")}</p>${missing.length ? `<ul>${missing.map((m) => `<li>${esc(packetNeed(m))}</li>`).join('')}</ul>` : '<p class="description">Local inputs met their checks when this draft was prepared. Verify the actual result separately.</p>'}<div class="toolbar">${action}</div><details><summary>Tasks and verification</summary><ol>${tasks.map((t) => `<li>${esc(t)}</li>`).join('')}</ol><p>${esc(packet.operations?.verify || '')}</p><div class="toolbar">${tools}</div></details><details class="packet-technical"><summary>Technical packet (JSON)</summary><pre>${json(packet)}</pre>${downloadButton}</details></article>`;
}

function automaticPreparationPanel() {
  const p = state.workspace.preparation;
  if (!p) return '';
  return `<section class="panel" id="automatic-preparation"><div class="section-heading"><div><p class="eyebrow">PREPARED AUTOMATICALLY</p><h2>Your work is ready to inspect</h2></div>${button('Inspect current work', 'automatic-open')}</div><p>All 12 stages are prepared from this app’s current evidence. ${p.ready_count} meet local checks; ${p.needs.length} distinct evidence needs remain.</p><p class="description">No preparation run is required. Missing proof stays blocked. Publication and spending keep their approval controls.</p>${campaignCollectionPanel()}</section>${sequencePanel()}${trackingPanel()}`;
}

function campaignCollectionPanel() {
  const c = state.workspace.preparation?.collection;
  if (!c) return '';
  const names = {
    identity_inventory: 'App and account inventory',
    reviews: 'Public customer reviews',
    subscription_catalog: 'Subscription catalog',
    release_inventory: 'Selected release and screenshots',
  };
  const rows = c.tasks
    .map(
      (t) =>
        `<li>${esc(names[t.operation] || label(t.operation))} · ${esc(label(t.provider))} · ${esc(t.job ? label(t.job.status) : 'Ready to collect')}${t.job ? ` ${button('Inspect source result', 'job', `data-id="${esc(t.job.id)}"`)}` : ''}</li>`,
    )
    .join('');
  const work = c.tasks.length
    ? `<ul>${rows}</ul>${button('Collect campaign inputs', 'automatic-collect-inputs')}`
    : '<p>No usable app-owned provider source is connected for these reads. The agent still needs a permitted source; no campaign facts have been invented.</p>';
  return `<section class="campaign-collection" aria-label="Agent input collection"><h3>Let the agent collect the facts</h3><p>Reads are selected from this app’s saved connections and release. You do not need to enter report parameters. Collection does not publish or spend.</p>${work}<div class="toolbar">${button('Review source access', 'measurement-connections')}${button('Review agent operating rules', 'automatic-manifest')}</div><details><summary>What the agent still needs to do</summary><ul>${c.agent_remaining.map((s) => `<li>${esc(s)}</li>`).join('')}</ul>${c.excluded.length ? `<ul>${c.excluded.map((s) => `<li>${esc(s.reason)}</li>`).join('')}</ul>` : ''}<p>Reads are reused within the current source/hour. Failed or cancelled reads remain visible; starting again does not silently retry them.</p></details></section>`;
}

function campaignManifestDialog() {
  const p = state.workspace.preparation.collection.operating_manifest;
  modal(
    'Agent operating rules',
    `<div class="modal-content"><h3>${esc(state.workspace.app.data.name)}</h3><p>${esc(p.objective || 'No app objective is recorded yet.')}</p><p>You approve or edit. This installed execution profile supports app-owned provider reads only; publication, spending and live A/B execution are not enabled.</p><h3>Evidence standards</h3><ul>${p.source_rules.map((s) => `<li>${esc(s)}</li>`).join('')}</ul><h3>Resolution workflow</h3><ul>${p.resolution_contract.map((s) => `<li>${esc(s)}</li>`).join('')}</ul><h3>A/B operating contract</h3><ul>${p.ab_contract.map((s) => `<li>${esc(s)}</li>`).join('')}</ul><details><summary>Exact versioned manifest</summary><pre>${json(p)}</pre></details></div><div class="modal-actions">${button('Edit app objective', 'edit-app')}${button('Close', 'close')}</div>`,
    'ENFORCED SOURCE-COLLECTION PROFILE',
  );
}

const WMMGoalPacket = (() => {
  const stages = { research: [5, 6], creative: [6], campaign: [7], measurement: [3, 4, 10, 11] };
  function output(w, stage) {
    const o = (w.preparation?.outputs || []).find((o) => Number(o.stage) === stage);
    return o &&
      o.packet &&
      typeof o.packet.title === 'string' &&
      typeof o.status === 'string' &&
      (w.workflow?.steps || []).some((s) => Number(s.id) === stage)
      ? o
      : null;
  }
  function selected() {
    return state.goalChoice?.app === state.app
      ? state.goalChoice.id
      : WMMGoalJourney.read(WMMGoalJourney.browserStorage(), state.app);
  }
  function model() {
    const id = selected(),
      goal = WMMGoalJourney.choices[id],
      w = state.workspace;
    return {
      schema: 'wmm.goal-evidence-packet.v1',
      app_id: w.app.id,
      manifest_version: w.app.version,
      goal: goal ? id : '',
      title: goal?.title || 'Choose your goal',
      purpose: goal?.description || 'Choose a goal on the home page before opening a packet.',
      source_hash: w.preparation?.source_hash || '',
      classification: 'LOCAL_DRAFT_NO_AUTHORITY',
      outputs: (stages[id] || []).map((stage) => ({ stage, output: output(w, stage) })),
    };
  }
  function attributes(m) {
    return `data-app="${esc(m.app_id)}" data-version="${esc(m.manifest_version)}" data-goal="${esc(m.goal)}" data-source-hash="${esc(m.source_hash)}"`;
  }
  function check(node) {
    const m = model(),
      d = node.dataset;
    if (
      state.app !== m.app_id ||
      d.app !== m.app_id ||
      Number(d.version) !== m.manifest_version ||
      d.goal !== m.goal ||
      d.sourceHash !== m.source_hash
    )
      throw new Error('App, goal or evidence changed. Reopen your first packet.');
    return m;
  }
  function view(m) {
    return `<p>${esc(m.purpose)}</p>${notice('Local evidence drafts only. Missing measurements remain unknown. This packet grants no approval and proves no delivery or business outcome.')}${m.goal ? m.outputs.map(({ stage, output: o }) => `<section class="panel" data-goal-packet-stage="${esc(stage)}"><h3>${esc(o?.packet?.title || `Step ${stage}`)}</h3><p>${esc(o?.status || 'UNKNOWN — no current output')}</p>${(o?.missing || []).length ? `<ul>${o.missing.map((v) => `<li>${esc(packetNeed(v))}</li>`).join('')}</ul>` : '<p>Review the underlying evidence; local preparation does not establish measured results.</p>'}<details><summary>Stage tasks and evidence</summary><ol>${(o?.packet?.operations?.tasks || []).map((v) => `<li>${esc(v)}</li>`).join('')}</ol><pre>${json(o?.packet || null)}</pre></details></section>`).join('') : '<p>Choose a goal on the home page, then open your first packet.</p>'}<details><summary>Packet source</summary><p>${esc(m.app_id)} · version ${esc(m.manifest_version)} · ${esc(m.source_hash)}</p></details>`;
  }
  function history(m) {
    return (state.workspace.jobs || [])
      .filter(
        (j) =>
          j.app_id === m.app_id && j.action === 'pipeline' && j.data?.goal_packet?.goal === m.goal,
      )
      .slice(0, 5);
  }
  function historyView(m) {
    const rows = history(m),
      a = attributes(m);
    return `<section aria-label="Saved goal packets"><h3>Pick up where you left off</h3><p>Save this draft to keep a dated copy in this workspace. Reopen it here after restarting WMM. Saving prepares local work; it does not run a campaign.</p>${rows.length ? rows.map((j) => `<p>${button('Open saved packet', 'automatic-goal-reopen', `${a} data-job="${esc(j.id)}"`)} ${esc(j.created)} · ${esc(j.status === 'SUCCEEDED' ? 'Draft saved' : j.status === 'BLOCKED' ? 'Needs attention' : j.status)}</p>`).join('') : '<p>No saved packet for this goal in the latest 100 app runs.</p>'}</section>`;
  }
  function saved(m, id) {
    const row = history(m).find((j) => j.id === id);
    if (!row)
      throw new Error(
        'Saved packet is not in this app and goal history. Refresh the current goal.',
      );
    const p = row.result?.goal_packet,
      q = row.data.goal_packet;
    if (row.status !== 'SUCCEEDED' || !p) return { row, packet: null };
    if (
      p.schema !== 'wmm.goal-evidence-packet.v1' ||
      p.classification !== 'LOCAL_DRAFT_NO_AUTHORITY' ||
      p.app_id !== m.app_id ||
      p.goal !== m.goal ||
      p.manifest_version !== q.manifest_version ||
      p.source_hash !== q.source_hash ||
      !p.created_at ||
      !Array.isArray(p.outputs) ||
      JSON.stringify(p.outputs.map((o) => o.stage)) !== JSON.stringify(stages[m.goal]) ||
      p.outputs.some((o) => !o.output?.packet || typeof o.output.status !== 'string')
    )
      throw new Error('Saved packet bindings are incomplete. Inspect its run before using it.');
    return { row, packet: p };
  }
  function openSaved(id) {
    const m = model(),
      { row, packet: p } = saved(m, id),
      a = `${attributes(m)} data-job="${esc(id)}"`;
    const historical =
      p && (p.source_hash !== m.source_hash || p.manifest_version !== m.manifest_version);
    modal(
      m.title + ' — saved packet',
      `<div class="modal-content"><p role="status">${p ? (historical ? 'Historical snapshot — app or evidence changed. Open the current packet before taking a new action.' : 'Saved local draft — current source matches.') : ['QUEUED', 'RUNNING'].includes(row.status) ? 'Preparing a local draft. Refresh this saved run to inspect its result.' : 'Packet was not saved. Review the run, then explicitly save from current evidence.'}</p><p>Packet ID: ${esc(id)} · requested ${esc(row.created)}</p>${p ? `<p>Snapshot prepared ${esc(p.created_at)}</p>${view({ ...p, title: m.title, purpose: m.purpose })}` : `<p>${esc(row.result?.error || 'No completed packet output is available yet.')}</p>`}</div><div class="modal-actions">${button('Refresh saved packet', 'automatic-goal-saved-refresh', a)}${p ? button('Download saved packet JSON', 'automatic-goal-saved-json', a) + button('Report / Save PDF', 'automatic-goal-saved-pdf', a) : ''}${button('Open current packet', 'automatic-goal-open', attributes(m))}${button('Close', 'close')}</div>`,
      'SAVED LOCAL PREPARATION',
    );
  }
  function ticket(node, m) {
    const anchor = node.closest?.('dialog');
    return () =>
      state.app === m.app_id &&
      selected() === m.goal &&
      node.isConnected !== false &&
      (!anchor || (anchor.open && (!anchor.contains || anchor.contains(node))));
  }
  async function save(node) {
    const m = check(node),
      current = ticket(node, m);
    node.disabled = true;
    try {
      const value = await api(`/api/apps/${encodeURIComponent(m.app_id)}/jobs`, {
        action: 'pipeline',
        data: {
          stage: 0,
          goal_packet: {
            goal: m.goal,
            manifest_version: m.manifest_version,
            source_hash: m.source_hash,
          },
        },
        request_key: `goal-packet-${m.goal}-${m.source_hash}`,
      });
      if (!current()) return;
      await refresh();
      if (current()) openSaved(value.id);
    } finally {
      if (node.isConnected !== false) node.disabled = false;
    }
  }
  async function refreshSaved(node) {
    const m = model(),
      current = ticket(node, m);
    await refresh();
    if (current()) return openSaved(node.dataset.job);
  }
  function report(m, id) {
    const { row, packet: p } = saved(m, id);
    if (!p) throw new Error('Wait for a saved packet before exporting.');
    return {
      schema: 'growth.page-report.v1',
      page: 'overview',
      title: m.title + ' — saved packet',
      purpose: m.purpose,
      next_step: 'Review missing inputs in the current goal packet before approving an action.',
      scope: 'SELECTED_APP',
      app_id: p.app_id,
      app_name: p.app_name || p.app_id,
      manifest_version: p.manifest_version,
      loaded_at: p.created_at,
      generated_at: new Date().toISOString(),
      filters: {
        goal: p.goal,
        packet_id: row.id,
        source_hash: p.source_hash,
        snapshot_state:
          p.source_hash === m.source_hash && p.manifest_version === m.manifest_version
            ? 'MATCHES_CURRENT_SOURCE'
            : 'HISTORICAL',
      },
      metrics: [
        {
          label: 'Saved stages',
          value: p.outputs.length,
          unit: 'stages',
          source: 'Saved goal packet',
        },
        {
          label: 'Locally prepared stages',
          value: p.outputs.filter((o) => o.output.status === 'PREPARED').length,
          unit: 'stages',
          source: 'Saved goal packet',
        },
        {
          label: 'Measured campaign outcomes',
          value: null,
          unit: 'outcomes',
          source: 'This local draft supplies no outcome observations',
        },
      ],
      cohorts: [],
      notes: [
        p.source_hash === m.source_hash && p.manifest_version === m.manifest_version
          ? 'Current source matches this saved snapshot.'
          : 'Historical snapshot: app or evidence changed; review current inputs before taking an action.',
        'Saved local draft. No approval, publication, spending or measured business outcome.',
        ...p.outputs.flatMap((o) => o.output.missing || []),
      ],
    };
  }
  function open(node) {
    const m = check(node),
      a = attributes(m);
    modal(
      m.title + ' — evidence packet',
      `<div class="modal-content">${view(m)}${m.goal ? historyView(m) : ''}</div><div class="modal-actions">${m.goal ? button(WMMGoalJourney.choices[m.goal].next, 'automatic-goal-next', a) + (m.source_hash && m.outputs.some((x) => x.output) ? button('Save packet in this workspace', 'automatic-goal-save', a) + button('Download goal packet', 'automatic-goal-download', a) : '') : ''}${button('See all twelve stages', 'automatic-open')}${button('Close', 'close')}</div>`,
      'SELECTED GOAL / LOCAL DRAFT',
    );
  }
  function action(node) {
    const m = check(node),
      mode = node.dataset.action;
    if (mode === 'automatic-goal-open') return open(node);
    if (!m.goal) throw new Error('Choose a goal first.');
    if (
      ['automatic-goal-download', 'automatic-goal-save'].includes(mode) &&
      (!m.source_hash || !m.outputs.some((x) => x.output))
    )
      throw new Error('Current source evidence is unavailable; inspect the missing outputs first.');
    if (mode === 'automatic-goal-save') return save(node);
    if (mode === 'automatic-goal-reopen') return openSaved(node.dataset.job);
    if (mode === 'automatic-goal-saved-refresh') return refreshSaved(node);
    if (mode === 'automatic-goal-saved-json') {
      const value = saved(m, node.dataset.job);
      if (!value.packet) throw new Error('No completed saved packet is available.');
      return download(`${m.app_id}-${m.goal}-saved-packet.json`, {
        packet_id: value.row.id,
        packet_hash: value.row.result.goal_packet_hash,
        ...value.packet,
      });
    }
    if (mode === 'automatic-goal-saved-pdf')
      return WMMPageReports.openReport(report(m, node.dataset.job), window);
    if (mode === 'automatic-goal-download') return download(`${m.app_id}-${m.goal}-packet.json`, m);
    if (mode === 'automatic-goal-next')
      return goalAction({
        dataset: {
          action: 'goal-next',
          app: m.app_id,
          version: String(m.manifest_version),
          goal: m.goal,
        },
      });
    throw new Error('Unknown goal packet action.');
  }
  return { model, attributes, check, view, open, action, history, saved, openSaved, report };
})();

function openAutomaticPreparation({ firstPacket = false } = {}) {
  if (firstPacket) throw new Error('Reopen your first packet from the current goal.');
  const p = state.workspace.preparation;
  modal(
    'Your prepared workflow',
    `<div class="modal-content">${notice("These are working drafts, not completed campaigns. Use each step's button to open its current workflow. Nothing is published and no money is spent here.")}<h3>${p.ready_count} of 12 steps have the required local inputs</h3>${p.outputs.map((o) => stagePacketCard(o)).join('')}<details><summary>Technical source reference</summary><p class="app-mono">${esc(p.source_hash)}</p></details></div><div class="modal-actions">${button('Download all packets', 'automatic-download')}${button('Close', 'close')}</div>`,
    'CURRENT WORKFLOW',
  );
  if (p.recommendations && !firstPacket)
    $('#modal .modal-content').insertAdjacentHTML(
      'afterbegin',
      automationPanel('packet-automation'),
    );
}

async function automaticPreparationAction(node) {
  if (node.dataset.action.startsWith('automatic-goal-')) return WMMGoalPacket.action(node);
  if (node.dataset.action.startsWith('automatic-tracking-')) return trackingAction(node);
  if (node.dataset.action.startsWith('automatic-sequence-')) return sequenceAction(node);
  if (node.dataset.action === 'automatic-resolution-stage') {
    const app = state.app;
    await refresh();
    if (state.app === app) return openResolutionStage(Number(node.dataset.stage));
    return;
  }
  if (node.dataset.action === 'automatic-resolution-issue')
    return openResolutionIssue(node.dataset.id);
  if (node.dataset.action === 'automatic-resolution-run') return openResolutionRun(node.dataset.id);
  if (node.dataset.action === 'automatic-resolution-refresh') {
    const app = state.app,
      id = node.dataset.id;
    await refresh();
    if (state.app === app) return openResolutionRun(id);
    return;
  }
  if (node.dataset.action === 'automatic-resolution-options-refresh') {
    const app = state.app,
      id = node.dataset.id;
    await refresh();
    if (state.app === app) return openResolutionIssue(id);
    return;
  }
  if (node.dataset.action === 'automatic-manifest') return campaignManifestDialog();
  if (node.dataset.action === 'automatic-collect-inputs') {
    const app = state.app,
      c = state.workspace.preparation.collection;
    node.disabled = true;
    try {
      const result = await api(`/api/apps/${encodeURIComponent(app)}/campaign-inputs`, {
        manifest_version: c.manifest_version,
        source_hash: c.source_hash,
      });
      if (state.app !== app) return;
      await refresh();
      if (state.app !== app) return;
      toast(
        `${result.tasks.length} source reads queued or retained. Inspect their job results; collection is not campaign completion.`,
      );
    } finally {
      if (node.isConnected) node.disabled = false;
    }
    return;
  }
  if (node.dataset.action === 'automatic-open')
    return node.dataset.firstPacket === 'true'
      ? WMMGoalPacket.open(node)
      : openAutomaticPreparation();
  if (node.dataset.action === 'automatic-download')
    return download(`${state.app}-current-work.json`, state.workspace.preparation);
  if (node.dataset.action === 'automatic-packet') {
    const output = state.workspace.preparation.outputs.find(
      (o) => o.stage === Number(node.dataset.stage),
    );
    if (output) return download(`${state.app}-stage-${output.stage}.json`, output.packet);
  }
  if (node.dataset.action === 'automatic-stage') return openStage(node.dataset.id);
}

function resolutionIssues(stage) {
  const all = state.workspace.resolutions?.issues || [];
  const direct = all.filter((i) => i.stages.includes(stage));
  if (direct.length) return direct;
  const step = state.workspace.workflow.steps.find((s) => s.id === stage);
  const dependencies = (step?.dependency_needs || []).map((s) =>
    Number(s.match(/^Finish stage (\d+)/)?.[1]),
  );
  return all.filter((i) => i.stages.some((id) => dependencies.includes(id)));
}

function resolutionButton(stage, title = 'Review agent resolution') {
  return resolutionIssues(stage).length
    ? button(title, 'automatic-resolution-stage', `data-stage="${stage}"`)
    : '';
}

function openResolutionStage(stage) {
  const issues = resolutionIssues(stage),
    history = state.workspace.resolutions?.history || [];
  modal(
    'Agent resolution options',
    `<div class="modal-content"><p>The agent proposes the work. Review the action, approve it or edit the target; inspect its evidence before treating the requirement as verified.</p>${
      issues
        .map(
          (issue) =>
            `<article class="panel"><h3>${esc(issue.goal)}</h3><p><strong>Acceptance target (not yet verified):</strong> ${esc(issue.verification)}</p>${button('Review agent options', 'automatic-resolution-issue', `data-id="${esc(issue.id)}"`)}<details><summary>Evidence gap and affected steps</summary><p>${esc(issue.gap)}</p><p>Steps ${esc(issue.stages.join(', '))}</p></details>${history
              .filter((h) => h.issue_id === issue.id)
              .slice(0, 3)
              .map(
                (h) =>
                  `<p>${esc(label(h.status))} ${button('Inspect agent result', 'automatic-resolution-run', `data-id="${esc(h.job_id)}"`)}</p>`,
              )
              .join('')}</article>`,
        )
        .join('') ||
      '<p>No direct unverified input is recorded for this stage. Review its existing evidence and prerequisites.</p>'
    }</div><div class="modal-actions">${button('Review source access', 'measurement-connections')}${button('Close', 'close')}</div>`,
    'AGENT WORK / OWNER APPROVAL',
  );
}

function optionDescription(option) {
  const name = option.parameters.provider || option.parameters.name;
  return name ? `${option.title} · ${name}` : option.title;
}

function resolutionOptionBody(issue, option) {
  const target =
    option.tool === 'inspect_site'
      ? field(
          'resolution_target',
          option.parameters.url || '',
          'url',
          "Optional edit; must stay on this app's public website origin.",
          false,
        )
      : option.tool === 'reuse_observation'
        ? `<details><summary>Exact saved observation</summary><p>${esc(option.parameters.url)}</p><p>Artifact: ${esc(option.parameters.artifact_id)}</p><p>SHA256: ${esc(option.parameters.artifact_hash)}</p><p>Source run: ${esc(option.parameters.source_job_id)}</p></details>`
        : '';
  return `<h3>${esc(option.title)}</h3><p>${esc(option.access)}</p><dl><dt>Expected evidence</dt><dd>${esc(option.artifact)}</dd><dt>What this verifies</dt><dd>${esc(option.verifies)}</dd><dt>What remains unverified</dt><dd>${esc(option.limits)}</dd><dt>Cost and limits</dt><dd>${esc(option.cost)}</dd></dl>${target}<details><summary>Recovery and stopping rules</summary><p>${esc(option.fallback)}</p><p>${esc(option.stop)}</p></details>${!option.ready ? notice('This action needs source access or an app target first. Review that prerequisite below; no execution has been claimed.') : ''}<div class="toolbar">${option.ready ? '<button type="submit" class="button">Approve agent action</button>' : button('Review required access', option.prerequisite === 'app' ? 'edit-app' : 'measurement-connections')}${button('Review source access', 'measurement-connections')}${button('Edit app target', 'edit-app')}</div>`;
}

function openResolutionIssue(id) {
  const issue = state.workspace.resolutions?.issues.find((i) => i.id === id);
  if (!issue)
    return modal(
      'Resolution needs refreshed',
      `<div class="modal-content"><p>This input changed or now meets its local check. Review the current workflow; old approval is not reused.</p></div><div class="modal-actions">${button('Close', 'close')}</div>`,
    );
  modal(
    'Review the agent action',
    `<form id="resolution-form" data-app="${esc(state.app)}" data-manifest="${state.workspace.app.version}" data-issue="${esc(issue.id)}" data-source="${esc(issue.source_hash)}" data-request="${crypto.randomUUID()}"><div class="modal-content"><h3>${esc(issue.goal)}</h3><p><strong>Acceptance target (not yet verified):</strong> ${esc(issue.verification)}</p><label class="field" for="resolution-option">Proposed action<select id="resolution-option" name="option">${issue.options.map((o) => `<option value="${esc(o.id)}">${esc(optionDescription(o))}${o.ready ? '' : ' — access needed'}</option>`).join('')}</select></label><div id="resolution-option-body">${resolutionOptionBody(issue, issue.options[0])}</div><p id="resolution-error" class="field-error" role="alert"></p>${button('Refresh options', 'automatic-resolution-options-refresh', `data-id="${esc(issue.id)}"`)}<details><summary>Source and approval boundary</summary><p>${esc(issue.gap)}</p><p>Approval applies to the displayed app, action and target for 30 minutes. Edits require a new exact approval. No campaign publication, ad spending or automatic proof promotion is authorized.</p></details></div></form>`,
    'APPROVE / EDIT',
  );
}

function resolutionRunDetails(row) {
  const actions = row.next_actions.map((a) =>
    typeof a === 'string'
      ? a
      : a?.instruction ||
        'Inspect this source finding in Evidence references before choosing the next action.',
  );
  if (row.artifacts.some((a) => a.kind === 'setup_proposal'))
    actions.unshift('Open the collected app details using the review button below.');
  return `<p id="resolution-live-status" role="status" aria-live="polite">${esc(label(row.status))} · ${esc(row.summary)}</p><p>Proof status: ${esc(label(row.proof_status))}. This result has not automatically verified the original requirement.</p>${row.children.length ? `<h3>Source work</h3><ul>${row.children.map((c) => `<li>${esc(label(c.status))} · ${esc(c.job_id)}</li>`).join('')}</ul>` : ''}<h3>Next agent resolution steps</h3><ul>${actions.map((a) => `<li>${esc(a)}</li>`).join('')}</ul><details><summary>Evidence references</summary><ul>${row.artifacts.map((a) => `<li>${esc(a.kind || 'source job')} · ${esc(a.id || a.job_id || a.experiment_id || a.source_id)}${a.sha256 ? ` · ${esc(a.sha256)}` : ''}</li>`).join('') || '<li>No accepted artifact is available yet.</li>'}</ul></details>`;
}

function openResolutionRun(id) {
  const row = state.workspace.resolutions?.history.find((r) => r.job_id === id);
  if (!row)
    return toast('This saved resolution is not in the current history. Refresh the selected app.');
  modal(
    'Agent evidence result',
    `<div class="modal-content"><div id="resolution-run-details">${resolutionRunDetails(row)}</div></div><div class="modal-actions">${button('Refresh progress', 'automatic-resolution-refresh', `data-id="${esc(id)}"`)}${button('Plan next agent step', 'agent-next-step')}${button('Review next resolution', 'automatic-resolution-issue', `data-id="${esc(row.issue_id)}"`)}${button('Review source access', 'measurement-connections')}${['QUEUED', 'RUNNING'].includes(row.job_status) ? button('Cancel local run', 'cancel-job', `data-id="${esc(id)}"`) : ''}${button('Close', 'close')}</div>`,
    'EXECUTION / EVIDENCE / REMAINING PROOF',
  );
  $('#modal-body').dataset.job = id;
  for (const artifact of row.artifacts.filter((item) => item.kind === 'setup_proposal'))
    $('#resolution-run-details').insertAdjacentHTML(
      'beforeend',
      button('Review collected app details', 'setup-review', `data-id="${esc(artifact.id)}"`),
    );
  const key = `${state.app}:${id}`;
  if (
    ['QUEUED', 'RUNNING', 'COLLECTING_SOURCES', 'WAITING_FOR_SOURCES'].includes(row.status) &&
    state.resolutionPoll !== key
  ) {
    state.resolutionPoll = key;
    pollResolution(id, state.app)
      .catch((error) => toast(error.message))
      .finally(() => {
        if (state.resolutionPoll === key) state.resolutionPoll = null;
      });
  }
}

async function pollResolution(id, app) {
  for (let attempt = 0; attempt < 120; attempt++) {
    await new Promise((resolve) => setTimeout(resolve, 1000));
    if (state.app !== app || !$('#modal').open || $('#modal-body').dataset.job !== id) return;
    await refresh();
    if (state.app !== app || !$('#modal').open || $('#modal-body').dataset.job !== id) return;
    const row = state.workspace.resolutions?.history.find((r) => r.job_id === id);
    if (!row) return;
    const target = $('#resolution-run-details');
    const value = JSON.stringify(row);
    if (target && target.dataset.observation !== value) {
      target.innerHTML = resolutionRunDetails(row);
      target.dataset.observation = value;
      appendSetupReviewLinks(target, row);
    }
    if (!['QUEUED', 'RUNNING'].includes(row.job_status))
      $('#modal-body').querySelector('[data-action="cancel-job"]')?.remove();
    if (!['QUEUED', 'RUNNING', 'COLLECTING_SOURCES', 'WAITING_FOR_SOURCES'].includes(row.status))
      return;
  }
  toast(
    'Evidence work continues in the durable worker. Refresh progress to inspect its next result.',
  );
}

document.addEventListener('change', (event) => {
  if (event.target.id !== 'resolution-option') return;
  const form = event.target.closest('form'),
    issue = state.workspace.resolutions?.issues.find((i) => i.id === form.dataset.issue);
  if (!issue || form.dataset.app !== state.app) return;
  if (form.dataset.source !== issue.source_hash) {
    $('#resolution-error').textContent = 'Sources changed. Refresh the options before approving.';
    return;
  }
  const option = issue.options.find((o) => o.id === event.target.value);
  $('#resolution-option-body').innerHTML = resolutionOptionBody(issue, option);
  form.dataset.request = crypto.randomUUID();
});

document.addEventListener('submit', async (event) => {
  if (event.target.id !== 'resolution-form') return;
  event.preventDefault();
  const form = event.target,
    app = form.dataset.app,
    submit = event.submitter;
  if (submit) submit.disabled = true;
  try {
    const issue = state.workspace.resolutions?.issues.find((i) => i.id === form.dataset.issue);
    if (
      state.app !== app ||
      form.dataset.manifest !== String(state.workspace.app.version) ||
      issue?.source_hash !== form.dataset.source
    )
      throw Error('App or sources changed. Refresh the resolution options before approving.');
    const option = issue.options.find((o) => o.id === form.elements.option.value);
    const target = option.tool === 'inspect_site' ? form.elements.resolution_target.value : null;
    const job = await api(`/api/apps/${encodeURIComponent(app)}/resolutions/approve`, {
      issue_id: issue.id,
      option_id: option.id,
      source_hash: issue.source_hash,
      target_url: target,
      request_key: form.dataset.request,
    });
    if (state.app !== app) return;
    await refresh();
    if (state.app !== app) return;
    openResolutionRun(job.id);
  } catch (error) {
    if (form.isConnected) $('#resolution-error').textContent = error.message;
  } finally {
    if (submit?.isConnected) submit.disabled = false;
  }
});

export {
  packetNeed,
  stagePacketCard,
  automaticPreparationPanel,
  campaignCollectionPanel,
  campaignManifestDialog,
  WMMGoalPacket,
  openAutomaticPreparation,
  automaticPreparationAction,
  resolutionIssues,
  resolutionButton,
  openResolutionStage,
  optionDescription,
  resolutionOptionBody,
  openResolutionIssue,
  resolutionRunDetails,
  openResolutionRun,
  pollResolution,
};
