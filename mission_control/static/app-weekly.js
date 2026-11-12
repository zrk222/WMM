'use strict';

function visibleWeeklyExceptions(value, principal) {
  return WMMPageReports.visibleWeeklyExceptions(value, principal) || [];
}

function weeklyView() {
  const value = state.weeklyReview;
  const intro = heading(
    'Your weekly exceptions',
    'Review what needs attention across your apps. Saved local evidence; no campaign execution.',
    button('Refresh review', 'weekly-refresh'),
  );
  if (state.weeklyLoading) return intro + '<p role="status">Reviewing saved app evidenceâ€¦</p>';
  if (state.weeklyError)
    return (
      intro + notice(state.weeklyError + ' Refresh to retry; saved work is preserved.', 'error')
    );
  if (!value)
    return (
      intro +
      empty(
        'Start your portfolio review',
        'Gather saved evidence across up to five apps per page.',
        button('Review apps', 'weekly-refresh'),
      )
    );
  const visible = visibleWeeklyExceptions(value, state.workspace.identity?.principal);
  const cards = visible
    .map(
      (c) =>
        `<article class="panel"><p class="eyebrow">${esc(c.app_name)} / ${esc(c.category)}</p><h2>${esc(c.title)}</h2>${status(c.state)}<p>${esc(c.reason)}</p><p><strong>Recommended next step:</strong> ${esc(c.next_action)}</p><p class="description">Handled by: ${esc(c.owner)} Â· Cost unknown Â· Change from prior review not assessed.</p>${button(c.resolution_route === 'agent_review' ? (c.state === 'SOURCE_UNAVAILABLE' ? 'Open review queue' : 'Open exact request') : 'Open recovery', 'weekly-recover', `data-app="${esc(c.app_id)}" data-tool="${esc(c.resolution_route)}" data-resource="${esc(c.action?.resource_id || '')}" data-scope="${esc(c.action?.scope_id || '')}"`)}<details><summary>Source and limits</summary><p>App ${esc(c.source_receipt.app_id)} Â· setup version ${esc(c.source_receipt.manifest_version)} Â· reviewed ${esc(c.source_receipt.observed_at)}</p><p class="app-mono">${esc(c.source_receipt.source_hash || 'Source unavailable')}</p><p>Local input checks do not prove retained value, permission to spend or measured growth.</p></details></article>`,
    )
    .join('');
  const coverage = value.coverage;
  const work =
    value.owner_operations_principal &&
    state.workspace.identity?.principal === value.owner_operations_principal
      ? value.active_work || []
      : [];
  const workRows = work
    .map(
      (w) =>
        `<div class="record-row"><span class="record-main"><strong>${esc(w.app_name)} Â· ${esc(label(w.kind))}</strong><small>${esc(w.title)} Â· updated ${esc(new Date(w.updated_at).toLocaleString())}${w.expires_at ? ` Â· expires ${esc(new Date(w.expires_at).toLocaleString())}` : ''}</small></span>${status(w.state)}${button('Open', 'weekly-recover', `data-app="${esc(w.app_id)}" data-tool="${esc(w.resolution_route)}"`)}</div>`,
    )
    .join('');
  const workSection = `<details class="panel"><summary>Active work across this page (${work.length})</summary>${work.length ? `<div class="record-list">${workRows}</div>` : notice('No saved active jobs, sequences or approvals expiring within seven days on this page.')}<p class="description">Timestamps come from the saved local row. Active work is not a completed result.</p></details>`;
  const statusRows = value.apps
    .map((a) => {
      const stage = a.current_stage || {};
      return `<tr><th scope="row">${esc(a.app_name)}</th><td>${stage.id ? esc(`Step ${stage.id}: ${stage.title || ''}`) : 'Unavailable'}</td><td>${Number.isSafeInteger(a.high_priority_gaps) ? esc(a.high_priority_gaps) : 'Unavailable'}</td><td>${Number.isSafeInteger(a.active_sequences) ? esc(a.active_sequences) : 'Unavailable'}</td><td>${esc((a.local_ready || []).join(', ') || 'None')}</td></tr>`;
    })
    .join('');
  const statusSection = `<details class="panel"><summary>Portfolio status</summary><table><caption>Saved local state per app</caption><thead><tr><th scope="col">App</th><th scope="col">Current stage</th><th scope="col">P0 gaps</th><th scope="col">Active sequences</th><th scope="col">Local-ready checks</th></tr></thead><tbody>${statusRows}</tbody></table><p class="description">Counts describe saved local state for each app. They are not comparable outcomes, and an unavailable source stays explicit.</p></details>`;
  return (
    intro +
    `<p role="status">Apps ${coverage.offset + 1}â€“${coverage.offset + coverage.evaluated} of ${coverage.total_apps} reviewed Â· ${visible.length} exceptions and ${work.length} active items on this page.</p>` +
    (cards ||
      notice(
        'No exceptions on this page. Local-ready inputs still require independent outcome and permission checks.',
      )) +
    workSection +
    statusSection +
    `<div class="toolbar">${coverage.offset ? button('First apps', 'weekly-page', 'data-offset="0"') : ''}${coverage.next_offset !== null ? button('Next apps', 'weekly-page', `data-offset="${coverage.next_offset}"`) : ''}</div>`
  );
}

async function weeklyAction(node) {
  const generation = (state.weeklyGeneration = (state.weeklyGeneration || 0) + 1);
  if (node.dataset.action === 'weekly-recover') {
    const app = node.dataset.app,
      tool = node.dataset.tool,
      principal = state.workspace.identity?.principal;
    const allowed = new Set([
      'workspace',
      'readiness',
      'measurement',
      'results',
      'retention',
      'findings',
      'monitor',
      'campaign',
      'owner_reports',
      'agent_review',
      'activity',
      'agents',
    ]);
    if (!allowed.has(tool) || !state.boot.apps.some((a) => a.id === app))
      throw new Error('Refresh this review before opening recovery.');
    const reviewCard =
      tool === 'agent_review'
        ? visibleWeeklyExceptions(state.weeklyReview, principal).find(
            (c) =>
              c.app_id === app &&
              c.resolution_route === tool &&
              c.action?.resource_id === node.dataset.resource,
          )
        : null;
    if (tool === 'agent_review' && !reviewCard)
      throw new Error('Refresh this signed-in review before opening the request.');
    state.app = app;
    $('#app-select').value = app;
    await refresh();
    if (
      state.weeklyGeneration !== generation ||
      state.view !== 'weekly' ||
      state.app !== app ||
      !currentWorkspace()
    )
      return;
    if (tool === 'agent_review') {
      if (state.workspace.identity?.principal !== principal) return;
      return WMMAgentControl.action(
        {
          dataset:
            reviewCard.state === 'SOURCE_UNAVAILABLE'
              ? { action: 'control-queue' }
              : { action: 'control-inspect', id: node.dataset.resource },
        },
        growthReviewServices(),
      );
    }
    if (tool === 'monitor') {
      await WMMCampaignMonitor.open();
      return node.dataset.resource ? WMMCampaignMonitor.inspect(node.dataset.resource) : undefined;
    }
    if (tool === 'campaign')
      return node.dataset.scope ? campaignStatus(node.dataset.scope) : campaignOpen();
    if (tool === 'owner_reports') {
      await WMMOwnerReports.open();
      return node.dataset.resource
        ? WMMOwnerReports.inspect('plan', node.dataset.resource)
        : undefined;
    }
    if (tool === 'activity') return guidedNavigate('activity');
    if (tool === 'agents') return guidedNavigate('agents');
    return tool === 'workspace' ? guidedNavigate('overview') : guidedOpenTool(tool);
  }
  const offset = node.dataset.action === 'weekly-page' ? Number(node.dataset.offset) : 0;
  state.weeklyLoading = true;
  state.weeklyError = '';
  render();
  try {
    const principal = state.workspace.identity?.principal;
    const result = await api('/api/weekly-review?offset=' + offset);
    if (
      state.weeklyGeneration !== generation ||
      state.view !== 'weekly' ||
      principal !== state.workspace.identity?.principal
    )
      return;
    state.weeklyReview = result;
  } catch (error) {
    if (state.weeklyGeneration !== generation || state.view !== 'weekly') return;
    state.weeklyError = error.message;
  } finally {
    if (state.weeklyGeneration === generation) {
      state.weeklyLoading = false;
      if (state.view === 'weekly') render();
    }
  }
}
