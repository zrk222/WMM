'use strict';

function researchView() {
  const ledger = state.research.ledger;
  const profile = state.research.acquisition.apps.find((app) => app.app_id === state.app);
  const sources = (ledger.other_notebooks || [])
    .map(
      (source) =>
        `<section class="panel"><h3>${esc(source.title || source.name || source.artifact || 'Saved research')}</h3><p class="description">${esc(source.review_scope || source.scope || 'Selected saved artifact; review the evidence boundary.')}</p><details><summary>Inspect source and retained findings</summary><pre>${json(source)}</pre></details></section>`,
    )
    .join('');
  return `${heading('Research into useful action', 'Keep the source, question and actual product proof connected.')}${notice('Research findings are hypotheses, not product claims or guaranteed growth. The library records exactly what was reviewed.')}${spyTokPanel()}${spiraPanel()}${aeoPanel()}${acquisitionPanel()}${rankingPanel()}${productionPanel()}${renderingPanel()}<div class="section-heading"><h2>App-specific ASA / AEO intents</h2></div>${profile ? `<div class="stage-grid">${profile.intent_clusters.map((cluster) => `<section class="panel"><p class="eyebrow">${esc(cluster.id)}</p><h3>${esc(cluster.aeo_seed)}</h3><p class="description">${esc(cluster.page_hypothesis)}</p><div class="details-list"><div class="detail-item"><strong>Apple Ads seed</strong>${esc(cluster.asa_seed)}</div><div class="detail-item"><strong>First-value event</strong>${esc(cluster.activation)}</div></div>${status('HYPOTHESIS')}</section>`).join('')}</div>` : empty("Define this app's first intent", 'Start with its researched user job, then map the search term, answer page, claim evidence and first-value event.')}<div class="section-heading"><h2>Source library</h2></div><section class="panel"><h3>Primary notebook</h3><p class="description">Your local source library starts empty. Add independently reviewed evidence for each app.</p><details><summary>Reviewed titles and coverage</summary><pre>${json(ledger.primary_notebook)}</pre></details></section><div class="section-heading"><h2>Additional saved research</h2></div><div class="stage-grid">${sources}</div>`;
}

function activityTimelineEvent(item) {
  const digest = item.receipt?.sha256;
  const receipt = `<span class="app-mono"> Â· ${esc(item.receipt.id)}</span>${digest ? ` Â· sha256 ${esc(digest.slice(0, 12))}â€¦` : ''}`;
  const causes = item.caused_by?.length
    ? ` Â· recorded after ${item.caused_by.map(esc).join(', ')}`
    : '';
  return `<div class="record-row"><span class="record-main"><strong>${esc(label(String(item.action).replaceAll('.', ' ')))}</strong><small>${esc(item.kind)} Â· ${esc(new Date(item.at).toLocaleString())}${receipt}${causes}</small></span>${item.status ? status(item.status) : ''}</div>`;
}

function activityTimelineEvents(items) {
  return items.length
    ? items.map(activityTimelineEvent).join('')
    : notice('No local activity matches this filter yet.');
}

function activityTimelinePanel() {
  const t = state.workspace?.activity_timeline;
  if (!t) return '';
  const kinds = Object.keys(t.coverage?.counts || {});
  return `<section class="panel" aria-label="Unified activity timeline"><h2>Unified activity timeline</h2><p>${esc(t.events.length)} newest local records. ${esc(t.boundary)}</p><div class="toolbar"><label class="field" for="activity-kind">Record type<select id="activity-kind"><option value="">All record types</option>${kinds.map((k) => `<option value="${esc(k)}">${esc(label(k))}</option>`).join('')}</select></label>${button('Filter timeline', 'activity-filter')}${t.next_cursor ? button('Load older records', 'activity-more', `data-cursor="${esc(t.next_cursor)}"`) : ''}</div><div id="activity-timeline-list">${activityTimelineEvents(t.events)}</div>${t.coverage?.truncated_sources?.length ? notice('These bounded sources may be incomplete: ' + t.coverage.truncated_sources.join(', '), 'warning') : ''}</section>`;
}

async function activityAction(node) {
  const kind = $('#activity-kind')?.value || '';
  const cursor = node.dataset.cursor || '';
  const params = new URLSearchParams({ limit: '20' });
  if (kind) params.set('kind', kind);
  if (cursor) params.set('cursor', cursor);
  const result = await api(`/api/apps/${encodeURIComponent(state.app)}/activity/history?${params}`);
  const list = $('#activity-timeline-list');
  list.innerHTML = cursor
    ? list.innerHTML + activityTimelineEvents(result.events)
    : activityTimelineEvents(result.events);
  const holder = list.closest('section');
  holder.querySelector("[data-action='activity-more']")?.remove();
  if (result.next_cursor)
    holder
      .querySelector('.toolbar')
      .insertAdjacentHTML(
        'beforeend',
        button('Load older records', 'activity-more', `data-cursor="${esc(result.next_cursor)}"`),
      );
  holder.querySelector('p').textContent =
    `${esc(result.events.length)} records on this page. ${esc(result.boundary)}`;
}

function activityView() {
  const w = state.workspace;
  return `${heading('Every action leaves a trail', 'Inspect saved runs, review packets and the history of this app workspace.')}${guidedEvidenceStates()}${activityTimelinePanel()}${guidedExceptionPanel(w.workflow.exceptions)}${verifiedReviewPanel()}<section class="panel" aria-label="Watch campaign delivery"><h2>Watch campaign delivery</h2><p>Review saved provider checks, exceptions and protective pauses for approved Facebook campaigns.</p>${button('Monitor approved campaigns', 'campaign-monitor-open')}${button('Review private campaign outcomes', 'owner-report-open')}</section>${providerActionsPanel()}${notice('Legacy local-name packets below are manual bookkeeping. They cannot establish verified identity or authorize provider execution.')}<div class="section-heading"><h2>Manual review history</h2>${button('Prepare review packet', 'prepare-review')}</div>${w.approvals.length ? `<div class="record-list">${w.approvals.map((r) => `<button class="record-row" data-action="review" data-id="${esc(r.id)}"><span class="record-icon" aria-hidden="true">âœ“</span><span class="record-main"><strong>${esc(r.packet.record.title)}</strong><small>Prepared by ${esc(r.preparer)} Â· expires ${esc(new Date(r.expires).toLocaleString())}</small></span>${status(r.status)}</button>`).join('')}</div>` : empty('Nothing waiting for review', 'Add a distribution, store or experiment record, then freeze its exact contents into a review packet.')}<div class="section-heading"><h2>Saved runs</h2></div>${w.jobs.length ? `<div class="record-list">${w.jobs.map((job) => `<button class="record-row" data-action="job" data-id="${esc(job.id)}"><span class="record-icon" aria-hidden="true">â†»</span><span class="record-main"><strong>${job.action === 'agent_run' ? 'Agent campaign draft' : job.action === 'resolution' ? 'Agent evidence resolution' : job.action === 'pipeline' ? 'Pipeline preparation' : job.action === 'experiment' ? 'Experiment analysis' : 'Provider synchronization'}</strong><small>${esc(new Date(job.created).toLocaleString())} Â· attempt ${job.attempts}</small></span>${status(job.status)}</button>`).join('')}</div>` : empty('Your first run starts the trail', 'Prepare the pipeline to save app-scoped packets and exact missing-input checklists.', button('Prepare the pipeline', 'run-all'))}<div class="section-heading"><h2>Workspace history</h2></div>${
    w.audit.length
      ? `<div class="record-list">${w.audit
          .slice(0, 20)
          .map(
            (entry) =>
              `<div class="record-row"><span class="record-main"><strong>${esc(label(entry.action.replaceAll('.', ' ')))}</strong><small>${esc(new Date(entry.created).toLocaleString())}</small></span><span class="app-mono">#${entry.id}</span></div>`,
          )
          .join('')}</div>`
      : notice('No workspace changes have been recorded yet.')
  }`;
}
