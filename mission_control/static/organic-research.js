/* Operational owner research; collectors keep separately scoped CLI/MCP access. */
(function (root, factory) {
  const value = factory(
    root.WMMDiscoveryModel ||
      (typeof require === 'function' ? require('./discovery-model.js') : null),
  );
  if (typeof module === 'object' && module.exports) module.exports = value;
  else root.WMMOrganicResearch = value;
})(globalThis, function (m) {
  'use strict';
  const HOSTS = {
    tiktok: ['tiktok.com', 'www.tiktok.com'],
    facebook: ['facebook.com', 'www.facebook.com'],
    instagram: ['instagram.com', 'www.instagram.com'],
    youtube: ['youtube.com', 'www.youtube.com'],
    linkedin: ['linkedin.com', 'www.linkedin.com'],
  };
  const CHANNEL_NAMES = {
    facebook: 'Facebook Page',
    instagram: 'Instagram Reels',
    tiktok: 'TikTok',
    youtube: 'YouTube Shorts',
    linkedin: 'LinkedIn',
  };
  // Platform marks from Simple Icons, pinned 4bfa9da744e2c06928047314ce30dc5c8d1ad759; names identify channels.
  const CHANNEL_ICONS = {
    linkedin:
      'M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.049c.476-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 1 1 0-4.124 2.062 2.062 0 0 1 0 4.124zM7.119 20.452H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0z',
    facebook:
      'M9.101 23.691v-7.98H6.627v-3.667h2.474v-1.58c0-4.085 1.848-5.978 5.858-5.978.401 0 .955.042 1.468.103a8.68 8.68 0 0 1 1.141.195v3.325a8.623 8.623 0 0 0-.653-.036 26.805 26.805 0 0 0-.733-.009c-.707 0-1.259.096-1.675.309a1.686 1.686 0 0 0-.679.622c-.258.42-.374.995-.374 1.752v1.297h3.919l-.386 2.103-.287 1.564h-3.246v8.245C19.396 23.238 24 18.179 24 12.044c0-6.627-5.373-12-12-12s-12 5.373-12 12c0 5.628 3.874 10.35 9.101 11.647Z',
    instagram:
      'M7.0301.084c-1.2768.0602-2.1487.264-2.911.5634-.7888.3075-1.4575.72-2.1228 1.3877-.6652.6677-1.075 1.3368-1.3802 2.127-.2954.7638-.4956 1.6365-.552 2.914-.0564 1.2775-.0689 1.6882-.0626 4.947.0062 3.2586.0206 3.6671.0825 4.9473.061 1.2765.264 2.1482.5635 2.9107.308.7889.72 1.4573 1.388 2.1228.6679.6655 1.3365 1.0743 2.1285 1.38.7632.295 1.6361.4961 2.9134.552 1.2773.056 1.6884.069 4.9462.0627 3.2578-.0062 3.668-.0207 4.9478-.0814 1.28-.0607 2.147-.2652 2.9098-.5633.7889-.3086 1.4578-.72 2.1228-1.3881.665-.6682 1.0745-1.3378 1.3795-2.1284.2957-.7632.4966-1.636.552-2.9124.056-1.2809.0692-1.6898.063-4.948-.0063-3.2583-.021-3.6668-.0817-4.9465-.0607-1.2797-.264-2.1487-.5633-2.9117-.3084-.7889-.72-1.4568-1.3876-2.1228C21.2982 1.33 20.628.9208 19.8378.6165 19.074.321 18.2017.1197 16.9244.0645 15.6471.0093 15.236-.005 11.977.0014 8.718.0076 8.31.0215 7.0301.0839m.1402 21.6932c-1.17-.0509-1.8053-.2453-2.2287-.408-.5606-.216-.96-.4771-1.3819-.895-.422-.4178-.6811-.8186-.9-1.378-.1644-.4234-.3624-1.058-.4171-2.228-.0595-1.2645-.072-1.6442-.079-4.848-.007-3.2037.0053-3.583.0607-4.848.05-1.169.2456-1.805.408-2.2282.216-.5613.4762-.96.895-1.3816.4188-.4217.8184-.6814 1.3783-.9003.423-.1651 1.0575-.3614 2.227-.4171 1.2655-.06 1.6447-.072 4.848-.079 3.2033-.007 3.5835.005 4.8495.0608 1.169.0508 1.8053.2445 2.228.408.5608.216.96.4754 1.3816.895.4217.4194.6816.8176.9005 1.3787.1653.4217.3617 1.056.4169 2.2263.0602 1.2655.0739 1.645.0796 4.848.0058 3.203-.0055 3.5834-.061 4.848-.051 1.17-.245 1.8055-.408 2.2294-.216.5604-.4763.96-.8954 1.3814-.419.4215-.8181.6811-1.3783.9-.4224.1649-1.0577.3617-2.2262.4174-1.2656.0595-1.6448.072-4.8493.079-3.2045.007-3.5825-.006-4.848-.0608M16.953 5.5864A1.44 1.44 0 1 0 18.39 4.144a1.44 1.44 0 0 0-1.437 1.4424M5.8385 12.012c.0067 3.4032 2.7706 6.1557 6.173 6.1493 3.4026-.0065 6.157-2.7701 6.1506-6.1733-.0065-3.4032-2.771-6.1565-6.174-6.1498-3.403.0067-6.156 2.771-6.1496 6.1738M8 12.0077a4 4 0 1 1 4.008 3.9921A3.9996 3.9996 0 0 1 8 12.0077',
    tiktok:
      'M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.15 1.07-.14 1.61.24 1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03-.01-8.05.02-12.07z',
    youtube:
      'M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z',
  };
  const CHANNEL_COLORS = {
    facebook: '0866FF',
    instagram: 'E4405F',
    tiktok: '111111',
    youtube: 'FF0000',
    linkedin: '0A66C2',
  };
  const channelLogo = (key) =>
    `<svg class="channel-logo" aria-hidden="true" focusable="false" width="20" height="20" viewBox="0 0 24 24" fill="#${CHANNEL_COLORS[key]}"><path d="${CHANNEL_ICONS[key]}"></path></svg>`;
  const channelMarks = () =>
    `<ul class="toolbar channel-marks" role="list" aria-label="Video channels">${Object.keys(
      CHANNEL_NAMES,
    )
      .map((key) => `<li class="tag">${channelLogo(key)}${m.esc(CHANNEL_NAMES[key])}</li>`)
      .join('')}</ul>`;
  const RESEARCH_REQUEST_TIMEOUT_MS = 30000,
    RESEARCH_PENDING_LIMIT = 25,
    RESEARCH_MAX_CARD_TEXT = 4000;
  let active = null;
  const pending = new Map();
  const member = (s) =>
    s.workspace?.access?.members?.find((r) => r.principal === s.workspace?.identity?.principal);
  const owner = (s) => member(s)?.role === 'OWNER' && member(s)?.status === 'ACTIVE';
  const scope = (s) => ({
    app: s.app,
    version: s.workspace?.app?.version,
    principal: s.workspace?.identity?.principal,
    role: member(s)?.role,
    roleVersion: member(s)?.version,
    roleStatus: member(s)?.status,
    session: s.boot?.csrf,
  });
  const current = (t) =>
    active === t && t.node.open && m.equal(t.scope, scope(t.d.state)) && owner(t.d.state);
  const label = (s) =>
    String(s ?? '')
      .replaceAll('_', ' ')
      .toLowerCase();
  const button = (text, action, id = '', primary = false) =>
    `<button type="button" class="button ${primary ? '' : 'outline'}" data-action="oresearch-${action}" data-id="${m.esc(id)}">${m.esc(text)}</button>`;
  const field = (name, title, value = '', type = 'text', extra = '') =>
    `<label class="field" for="oresearch-${name}">${m.esc(title)}<input id="oresearch-${name}" name="${name}" type="${type}" value="${m.esc(value)}" ${extra}></label>`;
  const area = (name, title, value = '', limit = RESEARCH_MAX_CARD_TEXT) =>
    `<label class="field" for="oresearch-${name}">${m.esc(title)}<textarea id="oresearch-${name}" name="${name}" maxlength="${limit}" required>${m.esc(value)}</textarea></label>`;
  const select = (name, title, values) =>
    `<label class="field" for="oresearch-${name}">${m.esc(title)}<select id="oresearch-${name}" name="${name}">${values.map(([value, text]) => `<option value="${m.esc(value)}">${m.esc(text)}</option>`).join('')}</select></label>`;
  const check = (name, title, value = 'on', icon = '') =>
    `<label class="check-row"><input type="checkbox" name="${name}" value="${m.esc(value)}"> ${icon}${m.esc(title)}</label>`;
  function clear() {
    active = null;
  }
  function invalidate(state) {
    if (active && !m.equal(active.scope, scope(state))) {
      const node = active.node;
      clear();
      node.close();
      node.querySelector('#modal-body').replaceChildren();
    }
  }
  function entry() {
    return `<section class="panel" aria-label="Five video channels"><h2>Five video channels</h2>${channelMarks()}<p>Research Facebook Page videos, Instagram Reels, TikTok, YouTube Shorts and LinkedIn. Turn a useful reference into creative for your app, then check delivery options by channel.</p><button class="button outline" data-action="research-channel-open">Explore video channels</button></section>`;
  }
  function panel() {
    return `<section class="panel" aria-label="Agent video research"><p class="eyebrow">FROM ATTENTION TO AN APP EXPERIMENT</p><h2>Give your agent a focused video search</h2>${channelMarks()}<p>Choose Facebook Page videos, Instagram Reels, TikTok, YouTube Shorts or LinkedIn, with an audience and research limits. Your connected agent returns source observations; you inspect the hook, confirm app relevance and save the next experiment.</p>${button('Find viral ideas for my app', 'open', '', true)}<p>Viral-only requires 100,000 views AND 10× a documented creator baseline. Your own UGC stays available through the media library without that cutoff. Research approval grants no reuse or publication rights.</p><p><strong>Delivery today:</strong> Facebook Page has governed Reel delivery. Instagram Reels, TikTok, YouTube Shorts and LinkedIn use their own connected accounts and exact publication review. A local Hypit render needs no social connection.</p></section>`;
  }
  function show(d, title, kind, html, data = null, captured = null) {
    const savedScope = captured || scope(d.state);
    d.modal(
      title,
      `<div class="modal-content organic-research-workspace" tabindex="-1">${html}<p id="oresearch-progress" role="status" aria-live="polite"></p><p id="oresearch-error" class="field-error" role="alert"></p><div id="oresearch-recovery"></div></div>`,
      'AGENT VIDEO RESEARCH',
    );
    active = {
      d,
      node: d.document.querySelector('#modal'),
      scope: savedScope,
      kind,
      data,
      busy: false,
    };
    active.node.querySelector('.organic-research-workspace').focus({ preventScroll: true });
    return active;
  }
  function busy(t, value, message = '') {
    t.busy = value;
    if (!current(t)) return;
    t.node.querySelector('.organic-research-workspace').setAttribute('aria-busy', String(value));
    if (message) t.node.querySelector('#oresearch-progress').textContent = message;
    t.node.querySelectorAll('button,input,textarea,select').forEach((n) => (n.disabled = value));
  }
  function fail(t, e) {
    if (current(t))
      t.node.querySelector('#oresearch-error').textContent =
        e.message + ' Your saved work is preserved.';
  }
  function validation(node, d, invalid = false) {
    const t = active;
    if (!t || !current(t) || !node.closest('form[id^="oresearch-"]')) return;
    if (invalid) {
      node.setAttribute('aria-invalid', 'true');
      t.node.querySelector('#oresearch-error').textContent =
        (node.labels?.[0]?.textContent.trim() || 'Research field') + ': ' + node.validationMessage;
    } else if (node.validity?.valid) {
      node.removeAttribute('aria-invalid');
      if (!t.node.querySelector('[aria-invalid="true"]'))
        t.node.querySelector('#oresearch-error').textContent = '';
    }
  }
  async function hash(value, browser = globalThis) {
    return Array.from(
      new Uint8Array(
        await browser.crypto.subtle.digest('SHA-256', new TextEncoder().encode(m.stable(value))),
      ),
      (b) => b.toString(16).padStart(2, '0'),
    ).join('');
  }
  async function request(t, action, body) {
    const allowed = [
      'task-list',
      'task-read',
      'prepare',
      'intake',
      'policy-context',
      'policy-history',
      'policy-read',
      'policy-admit',
      'workflow-prepare',
      'policy-reserve',
      'render-status',
      'render-queue',
      'intent-create',
      'intent-reconcile',
      'schedule-prepare',
      'schedule-status',
      'schedule-activate',
      'schedule-revoke',
    ];
    if (!allowed.includes(action)) throw new Error('Unsupported research action.');
    const controller = new AbortController(),
      timer = setTimeout(() => controller.abort(), RESEARCH_REQUEST_TIMEOUT_MS);
    let response, value;
    try {
      response = await (t.d.fetch || t.d.browser.fetch.bind(t.d.browser))(
        '/api/apps/' + encodeURIComponent(t.scope.app) + '/organic-video/' + action,
        {
          method: 'POST',
          credentials: 'same-origin',
          redirect: 'error',
          headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': t.d.state.boot.csrf },
          body: JSON.stringify(body),
          signal: controller.signal,
        },
      );
      value = await response.json();
    } catch (cause) {
      const e = new Error(
        'The local research response was not received. Inspect the saved request before sending it again.',
      );
      e.uncertain = true;
      throw e;
    } finally {
      clearTimeout(timer);
    }
    if (!response.ok) {
      const e = new Error(value.error || 'Research request rejected.');
      e.uncertain = response.status >= 500;
      throw e;
    }
    return value;
  }
  const retained = (t) => [...pending.values()].filter((r) => m.equal(r.scope, t.scope));
  function recovery(t) {
    if (current(t))
      t.node.querySelector('#oresearch-recovery').innerHTML = retained(t)
        .map(
          (r) =>
            `<section class="notice"><p>Save outcome unknown. Keep this exact request until inspected.</p>${button('Inspect saved request', 'inspect', r.body.request_id)}${button('Retry this identical save', 'retry', r.body.request_id)}</section>`,
        )
        .join('');
  }
  function taskHistoryRow(row) {
    const found = row.candidate_count || 0;
    const toReview = row.reviewable_count || 0;
    const summary = found
      ? `${found} clip${found === 1 ? '' : 's'} found · ${toReview} meet reported thresholds`
      : 'No clips returned yet';
    return `<section class="next-step"><div><h4>${m.esc(row.query.genre)}</h4><p>${m.esc(row.query.search_terms)}</p><p>${m.esc(label(row.status))} · saved ${m.esc(row.created)}</p><p><strong>${summary}</strong></p><p>${row.intakes.length} approved research cards</p>${button(found ? 'Review found videos' : 'Inspect search', 'read', row.id)}</div></section>`;
  }
  async function open(d, offset = 0) {
    if (!owner(d.state))
      throw new Error('Sign in as this app owner to assign or approve research.');
    const t = show(
      d,
      'Your agent research',
      'history',
      '<p>Reading saved tasks for this app and owner.</p>',
    );
    busy(t, true, 'Loading research history');
    try {
      const page = await request(t, 'task-list', { offset, request_id: null });
      if (!current(t)) return;
      const html = `<p>Start with a clear marketing question. Your agent gathers permitted public evidence; you decide which idea deserves an original app creative.</p>${button('Assign a new search', 'new', '', true)}<h3>Saved research tasks</h3><p>Open a search with clips to review their source evidence and choose what to process.</p>${button('Refresh results', 'page', String(offset))}${page.items.map(taskHistoryRow).join('') || '<p>No research task is saved for this app and owner. Assign a search to an agent with research access. You can review permitted sources manually in the saved-source research workspace.</p>'}<div class="button-row">${offset ? button('First tasks', 'page', '0') : ''}${page.next_offset !== null ? button('More tasks', 'page', String(page.next_offset)) : ''}</div>`;
      const next = show(d, 'Your agent research', 'history', html, page, t.scope);
      recovery(next);
    } catch (e) {
      fail(t, e);
    } finally {
      busy(t, false);
    }
  }
  function eligible(grant, s, at = Date.now()) {
    return (
      owner(s) &&
      grant.status === 'ACTIVE' &&
      grant.owner === s.workspace.identity.principal &&
      grant.owner_version === member(s)?.version &&
      grant.app_id === s.app &&
      grant.app_version === s.workspace.app.version &&
      Date.parse(grant.expires) > at &&
      grant.used < grant.max_calls &&
      ['organic-video.claim', 'organic-video.submit'].every((op) => grant.operations.includes(op))
    );
  }
  async function assignment(t) {
    if (retained(t).length)
      throw new Error('Inspect the uncertain save before assigning another search.');
    busy(t, true, 'Reading your existing agent grants');
    try {
      const result = await t.d.api(
        '/api/apps/' + encodeURIComponent(t.scope.app) + '/agent-grants/list',
        {},
      );
      if (!current(t)) return;
      const grants = result.grants.filter((g) => eligible(g, t.d.state));
      if (!grants.length) {
        show(
          t.d,
          'Connect an agent for research',
          'empty',
          `<p>No current owner-issued grant can both claim and submit video research. Open Agent permissions, choose this app and enable those two research operations for your connected agent. Its external browsing/API access is configured in that agent.</p><button class="button" type="button" data-action="control-grants">Open agent permissions</button>${button('Back to research', 'open')}`,
          null,
          t.scope,
        );
        return;
      }
      const app = t.d.state.workspace.app.data;
      const html = `<p>This assigns metadata research to an existing agent. It creates no credential, downloads no video and publishes nothing. The agent's own permitted source access is required.</p><form id="oresearch-task-form"><div class="form-grid">${select(
        'grant',
        'Connected research agent',
        grants.map((g) => [
          g.id,
          g.agent_id + ' · ' + (g.max_calls - g.used) + ' grant calls left',
        ]),
      )}${field('genre', 'Genre or audience problem', app.job || '', 'text', 'required maxlength="120"')}${field('app_type', 'App type', app.category || '', 'text', 'required maxlength="120"')}${field('search_terms', 'Search terms', '', 'text', 'required maxlength="500"')}</div><fieldset><legend>Platforms to research</legend>${Object.keys(
        CHANNEL_NAMES,
      )
        .map((p) => check('platform', CHANNEL_NAMES[p], p, channelLogo(p)))
        .join('')}</fieldset><div class="form-grid">${select('access', 'Permitted source access', [
        ['PUBLIC_WEB', 'Public web'],
        ['OWNER_AUTHORIZED_PLATFORM', 'Owner-authorized platform session'],
        ['PERMITTED_API', 'Permitted platform API'],
      ])}${field('minutes', 'Task expires after minutes', 30, 'number', 'required min="1" max="1440"')}${field('max_candidates', 'Maximum candidates', 5, 'number', 'required min="1" max="20"')}${field('max_reads', 'Maximum source reads', 100, 'number', 'required min="1" max="500"')}${field('max_seconds', 'Maximum collection seconds', 600, 'number', 'required min="1" max="3600"')}</div><p>Submit the direct link and its post ID or shortcode. Host scope is limited to the selected platforms' public domains. YouTube collection reads public Shorts metadata only; exact /shorts/video-id URLs and comparable creator Shorts evidence are required. Publishing uses a separate account connection and approval. Task expiry is shortened to the selected grant's expiry. WMM does not delegate its stored credentials to the collector.</p><button type="submit" class="button">Review search assignment</button></form>${button('Back to research', 'open')}`;
      show(t.d, 'Give your agent a focused search', 'assignment', html, { grants }, t.scope);
    } catch (e) {
      fail(t, e);
    } finally {
      busy(t, false);
    }
  }
  function taskBody(fd, grants, state, uuid, at = Date.now()) {
    const grant = grants.find((g) => g.id === fd.get('grant'));
    if (!grant || !eligible(grant, state, at))
      throw new Error('Select a current research agent grant.');
    const platforms = fd.getAll('platform');
    if (
      !platforms.length ||
      new Set(platforms).size !== platforms.length ||
      platforms.some((p) => !HOSTS[p])
    )
      throw new Error('Select at least one supported research platform.');
    const access = fd.get('access');
    if (!['PUBLIC_WEB', 'OWNER_AUTHORIZED_PLATFORM', 'PERMITTED_API'].includes(access))
      throw new Error('Choose permitted source access.');
    const expires = new Date(
      Math.min(
        at + m.integer(fd.get('minutes'), 'Expiry minutes', 1, 1440) * 60000,
        Date.parse(grant.expires),
      ),
    ).toISOString();
    return {
      request_id: uuid(),
      query: {
        genre: m.text(fd.get('genre'), 'Genre', 120),
        app_type: m.text(fd.get('app_type'), 'App type', 120),
        search_terms: m.text(fd.get('search_terms'), 'Search terms', 500),
      },
      policy: {
        recipient_grant_id: grant.id,
        platforms,
        hosts: platforms.flatMap((p) => HOSTS[p]).sort(),
        expires,
        max_candidates: m.integer(fd.get('max_candidates'), 'Candidates', 1, 20),
        max_reads: m.integer(fd.get('max_reads'), 'Source reads', 1, 500),
        max_seconds: m.integer(fd.get('max_seconds'), 'Collection seconds', 1, 3600),
        access,
      },
    };
  }
  function counts(saved) {
    const rows = saved.result?.items || [];
    return {
      observed_candidates: saved.submission?.candidates?.length || 0,
      qualified_by_reported_counts: rows.filter(
        (r) => r.qualification?.qualification === 'QUALIFIED_BY_REPORTED_COUNTS',
      ).length,
      baseline_missing: rows.filter(
        (r) => r.qualification?.qualification === 'INSUFFICIENT_BASELINE',
      ).length,
      reuse_rights_not_established: rows.filter((r) => r.reuse_permission !== 'APPROVED').length,
      ugc_review: rows.filter((r) => r.status === 'UGC_OWNER_REVIEW_REQUIRED').length,
      failed_sources: saved.result?.source_failures?.length || 0,
    };
  }
  function safeURL(url) {
    try {
      const u = new URL(url);
      return (!HOSTS.youtube.includes(u.hostname) ||
        (/^\/shorts\/[A-Za-z0-9_-]{11}$/.test(u.pathname) && !u.search && !u.hash)) &&
        u.protocol === 'https:' &&
        Object.values(HOSTS).flat().includes(u.hostname) &&
        !u.username &&
        !u.password &&
        (!u.port || u.port === '443')
        ? u.href
        : null;
    } catch (e) {
      return null;
    }
  }
  function adoptable(saved, row, entry, state) {
    return (
      owner(state) &&
      ['SUBMITTED', 'INCOMPLETE'].includes(saved.status) &&
      saved.task.app.version === state.workspace.app.version &&
      row.status === 'COLLECTION_REVIEW_REQUIRED' &&
      entry.candidate?.post_id === row.candidate_id &&
      !saved.intakes.some(
        (x) => x.data.provenance.candidate_hash === row.qualification.candidate_hash,
      ) &&
      entry.kind === 'REFERENCE'
    );
  }
  function coverageRows(saved) {
    return Object.entries(saved.channel_coverage || {}).map(
      ([platform, { candidates, failures, status }]) => {
        if (status === 'NOT_REPORTED')
          return `${CHANNEL_NAMES[platform] || platform} � No result reported � ask your agent to finish this channel`;
        if (status === 'NOT_RUN') return `${CHANNEL_NAMES[platform] || platform} � Search not run`;
        if (status === 'REPORTED_EMPTY')
          return `${CHANNEL_NAMES[platform] || platform} � Search reported no candidates`;
        const outcome = candidates
          ? `${candidates} candidate${candidates === 1 ? '' : 's'} reported`
          : 'No candidates reported';
        return `${CHANNEL_NAMES[platform] || platform} · ${outcome}${failures ? ` · ${failures} source check${failures === 1 ? '' : 's'} failed` : ''}`;
      },
    );
  }
  function selectionSummary(entry, qualification) {
    const q = qualification;
    const fit =
      {
        MATCH: 'The collector marked it relevant to the app search.',
        UNCERTAIN: 'The collector could not confirm the app fit.',
        NO_MATCH: 'The collector did not find a clear app fit.',
      }[entry.relevance] || 'App fit needs review.';
    if (q.qualification === 'UGC_EXEMPT')
      return 'Included as UGC, which is exempt from viral thresholds. ' + fit;
    if (q.qualification === 'QUALIFIED_BY_REPORTED_COUNTS') {
      const median = q.median?.numerator / q.median?.denominator;
      const multiple =
        Number.isFinite(median) && median > 0 ? entry.candidate.views / median : null;
      const evidence = Number.isFinite(multiple)
        ? ` It reached ${multiple.toFixed(2)}× the reported creator median.`
        : '';
      return (
        fit +
        ' Reported views met both viral thresholds.' +
        evidence +
        ' Check the source before approval.'
      );
    }
    if (q.qualification === 'INSUFFICIENT_BASELINE')
      return (
        fit +
        ' Kept as a candidate; there are not enough comparable posts to verify the creator baseline.'
      );
    return fit + ' Kept as a candidate; it has not met the viral qualification checks.';
  }
  function taskHTML(saved, state) {
    const c = counts(saved),
      policy = saved.task.policy;
    const cards = (saved.result?.items || [])
      .map((row, index) => {
        const entry = saved.submission.candidates[index],
          obs = entry.candidate,
          url = safeURL(obs.url),
          q = row.qualification;
        return `<article class="panel"><h3>${m.esc(obs.creator_id)} · ${m.esc(label(obs.platform))}</h3><p>${url ? `<a href="${m.esc(url)}" target="_blank" rel="noopener noreferrer">Inspect original source</a>` : 'Source link unavailable'}</p><p>Observed views: ${m.esc(obs.views ?? 'Unavailable')} · observed ${m.esc(obs.observed_at)} · Post ID ${m.esc(obs.post_id)}</p><p>Qualification: ${m.esc(label(q.qualification))} · comparable baseline posts: ${m.esc(q.baseline_count ?? 'Not required for UGC')}</p><p><strong>Why it was selected:</strong> ${m.esc(selectionSummary(entry, q))}</p><p>App relevance: ${m.esc(label(entry.relevance))} · collector's rights claim: ${m.esc(label(entry.rights))}. Reuse permission remains unestablished.</p><p>${m.esc((q.reasons || []).map(label).join('; '))}</p>${adoptable(saved, row, entry, state) ? button('Review this research idea', 'adopt', q.candidate_hash) : '<p>Keep as a candidate until the reported evidence, app relevance and current review requirements are satisfied. Bring owned UGC through the media library.</p>'}</article>`;
      })
      .join('');
    return `<p><strong>${m.esc(label(saved.status))}</strong> · ${m.esc(saved.task.query.genre)} · ${m.esc(saved.task.query.app_type)}</p><p>Search: ${m.esc(saved.task.query.search_terms)}</p><p>${m.esc(policy.platforms.join(', '))} · access ${m.esc(label(policy.access))} · expires ${m.esc(policy.expires)}</p><p>Limits: ${policy.max_candidates} candidates, ${policy.max_reads} source reads, ${policy.max_seconds} collection seconds. Collector access is externally configured and not independently verified by this receipt.</p><dl>${Object.entries(
      c,
    )
      .map(([k, v]) => `<dt>${m.esc(label(k))}</dt><dd>${v}</dd>`)
      .join(
        '',
      )}</dl>${saved.status === 'READY' ? '<p>Your agent can now claim this exact task through its existing scoped CLI/MCP grant. No collection has run yet.</p>' : ''}${saved.status === 'CLAIMED' ? `<p>The agent has claimed this task until ${m.esc(saved.claim_until)}. Refresh for its submitted evidence.</p>` : ''}${
      coverageRows(saved).length
        ? `<h3>Channel coverage</h3><ul>${coverageRows(saved)
            .map((row) => `<li>${m.esc(row)}</li>`)
            .join('')}</ul>`
        : ''
    }${cards}<h3>Source failures</h3>${(saved.result?.source_failures || []).map((f) => `<p>${m.esc(f.source)} · ${m.esc(label(f.code))}</p>`).join('') || '<p>No source failures recorded. A ready task with no submission has no collection coverage.</p>'}<h3>Saved research approvals</h3>${saved.intakes.map((r) => `<p>Research card saved: ${m.esc(r.id)}. Source ${m.esc(r.data.source.id)} · collection ${m.esc(r.data.collection.id)}. </p>${saved.task.app.version === state.workspace.app.version ? button('Prepare original brief', 'brief', r.id) : '<p>This card belongs to an earlier app version. Start a fresh search to use current app proof.</p>'}${button('Plan or inspect a local render', 'render-start', r.id) + button('Render a local Hypit video', 'hypit-local', r.id)}`).join('') || '<p>No research candidate adopted yet.</p>'}<p>Research approval creates a source card and proposed experiment. It grants no foreign-media reuse, production execution, publication or measured app sales.</p><div class="button-row">${button('Refresh saved task', 'read', saved.id)}${button('Report / Save PDF', 'pdf')}${button('Download report JSON', 'json')}${button('Back to tasks', 'open')}</div>`;
  }
  function details(t, saved) {
    const next = show(
      t.d,
      'Review agent research',
      'detail',
      taskHTML(saved, t.d.state),
      saved,
      t.scope,
    );
    recovery(next);
    return next;
  }
  async function prepareBrief(t, id) {
    const intake = t.data.intakes.find((item) => item.id === id);
    if (!intake || t.data.task.app.version !== t.scope.version)
      throw new Error('Use a research card from the current app version.');
    const { review, collection, source, analysis } = intake.data;
    const base = '/api/apps/' + encodeURIComponent(t.scope.app) + '/discovery/read';
    busy(t, true, 'Checking the saved research and app proof');
    try {
      const checked = await t.d.api(
        base,
        { kind: 'REVIEW', id: review.id },
        { signal: AbortSignal.timeout(RESEARCH_REQUEST_TIMEOUT_MS) },
      );
      if (!current(t)) return;
      if (
        checked.hash !== review.hash ||
        checked.version !== review.version ||
        !checked.currentness.current_app_context ||
        checked.data.reference_id !== source.id ||
        checked.data.source_hash !== source.hash
      )
        throw new Error(
          'The source review changed. Inspect current research before preparing a brief.',
        );
      await t.d.refresh();
      if (!current(t)) return;
      t.d.openResearchBrief({
        analysis_id: analysis.id,
        analysis_hash: analysis.hash,
        channel: 'SHORT_VIDEO',
        asset_ids: checked.data.review.card.authentic_evidence_ids,
        objective: checked.data.review.card.next_experiment,
        discovery: {
          schema: 'wmm.brief-discovery.v1',
          mode: 'ORIGINAL_RECREATION',
          manifest_version: t.scope.version,
          collection_id: collection.id,
          collection_hash: collection.hash,
          reference_id: source.id,
          review_hash: review.hash,
        },
      });
    } finally {
      busy(t, false);
    }
  }
  async function localHypit(t, id) {
    const intake = t.data.intakes.find((item) => item.id === id);
    if (!intake || t.data.task.app.version !== t.scope.version)
      throw new Error('Use a research card from the current app version.');
    busy(t, true, 'Finding the current brief for this reference');
    try {
      await t.d.refresh();
    } finally {
      busy(t, false);
    }
    if (!current(t)) return;
    const briefIds = (t.d.state.workspace.briefs || [])
      .filter(
        (b) =>
          b.evidence_status === 'CURRENT' &&
          b.current.data.discovery?.collection_provenance?.intake_id === intake.id,
      )
      .map((b) => b.id);
    if (!briefIds.length) return prepareBrief(t, id);
    return t.d.openResearchHypit(briefIds);
  }
  const renderKey = (t, id) =>
    'wmm-local-render:' + JSON.stringify([t.scope.app, t.scope.principal, id]);
  function renderRecord(t, intake) {
    try {
      return JSON.parse(t.d.browser.sessionStorage.getItem(renderKey(t, intake.id)));
    } catch {
      return null;
    }
  }
  function storeRender(t, record) {
    // Keep exact retry identities and clip positions in this tab. Never persist session credentials.
    t.d.browser.sessionStorage.setItem(renderKey(t, record.intake.id), JSON.stringify(record));
  }
  async function renderStart(t, id, offset = 0) {
    const saved = t.kind === 'detail' ? t.data : t.data.saved;
    const intake = saved.intakes.find((item) => item.id === id);
    if (!intake) throw new Error('Select a saved research card.');
    const record = renderRecord(t, intake);
    if (record && t.kind === 'detail') return inspectRender(t, record, saved);
    if (saved.task.app.version !== t.scope.version)
      throw new Error('Use a research card from the current app version.');
    busy(t, true, 'Finding compatible briefs and production approvals');
    try {
      const page = await request(t, 'policy-history', { offset, request_id: null });
      if (!current(t)) return;
      const briefs = (t.d.state.workspace.briefs || []).filter(
        (b) =>
          b.evidence_status === 'CURRENT' &&
          b.current.data.discovery?.collection_provenance?.intake_id === intake.id,
      );
      const policies = page.items.filter(
        (p) =>
          !p.revoked &&
          !p.expired &&
          p.app_current &&
          p.owner_current &&
          p.remaining.generations > 0,
      );
      const choices = [];
      for (const brief of briefs) {
        const claims = brief.current.data.records.filter((r) => r.kind === 'claim');
        for (const policy of policies) {
          const rules = policy.snapshot.policy;
          if (!claims.every((c) => rules.claims.some((r) => r.id === c.id && r.sha256 === c.hash)))
            continue;
          for (const template of rules.templates) {
            if (
              template.claim_ids.length !== claims.length ||
              !claims.every((c) => template.claim_ids.includes(c.id))
            )
              continue;
            choices.push({ brief, policy, template });
          }
        }
      }
      const rows = choices
        .map(
          ({ brief, policy, template }, index) =>
            `<section class="next-step"><h3>${m.esc(brief.current.data.definition.objective)}</h3><p>Page ${m.esc(policy.snapshot.policy.page_id)} · ${policy.remaining.generations} local slots remaining</p><p>${m.esc(template.caption)}</p>${button('Use this brief and caption', 'render-policy', String(index))}</section>`,
        )
        .join('');
      const next =
        page.next_offset !== null
          ? button('More saved approvals', 'render-page', String(page.next_offset))
          : '';
      show(
        t.d,
        'Choose an approved local render',
        'render-choices',
        `<p>Choose a brief and an exact caption from your saved production approvals. Then place the approved clips in the scenes you want to use.</p>${rows || '<p>No compatible brief and approval on this page. Save a current brief and choose its exact claims in Video production approvals.</p>'}${next}${button('Back to research card', 'render-back')}`,
        { saved, intake, choices },
        t.scope,
      );
    } finally {
      busy(t, false);
    }
  }
  async function renderForm(t, index) {
    const choice = t.data.choices[index];
    if (!choice) throw new Error('Choose a current brief and caption.');
    busy(t, true, 'Checking rights-reviewed clips');
    try {
      const context = await request(t, 'policy-context', {});
      if (!current(t)) return;
      const { brief, policy, template } = choice;
      const approved = policy.snapshot.policy.sources;
      const clips = context.eligible.sources.filter((c) =>
        approved.some(
          (s) => s.id === c.id && s.sha256 === c.sha256 && s.review_version === c.review_version,
        ),
      );
      if (!clips.length)
        throw new Error(
          'Review the source clip rights and approve the current clip versions before rendering.',
        );
      const beats = brief.current.data.content.beats;
      const options = [['', 'Text only'], ...clips.map((c) => [c.id, c.title || c.id])];
      const sceneFields = beats
        .map(
          (beat, i) =>
            `<fieldset><legend>Scene ${i + 1}</legend><p>${m.esc(beat.script)}</p>${select('clip-' + i, 'Approved clip for scene ' + (i + 1), options)}${field('frame-' + i, 'Clip start frame at 24 fps', '0', 'number', 'min="0" max="4319" step="1" required')}</fieldset>`,
        )
        .join('');
      show(
        t.d,
        'Place your approved clips',
        'render-form',
        `<p>Use at least one clip. Other scenes keep the brief’s original text. All clip audio is muted.</p><form id="oresearch-render-form">${select(
          'shape',
          'Output shape',
          [
            ['PORTRAIT', 'Portrait'],
            ['LANDSCAPE', 'Landscape'],
          ],
        )}${sceneFields}<button type="submit" class="button">Review this local render</button></form>${button('Back to research card', 'render-back')}`,
        { saved: t.data.saved, intake: t.data.intake, choice, clips },
        t.scope,
      );
    } finally {
      busy(t, false);
    }
  }
  async function reviewRender(t, form) {
    const { saved, intake, choice, clips } = t.data,
      { brief, policy, template } = choice;
    const fd = new t.d.FormData(form),
      footage = [];
    for (const [i] of brief.current.data.content.beats.entries()) {
      const id = fd.get('clip-' + i);
      if (!id) continue;
      const clip = clips.find((c) => c.id === id);
      if (!clip) throw new Error('Select a currently approved clip.');
      footage.push({
        scene_index: i,
        id,
        sha256: clip.sha256,
        in_frame: m.integer(fd.get('frame-' + i), 'Clip start frame', 0, 4319),
        audio: 'MUTE',
      });
    }
    if (!footage.length) throw new Error('Add at least one approved clip to a scene.');
    const input = {
      brief_id: brief.id,
      brief_hash: brief.current.hash,
      shape: fd.get('shape'),
      footage,
    };
    const body = {
      request_id: t.d.uuid(),
      intake_id: intake.id,
      intake_hash: intake.hash,
      policy_id: policy.id,
      policy_hash: policy.hash,
      template_id: template.id,
      render_input: input,
    };
    busy(t, true, 'Validating the exact brief, clips and approval');
    try {
      const plan = await request(t, 'workflow-prepare', body);
      const op = plan.data?.next_operation;
      const reserve = {
        policy_id: policy.id,
        policy_hash: policy.hash,
        request_id: body.request_id,
        template_id: template.id,
        render_input: input,
      };
      if (
        plan.hash !== (await hash(plan.data, t.d.browser)) ||
        plan.data.state !== 'READY_FOR_SEPARATE_RESERVATION' ||
        plan.data.intake_hash !== intake.hash ||
        op?.app_id !== t.scope.app ||
        op.operation !== 'organic-video.policy-reserve' ||
        !m.equal(op.input, reserve)
      )
        throw new Error('The render review receipt differs from your exact choices.');
      if (!current(t)) return;
      const preflight = await t.d.api(
        '/api/apps/' + encodeURIComponent(t.scope.app) + '/production/hypit-plan',
        { data: input },
        { signal: AbortSignal.timeout(RESEARCH_REQUEST_TIMEOUT_MS) },
      );
      if (preflight.input_hash !== plan.data.inputs_hash)
        throw new Error('The local production plan changed. Review the current inputs again.');
      if (preflight.readiness.remediation.length)
        throw new Error(preflight.readiness.remediation.join(' '));
      const lookup = {
        policy_id: policy.id,
        policy_hash: policy.hash,
        request_id: body.request_id,
        request_hash: await hash(reserve, t.d.browser),
      };
      if (!current(t)) return;
      const rows = footage
        .map(
          (f) =>
            `<li>Scene ${f.scene_index + 1} · ${m.esc(clips.find((c) => c.id === f.id).title || f.id)} · starts at frame ${f.in_frame} · muted</li>`,
        )
        .join('');
      const record = {
        intake: { id: intake.id, hash: intake.hash },
        version: t.scope.version,
        lookup,
        reserve,
        inputs_hash: plan.data.inputs_hash,
      };
      const scene = preflight.scene;
      show(
        t.d,
        'Review this exact local render',
        'render-confirm',
        `<h3>${m.esc(brief.current.data.definition.objective)}</h3><p>${m.esc(template.caption)}</p><p>${scene.width} × ${scene.height} · ${scene.duration_seconds} seconds · one local render slot · zero model-service spending</p><ul>${rows}</ul><p>Hypit checks its compiler and browser when you start the render. Publication requires its own approval.</p><div class="button-row">${button('Reserve this local render', 'render-reserve', '', true)}${button('Back to research card', 'render-back')}</div>`,
        { saved, record },
        t.scope,
      );
    } finally {
      busy(t, false);
    }
  }
  async function inspectRender(t, record, saved) {
    busy(t, true, 'Inspecting the saved reservation and render job');
    try {
      const result = await request(t, 'render-status', record.lookup);
      if (!current(t)) return;
      const reservation = result.reservation,
        job = result.job;
      if (
        reservation &&
        (reservation.hash !== (await hash(reservation.data, t.d.browser)) ||
          reservation.data.inputs_hash !== record.inputs_hash ||
          reservation.data.policy_hash !== record.lookup.policy_hash ||
          reservation.data.policy_id !== record.lookup.policy_id ||
          reservation.data.template_id !== record.reserve.template_id ||
          !m.equal(reservation.data.render_input, record.reserve.render_input))
      )
        throw new Error('Saved reservation differs from this reviewed render.');
      if (!current(t)) return;
      const mayWrite = record.version === t.scope.version;
      const summary = job
        ? `<p>Local render ${m.esc(label(job.status))}. Job ${m.esc(job.id)}.</p>`
        : reservation
          ? '<p>One slot is reserved. A render job has not been recorded.</p>'
          : '<p>No reservation was observed for this exact request.</p>';
      const next = job
        ? job.render_id
          ? button('Preview local MP4', 'render-preview', job.render_id)
          : ''
        : mayWrite
          ? reservation
            ? button('Start the reserved Hypit render', 'render-queue', '', true)
            : button('Retry the exact reservation', 'render-reserve', '', true)
          : '';
      const admission = result.admission;
      const matched =
        admission?.request_hash === record.admission?.request_hash &&
        admission?.request_id === record.lookup.request_id;
      const receipt = admission
        ? `<p>${record.admission && !matched ? 'A different artifact approval is already saved.' : 'Artifact approval saved.'} ${admission.reserved_calls} provider calls held. Facebook delivery is a separate step.</p><details><summary>View approval receipt</summary><p>Receipt ${m.esc(admission.id)}</p><p class="app-mono">${m.esc(admission.hash)}</p></details>`
        : '';
      const approval =
        !admission && mayWrite && job?.status === 'SUCCEEDED' && job.artifact_sha256
          ? button(
              record.admission
                ? 'Review the same artifact approval'
                : 'Review video for artifact approval',
              'render-admission',
              '',
              true,
            )
          : '';
      const delivery = result.delivery
        ? button(
            result.delivery.intent ? 'Open Facebook delivery' : 'Schedule this Facebook Reel',
            'delivery-open',
            '',
            true,
          )
        : '';
      const another =
        !reservation || ['SUCCEEDED', 'FAILED', 'CANCELLED'].includes(job?.status)
          ? button('Choose another render', 'render-new', record.intake.id)
          : '';
      show(
        t.d,
        'Local render status',
        'render-status',
        `${summary}${receipt}<div class="button-row">${delivery}${approval}${next}${button('Refresh render status', 'render-inspect')}${another}${button('Back to research card', 'render-back')}</div>`,
        { saved, record, reservation, job, admission, available: result.available },
        t.scope,
      );
    } finally {
      busy(t, false);
    }
  }
  async function writeRender(t, mode) {
    const { record, saved, reservation } = t.data;
    if (!record || record.version !== t.scope.version)
      throw new Error('The app changed. Inspect the saved status before preparing a new render.');
    storeRender(t, record);
    busy(
      t,
      true,
      mode === 'render-reserve' ? 'Reserving this exact input' : 'Starting the saved local render',
    );
    try {
      if (mode === 'render-reserve') await request(t, 'policy-reserve', record.reserve);
      else
        await request(t, 'render-queue', {
          reservation_id: reservation.id,
          reservation_hash: reservation.hash,
        });
      if (current(t)) await inspectRender(t, record, saved);
    } catch (error) {
      if (current(t))
        show(
          t.d,
          'Inspect this render request',
          'render-recovery',
          `<p role="alert">${m.esc(error.message)}</p><p>Read the saved reservation and job before attempting this action again.</p>${button('Inspect saved render status', 'render-inspect', '', true)}${button('Back to research card', 'render-back')}`,
          { saved, record },
          t.scope,
        );
    } finally {
      busy(t, false);
    }
  }
  async function reviewArtifact(t) {
    const { saved, record, reservation, job, admission, available } = t.data;
    if (admission || job?.status !== 'SUCCEEDED' || record.version !== t.scope.version)
      throw new Error('Select an unapproved completed video from the current app.');
    busy(t, true, 'Checking the approval and remaining allowance');
    try {
      const policy = await request(t, 'policy-read', {
        policy_id: record.lookup.policy_id,
        policy_hash: record.lookup.policy_hash,
      });
      if (!current(t)) return;
      const rules = policy.data.policy,
        template = rules.templates.find((row) => row.id === reservation.data.template_id);
      if (
        !template ||
        policy.hash !== record.lookup.policy_hash ||
        policy.id !== record.lookup.policy_id
      )
        throw new Error('The saved caption or approval changed.');
      if (rules.mode === 'EXACT' && !rules.approved_output_hashes.includes(job.artifact_sha256))
        throw new Error(
          'This approval does not cover the completed video bytes. Use a standing-generation approval to create a new eligible render.',
        );
      if (!available || available.posts < 1 || available.calls < 1)
        throw new Error(
          'This production approval has no remaining post or provider-call allowance.',
        );
      const body = {
        policy_id: policy.id,
        policy_hash: policy.hash,
        output: {
          request_id: record.lookup.request_id,
          artifact_id: job.render_id,
          artifact_sha256: job.artifact_sha256,
          template_id: template.id,
          caption: template.caption,
          transformation: 'DECLARATIVE_COMPOSITION',
          reservation_id: reservation.id,
          reservation_hash: reservation.hash,
        },
      };
      const url =
        '/api/apps/' +
        encodeURIComponent(t.scope.app) +
        '/hypit-renders/' +
        encodeURIComponent(job.render_id);
      const fixed = record.admission;
      const html = `<form id="oresearch-artifact-form"><video class="render-preview" controls playsinline preload="metadata" src="${url}/preview" aria-label="Exact local Hypit video"></video><p id="oresearch-video-error" role="status"></p><p><a href="${url}/download" download>Download this MP4</a></p><h3>Facebook Page ${m.esc(rules.page_id)}</h3><p>${m.esc(template.caption)}</p><details><summary>Video SHA-256</summary><code>${m.esc(job.artifact_sha256)}</code></details><p>Saving approval holds one post slot and the provider calls you choose. It starts no delivery or paid campaign.</p>
        ${field('calls', 'Provider calls to hold (up to ' + available.calls + ')', fixed?.calls ?? '', 'number', `min="1" max="${available.calls}" step="1" required ${fixed ? 'readonly' : ''}`)}
        ${check('previewed', 'I reviewed this exact video and caption.')}<button type="submit" class="button">Save artifact approval</button></form>${button('Back to render status', 'render-inspect')}`;
      const next = show(
        t.d,
        'Review your finished video',
        'artifact-review',
        html,
        { saved, record, body, available },
        t.scope,
      );
      next.node.querySelector('video').addEventListener('error', () => {
        if (current(next))
          next.node.querySelector('#oresearch-video-error').textContent =
            'If this preview cannot play, open the downloaded MP4 before approving.';
      });
    } finally {
      busy(t, false);
    }
  }
  async function approveArtifact(t, form) {
    const { record, saved, body, available } = t.data,
      fd = new t.d.FormData(form);
    if (fd.get('previewed') !== 'on')
      throw new Error('Confirm you reviewed this exact video and caption.');
    const calls = m.integer(fd.get('calls'), 'Provider calls to hold', 1, available.calls);
    const approved = { ...body, output: { ...body.output, reserve_calls: calls } };
    busy(t, true, 'Saving the approval for this exact output');
    try {
      const requestHash = await hash(approved, t.d.browser);
      if (!current(t)) return;
      if (record.admission && record.admission.request_hash !== requestHash)
        throw new Error('This is a different approval request. Inspect the saved outcome.');
      record.admission = { request_hash: requestHash, calls };
      storeRender(t, record);
      await request(t, 'policy-admit', approved);
      if (current(t)) await inspectRender(t, record, saved);
    } catch (error) {
      if (current(t))
        show(
          t.d,
          'Inspect this render request',
          'render-recovery',
          `<p role="alert">${m.esc(error.message)}</p><p>Inspect the saved artifact approval before retrying.</p>${button('Inspect saved render status', 'render-inspect', '', true)}`,
          { saved, record },
          t.scope,
        );
    } finally {
      busy(t, false);
    }
  }
  const displayTime = (value) => new Date(value).toLocaleString();
  function deliveryStage(intent) {
    if (!intent) return '<p>Delivery has not been prepared.</p>';
    return `<dl><dt>Provider stage</dt><dd>${m.esc(label(intent.stage))}</dd><dt>Remote video ID</dt><dd>${m.esc(intent.remote_id || 'None recorded')}</dd><dt>Call allowance used</dt><dd>${intent.calls_used}</dd><dt>Last recorded update</dt><dd>${m.esc(displayTime(intent.updated))}</dd></dl>`;
  }
  async function openDelivery(t) {
    const { saved, record } = t.data;
    busy(t, true, 'Reading the exact approval and delivery history');
    try {
      const source = await request(t, 'render-status', record.lookup);
      if (!current(t)) return;
      const delivery = source.delivery,
        approval = source.admission;
      if (!delivery || !approval)
        throw new Error('Approve the finished artifact before planning delivery.');
      const data = { saved, record, delivery, approval };
      if (delivery.schedule_id) return await showSchedule(t, data, delivery.schedule_id);
      const identity = delivery.intent;
      const canDraft =
        (!identity || identity.stage === 'NEW') &&
        Date.parse(delivery.expires_at) > Date.now() &&
        record.version === t.scope.version;
      const form = canDraft
        ? `<form id="oresearch-schedule-form">${field('due', 'Post once at this local time', '', 'datetime-local', 'required')}<p>Approval expires ${m.esc(displayTime(delivery.expires_at))}. Saving this draft starts no delivery.</p><button class="button" type="submit">Save draft schedule</button></form>`
        : '';
      const repair =
        identity?.recovery_required && identity.remote_id
          ? button('Check the existing video on Facebook', 'delivery-reconcile')
          : '';
      show(
        t.d,
        'Plan one Facebook Reel',
        'delivery-plan',
        `<h3>Facebook Page ${m.esc(delivery.draft.page_id)}</h3><p>${m.esc(delivery.draft.caption)}</p>${deliveryStage(identity)}${form || '<p>Inspect the recorded stage or use a current approved artifact for a new delivery.</p>'}${repair}${button('Back to render status', 'render-inspect')}`,
        data,
        t.scope,
      );
    } finally {
      busy(t, false);
    }
  }
  async function showSchedule(t, data, id) {
    const value = await request(t, 'schedule-status', { batch_id: id });
    const summary = value.summary;
    if (
      value.id !== id ||
      summary.app_id !== t.scope.app ||
      summary.scope_hash !== data.record.lookup.policy_hash ||
      summary.kind !== 'ADMITTED_ORGANIC_VIDEO_V1' ||
      value.summary_hash !== (await hash(summary, t.d.browser)) ||
      !value.items.some((item) => item.intent.request.admission_id === data.approval.id)
    )
      throw new Error('The saved schedule differs from this approved video.');
    if (!current(t)) return;
    const controls =
      value.status === 'DRAFT'
        ? button('Activate this exact schedule', 'delivery-activate', '', true)
        : '';
    const stop = ['DRAFT', 'ACTIVE'].includes(value.status)
      ? button('Turn this schedule off', 'delivery-off')
      : '';
    const phases = value.items
      .map((item) => {
        const phase = item.phase_checks,
          observation = phase.observation;
        const next =
          phase.effective_state === 'WAITING' && observation?.next_due
            ? displayTime(observation.next_due * 1000)
            : 'None scheduled';
        const jobs = phase.jobs
          .map((job) => `<li>${m.esc(label(job.status))} · ${m.esc(job.id)}</li>`)
          .join('');
        const recover =
          item.intent.recovery_required && item.intent.remote_id
            ? button('Check the existing video on Facebook', 'delivery-reconcile', item.intent.id)
            : '';
        return `<section class="next-step"><div><h3>Due ${m.esc(displayTime(item.due_at))}</h3><p>${m.esc(item.intent.request.caption)}</p><p>Provider ${m.esc(label(item.intent.stage))} · phase checks ${m.esc(label(phase.effective_state))} · next check ${m.esc(next)}.</p><details><summary>Exact video and worker receipts</summary><p>UTC ${m.esc(item.due_at)} · ${m.esc(label(item.status))}</p><p>Video SHA-256 <code>${m.esc(item.intent.request.artifact_sha256)}</code></p>${deliveryStage(item.intent)}${observation ? `<p>${m.esc(observation.reason)}</p>` : ''}<ul>${jobs || '<li>No job recorded.</li>'}</ul></details>${recover}</div></section>`;
      })
      .join('');
    const monitoring = summary.monitoring;
    const followup = monitoring
      ? `Up to ${monitoring.max_followup_jobs} phase checks per video, every ${monitoring.interval_seconds} seconds, within its approved allowance.`
      : 'Follow-up checks were not included in this schedule.';
    show(
      t.d,
      'Facebook Reel schedule',
      'delivery-status',
      `<h3>${m.esc(label(value.status))} · Facebook Page ${m.esc(data.delivery.draft.page_id)}</h3><p>Selected video: ${data.approval.reserved_calls} reserved call units. ${followup}</p>${phases}<details><summary>Exact schedule</summary><p>Approval expires ${m.esc(displayTime(data.delivery.expires_at))}</p><p>Schedule SHA-256 <code>${m.esc(value.summary_hash)}</code></p></details><p>Provider phases describe processing. Public visibility and app outcomes need their own evidence. Turning off cancels queued work and stops future dispatch. A request already in flight can finish. Published posts stay on Facebook.</p><div class="button-row">${controls}${stop}${button('Refresh schedule status', 'delivery-open')}${button('Download schedule receipt', 'delivery-json')}${button('Report / Save PDF', 'delivery-pdf')}${button('Back to render status', 'render-inspect')}</div>`,
      { ...data, schedule: value },
      t.scope,
    );
  }
  async function changeDelivery(t, mode, { due, intentId } = {}) {
    const { delivery, record, schedule } = t.data;
    busy(t, true, 'Applying the reviewed delivery step');
    try {
      if (mode === 'draft') {
        const intent = delivery.intent || (await request(t, 'intent-create', delivery.draft));
        if (!current(t)) return;
        if (
          intent.stage !== 'NEW' ||
          !m.equal(intent.request, { ...delivery.draft, request_id: intent.request.request_id })
        )
          throw new Error('The retained delivery differs from the exact approved Reel.');
        await request(t, 'schedule-prepare', {
          policy_id: record.lookup.policy_id,
          policy_hash: record.lookup.policy_hash,
          items: [{ intent_id: intent.id, due_at: due }],
        });
      } else if (mode === 'activate') {
        await request(t, 'schedule-activate', {
          batch_id: schedule.id,
          summary_hash: schedule.summary_hash,
        });
      } else if (mode === 'off') {
        await request(t, 'schedule-revoke', { batch_id: schedule.id, version: schedule.version });
      } else {
        const intent = schedule
          ? schedule.items.find((row) => row.intent.id === intentId)?.intent
          : delivery.intent;
        if (!intent?.remote_id || !intent.recovery_required)
          throw new Error('No known Facebook video is ready for recovery.');
        await request(t, 'intent-reconcile', { intent_id: intent.id });
      }
      if (current(t)) await openDelivery(t);
    } catch (error) {
      if (current(t))
        show(
          t.d,
          'Inspect Facebook delivery',
          'delivery-recovery',
          `<p role="alert">${m.esc(error.message)}</p><p>Read the saved intent and schedule before choosing another action.</p>${button('Inspect saved Facebook delivery', 'delivery-open', '', true)}${button('Back to render status', 'render-inspect')}`,
          t.data,
          t.scope,
        );
    } finally {
      busy(t, false);
    }
  }
  function deliveryReport(t) {
    const value = t.data.schedule;
    return {
      schema: 'wmm.reel-schedule-report.v1',
      title: 'Facebook Reel schedule',
      app_id: t.scope.app,
      app_name: t.d.state.workspace.app.data.name,
      scope: 'SELECTED_APP',
      manifest_version: t.scope.version,
      generated_at: new Date().toISOString(),
      loaded_at: new Date().toISOString(),
      purpose: 'Review the scheduled Reel and saved provider observations.',
      next_step: 'Inspect the latest worker receipt and verify public visibility separately.',
      filters: { schedule_id: value.id, state: value.status, summary_hash: value.summary_hash },
      metrics: [
        {
          label: 'Selected video reserved call units',
          value: t.data.approval.reserved_calls,
          unit: 'count',
          source: 'Exact artifact approval',
        },
      ],
      cohorts: value.items.map((row) => ({
        id: row.intent.id,
        status: row.intent.stage,
        horizon: row.due_at,
        currency: 'NOT_APPLICABLE',
        provider_calls_used: row.intent.calls_used,
        remote_video_id: row.intent.remote_id,
        public_visibility: row.intent.public_visibility,
        phase_check_state: row.phase_checks.effective_state,
        phase_note: row.phase_checks.observation?.reason ?? null,
        next_check:
          row.phase_checks.effective_state === 'WAITING' && row.phase_checks.observation?.next_due
            ? new Date(row.phase_checks.observation.next_due * 1000).toISOString()
            : null,
        worker_receipts:
          row.phase_checks.jobs.map((job) => job.id + ' · ' + job.status).join(', ') ||
          'None recorded',
      })),
      notes: [
        'Scheduled delivery and provider processing do not establish public visibility or app outcomes.',
      ],
      schedule: value,
    };
  }
  async function read(t, id) {
    busy(t, true, 'Reading retained task and evidence');
    try {
      const saved = await request(t, 'task-read', { task_id: id });
      if (current(t)) details(t, saved);
    } catch (e) {
      fail(t, e);
    } finally {
      busy(t, false);
    }
  }
  async function adoption(t, id) {
    if (retained(t).length)
      throw new Error('Inspect the uncertain save before adopting another source.');
    const saved = t.data,
      index = saved.result.items.findIndex((x) => x.qualification.candidate_hash === id);
    const row = saved.result.items[index],
      entry = saved.submission.candidates[index];
    if (!row || !entry || !adoptable(saved, row, entry, t.d.state))
      throw new Error('This candidate is not eligible for current research adoption.');
    let contract;
    busy(t, true, 'Reading the current research field contract');
    try {
      contract =
        t.d.state.workspace.agent_operations ||
        (await t.d.api('/api/apps/' + encodeURIComponent(t.scope.app) + '/agent-operations'));
    } finally {
      busy(t, false);
    }
    if (!current(t)) return;
    const c = contract.local_catalog?.domain_contracts?.discovery_research;
    if (!c) throw new Error('Reload the workspace to read the research taxonomy.');
    const assets = (t.d.state.workspace.records || []).filter((r) => r.kind === 'asset');
    const html = `<p>Inspect the permitted original source first. Describe what you observed and how an original creative will demonstrate your app. Counts remain collector-reported; source approval does not authorize copying or publishing.</p><form id="oresearch-adopt-form"><div class="form-grid">${field('title', 'Source title', '', 'text', 'required maxlength="200"')}${select(
      'industry',
      'Industry',
      c.industries.map((x) => [x, label(x)]),
    )}${select(
      'narrative',
      'Story or narrative',
      c.narratives.map((x) => [x, label(x)]),
    )}${select(
      'treatment',
      'Production treatment',
      c.treatments.map((x) => [x, label(x)]),
    )}${field('duration', 'Inspected duration in seconds', 30, 'number', 'required min="1" max="3600"')}${field('hook_end', 'Opening hook ends at second', 3, 'number', 'required min="1" max="3600"')}</div>${area('hook', 'What happens in the opening hook?', '', 2000)}${area('mechanism', 'Your interpretation: why does it attract attention?')}${area('rationale', 'Why does this fit your app and audience?')}${area('requirements', 'What must your original creative reproduce? One requirement per line.', '', 2000)}<fieldset><legend>Authentic app proof used in your original creative</legend>${assets.map((r) => check('evidence', r.title || r.data?.title || r.id, r.id)).join('') || '<p>Add an authentic app evidence asset in the Evidence screen, then reopen this review.</p>'}</fieldset>${area('experiment', 'Proposed next app-marketing experiment')}${area('uncertainty', 'What is uncertain about your inspection?', 'Public counters do not establish installs, sales or causal lift.', 2000)}${check('inspected', 'I directly inspected this permitted source and have permission to save its public reference metadata.')}<button type="submit" class="button">Review research approval</button></form>${button('Back to source results', 'read', saved.id)}`;
    return show(
      t.d,
      'Turn this source into an app experiment',
      'adoption',
      html,
      { saved, row, entry },
      t.scope,
    );
  }
  async function adoptionBody(fd, t) {
    const { saved, row, entry } = t.data,
      state = t.d.state;
    if (!adoptable(saved, row, entry, state) || fd.get('inspected') !== 'on')
      throw new Error('Confirm direct inspection and permission before approving research.');
    const evidence = fd.getAll('evidence'),
      available = (state.workspace.records || [])
        .filter((r) => r.kind === 'asset')
        .map((r) => r.id);
    if (
      !evidence.length ||
      new Set(evidence).size !== evidence.length ||
      evidence.some((id) => !available.includes(id))
    )
      throw new Error('Select authentic app evidence from this workspace.');
    const duration = m.integer(fd.get('duration'), 'Inspected duration', 1, 3600),
      end = m.integer(fd.get('hook_end'), 'Hook end', 1, duration),
      hook = m.text(fd.get('hook'), 'Observed hook', 2000);
    const rationale = m.text(fd.get('rationale'), 'App relevance', 2000),
      mechanism = m.text(fd.get('mechanism'), 'Interpretation'),
      experiment = m.text(fd.get('experiment'), 'Next experiment');
    const requirements = m.list(fd.get('requirements'), 'Reproduction requirements');
    if (!requirements.length || requirements.some((x) => x.length > 1000))
      throw new Error('Describe at least one reproduction requirement within 1,000 characters.');
    const candidateHash = await hash(entry.candidate, t.d.browser);
    if (candidateHash !== row.qualification.candidate_hash)
      throw new Error('Candidate evidence changed. Refresh and review again.');
    const stamp = new Date().toISOString(),
      obs = entry.candidate,
      published = Date.parse(obs.published_at);
    const taxonomy = {
      original_labels: [obs.format],
      industry: fd.get('industry'),
      narrative: fd.get('narrative'),
      treatment: fd.get('treatment'),
      classified_by: 'HUMAN_SUPPLIED',
      rationale,
    };
    return {
      request_id: t.d.uuid(),
      task_id: saved.id,
      task_hash: saved.task_hash,
      submission_hash: saved.submission_hash,
      result_hash: saved.result_hash,
      candidate_id: row.candidate_id,
      candidate_hash: candidateHash,
      source_metadata: {
        title: m.text(fd.get('title'), 'Source title', 200),
        locale: m.text(state.workspace.app.data.locale, 'App locale; update app setup first', 120),
        traffic_class: 'UNKNOWN',
        topic: saved.task.query.genre,
        relevance_note: rationale,
        permission_confirmed: true,
      },
      review: {
        taxonomy,
        duration_ms: duration * 1000,
        transcript: null,
        metrics: null,
        card: {
          observed_hook: hook,
          observed_beats: [{ start_ms: 0, end_ms: end * 1000, text: hook }],
          interpreted_mechanism: mechanism,
          relevance_rationale: rationale,
          reproduction_requirements: requirements,
          authentic_evidence_ids: evidence,
          rights_status: 'REFERENCE_ONLY',
          rights_evidence: 'Public reference metadata only; reuse is not approved.',
          next_experiment: experiment,
        },
      },
      analysis: {
        inspection_kind: 'DIRECT_VIEW',
        inspection_confirmed: true,
        inspected_at: stamp,
        analyst: state.workspace.identity.principal,
        format_family: obs.format,
        duration_seconds: duration,
        observations: [
          {
            role: 'HOOK',
            basis: 'OBSERVED',
            detail: hook,
            evidence_note: rationale,
            start_seconds: 0,
            end_seconds: end,
          },
        ],
        uncertainty: m.text(fd.get('uncertainty'), 'Inspection uncertainty', 2000),
      },
      query: {
        outcome: state.workspace.app.data.job || saved.task.query.genre,
        audience: state.workspace.app.data.audience || saved.task.query.app_type,
        industries: [],
        narratives: [],
        treatments: [],
        published_after: new Date(published - 1).toISOString(),
        published_before: stamp,
        freshness_seconds: 86400,
        minimum_views: 100000,
        baseline_required: true,
        viral_only: true,
        ranking: 'REACH',
      },
    };
  }
  function reviewWrite(t, action, body) {
    const html =
      action === 'prepare'
        ? `<p>Assign this exact search to your selected agent. The agent receives metadata-read authority only.</p><dl>${Object.entries(
            body.query,
          )
            .map(([k, v]) => `<dt>${m.esc(label(k))}</dt><dd>${m.esc(v)}</dd>`)
            .join(
              '',
            )}</dl><p>Platforms: ${m.esc(body.policy.platforms.join(', '))}. Hosts: ${m.esc(body.policy.hosts.join(', '))}.</p><p>Access: ${m.esc(label(body.policy.access))}. Expires ${m.esc(body.policy.expires)}. At most ${body.policy.max_candidates} candidates, ${body.policy.max_reads} reads and ${body.policy.max_seconds} seconds.</p>`
        : `<p>Save a research card for ${m.esc(body.source_metadata.title)}.</p><p>Observed hook: ${m.esc(body.review.card.observed_hook)}</p><p>App relevance: ${m.esc(body.review.card.relevance_rationale)}</p><p>Next experiment: ${m.esc(body.review.card.next_experiment)}</p><dl>${Object.entries(
            body.review.taxonomy,
          )
            .filter(([k]) => k !== 'original_labels')
            .map(([k, v]) => `<dt>${m.esc(label(k))}</dt><dd>${m.esc(v)}</dd>`)
            .join(
              '',
            )}<dt>Inspected duration</dt><dd>${body.analysis.duration_seconds} seconds</dd><dt>Interpretation</dt><dd>${m.esc(body.review.card.interpreted_mechanism)}</dd><dt>Reproduction requirements</dt><dd>${m.esc(body.review.card.reproduction_requirements.join('; '))}</dd><dt>Inspection uncertainty</dt><dd>${m.esc(body.analysis.uncertainty)}</dd></dl><p>Authentic app evidence: ${m.esc(body.review.card.authentic_evidence_ids.join(', '))}. Rights remain reference-only. No production or publication is approved.</p><details><summary>Inspect all exact saved inputs</summary><pre>${m.esc(JSON.stringify(body, null, 2))}</pre></details>`;
    return show(
      t.d,
      action === 'prepare' ? 'Review the search assignment' : 'Review this research approval',
      'confirm',
      html +
        button(
          action === 'prepare' ? 'Assign this exact search' : 'Approve this research card',
          'confirm',
          '',
          true,
        ) +
        button('Cancel and return to tasks', 'open'),
      { action, body },
      t.scope,
    );
  }
  async function write(t, r) {
    if (!current(t) || !m.equal(r.scope, t.scope)) return;
    busy(t, true, 'Saving the exact reviewed request');
    let acknowledged = false;
    try {
      const saved = await request(t, r.action, r.body);
      acknowledged = true;
      const detail = await request(t, 'task-read', {
          task_id: r.action === 'prepare' ? saved.id : r.body.task_id,
        }),
        expected = await hash(r.body, t.d.browser);
      const exact =
        r.action === 'prepare'
          ? detail.request_id === r.body.request_id && detail.request_hash === expected
          : detail.intakes.some(
              (x) => x.request_id === r.body.request_id && x.request_hash === expected,
            );
      if (!exact) {
        const e = new Error(
          'The save receipt differs from the exact request. Inspect saved history.',
        );
        e.uncertain = true;
        throw e;
      }
      if (!current(t)) return;
      pending.delete(r.body.request_id);
      details(t, detail);
    } catch (e) {
      if (!e.uncertain && !acknowledged) pending.delete(r.body.request_id);
      if (acknowledged)
        e.message = 'The save was acknowledged, but exact readback is not confirmed. ' + e.message;
      fail(t, e);
      recovery(t);
    } finally {
      busy(t, false);
    }
  }
  async function inspect(t, r) {
    busy(t, true, 'Inspecting saved request identity without a retry');
    try {
      const expected = await hash(r.body, t.d.browser);
      let saved;
      if (r.action === 'prepare') {
        const page = await request(t, 'task-list', { offset: 0, request_id: r.body.request_id });
        saved = page.items.find(
          (x) => x.request_id === r.body.request_id && x.request_hash === expected,
        );
        if (saved) {
          const detail = await request(t, 'task-read', { task_id: saved.id });
          if (current(t)) {
            pending.delete(r.body.request_id);
            details(t, detail);
          }
          return;
        }
      } else {
        const detail = await request(t, 'task-read', { task_id: r.body.task_id });
        saved = detail.intakes.find(
          (x) => x.request_id === r.body.request_id && x.request_hash === expected,
        );
        if (saved) {
          if (current(t)) {
            pending.delete(r.body.request_id);
            details(t, detail);
          }
          return;
        }
      }
      throw new Error(
        'No matching saved request was observed. Keep this uncertainty, or explicitly retry the identical request.',
      );
    } catch (e) {
      fail(t, e);
    } finally {
      busy(t, false);
    }
  }
  async function submit(form, d) {
    const t = active;
    if (!t || !current(t) || t.busy) return;
    try {
      if (t.kind === 'render-form') return await reviewRender(t, form);
      if (t.kind === 'artifact-review') return await approveArtifact(t, form);
      if (t.kind === 'delivery-plan') {
        const due = new Date(new d.FormData(form).get('due'));
        if (
          !Number.isFinite(due.getTime()) ||
          due.getTime() <= Date.now() ||
          due.getTime() >= Date.parse(t.data.delivery.expires_at)
        )
          throw new Error('Choose a future time before the approval expires.');
        return await changeDelivery(t, 'draft', { due: due.toISOString() });
      }
      if (retained(t).length) throw new Error('Inspect the uncertain save before another request.');
      if (t.kind === 'assignment')
        return reviewWrite(
          t,
          'prepare',
          taskBody(new d.FormData(form), t.data.grants, d.state, d.uuid),
        );
      if (t.kind === 'adoption') {
        const fields = new d.FormData(form);
        busy(t, true, 'Binding your review to the saved candidate');
        const body = await adoptionBody(fields, t);
        if (current(t)) return reviewWrite(t, 'intake', body);
      }
    } catch (e) {
      fail(t, e);
    } finally {
      busy(t, false);
    }
  }
  function reportedRows(saved) {
    const candidates = (saved.result?.items || []).map((row, index) => {
      const entry = saved.submission.candidates[index],
        source = entry.candidate,
        q = row.qualification;
      return {
        id: source.platform + '/' + row.candidate_id,
        status: row.status,
        horizon: source.observed_at,
        currency: 'NOT_APPLICABLE',
        source_url: safeURL(source.url) || 'Unavailable',
        creator: source.creator_id,
        reported_views: source.views,
        published_at: source.published_at,
        qualification: q.qualification,
        selection_summary: selectionSummary(entry, q),
        qualification_reasons: (q.reasons || []).join('; '),
        baseline_posts: q.baseline_count ?? null,
        baseline_median_numerator: q.median?.numerator ?? null,
        baseline_median_denominator: q.median?.denominator ?? null,
        required_views: q.required_views ?? null,
        relevance: entry.relevance,
        collector_rights_claim: entry.rights,
        reuse_permission: row.reuse_permission,
        publication: row.publication,
      };
    });
    const failures = (saved.result?.source_failures || []).map((row) => ({
      id: row.source,
      status: row.code,
      horizon: saved.submission?.collected_at || 'Not recorded',
      currency: 'NOT_APPLICABLE',
      kind: 'SOURCE_READ_FAILURE',
    }));
    return [...candidates, ...failures];
  }
  function report(saved, state) {
    return {
      schema: 'wmm.organic-research-report.v1',
      title: 'Agent video research',
      app_id: state.app,
      app_name: state.workspace.app.data.name,
      scope: 'SELECTED_APP',
      manifest_version: saved.task.app.version,
      generated_at: new Date().toISOString(),
      loaded_at: saved.submission?.collected_at || 'No collection observed',
      purpose: 'Inspect reported viral evidence, missing inputs and saved research decisions.',
      next_step:
        'Review current source evidence and authentic app proof before preparing original creative.',
      filters: saved.task.query,
      metrics: Object.entries(counts(saved)).map(([name, value]) => ({
        label: label(name),
        value,
        unit: 'count',
        source: 'Saved research task ' + saved.id,
      })),
      cohorts: reportedRows(saved),
      notes: [
        'Task ' + saved.id + ' / ' + saved.task_hash,
        'Collection and counters are external-agent reports requiring inspection.',
        ...coverageRows(saved),
        'Viral eligibility requires 100,000 views AND 10 times a documented comparable creator baseline.',
        'Research approval grants no media reuse, production, publication, app sales or causal-lift claim.',
        ...saved.intakes.map((r) => 'Saved research intake ' + r.id + ' / ' + r.hash),
      ],
    };
  }
  function download(t) {
    const value = report(t.data, t.d.state),
      blob = new t.d.browser.Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }),
      url = t.d.browser.URL.createObjectURL(blob);
    try {
      const a = t.d.document.createElement('a');
      a.href = url;
      a.download = t.scope.app + '-agent-research.json';
      a.click();
    } finally {
      t.d.browser.URL.revokeObjectURL(url);
    }
  }
  async function action(node, d) {
    const mode = node.dataset.action.slice('oresearch-'.length);
    if (mode === 'open') {
      if (!owner(d.state)) {
        d.toast('Sign in as this app owner to assign or approve research.');
        return;
      }
      return open(d);
    }
    const t = active;
    if (!t || !current(t) || t.busy) return;
    try {
      if (mode === 'new') return assignment(t);
      if (mode === 'page') return open(d, m.integer(node.dataset.id, 'History offset', 0, 100000));
      if (mode === 'read') return read(t, node.dataset.id);
      if (mode === 'adopt') return await adoption(t, node.dataset.id);
      if (mode === 'brief' && t.kind === 'detail') return await prepareBrief(t, node.dataset.id);
      if (mode === 'hypit-local' && t.kind === 'detail')
        return await localHypit(t, node.dataset.id);
      if (mode === 'render-start' && t.kind === 'detail')
        return await renderStart(t, node.dataset.id);
      if (mode === 'render-page' && t.kind === 'render-choices')
        return await renderStart(
          t,
          t.data.intake.id,
          m.integer(node.dataset.id, 'Approval history offset', 0, 2000),
        );
      if (mode === 'render-policy' && t.kind === 'render-choices')
        return await renderForm(t, Number(node.dataset.id));
      if (mode === 'render-admission' && t.kind === 'render-status') return await reviewArtifact(t);
      if (mode === 'delivery-open' && t.data?.record) return await openDelivery(t);
      if (
        mode === 'delivery-activate' &&
        t.kind === 'delivery-status' &&
        t.data.schedule.status === 'DRAFT'
      )
        return await changeDelivery(t, 'activate');
      if (mode === 'delivery-off' && t.kind === 'delivery-status')
        return await changeDelivery(t, 'off');
      if (mode === 'delivery-reconcile' && ['delivery-plan', 'delivery-status'].includes(t.kind))
        return await changeDelivery(t, 'reconcile', { intentId: node.dataset.id });
      if (mode === 'delivery-pdf' && t.kind === 'delivery-status')
        return d.pageReports.openReport(deliveryReport(t), d.browser);
      if (mode === 'delivery-json' && t.kind === 'delivery-status')
        return d.download(t.scope.app + '-reel-schedule.json', deliveryReport(t));
      if (mode === 'render-back' && t.kind.startsWith('render-')) return details(t, t.data.saved);
      if (mode === 'render-inspect' && t.data?.record)
        return await inspectRender(t, t.data.record, t.data.saved);
      if (mode === 'render-new' && t.kind === 'render-status') {
        t.d.browser.sessionStorage.removeItem(renderKey(t, node.dataset.id));
        return await renderStart(t, node.dataset.id);
      }
      if (
        (mode === 'render-reserve' && ['render-confirm', 'render-status'].includes(t.kind)) ||
        (mode === 'render-queue' && t.kind === 'render-status' && t.data.reservation)
      )
        return await writeRender(t, mode);
      if (mode === 'render-preview' && t.kind === 'render-status') {
        busy(t, true, 'Opening the saved local MP4');
        try {
          await t.d.refresh();
          if (current(t)) t.d.openResearchRender(node.dataset.id);
        } finally {
          busy(t, false);
        }
        return;
      }
      if (mode === 'confirm') {
        if (t.kind !== 'confirm' || retained(t).length)
          throw new Error('Review the current exact request before confirming.');
        if (pending.size >= RESEARCH_PENDING_LIMIT)
          throw new Error('Inspect existing uncertain saves before another request.');
        const r = { scope: m.copy(t.scope), action: t.data.action, body: m.copy(t.data.body) };
        pending.set(r.body.request_id, r);
        return write(t, r);
      }
      if (mode === 'inspect' || mode === 'retry') {
        const r = pending.get(node.dataset.id);
        if (!r || !m.equal(r.scope, t.scope))
          throw new Error('No uncertain request belongs to this context.');
        return mode === 'inspect' ? inspect(t, r) : write(t, r);
      }
      if (mode === 'json' && t.kind === 'detail') return download(t);
      if (mode === 'pdf' && t.kind === 'detail')
        return d.pageReports.openReport(report(t.data, d.state), d.browser);
    } catch (e) {
      fail(t, e);
    }
  }
  return {
    owner,
    scope,
    current,
    clear,
    invalidate,
    entry,
    panel,
    open,
    action,
    submit,
    validation,
    eligible,
    taskBody,
    counts,
    safeURL,
    adoptable,
    taskHTML,
    adoptionBody,
    report,
    request,
    show,
    pending,
  };
});
