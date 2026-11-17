import { $, button, esc, label, notice, render, state, status } from './app.mjs';
import { acqIntentForm } from './acquisition.mjs';
import { appForm, download, modal } from './app-ui.mjs';
import {
  briefForm,
  inspectionForm,
  referenceForm,
  referenceImportForm,
} from './app-production.mjs';
import { capabilityForm } from './production-feasibility.mjs';
import { experimentForm } from './app-results.mjs';
('use strict');

const spyTokDiscovery = Object.freeze({
  all: { title: 'All categories', path: '/top-posts' },
  business: { title: 'Business / productivity', path: '/top-posts/business' },
  lifestyle: { title: 'Lifestyle', path: '/top-posts/lifestyle' },
  demo: { title: 'App demonstrations', path: '/top-posts/app-demo' },
  business_demo: { title: 'Business app demonstrations', path: '/top-posts/business-app-demo' },
  problem: { title: 'Problem / solution', path: '/top-posts/problem-solution' },
});

function spyTokLink(key) {
  if (!Object.hasOwn(spyTokDiscovery, key)) throw new Error('Unknown discovery destination.');
  return 'https://spytok.com' + spyTokDiscovery[key].path;
}

function spyTokPanel() {
  return `<section class="panel" id="spytok-workflow"><div class="section-heading"><div><p class="eyebrow">CREATIVE DISCOVERY TO LAUNCH</p><h2>A clear path from reference to results</h2></div>${button('Open creative workflow', 'spytok-open')}</div><p>Review this app’s job and audience, find a feasible format, inspect the source, then connect an original brief to search and measured outcomes.</p><p class="description">SpyTok is optional public research. Imports use your permitted sources; supplier API access and performance claims remain unverified.</p></section>`;
}

const artifactIdentity = (item) => ({
  id: item.id,
  version: item.current.version,
  hash: item.current.hash,
});

function workspaceArtifacts() {
  const w = state.workspace;
  if (w?.app?.id !== state.app) throw new Error('The app changed. Reopen creative discovery.');
  const references = w.references || [],
    analyses = w.analyses || [],
    briefs = w.briefs || [];
  if (
    [...references, ...analyses, ...briefs].some(
      (r) => r.current?.app_id !== w.app.id || (r.app_id !== undefined && r.app_id !== w.app.id),
    )
  )
    throw new Error('Foreign app artifact rejected.');
  return { w, references, analyses, briefs };
}

function sourceDecision(referenceId, artifacts = workspaceArtifacts()) {
  if (!referenceId) return null;
  const reference = artifacts.references.find((item) => item.id === referenceId);
  if (!reference) throw new Error('The source changed. Reopen creative discovery.');
  const data = reference.current.data;
  const analysis = artifacts.analyses.find(
    (item) =>
      item.source_status === 'CURRENT' &&
      item.current.data.reference_id === reference.id &&
      item.current.data.capture_hash === reference.current.hash,
  );
  const inspection = analysis?.current.data;
  const hook = inspection?.observations?.find(
    (phase) => phase.role === 'HOOK' && phase.basis === 'OBSERVED',
  );
  const capability = artifacts.w.capabilities;
  const production = capability?.evaluations?.find((item) => item.reference_id === reference.id);
  const missing = ['claim', 'asset', 'readiness', 'store', 'route'].filter(
    (kind) => !artifacts.w.records?.some((record) => record.kind === kind),
  );
  let next;
  if (!analysis) next = { mode: 'inspect', caption: 'Inspect this source', tone: 'NEEDS_REVIEW' };
  else if (!capability?.profile?.length)
    next = { mode: 'team', caption: 'Set up team production capability', tone: 'NEEDS_REVIEW' };
  else if (production?.status !== 'READY')
    next = { mode: 'requirements', caption: 'Review production requirements', tone: 'BLOCKED' };
  else if (missing.length)
    next = { mode: 'brief', caption: 'Review missing app proof', tone: 'NEEDS_REVIEW' };
  else next = { mode: 'brief', caption: 'Prepare an original brief', tone: 'READY' };
  return {
    ...artifactIdentity(reference),
    title: data.title,
    analysis: analysis ? artifactIdentity(analysis) : null,
    observed_hook: hook
      ? {
          basis: 'OBSERVED',
          provenance: 'SAVED_USER_SUPPLIED_INSPECTION',
          detail: hook.detail,
          inspected_at: inspection.inspected_at,
        }
      : null,
    observation: {
      kind: data.metric_kind || 'UNKNOWN',
      value: Number.isFinite(data.metric_value) ? data.metric_value : null,
      at: data.metric_at || null,
    },
    relevance: data.relevance_note || null,
    rights: data.rights || 'UNKNOWN',
    production: {
      status: production?.status || 'NOT_REVIEWED',
      reasons: production?.reasons || [],
    },
    activation: artifacts.w.app.data.activation || null,
    missing,
    next,
  };
}

function primaryAction(caption, mode) {
  return button(caption, 'spytok-local', `data-next="${mode}" data-spytok-primary`, '');
}

function decisionCard(selected, hasSources) {
  if (!selected)
    return `<h3>${hasSources ? 'Select a source to review' : 'Start with a permitted source'}</h3><p>${hasSources ? 'Choose a saved source to see its evidence, production fit, and next action.' : 'Add a public reference or import an export you have permission to use.'}</p><div class="button-row">${primaryAction(hasSources ? 'Choose a saved source' : 'Add a permitted source', hasSources ? 'select' : 'source')}${button('Preview a permitted export', 'spytok-local', 'data-next="import"')}</div>`;
  const { observation, production, next } = selected;
  const observedDate = observation.at && new Date(observation.at);
  const dateLabel =
    observedDate && Number.isFinite(observedDate.getTime())
      ? ` · ${observedDate.toISOString().slice(0, 10)} UTC`
      : ' · date unknown';
  const observed =
    observation.value === null
      ? 'Unknown'
      : `${label(observation.kind)}: ${new Intl.NumberFormat().format(observation.value)}${dateLabel}`;
  const reasons = production.reasons.length
    ? `<ul>${production.reasons.map((reason) => `<li>${esc(reason)}</li>`).join('')}</ul>`
    : '';
  const rightsNote =
    selected.rights === 'REFERENCE_ONLY'
      ? 'Borrow the structure; footage reuse requires separate permission.'
      : 'This record does not authorize footage reuse or publication.';
  const hypothesis = selected.observed_hook
    ? 'Adapt only the structure of the saved observed hook for an original opening.'
    : 'Test one original hook or format; no observed hook is recorded for this capture.';
  const experiment = selected.activation
    ? `${hypothesis} Show “${selected.activation}.” Measure that user action only if tracked. Source views show exposure, not installs or lift.`
    : `${hypothesis} Define this app’s first useful user action before choosing what to measure. Source views show exposure, not installs or lift.`;
  return `<h3>${esc(selected.title)}</h3><p>${status(next.tone)} ${next.tone === 'READY' ? 'Ready to draft only.' : 'Review this step before preparing a draft.'}</p>
    <div class="button-row">${primaryAction(next.caption, next.mode)}${button('Plan a test', 'spytok-local', `data-next="experiment" data-spytok-plan-test`)}</div>
    <dl class="details-list">
      <div><dt>Observed metric</dt><dd>${esc(observed)}</dd></div>
      <div><dt>Observed hook</dt><dd>${selected.observed_hook ? `${esc(selected.observed_hook.detail)}<p class="description">User-supplied inspection${selected.observed_hook.inspected_at ? ` · ${esc(selected.observed_hook.inspected_at)}` : ''}.</p>` : 'No observed hook in this capture’s current inspection.'}</dd></div>
      <div><dt>App relevance</dt><dd>${esc(selected.relevance || 'Unknown; document why this source fits the audience.')}</dd></div>
      <div><dt>Reuse rights</dt><dd>${esc(label(selected.rights))}. ${esc(rightsNote)}</dd></div>
      <div><dt>Production fit</dt><dd>${esc(label(production.status))}${reasons}${selected.missing.length ? `<p>App proof to review: ${esc(selected.missing.join(', '))}.</p>` : ''}</dd></div>
    </dl>
    <p><strong>Candidate only.</strong> Check viral qualification in saved-source discovery: at least 100,000 views and 10× a documented comparable creator median.</p>
    <p><strong>Next experiment:</strong> ${esc(experiment)}</p>
`;
}

function spyTokHandoff(referenceId = '') {
  const artifacts = workspaceArtifacts();
  const { w, references, analyses, briefs } = artifacts;
  const a = w.app;
  const selected = sourceDecision(referenceId, artifacts);
  return {
    schema: 'growth.creative-workflow-handoff.v1',
    status: 'PREPARED_HANDOFF',
    app_id: a.id,
    app_version: a.version,
    profile: {
      name: a.data.name,
      job: a.data.job,
      audience: a.data.audience,
      activation: a.data.activation,
      release: a.data.release,
      locale: a.data.locale,
    },
    source_binding: w.preparation?.source_hash || null,
    references: references.map(artifactIdentity),
    analyses: analyses.map((r) => ({ ...artifactIdentity(r), source_status: r.source_status })),
    briefs: briefs.map((r) => ({ ...artifactIdentity(r), evidence_status: r.evidence_status })),
    questions: {
      product: [
        'What does the user do?',
        'What useful output can be shown?',
        'When is first value reached?',
      ],
      audience: [
        'Which real problem motivates use?',
        'Which permitted source supports the wording?',
        'What prevents trying or switching?',
      ],
      production: [
        'Which formats can the team make?',
        'Which authentic screens and rights are available?',
        'Which constraints exclude this format?',
      ],
    },
    discovery: Object.keys(spyTokDiscovery).map((key) => ({
      title: spyTokDiscovery[key].title,
      url: spyTokLink(key),
    })),
    evidence: {
      runtime: 'ev_0e8bf958e7d2eef75e7a87993f55f78bdeb925d462e1a2ebf8d1434c67b0c6e9',
      client_schema: 'ev_a56672b6d8c2fed54df1208ed32aa803e682c3b3331875bf1ec5dff0486e70fe',
    },
    supplier_api: 'UNVERIFIED',
    external_execution: 'NOT_RUN',
    growth_results: 'NOT_RUN',
    authorized_spend_minor: 0,
    ...(selected
      ? {
          selected_source: {
            id: selected.id,
            version: selected.version,
            hash: selected.hash,
            analysis: selected.analysis,
            observed_hook: selected.observed_hook,
            next_action: { mode: selected.next.mode, caption: selected.next.caption },
            observation: selected.observation,
            relevance: selected.relevance,
            rights: selected.rights,
            production: selected.production,
          },
        }
      : {}),
  };
}

function openSpyTokWorkflow() {
  const { w, references: refs } = workspaceArtifacts();
  const openedAppId = w.app.id,
    openedVersion = w.app.version;
  const captures = new Map(refs.map((ref) => [ref.id, artifactIdentity(ref)]));
  const step = (title, text, action, caption) =>
    `<section class="next-step"><div><h3>${esc(title)}</h3><p>${esc(text)}</p>${button(caption, 'spytok-local', `data-next="${action}"`)}</div></section>`;
  modal(
    'Creative discovery to measured outcomes',
    `<div class="modal-content">${notice('This guide uses your current app workspace. It does not contact SpyTok, generate evidence, connect a supplier account or publish anything.')}
    <div id="spytok-workspace">
      <label class="field" for="spytok-reference">Source to review<select id="spytok-reference"><option value="">Choose an existing source</option>${refs.map((r) => `<option value="${esc(r.id)}">${esc(r.current.data.title)}</option>`).join('')}</select></label>
      <section class="panel" id="spytok-decision">${decisionCard(null, refs.length > 0)}</section>
      <p class="sr-only" id="spytok-announcement" role="status"></p>
      <div class="button-row">${button('Open saved-source discovery', 'discovery-open')}${button('Open Hypit video research', 'oresearch-open')}</div>
    </div>
    <details><summary>Full discovery-to-results guide</summary>
    ${step('1. Review product and audience', 'Define the real user action, first useful result, audience and current release. Generated descriptions are hypotheses until checked.', 'profile', 'Review app setup')}
    <section class="next-step"><div><h3>2. Find a feasible mechanism</h3><p>Choose a category or narrative. Assess talent, editing ability, authentic output, rights and production cost before selecting a reference.</p><label class="field" for="spytok-discovery">Public discovery page<select id="spytok-discovery">${Object.keys(
      spyTokDiscovery,
    )
      .map((k) => `<option value="${k}">${esc(spyTokDiscovery[k].title)}</option>`)
      .join(
        '',
      )}</select></label><a class="button outline" id="spytok-discovery-link" href="${spyTokLink('all')}" target="_blank" rel="noopener noreferrer">Open selected SpyTok page ↗</a></div></section>
    ${step('3. Capture permitted source facts', 'Save the original public post link, observation time, metric unit and rights. A category summary is not a creator baseline or an install count.', 'source', 'Add a permitted source')}${button('Preview a permitted export', 'spytok-local', 'data-next="import"')}
    ${step('4. Inspect hook and mechanism', 'Record observed phases and actual timing; keep suggestions separate. If no source exists, the next control opens source setup.', 'inspect', 'Inspect selected source')}
    <section class="next-step"><div><h3>5. Review app fit and slate</h3><p>Compare comparable attention and app relevance. Unknown baselines stay unknown.</p>${button('Open saved-source discovery', 'discovery-open')}</div></section>
    ${step('6. Prepare original work', 'Bind current approved claims, authentic screens and tested destinations. Prepare channel-specific hooks and beats; missing proof opens setup.', 'brief', 'Prepare an original brief')}
    ${step('7. Connect ASA and AEO', 'Carry the source problem into an app-specific query and answer-page chain. Views never become search demand, bids or citations.', 'acquisition', 'Map an acquisition intent')}
    ${step('8. Render and review', 'Inspect the original brief and its local rendering controls. Confirm legibility, authenticity and rights before a separate publication action.', 'render', 'Open production controls')}
    ${step('9. Measure useful outcomes', 'Register the cohort, cost and analysis plan. Observe activation, payers, retention and refunds; missing attribution remains unknown.', 'experiment', 'Open experiment setup')}
    </details><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions">${button('Download current handoff', 'spytok-download')}${button('Close', 'close')}</div>`,
    'SOURCE → ORIGINAL WORK → MEASURED OUTCOME',
  );
  $('#spytok-discovery').addEventListener('change', (event) => {
    $('#spytok-discovery-link').href = spyTokLink(event.target.value);
  });
  $('#spytok-discovery-link').insertAdjacentHTML(
    'afterend',
    button('Set up team capability', 'spytok-local', 'data-next="team"'),
  );
  const select = $('#spytok-reference');
  const card = $('#spytok-decision');
  let displayed = null;
  const selectedDecision = () => {
    if (state.app !== openedAppId || state.workspace?.app?.version !== openedVersion)
      throw new Error('The app changed. Reopen creative discovery.');
    const current = sourceDecision(select.value);
    const captured = captures.get(select.value);
    if (
      current &&
      (!captured || captured.version !== current.version || captured.hash !== current.hash)
    )
      throw new Error('The source capture changed. Reopen creative discovery.');
    return current;
  };
  const currentDecision = () => {
    const current = selectedDecision();
    if (!select.isConnected || JSON.stringify(current) !== JSON.stringify(displayed))
      throw new Error('The selected source or its review changed. Reopen creative discovery.');
    return current;
  };
  const reportError = (error) => {
    $('#form-error').textContent = error.message;
  };
  select.addEventListener('change', () => {
    try {
      displayed = selectedDecision();
      card.innerHTML = decisionCard(displayed, refs.length > 0);
      $('#form-error').textContent = '';
      $('#spytok-announcement').textContent = displayed
        ? `${displayed.title}. ${displayed.next.caption}.`
        : 'No source selected.';
    } catch (error) {
      card.replaceChildren();
      reportError(error);
    }
  });
  $('#modal-body')
    .querySelectorAll('[data-action="discovery-open"], [data-action="oresearch-open"]')
    .forEach((control) =>
      control.addEventListener('click', (event) => {
        try {
          currentDecision();
        } catch (error) {
          event.stopPropagation();
          reportError(error);
        }
      }),
    );
  activeSpyTok = { select, currentDecision };
}

let activeSpyTok = null;

function spyTokAction(node) {
  const action = node.dataset.action;
  if (action === 'spytok-open') return openSpyTokWorkflow();
  if (!$('#modal').open || !activeSpyTok?.select.isConnected)
    throw new Error('Reopen creative discovery before continuing.');
  const selected = activeSpyTok.currentDecision();
  if (action === 'spytok-download')
    return download(`${state.app}-creative-handoff.json`, spyTokHandoff(selected?.id));
  if (action !== 'spytok-local') throw new Error('Unknown creative workflow action.');
  const research = () => {
    $('#modal').close();
    state.view = 'research';
    render();
    const heading = $('#creative-rendering-heading');
    if (!heading) throw new Error('Open Research to locate video production.');
    heading.focus();
  };
  const handlers = {
    profile: () => appForm(false),
    select: () => activeSpyTok.select.focus(),
    source: () => referenceForm(),
    import: referenceImportForm,
    team: () => capabilityForm('profile'),
    requirements: () => capabilityForm('requirement', selected?.id),
    inspect: () => (selected ? inspectionForm(selected.id) : referenceForm()),
    brief: () =>
      briefForm(null, null, selected?.analysis ? { analysis_id: selected.analysis.id } : {}),
    acquisition: acqIntentForm,
    render: research,
    experiment: () =>
      experimentForm(
        selected?.activation
          ? {
              hypothesis: `An original opening that demonstrates “${selected.activation}” will increase that tracked first-value action versus our current opening. Change only the opening; confirm the event and baseline before running.`,
            }
          : {},
      ),
  };
  if (
    node.hasAttribute('data-spytok-primary') &&
    selected &&
    node.dataset.next !== selected.next.mode
  )
    throw new Error('The next step changed. Reopen creative discovery.');
  if (!Object.hasOwn(handlers, node.dataset.next))
    throw new Error('Unknown creative workflow step.');
  return handlers[node.dataset.next]();
}

export {
  spyTokDiscovery,
  spyTokLink,
  spyTokPanel,
  spyTokHandoff,
  openSpyTokWorkflow,
  spyTokAction,
};
