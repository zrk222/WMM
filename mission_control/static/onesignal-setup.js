/* Owner-scoped OneSignal setup. Provider changes only run after exact review. */
(function (root, factory) {
  const value = factory();
  if (typeof module === 'object' && module.exports) module.exports = value;
  else root.WMMOneSignal = value;
})(globalThis, function () {
  'use strict';
  const esc = (v) =>
    String(v ?? '').replace(
      /[&<>"']/g,
      (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
    );
  const button = (label, action, extra = '') =>
    `<button type="button" class="button outline" data-action="onesignal-${action}" ${extra}>${esc(label)}</button>`;
  const input = (name, label, type = 'text', value = '') =>
    `<label class="field">${esc(label)}<input name="${name}" type="${type}" value="${esc(value)}" autocomplete="off"></label>`;
  const stateLabels = {
    KEY_NOT_CONFIGURED: 'Save your OneSignal key',
    KEY_SAVED_UNBOUND: 'Choose your OneSignal app',
    APP_BOUND: 'Your app is connected',
    APNS_CONFIGURED_UNVERIFIED: 'Apple push settings saved; verification needed',
    FCM_CONFIGURED_UNVERIFIED: 'Android push settings saved; verification needed',
    SDK_BUILD_NOT_VERIFIED: 'SDK build not yet verified',
    DEVICE_SUBSCRIPTION_NOT_VERIFIED: 'Device subscription not yet verified',
  };
  let active = null;
  function scope(s) {
    const w = s.workspace || {},
      i = w.identity || {},
      r = (w.access?.members || []).find(
        (x) => x.principal === i.principal && x.status === 'ACTIVE',
      );
    return JSON.stringify({
      app: s.app,
      workspace: w.app?.id,
      version: w.app?.version,
      principal: i.principal,
      status: i.status,
      expires: i.expires_at_epoch,
      role: r?.role,
      roleVersion: r?.version,
      csrf: s.boot?.csrf,
    });
  }
  function clear() {
    active = null;
  }
  function invalidate(s) {
    if (active && active.scope !== scope(s)) clear();
  }
  function current(t) {
    return (
      active === t &&
      t.scope === scope(t.d.state) &&
      t.node?.isConnected &&
      t.d.document.querySelector('#modal')?.open
    );
  }
  function panel() {
    return `<section class="panel" aria-label="OneSignal setup"><p class="eyebrow">PUSH NOTIFICATIONS</p><h2>Connect OneSignal</h2><p>Find or create your app and optionally configure push channels. Review each provider change before it runs.</p>${button('Set up OneSignal', 'open')}</section>`;
  }
  function show(d, html) {
    d.modal(
      'OneSignal setup',
      `<div id="onesignal-root" class="modal-content">${html}<p id="onesignal-progress" role="status" aria-live="polite"></p><p id="onesignal-error" class="field-error" role="alert"></p></div>`,
      'PUSH NOTIFICATIONS',
    );
    const t = {
      d,
      scope: scope(d.state),
      node: d.document.querySelector('#onesignal-root'),
      pending: false,
      status: null,
      effects: [],
      apps: [],
      proposal: null,
    };
    active = t;
    return t;
  }
  const path = (t, a) => '/api/apps/' + encodeURIComponent(t.d.state.app) + '/onesignal/' + a;
  async function call(t, a, b) {
    if (!current(t)) throw Error('App or owner session changed. Reopen setup.');
    return t.d.api(path(t, a), b);
  }
  function busy(t, on, msg = '') {
    t.pending = on;
    if (current(t)) {
      t.node.setAttribute('aria-busy', String(on));
      t.node.querySelectorAll('button,input,select,textarea').forEach((x) => (x.disabled = on));
      if (msg) t.node.querySelector('#onesignal-progress').textContent = msg;
    }
  }
  function error(t, e) {
    if (current(t))
      t.node.querySelector('#onesignal-error').textContent =
        e.message +
        ' No request was repeated. Refresh status and inspect history before trying again.';
  }
  function view(t) {
    const s = t.status || {},
      unknown = t.effects.filter(
        (e) =>
          ['UNKNOWN', 'RESERVED'].includes(e.status) && e.recovery !== 'RECOVERED_READBACK_ONLY',
      );
    const states = [
      s.state,
      ...(s.channel_states || []),
      s.sdk || 'SDK_BUILD_NOT_VERIFIED',
      s.device || 'DEVICE_SUBSCRIPTION_NOT_VERIFIED',
    ].filter(Boolean);
    const entries = states
      .map((x) => `<li>${esc(stateLabels[x] || x.replaceAll('_', ' ').toLowerCase())}</li>`)
      .join('');
    const step = s.provider_app_id ? 2 : s.protected_key ? 1 : 0;
    const steps = ['Save key', 'Choose app', 'Verify delivery']
      .map(
        (label, i) =>
          `<li${i === step ? ' aria-current="step"' : ''}><span>${i + 1}</span>${esc(label)}<small>${i < step ? 'Done' : i === step ? 'Current step' : 'Next'}</small></li>`,
      )
      .join('');
    const history = t.effects
      .map(
        (e) =>
          `<li>${esc(e.action)} · ${esc(e.status)} · effect ${esc(e.id)}${e.recovery ? ` · ${esc(e.recovery)} (original outcome remains uncertain)` : ''}</li>`,
      )
      .join('');
    const appRows = t.apps
      .map(
        (a, i) =>
          `<li>${esc(a.name)}${a.name.toLocaleLowerCase() === String(t.d.state.workspace.app.data.name || '').toLocaleLowerCase() ? ' (name matches this app; verify the IDs)' : ''} · App ID ${esc(a.id)} · Organization ${esc(a.organization_id || 'Not provided')} ${button('Select this exact app', 'bind', `data-index="${i}"`)}</li>`,
      )
      .join('');
    const recovery = unknown
      .map(
        (e) =>
          `<form id="onesignal-recovery-form" data-effect="${esc(e.id)}"><h3>Recover uncertain ${esc(e.action)}</h3><p>Effect ${esc(e.id)} remains uncertain. Do not retry. Inspect OneSignal, then read back the exact app with a key. In-progress requests may require a short wait.</p>${input('provider_app_id', 'Exact OneSignal app ID', 'text', e.provider_app_id || '')}<label class="field">Readback key type<select name="key_kind"><option value="app">App key</option><option value="org">Organization key</option></select></label>${input('key', 'OneSignal readback key', 'password')}<button class="button" type="submit">Review recovery readback</button></form>`,
      )
      .join('');
    const key = `<form id="onesignal-key-form"><h3>${s.protected_key ? 'Rotate protected key' : 'Save a protected key'}</h3><p>${s.protected_key ? 'Replacing the key clears the current app binding.' : 'Use an app key for one app, or an organization key to find apps and review push settings.'}</p><label class="field">Key type<select name="kind"><option value="app">App key</option><option value="org">Organization key</option></select></label>${input('key', 'OneSignal key', 'password')}<button class="button" type="submit">Save protected key</button></form>`;
    const reads = s.protected_key
      ? `<form id="onesignal-read-form"><h3>Find your app</h3><p>${s.key_kind === 'app' ? 'Enter the exact OneSignal app ID for this key.' : 'Discover apps available to your organization key.'}</p>${s.key_kind === 'app' ? input('selected_id', 'Exact OneSignal app ID', 'text', s.provider_app_id || '') : ''}<button class="button" type="submit">Read OneSignal apps</button></form>${appRows ? `<ul>${appRows}</ul>` : '<p>No current app readback. Read the provider to see choices.</p>'}`
      : '';
    const create =
      s.key_kind === 'org'
        ? `<form id="onesignal-create-form"><h3>Create a OneSignal app</h3><p>Use the exact organization ID from OneSignal. Review is required before creation.</p>${input('name', 'App name', 'text', t.d.state.workspace.app.data.name || '')}${input('organization_id', 'Organization ID')}<button class="button" type="submit">Review app creation</button></form>`
        : '';
    const channels =
      s.key_kind === 'org' && s.provider_app_id
        ? `<form id="onesignal-channel-form"><h3>Optional push channels</h3><p>Enter the complete APNs group and/or Firebase service account JSON. Private values are protected and excluded from the review.</p>${input('apns_key_id', 'APNs key ID')}${input('apns_team_id', 'Apple team ID')}${input('apns_bundle_id', 'App bundle ID')}<label class="field">APNs environment<select name="apns_env"><option value="">Not selected</option><option value="production">Production</option><option value="development">Development</option></select></label><label class="field">APNs P8 private key<textarea name="apns_p8" autocomplete="off"></textarea></label><label class="field">Firebase service account JSON<textarea name="fcm_v1_service_account_json" autocomplete="off"></textarea></label><button class="button" type="submit">Review channel configuration</button></form>`
        : '';
    const optional = (id, title, content) =>
      content
        ? `<details id="${id}" class="onesignal-option"><summary>${title}</summary>${content}</details>`
        : '';
    const keyPanel = s.protected_key
      ? optional('onesignal-key-options', 'Change protected key', key)
      : key;
    const forms = s.protected_key
      ? reads +
        optional('onesignal-create-options', 'Create another OneSignal app', create) +
        optional('onesignal-channel-options', 'Configure push channels (optional)', channels) +
        keyPanel
      : keyPanel;
    t.node.innerHTML = `<p class="onesignal-scope">For <strong>${esc(t.d.state.workspace.app.data.name)}</strong></p><ol class="onesignal-steps" aria-label="Connection progress">${steps}</ol>${unknown.length ? recovery : forms}<section class="onesignal-status" aria-label="Connection verification"><h3>What is verified</h3><ul>${entries}</ul><p>${esc(s.next_action || 'Save a key and read your OneSignal app.')}</p><p class="muted">Notifications have not been sent by this setup. Verify the SDK build and a device subscription separately.</p></section><details><summary>App identity and technical status</summary><p>App ID: ${esc(s.provider_app_id || 'Not bound')} · Organization: ${esc(s.organization_id || 'Not bound')}</p><ul>${states.map((x) => `<li><code>${esc(x)}</code></li>`).join('')}</ul></details><details><summary>Setup history</summary>${history ? `<ul>${history}</ul>` : '<p>No setup effects recorded.</p>'}</details><div class="onesignal-tools">${button('Refresh saved status and history', 'refresh')}${s.protected_key ? button('Check retired-key cleanup', 'cleanup') : ''}</div><p id="onesignal-progress" role="status" aria-live="polite"></p><p id="onesignal-error" class="field-error" role="alert"></p>`;
  }
  async function reload(t) {
    const [s, h] = await Promise.all([call(t, 'status', {}), call(t, 'history', {})]);
    if (!current(t)) return;
    t.status = s;
    t.effects = h.effects || [];
    t.proposal = null;
    view(t);
  }
  async function open(d) {
    const t = show(d, '<p role="status">Reading saved setup…</p>');
    const w = d.state.workspace || {},
      i = w.identity || {},
      r = (w.access?.members || []).find(
        (x) => x.principal === i.principal && x.status === 'ACTIVE',
      );
    if (i.status !== 'AUTHENTICATED' || r?.role !== 'OWNER') {
      t.node.innerHTML = '<p>Sign in as the current app owner to configure OneSignal.</p>';
      return;
    }
    try {
      await reload(t);
    } catch (e) {
      error(t, e);
    }
  }
  function recoveryReview(t, p) {
    const q = p.proposal || {},
      v = q.provider_identity || {},
      old = q.original || {},
      now = q.current || {};
    t.proposal = p;
    t.node.innerHTML = `<h3>Review readback-only recovery</h3><p>Original ${esc(q.effect_action)} effect: ${esc(q.effect_id)} · ${esc(q.effect_status)}<br>OneSignal app: ${esc(v.name)}<br>App ID: ${esc(v.id)}<br>Organization: ${esc(v.organization_id || 'None')}<br>App revision: ${esc(old.app_version)} → ${esc(now.app_version)}<br>Owner revision: ${esc(old.role_version)} → ${esc(now.role_version)}<br>Connection revision: ${esc(old.connection_version)} → ${esc(now.connection_version)}<br>Expires: ${esc(q.expires_at)}</p><p>This repeats only the exact app readback. It will not repeat the original change or assert that it succeeded. Save and bind a current key afterward if needed.</p>${button('Confirm readback recovery', 'recovery-confirm')}${button('Cancel recovery review', 'refresh')}<p id="onesignal-progress" role="status" aria-live="polite"></p><p id="onesignal-error" class="field-error" role="alert"></p>`;
  }
  function review(t, p) {
    const q = p.proposal || {},
      x = q.details || {};
    t.proposal = p;
    t.node.innerHTML = `<h3>Review exact provider change</h3><p>Action: ${esc(q.action)}<br>WMM app: ${esc(t.d.state.workspace.app.data.name)}<br>OneSignal app: ${esc(x.name || t.status.name || 'New app')}<br>OneSignal app ID: ${esc(q.provider_app_id || 'Assigned on creation')}<br>Organization ID: ${esc(x.organization_id || q.organization_id || 'Not specified')}<br>Fields: ${esc(
      Object.entries(x)
        .filter(([k]) => !['name', 'organization_id'].includes(k))
        .map(
          ([k, v]) =>
            k +
            ': ' +
            (['apns_p8', 'fcm_v1_service_account_json'].includes(k)
              ? 'PROTECTED_VALUE_SELECTED'
              : v),
        )
        .join(', ') || 'App identity only',
    )}<br>Effect ID: ${esc(p.id)}<br>Expires: ${esc(q.expires_at)}</p><p>This runs only the listed creation or channel configuration. No notifications, deletion, transfer or paid upgrade. Provider response and device delivery are separate checks.</p>${button('Confirm and apply this exact change', 'execute')}${button('Cancel review', 'refresh')}<p id="onesignal-progress" role="status" aria-live="polite"></p><p id="onesignal-error" class="field-error" role="alert"></p>`;
  }
  async function action(node, d) {
    if (node.dataset.action === 'onesignal-open') return open(d);
    const t = active;
    if (!t || !current(t) || t.pending) return;
    const a = node.dataset.action.slice(10);
    busy(t, true, 'Working…');
    try {
      if (a === 'refresh') {
        await reload(t);
        return;
      }
      if (a === 'cleanup') {
        await call(t, 'cleanup', {});
        await reload(t);
        if (current(t))
          t.node.querySelector('#onesignal-progress').textContent =
            'Retired-key cleanup checked. Provider key revocation was not performed.';
        return;
      }
      if (a === 'bind') {
        const app = t.apps[Number(node.dataset.index)];
        if (!app) throw Error('Read and select the exact app again.');
        await call(t, 'bind', {
          provider_app_id: app.id,
          expected_name: app.name,
          expected_org: app.organization_id ?? null,
          version: t.status.version,
        });
        await reload(t);
        return;
      }
      if (a === 'recovery-confirm') {
        const p = t.proposal;
        if (!p) throw Error('Recovery review expired. Prepare it again.');
        t.proposal = null;
        await call(t, 'recovery-confirm', {
          recovery_id: p.id,
          source_hash: p.source_hash,
          confirmed: true,
        });
        await reload(t);
        if (current(t))
          t.node.querySelector('#onesignal-progress').textContent =
            'Readback recovery recorded. The original effect remains uncertain; no mutation was retried. Save and bind a current key if needed.';
        return;
      }
      if (a === 'execute') {
        const p = t.proposal;
        if (!p) throw Error('Review expired. Prepare the change again.');
        t.proposal = null;
        const result = await call(t, 'execute', {
          effect_id: p.id,
          source_hash: p.source_hash,
          confirmed: true,
        });
        await reload(t);
        if (current(t))
          t.node.querySelector('#onesignal-progress').textContent =
            result.status === 'SUCCEEDED'
              ? 'Provider change completed with app readback. Verify the SDK and device separately.'
              : result.status === 'BLOCKED_NOT_SENT'
                ? 'No provider change was sent. Review a new proposal if needed.'
                : 'Outcome uncertain. Inspect the provider and reconcile the exact app; do not retry.';
      }
    } catch (e) {
      error(t, e);
    } finally {
      busy(t, false);
    }
  }
  async function submit(form, d) {
    const t = active;
    if (!t || !current(t) || t.pending || !form.isConnected) return;
    const f = new d.FormData(form),
      id = form.id;
    let a, b;
    if (id === 'onesignal-key-form') {
      a = 'save-key';
      b = { kind: f.get('kind'), key: f.get('key'), version: t.status.version || 0 };
    } else if (id === 'onesignal-read-form') {
      a = 'read';
      b = { selected_id: t.status.key_kind === 'app' ? f.get('selected_id') : null };
    } else if (id === 'onesignal-create-form') {
      a = 'prepare';
      b = {
        action: 'create',
        details: { name: f.get('name'), organization_id: f.get('organization_id') },
        request_key: crypto.randomUUID(),
      };
    } else if (id === 'onesignal-channel-form') {
      a = 'prepare';
      const details = {};
      for (const k of [
        'apns_p8',
        'apns_key_id',
        'apns_team_id',
        'apns_bundle_id',
        'apns_env',
        'fcm_v1_service_account_json',
      ])
        if (f.get(k)) details[k] = f.get(k);
      b = { action: 'update', details, request_key: crypto.randomUUID() };
    } else if (id === 'onesignal-recovery-form') {
      a = 'recovery-prepare';
      b = {
        effect_id: form.dataset.effect,
        provider_app_id: f.get('provider_app_id'),
        key_kind: f.get('key_kind'),
        key: f.get('key'),
      };
    } else return;
    busy(t, true, 'Working…');
    try {
      const result = await call(t, a, b);
      if (!current(t)) return;
      if (a === 'read') {
        t.apps = result;
        view(t);
      } else if (a === 'prepare') {
        review(t, result);
      } else if (a === 'recovery-prepare') {
        recoveryReview(t, result);
      } else {
        if (a === 'save-key') t.apps = [];
        await reload(t);
        if (current(t) && a === 'reconcile')
          t.node.querySelector('#onesignal-progress').textContent =
            'Exact app reconciled. Channel configuration and device delivery still require verification.';
      }
    } catch (e) {
      error(t, e);
    } finally {
      form.querySelectorAll('input[type=password],textarea').forEach((x) => (x.value = ''));
      busy(t, false);
    }
  }
  return { panel, scope, clear, invalidate, open, action, submit };
});
