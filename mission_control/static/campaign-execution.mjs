import { $, api, button, esc, notice, state } from './app.mjs';
import { modal } from './app-ui.mjs';
import { WMMPageReports } from './feature-apis.mjs';
('use strict');
/* Owner scope is authority; this view cannot issue authority for an agent. */
function campaignPanel() {
  return `<section class="panel"><h2>Campaign automation</h2><p>Approve your exact posts, Page, audience, time window and media budget. Your agent can then publish and run supported Meta campaigns inside that scope. Inspect saved delivery receipts and stop future work here.</p>${button('Review campaign automation', 'campaign-open')}${button('Monitor approved campaigns', 'campaign-monitor-open')}</section>`;
}

function campaignStable(value) {
  if (Array.isArray(value)) return '[' + value.map(campaignStable).join(',') + ']';
  if (value && typeof value === 'object')
    return (
      '{' +
      Object.keys(value)
        .sort()
        .map((k) => JSON.stringify(k) + ':' + campaignStable(value[k]))
        .join(',') +
      '}'
    );
  return JSON.stringify(value);
}

async function campaignHash(value) {
  const bytes = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(campaignStable(value)),
  );
  return Array.from(new Uint8Array(bytes), (x) => x.toString(16).padStart(2, '0')).join('');
}

function campaignBound(form) {
  if (
    form.isConnected === false ||
    form.dataset.app !== state.app ||
    Number(form.dataset.version) !== state.workspace.app.version ||
    (form.dataset.principal !== undefined &&
      form.dataset.principal !== (state.workspace.identity?.principal || ''))
  )
    throw new Error('App changed. Reopen campaign automation and review its current scope.');
}
function campaignExpiryUI() {
  return globalThis.WMMAuthorityExpiry;
}

async function campaignOpen(source = null, study = null) {
  const destination = study?.destination;
  const app = state.app,
    version = state.workspace.app.version,
    principal = state.workspace.identity?.principal,
    history = await api(`/api/apps/${app}/campaigns/history`, {});
  if (
    state.workspace.app.version !== version ||
    app !== state.app ||
    state.workspace.identity?.principal !== principal ||
    (source && !source.isConnected) ||
    (study && (state.measuredPost !== study || study.destination !== destination))
  )
    return;
  const schedules = await api(`/api/apps/${app}/campaigns/schedule-history`, {});
  if (
    state.workspace.app.version !== version ||
    app !== state.app ||
    state.workspace.identity?.principal !== principal ||
    (source && !source.isConnected) ||
    (study && (state.measuredPost !== study || study.destination !== destination))
  )
    return;
  const accounts = (state.workspace.social_access?.accounts || []).filter(
    (r) =>
      r.provider === 'facebook' && r.status === 'CONNECTED_READ_TESTED' && !r.reconnect_required,
  );
  const selected = study && accounts.find((row) => row.data.destination.id === destination);
  if (study && !selected)
    throw new Error(
      'The selected Facebook Page is no longer available. Reconnect it and select it again.',
    );
  modal(
    'Campaign automation',
    `<form id="campaign-scope-form" class="modal-content" data-app="${esc(app)}" data-version="${state.workspace.app.version}" data-principal="${esc(principal || '')}"><p>Choose the work once, review its exact limits, then let your agent operate within them. Account permissions are checked separately before execution.</p><label class="field">Facebook Page connection<select name="connection_id" required><option value="">Choose a connected Page</option>${accounts.map((r) => `<option value="${esc(r.id)}">${esc(r.data.destination.name)} · ${esc(r.data.destination.id)}</option>`).join('')}</select></label>${accounts.length ? '' : notice('Connect a Facebook Page first. Select publishing or ad access during setup, complete official login, then return here.', 'warning')}<label class="field">Approved post copy<textarea name="posts" rows="6" maxlength="50000" required placeholder="Write one post. Separate additional posts with a line containing ---"></textarea></label><p>Up to 20 exact posts per review. The workflow uses your approved words; it does not invent product claims.</p><label class="field">App or landing-page link<input name="link" type="url" placeholder="https://your-app.example" maxlength="2048"></label><label class="field">Rights and claims evidence<textarea name="rights" maxlength="2000" required placeholder="Explain your authority to use this copy and media, and where its app claims are substantiated."></textarea></label><label class="field">Maximum Meta requests<input name="max_calls" type="number" min="1" max="500" value="500" required></label><p>Includes account checks, publication and verification. Your agent has a separate WMM call limit.</p><label class="field">Authority expires in hours<input name="hours" type="number" min="1" max="24" value="1" required></label><details><summary>Optional paid Meta campaign</summary><p>Leave the ad account empty for free organic publishing. Media limits exclude taxes, fees and currency conversion; provider reports may lag. A campaign's maximum approved media budget is reserved before activation.</p><label class="field">Numeric ad-account ID<input name="ad_account_id" inputmode="numeric" pattern="[0-9]+" maxlength="40"></label><label class="field">Currency<input name="currency" pattern="[A-Z]{3}" maxlength="3" value="${esc(state.workspace.app.data.currency || 'USD')}" required></label><label class="field">Maximum media budget in minor units<input name="budget" type="number" min="0" max="100000000" value="0" step="1"></label><label class="field">Audience country codes<input name="countries" value="CA" maxlength="100" placeholder="CA, US"></label><label class="check-row"><input name="billing" type="checkbox"> I approve this media commitment and understand separate provider taxes, fees and billing delays.</label><label class="check-row"><input name="ordinary" type="checkbox"> I confirm this is outside Meta special ad categories (including housing, employment, financial products and political or social-issue advertising).</label></details><details><summary>Optional measurement plan (enforced before launch)</summary><p>Complete this plan to require connected acquisition and outcome sources, a tagged link and a frozen measurement window before any post or paid campaign dispatches. Leave it empty only for an unscoped legacy workflow.</p><label class="field">Primary metric<input name="measurement_metric" maxlength="2000" placeholder="paid_conversion"></label><label class="field">Denominator<input name="measurement_denominator" maxlength="2000" placeholder="installs"></label><label class="field">Campaign tag<input name="measurement_tag" maxlength="64" placeholder="launch-a"></label><label class="field">Measurement starts<input name="measurement_starts" type="datetime-local"></label><label class="field">Measurement ends<input name="measurement_ends" type="datetime-local"></label><label class="field">Frozen hypothesis<textarea name="measurement_hypothesis" maxlength="2000"></textarea></label><label class="field">Decision rule<textarea name="measurement_rule" maxlength="2000"></textarea></label></details><p id="campaign-error" role="alert"></p><div class="modal-actions"><button class="button primary" type="submit">Review exact automation scope</button>${button('Cancel', 'close')}</div></form><section class="modal-content"><h3>Saved scopes</h3>${history.scopes.length ? history.scopes.map((s) => `<p>${esc(s.page_id)} · ${esc(s.status)} · expires ${esc(s.permission_expires_at || s.expires_at)} ${button('Inspect saved scope', 'campaign-status', `data-id="${esc(s.scope_id)}"`)}</p>`).join('') : '<p>No saved scopes for this owner and app yet.</p>'}<h3>Saved schedules</h3>${(schedules.batches || []).map((b) => `<p>${esc(b.status)} · ${esc(b.items.length)} posts ${button('Inspect scheduled batch', 'campaign-schedule-status', `data-batch="${esc(b.id)}"`)}</p>`).join('') || '<p>No saved scheduled batch yet.</p>'}</section>`,
  );
  $('#campaign-scope-form').dataset.principal = principal || '';
  const scopeForm = $('#campaign-scope-form');
  if (study) {
    scopeForm.elements.link.value = study.link.url;
    scopeForm.elements.connection_id.value = selected.id;
  }
  scopeForm
    .querySelector('[type=submit]')
    .insertAdjacentHTML(
      'beforebegin',
      '<label class="field">Or choose an exact expiry — device local time<input name="expires_at" type="datetime-local"></label><div data-expiry-consent hidden><label class="check-row"><input name="extended_expiry_consent" type="checkbox"> I explicitly consent to this approval lasting more than 24 hours.</label></div>',
    );
  campaignExpiryUI().bindConsent(scopeForm, 'expires_at');
}

function campaignReviewMarkup(scope, preview, posts, rights, targeting, pageName) {
  const paid = Boolean(scope.ad_account_id);
  const reviewedPosts = preview ? preview.summary.campaign.draft_posts : posts;
  const row = (label, value) => `<div><dt>${label}</dt><dd>${esc(value)}</dd></div>`;
  const media = (amount) => `${amount} minor units ${scope.currency}`;
  const facts = [
    row('Facebook Page', `${pageName} · ${scope.page_id}`),
    row(
      'What is allowed',
      `Up to ${scope.max_posts} exact ${scope.max_posts === 1 ? 'post' : 'posts'}${paid ? ` and ${scope.max_campaigns} Meta engagement campaign` : '; organic only'}`,
    ),
    row(
      'Maximum media commitment',
      paid ? media(scope.max_total_minor) : `0 ${scope.currency} · no paid ads`,
    ),
    row('Permission expires', campaignExpiryUI().dateLine(scope.expires_at)),
    row('Maximum Meta requests', scope.max_calls),
    ...(scope.measurement_plan
      ? [
          row(
            'Measurement plan',
            `${scope.measurement_plan.primary_metric} / ${scope.measurement_plan.denominator}; ${scope.measurement_plan.starts_at} to ${scope.measurement_plan.ends_at}`,
          ),
        ]
      : []),
    ...(paid
      ? [
          row('Meta ad account', scope.ad_account_id),
          row('Media cap per campaign', media(scope.max_campaign_minor)),
          row('Audience countries', targeting.countries.join(', ')),
        ]
      : []),
  ].join('');
  const cards = reviewedPosts
    .map(
      (post, index) => `
    <article class="panel">
      <h4>Post ${index + 1}</h4>
      <p class="campaign-review-copy">${esc(post.message)}</p>
      <p class="campaign-review-link">Proposed post link: <span>${esc(post.link || 'None')}</span></p>
    </article>`,
    )
    .join('');
  const stopRules = preview?.summary.stop_rules || [
    'OFF, revoked owner or grant',
    'Expiry, changed source or resource revisions',
    'Allowance or approved media ceiling exhausted',
    'Uncertain dispatch: reconcile before retry',
  ];
  return `
    <ol class="campaign-review-steps" aria-label="Campaign approval progress">
      <li><span aria-hidden="true">✓</span><strong>Draft ready</strong></li>
      <li aria-current="step"><span aria-hidden="true">2</span><strong>Review limits</strong></li>
      <li><span aria-hidden="true">3</span><strong>Run separately</strong></li>
    </ol>
    <section class="panel" aria-labelledby="campaign-review-decision">
      <h3 id="campaign-review-decision">What you’re approving</h3>
      <p>This saves permission. It does not publish, schedule, or spend now. An authorized run still needs to start.</p>
      <dl class="campaign-review-facts">${facts}</dl>
      ${paid ? `<p>${esc(scope.billing_notice)}</p>` : ''}
    </section>
    <section aria-labelledby="campaign-review-posts">
      <h3 id="campaign-review-posts">Exact post copy and links</h3>
      ${cards}
      <p><strong>Rights and claims evidence:</strong> ${esc(rights)}</p>
      <p>${esc(scope.rights_notice)}</p>
    </section>
    <p><strong>When work stops:</strong> ${esc(stopRules.join('; '))}. Already dispatched effects and incurred charges remain recorded.</p>
    <details><summary>Exact authority and limits</summary>
      ${preview ? `<p>Agreement summary hash: ${esc(preview.summary_hash)}</p>` : ''}
      <pre>${esc(JSON.stringify(scope, null, 2))}</pre>
    </details>
    <p id="campaign-error" role="alert"></p>
    <div class="button-row">
      ${button('Approve scope and enable automation', 'campaign-activate', '', 'primary')}
      ${button('Cancel', 'close')}
    </div>`;
}

async function campaignSubmit(form) {
  const submit = form.querySelector('[type=submit]');
  if (submit.disabled) return;
  submit.disabled = true;
  try {
    campaignBound(form);
    const app = state.app,
      values = Object.fromEntries(new FormData(form));
    const selected = state.workspace.social_access.accounts.find(
      (r) => r.id === values.connection_id && r.provider === 'facebook',
    );
    if (!selected) throw new Error('Choose a connected Facebook Page.');
    const messages = values.posts
      .split(/\r?\n---\r?\n/)
      .map((s) => s.trim())
      .filter(Boolean);
    if (!messages.length || messages.length > 20 || messages.some((s) => s.length > 5000))
      throw new Error('Use 1–20 posts, with at most 5,000 characters each.');
    const hours = Number(values.hours),
      paid = Boolean(values.ad_account_id),
      budget = Number(values.budget),
      extended = values.expires_at
        ? campaignExpiryUI().validateExpiry(
            values.expires_at,
            values.extended_expiry_consent === 'on',
          )
        : null;
    if (!extended && (!Number.isInteger(hours) || hours < 1 || hours > 24))
      throw new Error('Choose 1–24 hours or an exact future expiry.');
    if (!Number.isSafeInteger(budget) || budget < 0 || (!paid && budget !== 0))
      throw new Error(
        'Select an ad account for a paid budget, or use zero for organic publishing.',
      );
    const link = values.link.trim() || null,
      rights = values.rights.trim();
    if (!rights) throw new Error('Explain your rights and claim evidence before approving use.');
    const planValues = {
      metric: values.measurement_metric,
      denominator: values.measurement_denominator,
      tag: values.measurement_tag,
      hypothesis: values.measurement_hypothesis,
      rule: values.measurement_rule,
    };
    const anyPlan = Object.values(planValues).some((value) => String(value || '').trim());
    let measurementPlan = null;
    if (anyPlan) {
      if (
        Object.values(planValues).some((value) => !String(value || '').trim()) ||
        !values.measurement_starts ||
        !values.measurement_ends
      )
        throw new Error('Complete every measurement plan field or leave the plan empty.');
      if (!link) throw new Error('Add the approved tagged link before the measurement plan.');
      let parsed;
      try {
        parsed = new URL(link);
      } catch {
        throw new Error('Use a valid HTTPS measurement link.');
      }
      if (
        parsed.protocol !== 'https:' ||
        parsed.searchParams.get('utm_campaign') !== planValues.tag
      )
        throw new Error('The measurement link must carry the same utm_campaign tag.');
      const starts = new Date(values.measurement_starts),
        ends = new Date(values.measurement_ends);
      if (Number.isNaN(starts.getTime()) || Number.isNaN(ends.getTime()) || !(starts < ends))
        throw new Error('Use a valid measurement start before its end.');
      measurementPlan = {
        primary_metric: planValues.metric.trim(),
        denominator: planValues.denominator.trim(),
        link,
        campaign_tag: planValues.tag.trim(),
        starts_at: starts.toISOString(),
        ends_at: ends.toISOString(),
        hypothesis: planValues.hypothesis.trim(),
        decision_rule: planValues.rule.trim(),
      };
    }
    const rightsHash = await campaignHash({ app_id: app, attestation: rights });
    const posts = await Promise.all(
      messages.map(async (message) => ({
        request_id: crypto.randomUUID(),
        message,
        link,
        content_hash: await campaignHash({ message, link }),
        rights_hash: rightsHash,
      })),
    );
    const targeting = {
      countries: [
        ...new Set(
          values.countries
            .split(',')
            .map((s) => s.trim().toUpperCase())
            .filter(Boolean),
        ),
      ].sort(),
    };
    const targetingHash = await campaignHash(targeting),
      expires = extended?.expires || new Date(Date.now() + hours * 3600000).toISOString();
    const maxCalls = Number(values.max_calls ?? 500);
    if (!Number.isInteger(maxCalls) || maxCalls < 1 || maxCalls > 500)
      throw new Error('Use a Meta request limit from 1 to 500.');
    const scope = {
      connection_id: selected.id,
      page_id: selected.data.destination.id,
      ad_account_id: values.ad_account_id.trim() || null,
      currency: values.currency.trim(),
      expires_at: expires,
      ...(extended?.extended ? { extended_expiry_consent: true } : {}),
      max_posts: posts.length,
      max_calls: maxCalls,
      max_campaigns: paid ? 1 : 0,
      max_campaign_minor: paid ? budget : 0,
      max_total_minor: paid ? budget : 0,
      approved_content_hashes: [...new Set(posts.map((p) => p.content_hash))],
      approved_rights_hashes: [rightsHash],
      approved_targeting_hashes: paid ? [targetingHash] : [],
      billing_acknowledged: values.billing === 'on',
      ordinary_ad_attestation: values.ordinary === 'on',
      ...(measurementPlan ? { measurement_plan: measurementPlan } : {}),
    };
    campaignBound(form);
    const saved = await api(`/api/apps/${app}/campaigns/prepare`, { scope });
    campaignBound(form);
    let preview = null;
    if (!paid) {
      preview = await api(`/api/apps/${app}/agent-grants/agreement-preview`, {
        manifest_version: state.workspace.app.version,
        workflow_policy_id: null,
        campaign_scope_id: saved.scope_id,
        schedule_batch_id: null,
        draft_posts: posts,
      });
      campaignBound(form);
    }
    const review = campaignReviewMarkup(
      saved,
      preview,
      posts,
      rights,
      targeting,
      selected.data.destination.name,
    );
    modal(
      'Approve your campaign scope',
      `<div id="campaign-review" class="modal-content" data-app="${esc(app)}" data-version="${state.workspace.app.version}">${review}</div>`,
    );
    $('#campaign-review').dataset.principal = state.workspace.identity?.principal || '';
    if (scope.extended_expiry_consent === true || saved.extended_expiry_consent === true)
      $('#campaign-review').insertAdjacentHTML(
        'afterbegin',
        '<p>You explicitly consented to this selected expiry being more than 24 hours away.</p>',
      );
    $('#campaign-review').campaign = {
      scope: saved,
      posts,
      targeting,
      targetingHash,
      budget,
      expires,
      adRequestID: crypto.randomUUID(),
    };
    $('#modal').scrollTop = 0;
  } catch (error) {
    if (form.isConnected) form.querySelector('#campaign-error').textContent = error.message;
  } finally {
    submit.disabled = false;
  }
}

async function campaignStatus(scopeID, plan = null, source = null) {
  const app = state.app,
    version = state.workspace.app.version,
    principal = state.workspace.identity?.principal,
    result = await api(`/api/apps/${app}/campaigns/status`, { scope_id: scopeID });
  if (
    app !== state.app ||
    version !== state.workspace.app.version ||
    principal !== state.workspace.identity?.principal ||
    (source && !source.isConnected)
  )
    return;
  const scope = {
    ...result.scope,
    expires_at: result.scope.permission_expires_at || result.scope.expires_at,
  };
  if (
    plan &&
    (scope.status !== 'ACTIVE' ||
      result.intents.length ||
      plan.scope?.scope_id !== scope.scope_id ||
      !scope.approval_hash ||
      plan.scope.approval_hash !== scope.approval_hash)
  )
    plan = null;
  modal(
    'Campaign progress',
    `<div id="campaign-progress" class="modal-content" data-app="${esc(app)}" data-version="${state.workspace.app.version}" data-id="${esc(scopeID)}"><p>Scope: <strong>${esc(scope.status)}</strong> · Page ${esc(scope.page_id)} · expires ${esc(scope.expires_at)}.</p><p>Media ceiling: ${scope.max_total_minor} minor units ${esc(scope.currency)}. Calls used: ${esc(scope.call_allowance_units_used ?? scope.calls_used ?? 'Unknown')}/${scope.max_calls}.</p><p id="campaign-activity" role="status">Saved provider states shown below. A post ID or ad status does not establish app sales.</p>${result.intents.map((row) => `<section class="panel"><h3>${esc(row.status)}</h3><p>Receipt: ${esc(row.id)}</p><p>Provider ID: ${esc(row.remote_id || (row.ids ? Object.values(row.ids).join(', ') : 'Not confirmed'))}</p><pre>${esc(JSON.stringify(row.result, null, 2))}</pre>${button('Read provider status', 'campaign-reconcile', `data-intent="${esc(row.id)}"`)}${button('Pause owned paid campaign', 'campaign-pause', `data-intent="${esc(row.id)}"`)}</section>`).join('') || '<p>No effects have been dispatched for this scope.</p>'}<p id="campaign-error" role="alert"></p><div class="button-row">${plan && scope.status === 'ACTIVE' ? button('Run approved workflow', 'campaign-run', '', 'primary') : ''}${plan?.posts && !scope.ad_account_id && scope.status === 'ACTIVE' ? button('Schedule approved posts', 'campaign-schedule-open') : ''}${button('Campaign report / Save PDF', 'campaign-report')}${button('Refresh saved receipts', 'campaign-status', `data-id="${esc(scopeID)}"`)}${button('Turn off this scope', 'campaign-revoke')}</div></div>`,
  );
  const progress = $('#campaign-progress');
  if (
    scope.status === 'ACTIVE' &&
    state.workspace.access?.members?.some(
      (r) => r.principal === principal && r.role === 'OWNER' && r.status === 'ACTIVE',
    )
  )
    progress.insertAdjacentHTML(
      'beforeend',
      button(
        'Extend expiry',
        'campaign-extend',
        `data-id="${esc(scope.scope_id)}" data-expires="${esc(scope.expires_at)}"`,
      ),
    );
  progress.dataset.principal = principal || '';
  progress.campaign = {
    ...(plan || {}),
    scope,
    snapshot: result,
    read_at: new Date().toISOString(),
  };
  if (scope.status === 'ACTIVE' && scope.ad_account_id && campaignVerifiedPosts(result).length) {
    progress
      .querySelector('.button-row')
      .insertAdjacentHTML(
        'afterbegin',
        button('Schedule verified post promotion', 'campaign-schedule-paid-open'),
      );
  }
}

async function campaignAction(node) {
  const action = node.dataset.action;
  if (action === 'campaign-open') return campaignOpen(node);
  if (action === 'campaign-extend') {
    const id = node.dataset.id,
      expires = node.dataset.expires,
      app = state.app,
      version = state.workspace.app.version,
      principal = state.workspace.identity?.principal;
    return campaignExpiryUI().open({
      kind: 'CAMPAIGN',
      id,
      expires,
      app,
      api,
      modal,
      document,
      FormData: window.FormData,
      uuid: () => crypto.randomUUID(),
      owner: () =>
        state.workspace.access?.members?.some(
          (r) =>
            r.principal === state.workspace.identity?.principal &&
            r.role === 'OWNER' &&
            r.status === 'ACTIVE',
        ),
      current: () =>
        state.app === app &&
        state.workspace.app.version === version &&
        state.workspace.identity?.principal === principal,
      done: () => campaignStatus(id),
    });
  }
  if (action.startsWith('campaign-schedule-')) return campaignScheduleAction(node);
  if (action === 'campaign-status') {
    const progress = node.closest('#campaign-progress');
    if (!progress) return campaignStatus(node.dataset.id, null, node);
    campaignBound(progress);
    if (progress.dataset.busy === 'true') return;
    const plan = progress.campaign;
    return campaignStatus(
      node.dataset.id,
      plan?.posts && plan.scope?.scope_id === node.dataset.id ? plan : null,
      node,
    );
  }
  if (action === 'campaign-report') return campaignReport($('#campaign-progress'));
  const panel = $('#campaign-review') || $('#campaign-progress');
  if (!panel) return;
  if (panel.dataset.busy === 'true') return;
  panel.dataset.busy = 'true';
  panel.querySelectorAll('button').forEach((b) => (b.disabled = true));
  let stopWatching = () => {};
  try {
    campaignBound(panel);
    const app = state.app,
      plan = panel.campaign,
      scope = plan.scope;
    if (action === 'campaign-activate') {
      await api(`/api/apps/${app}/campaigns/activate`, {
        scope_id: scope.scope_id,
        approval_hash: scope.approval_hash,
      });
      campaignBound(panel);
      return campaignStatus(scope.scope_id, plan, panel);
    }
    if (action === 'campaign-run') {
      stopWatching = campaignWatch(panel, scope.scope_id);
      let firstPost = null;
      for (let i = 0; i < plan.posts.length; i++) {
        campaignBound(panel);
        $('#campaign-activity').textContent =
          `Publishing approved post ${i + 1} of ${plan.posts.length}…`;
        const result = await api(`/api/apps/${app}/campaigns/publish`, {
          scope_id: scope.scope_id,
          request: plan.posts[i],
        });
        campaignBound(panel);
        if (result.status !== 'VERIFIED')
          throw new Error(
            'Delivery needs reconciliation. Inspect the saved receipt; do not create a replacement request.',
          );
        if (i === 0) firstPost = result;
      }
      if (scope.ad_account_id && firstPost) {
        $('#campaign-activity').textContent =
          'Creating, verifying and activating the approved paid campaign…';
        await api(`/api/apps/${app}/campaigns/ad-launch`, {
          scope_id: scope.scope_id,
          request: {
            request_id: plan.adRequestID,
            post_id: firstPost.remote_id,
            content_hash: plan.posts[0].content_hash,
            rights_hash: plan.posts[0].rights_hash,
            targeting_hash: plan.targetingHash,
            targeting: plan.targeting,
            lifetime_budget_minor: plan.budget,
            end_time: plan.expires,
            name: 'WMM approved app campaign',
          },
        });
      }
      campaignBound(panel);
      return campaignStatus(scope.scope_id, null, panel);
    }
    const operation =
      action === 'campaign-revoke'
        ? 'revoke'
        : action === 'campaign-pause'
          ? 'pause'
          : action === 'campaign-reconcile'
            ? 'reconcile'
            : null;
    if (!operation) return;
    await api(`/api/apps/${app}/campaigns/${operation}`, {
      scope_id: scope.scope_id,
      ...(operation === 'revoke' ? {} : { intent_id: node.dataset.intent }),
    });
    campaignBound(panel);
    return campaignStatus(scope.scope_id, null, panel);
  } catch (error) {
    if (panel.isConnected) panel.querySelector('#campaign-error').textContent = error.message;
  } finally {
    stopWatching();
    panel.dataset.busy = 'false';
    if (panel.isConnected) panel.querySelectorAll('button').forEach((b) => (b.disabled = false));
  }
}

function campaignWatch(panel, scopeID) {
  const app = state.app;
  let stopped = false,
    timer = null,
    attempts = 0;
  const poll = async () => {
    if (stopped || !panel.isConnected || state.app !== app || attempts++ >= 120) return;
    try {
      if (!document.hidden) {
        const saved = await api(`/api/apps/${app}/campaigns/status`, { scope_id: scopeID });
        if (stopped || !panel.isConnected || state.app !== app) return;
        const latest = saved.intents.at(-1),
          activity = panel.querySelector('#campaign-activity');
        if (latest && activity)
          activity.textContent = `Live saved stage: ${latest.status}. ${saved.intents.length} delivery intents recorded. ${latest.remote_id ? 'Provider ID: ' + latest.remote_id : latest.ids ? 'Saved provider objects: ' + Object.keys(latest.ids).join(', ') : 'Provider ID not yet confirmed.'}`;
      }
    } catch (error) {
      if (panel.isConnected && !stopped)
        panel.querySelector('#campaign-error').textContent =
          'Progress refresh failed. Existing work continues; inspect saved receipts before any retry.';
    }
    if (!stopped) timer = setTimeout(poll, 5000);
  };
  timer = setTimeout(poll, 1500);
  return () => {
    stopped = true;
    clearTimeout(timer);
  };
}

function campaignReport(panel) {
  if (!panel) throw new Error('Open the current campaign receipts first.');
  campaignBound(panel);
  const saved = panel.campaign.snapshot,
    scope = saved.scope;
  const report = WMMPageReports.model(state);
  report.title = 'Campaign delivery';
  report.purpose = 'Inspect saved provider delivery and approved media commitments for this scope.';
  report.next_step =
    'Reconcile uncertain effects and compare source app KPIs in the declared experiment window.';
  report.loaded_at = panel.campaign.read_at;
  const source = 'Current authorized campaign scope and saved intent receipts';
  report.metrics = [
    { label: 'Scope status', value: scope.status, unit: 'state', source },
    {
      label: 'Verified Page posts',
      value: saved.intents.filter((r) => !r.kind && r.status === 'VERIFIED').length,
      unit: 'count',
      source,
    },
    {
      label: 'Paid intents',
      value: saved.intents.filter((r) => r.kind === 'AD').length,
      unit: 'count',
      source,
    },
    {
      label: 'Retained media commitments in this scope',
      value: saved.intents.filter((r) => r.kind === 'AD').reduce((sum, r) => sum + r.commitment, 0),
      unit: `minor units ${scope.currency}`,
      source,
    },
    {
      label: 'Approved scope media ceiling',
      value: scope.max_total_minor,
      unit: `minor units ${scope.currency}`,
      source,
    },
    {
      label: 'Provider boundary allowance used',
      value: scope.call_allowance_units_used ?? null,
      unit: 'conservative units',
      source,
    },
  ];
  for (const row of saved.intents.filter((r) => r.kind === 'AD'))
    report.metrics.push({
      label: `Reported spend · ${row.id}`,
      value: row.result?.reported_spend ?? null,
      unit: scope.currency,
      source: 'Last saved provider report; may lag',
    });
  report.notes = [
    'Scope ' + scope.scope_id + '; exact approval hash ' + scope.approval_hash,
    'Saved delivery is distinct from public reach, app installs, purchases and causal growth.',
    'Media commitments remain held after pause or uncertain responses. Taxes, fees and currency conversion are separate.',
    'No post copy, rights-attestation prose, credentials or raw creative payloads are included in this report.',
    'Refresh/reconcile provider observations before treating this saved view as current.',
  ];
  report.cohorts = [];
  return WMMPageReports.openReport(report, window);
}

function campaignScheduleItems(posts, values, expires, clock = Date.now()) {
  if (!Array.isArray(posts) || !posts.length || posts.length > 20)
    throw new Error('Schedule one to twenty reviewed posts.');
  return posts.map((request, index) => {
    const date = new Date(values['due_' + index]);
    if (
      !Number.isFinite(date.getTime()) ||
      date.getTime() <= clock ||
      date.getTime() >= Date.parse(expires)
    )
      throw new Error('Choose future due times strictly before campaign scope expiry.');
    return { due_at: date.toISOString(), request };
  });
}
function campaignVerifiedPosts(snapshot) {
  return (snapshot.intents || []).filter(
    (r) =>
      !r.kind &&
      r.status === 'VERIFIED' &&
      r.remote_id &&
      r.scope_id === snapshot.scope.scope_id &&
      r.page_id === snapshot.scope.page_id,
  );
}
function campaignPaidScheduleItem(
  scope,
  post,
  values,
  targetingHash,
  requestID,
  clock = Date.now(),
) {
  if (
    scope.status !== 'ACTIVE' ||
    !scope.ad_account_id ||
    !post ||
    post.status !== 'VERIFIED' ||
    post.scope_id !== scope.scope_id ||
    post.page_id !== scope.page_id
  )
    throw new Error('Select a verified post in this active paid scope.');
  const due = new Date(values.due_at),
    end = new Date(values.end_time),
    expiry = Date.parse(scope.expires_at);
  if (
    !Number.isFinite(expiry) ||
    !Number.isFinite(due.getTime()) ||
    !Number.isFinite(end.getTime()) ||
    due.getTime() <= clock ||
    end <= due ||
    end.getTime() > expiry
  )
    throw new Error('Choose a future start and later end within the scope expiry.');
  const budget = Number(values.budget),
    name = values.name.trim(),
    countries = values.countries
      .split(',')
      .map((s) => s.trim().toUpperCase())
      .filter(Boolean);
  if (
    !Number.isSafeInteger(budget) ||
    budget <= 0 ||
    budget > scope.max_campaign_minor ||
    budget > scope.max_total_minor
  )
    throw new Error('Choose a positive media budget within the approved limits.');
  if (
    !name ||
    name.length > 100 ||
    !countries.length ||
    countries.length > 20 ||
    countries.some((c) => !/^[A-Z]{2}$/.test(c)) ||
    new Set(countries).size !== countries.length
  )
    throw new Error('Provide a campaign name and unique two-letter country codes.');
  const targeting = { countries: countries.sort() };
  if (!scope.approved_targeting_hashes.includes(targetingHash))
    throw new Error('These countries are outside the approved scope.');
  return {
    due_at: due.toISOString(),
    operation: 'campaign.ad-launch',
    request: {
      request_id: requestID,
      post_id: post.remote_id,
      content_hash: post.content_hash,
      rights_hash: post.rights_hash,
      targeting_hash: targetingHash,
      lifetime_budget_minor: budget,
      end_time: end.toISOString(),
      targeting,
      name,
    },
  };
}
function campaignSchedulePaidOpen() {
  const panel = $('#campaign-progress');
  if (!panel) throw new Error('Open a saved paid scope first.');
  campaignBound(panel);
  const plan = panel.campaign,
    posts = campaignVerifiedPosts(plan.snapshot),
    scope = plan.scope;
  if (scope.status !== 'ACTIVE' || !scope.ad_account_id || !posts.length)
    throw new Error('An active paid scope and verified post are required.');
  modal(
    'Schedule a verified post promotion',
    '<form id="campaign-schedule-form" class="modal-content" data-app="' +
      esc(state.app) +
      '" data-version="' +
      state.workspace.app.version +
      '" data-principal="' +
      esc(state.workspace.identity?.principal || '') +
      '"><p>Select a saved verified Page post. The campaign runs only while WMM is running and must end by ' +
      esc(scope.expires_at) +
      '. The media commitment excludes provider taxes and fees.</p><label class="field">Verified Page post<select name="post_id" required>' +
      posts
        .map(
          (p) =>
            '<option value="' +
            esc(p.remote_id) +
            '">' +
            esc(p.remote_id) +
            ' · content ' +
            esc(p.content_hash) +
            '</option>',
        )
        .join('') +
      '</select></label><label class="field">Audience country codes<input name="countries" required placeholder="CA, US"></label><label class="field">Media budget in minor units (' +
      esc(scope.currency) +
      ')<input name="budget" type="number" min="1" max="' +
      esc(scope.max_campaign_minor) +
      '" step="1" required></label><label class="field">Start local date and time<input name="due_at" type="datetime-local" required></label><label class="field">End local date and time<input name="end_time" type="datetime-local" required></label><label class="field">Campaign name<input name="name" maxlength="100" required></label><p id="campaign-error" role="alert"></p><button type="submit" class="button primary">Review exact promotion</button>' +
      button('Cancel', 'close') +
      '</form>',
  );
  const form = $('#campaign-schedule-form');
  form.campaign = plan;
  form.paidPosts = posts;
  form.requestID = crypto.randomUUID();
}
function campaignScheduleOpen() {
  const panel = $('#campaign-progress');
  if (!panel) throw new Error('Open the approved campaign plan first.');
  campaignBound(panel);
  const plan = panel.campaign;
  if (plan.scope.ad_account_id)
    throw new Error('Use Schedule verified post promotion for this paid scope.');
  if (!plan.posts?.length) throw new Error('Prepare exact posts before scheduling.');
  modal(
    'Choose when the approved posts run',
    '<form id="campaign-schedule-form" class="modal-content" data-app="' +
      esc(state.app) +
      '" data-version="' +
      state.workspace.app.version +
      '" data-principal="' +
      esc(state.workspace.identity?.principal || '') +
      '"><p>The local worker publishes these exact posts while WMM is running. Closing the browser does not stop it; shutting down the host does. Future due times must be before ' +
      esc(plan.scope.expires_at) +
      '. No paid launch is scheduled.</p>' +
      plan.posts
        .map(
          (p, i) =>
            '<section class="panel"><p>' +
            esc(p.message) +
            '</p><label class="field">Post ' +
            (i + 1) +
            ' local date and time<input name="due_' +
            i +
            '" type="datetime-local" required></label></section>',
        )
        .join('') +
      '<p id="campaign-error" role="alert"></p><button type="submit" class="button">Review exact scheduled batch</button>' +
      button('Cancel', 'close') +
      '</form>',
  );
  $('#campaign-schedule-form').campaign = plan;
}
async function campaignScheduleSubmit(form) {
  const submit = form.querySelector('[type=submit]');
  if (submit.disabled) return;
  submit.disabled = true;
  try {
    campaignBound(form);
    const app = state.app,
      plan = form.campaign,
      values = Object.fromEntries(new FormData(form));
    let items;
    if (form.paidPosts) {
      const countries = values.countries
        .split(',')
        .map((s) => s.trim().toUpperCase())
        .filter(Boolean)
        .sort();
      const hash = await campaignHash({ countries });
      campaignBound(form);
      items = [
        campaignPaidScheduleItem(
          plan.scope,
          form.paidPosts.find((p) => p.remote_id === values.post_id),
          values,
          hash,
          form.requestID,
        ),
      ];
    } else items = campaignScheduleItems(plan.posts, values, plan.scope.expires_at);
    campaignBound(form);
    const saved = await api('/api/apps/' + app + '/campaigns/schedule-prepare', {
      scope_id: plan.scope.scope_id,
      items,
    });
    campaignBound(form);
    modal(
      'Approve the scheduled batch',
      '<div id="campaign-schedule-review" class="modal-content" data-app="' +
        esc(app) +
        '" data-version="' +
        state.workspace.app.version +
        '" data-principal="' +
        esc(state.workspace.identity?.principal || '') +
        '"><p>Review the exact UTC schedule. Activation uses the existing campaign scope and does not widen it.</p>' +
        saved.summary.items.map((i) => campaignScheduleReviewItem(i, plan.scope)).join('') +
        '<p>Summary hash: ' +
        esc(saved.summary_hash) +
        '</p><p>OFF cancels undispatched items. Dispatched effects may already exist; inspect their receipts. Provider taxes and fees are separate; commitments remain held.</p><p id="campaign-error" role="alert"></p>' +
        button('Approve exact batch and schedule', 'campaign-schedule-activate', '', 'primary') +
        button('Cancel', 'close') +
        '</div>',
    );
    $('#campaign-schedule-review').campaign = saved;
  } catch (e) {
    if (form.isConnected) form.querySelector('#campaign-error').textContent = e.message;
  } finally {
    submit.disabled = false;
  }
}
function campaignScheduleReviewItem(item, scope) {
  const r = item.request;
  if (item.operation === 'campaign.ad-launch')
    return (
      '<section class="panel"><h3>Promote verified post ' +
      esc(r.post_id) +
      '</h3><p>Account ' +
      esc(scope.ad_account_id) +
      ' · Page ' +
      esc(scope.page_id) +
      '</p><p>Countries ' +
      esc(r.targeting.countries.join(', ')) +
      ' · media budget ' +
      esc(r.lifetime_budget_minor) +
      ' minor ' +
      esc(scope.currency) +
      '</p><p>Starts ' +
      esc(item.due_at) +
      ' · ends ' +
      esc(r.end_time) +
      ' · name ' +
      esc(r.name) +
      '</p><p>Content ' +
      esc(r.content_hash) +
      ' · rights ' +
      esc(r.rights_hash) +
      ' · targeting ' +
      esc(r.targeting_hash) +
      '</p></section>'
    );
  return (
    '<section class="panel"><h3>' +
    esc(item.due_at) +
    '</h3><p>' +
    esc(r.message) +
    '</p><p>' +
    esc(r.link || 'No link') +
    '</p></section>'
  );
}
async function campaignScheduleStatus(batch, source = null) {
  const app = state.app,
    version = state.workspace.app.version,
    principal = state.workspace.identity?.principal,
    data = await api('/api/apps/' + app + '/campaigns/schedule-status', { batch_id: batch });
  if (
    state.app !== app ||
    state.workspace.app.version !== version ||
    state.workspace.identity?.principal !== principal ||
    (source && !source.isConnected)
  )
    return;
  modal(
    'Scheduled campaign progress',
    '<div id="campaign-schedule-progress" class="modal-content" data-app="' +
      esc(app) +
      '" data-version="' +
      version +
      '" data-principal="' +
      esc(principal || '') +
      '"><h3 id="schedule-batch-state">' +
      esc(data.status) +
      '</h3><p>Batch ' +
      esc(data.id) +
      ' · ' +
      esc(
        data.evidence_unavailable
          ? 'Saved item details unavailable.'
          : data.items.length + ' scheduled items.',
      ) +
      ' WMM must remain running. Saved provider state does not establish app sales.</p><p id="schedule-live-stage" role="status">' +
      esc(
        data.repair ||
          'Saved stages refresh while this dialog is visible. Provider observation times may lag.',
      ) +
      '</p><div id="schedule-live-items">' +
      data.items.map((i) => campaignScheduleProgressItem(i, data)).join('') +
      '</div><p id="campaign-error" role="alert"></p>' +
      button(
        'Refresh scheduled receipts',
        'campaign-schedule-status',
        'data-batch="' + esc(data.id) + '"',
      ) +
      button('Turn scheduled batch OFF', 'campaign-schedule-off') +
      button('Report / Save PDF', 'campaign-schedule-report') +
      '</div>',
  );
  const progress = $('#campaign-schedule-progress');
  progress.campaign = data;
  campaignScheduleWatch(progress);
}
function campaignScheduleWatch(panel) {
  let stopped = false,
    timer = null,
    reads = 0,
    failures = 0,
    inflight = false;
  const batch = panel.campaign.id,
    valid = () => {
      try {
        campaignBound(panel);
        return !stopped;
      } catch {
        return false;
      }
    };
  const again = (delay) => {
    if (valid() && reads < 120) timer = setTimeout(poll, delay);
  };
  const poll = async () => {
    if (!valid() || inflight || reads >= 120) return;
    if (document.hidden || panel.dataset.busy === 'true') {
      again(5000);
      return;
    }
    inflight = true;
    reads++;
    try {
      const data = await api('/api/apps/' + panel.dataset.app + '/campaigns/schedule-status', {
        batch_id: batch,
      });
      if (
        !valid() ||
        panel.dataset.busy === 'true' ||
        data.id !== batch ||
        data.version < panel.campaign.version
      )
        return;
      const changed = campaignStable(data) !== campaignStable(panel.campaign);
      panel.campaign = data;
      failures = 0;
      if (changed) {
        panel.querySelector('#schedule-batch-state').textContent = data.status;
        panel.querySelector('#schedule-live-items').innerHTML = data.items
          .map((i) => campaignScheduleProgressItem(i, data))
          .join('');
        panel.querySelector('#schedule-live-stage').textContent =
          data.repair ||
          'Saved stage: ' +
            data.status +
            '. ' +
            data.items.map((i) => i.effective_status || i.status).join(', ') +
            '. Provider status and app outcomes remain separate.';
      }
    } catch {
      failures++;
      if (valid())
        panel.querySelector('#schedule-live-stage').textContent =
          'Saved stage refresh failed. Existing work continues; refresh receipts before any retry.';
    } finally {
      inflight = false;
      again(Math.min(60000, 5000 * 2 ** Math.min(failures, 4)));
    }
  };
  again(5000);
  return () => {
    stopped = true;
    clearTimeout(timer);
  };
}

function campaignScheduleNextStep(item) {
  switch (item.effective_status) {
    case 'VERIFIED':
      return 'Post verified. Review the provider receipt and collect results.';
    case 'ACTIVE_VERIFIED':
      return 'Campaign verified active. Review monitoring and results.';
    case 'PAUSED_VERIFIED':
      return 'Campaign verified paused. Review the saved receipt.';
    case 'NEEDS_RECONCILIATION':
      return 'Check the provider receipt before retrying. The original action may have gone through.';
    case 'BLOCKED':
      return 'Review the campaign approval and saved receipts before scheduling again.';
    case 'CANCELLED':
      return 'This item is cancelled. Review a new schedule if you still want to run it.';
    default:
      return '';
  }
}
function campaignScheduleProgressItem(item, data) {
  const request = data.summary?.items?.find((r) => r.item_id === item.item_id)?.request || {},
    intent = item.intent || {},
    ids =
      intent.remote_id ||
      Object.entries(intent.ids || {})
        .map(([k, v]) => k + ': ' + v)
        .join(', ') ||
      'Not confirmed';
  const budget =
    item.operation === 'campaign.ad-launch'
      ? '<p>Approved budget ' +
        esc(request.lifetime_budget_minor) +
        ' minor ' +
        esc(intent.currency || 'units') +
        ' · retained commitment ' +
        esc(intent.commitment ?? 'Not reserved') +
        '</p>'
      : '';
  const nextStep = campaignScheduleNextStep(item);
  return (
    '<section class="panel"><h3>' +
    esc(item.operation || 'campaign.publish') +
    ' · ' +
    esc(item.effective_status || item.status) +
    '</h3><p>Due ' +
    esc(item.due_at) +
    ' · worker ' +
    esc(item.job_status || 'Not queued') +
    ' · intent ' +
    esc(intent.status || 'Not confirmed') +
    '</p><p>Provider IDs: ' +
    esc(ids) +
    '</p>' +
    budget +
    (nextStep ? '<p>' + esc(nextStep) + '</p>' : '') +
    '</section>'
  );
}
function campaignScheduleReport(data) {
  const report = WMMPageReports.model(state);
  report.title = 'Scheduled campaign batch';
  report.purpose = 'Inspect saved schedule states and provider identities.';
  report.metrics = [
    {
      label: 'Scheduled items',
      value: data.evidence_unavailable ? null : data.items.length,
      unit: 'count',
      source: 'Current owner schedule status',
    },
    {
      label: 'Verified post receipts',
      value: data.evidence_unavailable
        ? null
        : data.items.filter((i) => i.effective_status === 'VERIFIED').length,
      unit: 'count',
      source: 'Saved campaign intents',
    },
  ];
  report.notes = [
    'Schedule report uses saved local receipts; provider status may have changed.',
    'No post text, credentials or rights prose in this report. Saved receipts do not establish app growth.',
    ...(data.repair ? [data.repair] : []),
    ...data.items.map((item) => {
      const nextStep = campaignScheduleNextStep(item);
      return campaignScheduleReportLine(item, data) + (nextStep ? '. ' + nextStep : '');
    }),
  ];
  return report;
}
function campaignScheduleReportLine(item, data) {
  const request = data.summary?.items?.find((r) => r.item_id === item.item_id)?.request || {},
    intent = item.intent || {};
  const ids = Object.entries(intent.ids || {})
    .filter(
      ([k, v]) => ['campaign', 'adset', 'creative', 'ad'].includes(k) && /^[0-9]{1,40}$/.test(v),
    )
    .map(([k, v]) => k + ': ' + v);
  if (/^[0-9]{1,40}_[0-9]{1,40}$/.test(intent.remote_id || '')) ids.push(intent.remote_id);
  const status = /^[A-Z_]{1,40}$/.test(item.effective_status || '')
      ? item.effective_status
      : 'UNCONFIRMED',
    due = Number.isFinite(Date.parse(item.due_at))
      ? new Date(item.due_at).toISOString()
      : 'Unknown';
  const paid = item.operation === 'campaign.ad-launch',
    amount = Number.isSafeInteger(request.lifetime_budget_minor)
      ? request.lifetime_budget_minor
      : 'Unknown',
    held = Number.isSafeInteger(intent.commitment) ? intent.commitment : 'Not reserved',
    currency = /^[A-Z]{3}$/.test(intent.currency || '') ? intent.currency : 'units';
  return (
    (paid ? 'campaign.ad-launch' : 'campaign.publish') +
    ' · ' +
    due +
    ' · ' +
    status +
    ' · IDs ' +
    (ids.join(', ') || 'Unconfirmed') +
    (paid ? ' · approved ' + amount + ' minor ' + currency + ' · retained ' + held : '')
  );
}
async function campaignScheduleAction(node) {
  const action = node.dataset.action;
  if (action === 'campaign-schedule-open') return campaignScheduleOpen();
  if (action === 'campaign-schedule-paid-open') return campaignSchedulePaidOpen();
  if (action === 'campaign-schedule-status')
    return campaignScheduleStatus(node.dataset.batch, node);
  const panel = $('#campaign-schedule-review') || $('#campaign-schedule-progress');
  if (!panel || panel.dataset.busy === 'true') return;
  campaignBound(panel);
  panel.dataset.busy = 'true';
  node.disabled = true;
  try {
    const app = state.app,
      data = panel.campaign;
    if (action === 'campaign-schedule-report')
      return WMMPageReports.openReport(campaignScheduleReport(data), window);
    if (action === 'campaign-schedule-activate') {
      await api('/api/apps/' + app + '/campaigns/schedule-activate', {
        batch_id: data.summary.batch_id,
        summary_hash: data.summary_hash,
      });
      campaignBound(panel);
      return campaignScheduleStatus(data.summary.batch_id, panel);
    }
    if (action === 'campaign-schedule-off') {
      await api('/api/apps/' + app + '/campaigns/schedule-off', {
        batch_id: data.id,
        version: data.version,
      });
      campaignBound(panel);
      return campaignScheduleStatus(data.id, panel);
    }
  } catch (e) {
    if (panel.isConnected) panel.querySelector('#campaign-error').textContent = e.message;
  } finally {
    panel.dataset.busy = 'false';
    node.disabled = false;
  }
}

export {
  campaignPanel,
  campaignStable,
  campaignHash,
  campaignBound,
  campaignExpiryUI,
  campaignOpen,
  campaignReviewMarkup,
  campaignSubmit,
  campaignStatus,
  campaignAction,
  campaignWatch,
  campaignReport,
  campaignScheduleItems,
  campaignVerifiedPosts,
  campaignPaidScheduleItem,
  campaignSchedulePaidOpen,
  campaignScheduleOpen,
  campaignScheduleSubmit,
  campaignScheduleReviewItem,
  campaignScheduleStatus,
  campaignScheduleWatch,
  campaignScheduleProgressItem,
  campaignScheduleReport,
  campaignScheduleReportLine,
  campaignScheduleAction,
};
