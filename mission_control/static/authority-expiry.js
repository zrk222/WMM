/* Shared owner-only review for extending existing finite authority. */
(function (root, factory) {
  const value = factory();
  if (typeof module === 'object' && module.exports) module.exports = value;
  else root.WMMAuthorityExpiry = value;
})(typeof globalThis === 'object' ? globalThis : this, function () {
  'use strict';
  const DAY = 24 * 60 * 60 * 1000;
  const esc = (value) =>
    String(value ?? '').replace(
      /[&<>"']/g,
      (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
    );
  function localInput(value) {
    const date = value instanceof Date ? value : new Date(value);
    if (!Number.isFinite(date.getTime())) return '';
    return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
  }
  function expiryInput(name, value, label = 'Approval expires — device local time') {
    return `<label class="field">${esc(label)}<input name="${esc(name)}" type="datetime-local" value="${esc(localInput(value))}" required></label>`;
  }
  function consentMarkup(name = 'extended_expiry_consent') {
    return `<div data-expiry-consent hidden><label class="check-row"><input type="checkbox" name="${esc(name)}"> I explicitly consent to this approval lasting more than 24 hours.</label></div>`;
  }
  function consentRequired(iso, now = Date.now()) {
    const value = Date.parse(iso);
    if (!Number.isFinite(value) || !Number.isFinite(now))
      throw new Error('Choose a valid finite future expiry.');
    if (value <= now) throw new Error('Choose an expiry in the future.');
    return value > now + DAY;
  }
  function validateExpiry(localValue, consent, now = Date.now(), minimum = null) {
    const value = new Date(localValue).getTime();
    if (!Number.isFinite(value) || value <= now) throw new Error('Choose a valid future expiry.');
    if (minimum !== null && value <= Date.parse(minimum))
      throw new Error('Choose a date later than the current approval expiry.');
    const iso = new Date(value).toISOString(),
      extended = consentRequired(iso, now);
    if (extended && consent !== true)
      throw new Error('Explicit consent is required for an expiry more than 24 hours away.');
    return { expires: iso, extended };
  }
  function bindConsent(form, fieldName = 'expires_at', now = Date.now()) {
    if (!form?.elements) return;
    const input = form.elements.namedItem(fieldName),
      row = form.querySelector('[data-expiry-consent]'),
      checkbox = row?.querySelector('input[type=checkbox]');
    if (!input || !row || !checkbox) return;
    const update = () => {
      let required = false;
      try {
        required = consentRequired(new Date(input.value).toISOString(), now);
      } catch {}
      row.hidden = !required;
      if (!required) checkbox.checked = false;
    };
    input.addEventListener('input', update);
    input.addEventListener('change', update);
    update();
  }
  function dateLine(value) {
    const date = new Date(value);
    return Number.isFinite(date.getTime())
      ? `${date.toLocaleString()} (local) · ${date.toISOString()} (UTC)`
      : 'Unavailable';
  }
  function remaining(usage) {
    const out = {};
    if (Number.isFinite(usage?.max_calls)) {
      const used = usage.used ?? usage.calls ?? 0;
      out.calls = Math.max(0, usage.max_calls - used);
    }
    if (Number.isFinite(usage?.max_generations))
      out.generations = Math.max(0, usage.max_generations - (usage.generations ?? 0));
    if (Number.isFinite(usage?.max_posts)) {
      const used = Array.isArray(usage.posts) ? usage.posts.length : (usage.posts ?? 0);
      out.posts = Math.max(0, usage.max_posts - used);
    }
    if (Number.isFinite(usage?.max_total_minor))
      out.media_commitment_ceiling_minor = usage.max_total_minor;
    if (Number.isFinite(usage?.max_model_minor))
      out.model_spend_ceiling_minor = usage.max_model_minor;
    return out;
  }
  function deadlineRows(rows) {
    return (rows || []).map((row) => ({
      kind: row.kind,
      id: row.id,
      expires: dateLine(row.expires),
      status: row.status,
    }));
  }
  function readiness(value) {
    if (!value || typeof value !== 'object') return null;
    const result = {};
    for (const key of ['status', 'currentness', 'connection_status'])
      if (typeof value[key] === 'string') result[key] = value[key];
    for (const key of ['verification_due_at', 'provider_expires_at', 'permission_expires_at'])
      if (value[key]) result[key] = dateLine(value[key]);
    return result;
  }
  function formValues(config, form) {
    const FormDataCtor =
      config.FormData || config.document.defaultView?.FormData || globalThis.FormData;
    if (!FormDataCtor) throw new Error('Form values are unavailable in this browser.');
    return new FormDataCtor(form);
  }
  function reviewMarkup(result, hash) {
    const p = result?.preview || {};
    const safeReadiness = readiness(p.readiness),
      deadlines = deadlineRows(p.dependent_deadlines);
    const details = {
      kind: p.kind,
      id: p.id,
      old_expiry: p.old_expiry,
      new_expiry: p.new_expiry,
      usage: p.usage,
      remaining: remaining(p.usage),
      bundle: p.bundle,
      dependent_deadlines: deadlines,
      readiness: safeReadiness,
      dependent_work: p.dependent_work,
    };
    return `<section class="panel" aria-label="Exact expiry extension review"><h3>Exact permission change</h3><p>Current expiry: <strong>${esc(dateLine(p.old_expiry))}</strong></p><p>New expiry: <strong>${esc(dateLine(p.new_expiry))}</strong></p><p>Usage and allowances stay unchanged. Existing work with earlier deadlines and separate verification dates keep their own stop times.</p><details open><summary>Current usage, remaining allowances and earlier deadlines</summary><pre>${esc(JSON.stringify({ usage: p.usage ?? null, remaining: remaining(p.usage), bundle: p.bundle ?? [], dependent_deadlines: deadlines, readiness: safeReadiness, dependent_work: p.dependent_work ?? null }, null, 2))}</pre></details><details><summary>Exact server preview</summary><pre>${esc(JSON.stringify(details, null, 2))}</pre></details><p>Preview SHA256: <code>${esc(hash)}</code></p></section>`;
  }
  function receiptRows(value) {
    return (value || []).map((row) => ({
      kind: row.kind,
      id: row.authority_id || row.id,
      old_expiry: row.old_expiry,
      new_expiry: row.new_expiry,
      revision: row.revision,
      confirmed: row.confirmed,
      receipt_hash: row.receipt_hash,
    }));
  }
  function open(config) {
    if (
      !config ||
      !['AGENT_GRANT', 'AUTOMATION', 'CAMPAIGN', 'ORGANIC_POLICY'].includes(config.kind)
    )
      throw new Error('Unknown authority kind.');
    if (!config.owner?.()) throw new Error('Only the current app owner can extend this approval.');
    const app = config.app,
      id = config.id,
      kind = config.kind;
    if (!app || !id || !config.api || !config.modal || !config.document)
      throw new Error('The current owner approval could not be bound. Reload and try again.');
    const parsed = Date.parse(config.expires);
    if (!Number.isFinite(parsed) || parsed <= Date.now())
      throw new Error('Only an active approval can be extended.');
    const next = new Date(parsed + 60 * 60 * 1000),
      nextLocal = localInput(next);
    let preview = null,
      previewHash = '',
      selected = nextLocal,
      working = false,
      consentGranted = false,
      requestId = null,
      dateRevision = 0,
      consentRevision = 0;
    const endpoint = (action) => `/api/apps/${encodeURIComponent(app)}/authority-expiry/${action}`;
    const current = () => config.current?.() !== false && config.owner();
    const render = (title, markup) => {
      if (!current()) return;
      config.modal(
        title,
        `<form id="authority-expiry-form" class="modal-content"><p>Extend this exact owner approval. Existing usage limits and work deadlines stay in force.</p>${expiryInput('expires_at', selected, 'New expiry — device local time')}${consentMarkup()}<p id="authority-expiry-error" role="alert"></p>${markup}</form>`,
        'EXTEND OWNER APPROVAL',
      );
      const form = config.document.querySelector('#authority-expiry-form'),
        input = form?.elements.namedItem('expires_at');
      if (!form || !input) return;
      bindConsent(form, 'expires_at');
      form.elements.namedItem('extended_expiry_consent').addEventListener('change', () => {
        consentRevision++;
      });
      input.addEventListener('input', () => {
        dateRevision++;
        if (preview) {
          preview = null;
          previewHash = '';
          form.dataset.changed = 'true';
          const confirm = form.querySelector('[data-expiry-confirm]');
          if (confirm) confirm.disabled = true;
          const error = form.querySelector('#authority-expiry-error');
          if (error)
            error.textContent = 'The date changed. Review a fresh preview before confirming.';
        }
      });
      form.addEventListener('submit', (event) => {
        event.preventDefault();
        if (form.dataset.mode === 'confirm') confirm(form);
        else makePreview(form);
      });
    };
    const controls = () =>
      `<div class="modal-actions"><button class="button primary" type="submit" data-expiry-preview>Review this expiry</button><button class="button outline" type="button" data-expiry-history>View extension history</button></div>`;
    async function makePreview(form) {
      if (working) return;
      working = true;
      const submit = form.querySelector('[data-expiry-preview]'),
        error = form.querySelector('#authority-expiry-error');
      if (submit) submit.disabled = true;
      if (error) error.textContent = '';
      try {
        const values = formValues(config, form),
          result = validateExpiry(
            values.get('expires_at'),
            values.get('extended_expiry_consent') === 'on',
            Date.now(),
            config.expires,
          ),
          revision = dateRevision,
          consentVersion = consentRevision;
        selected = values.get('expires_at');
        consentGranted = values.get('extended_expiry_consent') === 'on';
        const response = await config.api(endpoint('preview'), {
          kind,
          id,
          expires: result.expires,
        });
        if (!current()) return;
        preview = response.preview;
        previewHash = response.preview_hash;
        const same =
          preview?.kind === kind &&
          preview?.id === id &&
          Number.isFinite(Date.parse(preview?.new_expiry)) &&
          Date.parse(preview.new_expiry) === Date.parse(result.expires);
        if (
          !current() ||
          !form.isConnected ||
          revision !== dateRevision ||
          consentVersion !== consentRevision
        )
          return;
        if (!same)
          throw new Error(
            'The owner-bound preview did not match this authority and selected expiry.',
          );
        requestId = (config.uuid || (() => globalThis.crypto.randomUUID()))();
        renderReview();
      } catch (errorValue) {
        if (current() && form.isConnected) {
          const target = form.querySelector('#authority-expiry-error');
          if (target) target.textContent = errorValue.message + ' The approval is unchanged.';
        }
      } finally {
        working = false;
        if (submit?.isConnected) submit.disabled = false;
      }
    }
    function renderReview() {
      render(
        'Review this approval extension',
        `${reviewMarkup({ preview }, previewHash)}<p>${esc(dateLine(preview.old_expiry))} → ${esc(dateLine(preview.new_expiry))}</p><p>This is an owner decision. Confirm only if the app, authority, usage and selected date are correct.</p><p id="authority-expiry-error" role="alert"></p><div class="modal-actions"><button class="button primary" type="submit" data-expiry-confirm>Confirm this extension</button><button class="button outline" type="submit" data-expiry-preview>Review changed date</button><button class="button outline" type="button" data-expiry-history>View extension history</button></div>`,
      );
      const form = config.document.querySelector('#authority-expiry-form');
      form.dataset.mode = 'confirm';
      const input = form.elements.namedItem('expires_at');
      input.value = selected;
      form.elements.namedItem('extended_expiry_consent').checked = consentGranted;
      input.addEventListener('input', () => {
        dateRevision++;
        preview = null;
        previewHash = '';
        consentGranted = false;
        form.elements.namedItem('extended_expiry_consent').checked = false;
        form.dataset.mode = 'preview';
        form.querySelector('[data-expiry-confirm]').disabled = true;
        form.querySelector('#authority-expiry-error').textContent =
          'The date changed. Review a fresh preview before confirming.';
      });
      form.querySelector('[data-expiry-preview]').addEventListener('click', (event) => {
        event.preventDefault();
        form.dataset.mode = 'preview';
        makePreview(form);
      });
      form.querySelector('[data-expiry-history]').addEventListener('click', (event) => {
        event.preventDefault();
        history();
      });
    }
    async function confirm(form) {
      if (working || !preview || !previewHash || form.dataset.changed === 'true') return;
      working = true;
      const button = form.querySelector('[data-expiry-confirm]'),
        error = form.querySelector('#authority-expiry-error');
      button.disabled = true;
      if (error) error.textContent = '';
      try {
        const values = formValues(config, form),
          value = validateExpiry(
            values.get('expires_at'),
            values.get('extended_expiry_consent') === 'on',
            Date.now(),
            config.expires,
          );
        if (!value.extended)
          throw new Error(
            'An expiry extension must be more than 24 hours from now and later than the current expiry.',
          );
        const response = await config.api(endpoint('confirm'), {
          preview,
          preview_hash: previewHash,
          request_id: requestId,
          extended_expiry_consent: true,
        });
        if (!current()) return;
        const historyResult = await config.api(endpoint('history'), { kind, id });
        if (!current()) return;
        const rows = receiptRows(historyResult.receipts);
        config.modal(
          'Extension saved',
          `<div class="modal-content"><p>Owner expiry extension saved for ${esc(kind)} ${esc(id)}.</p><p>New expiry: ${esc(dateLine(response.receipt?.new_expiry || preview.new_expiry))}</p><p>Allowance and usage were retained. Work with earlier independent deadlines still stops at those dates.</p><details><summary>Saved owner history (${rows.length} receipts)</summary><pre>${esc(JSON.stringify(rows, null, 2))}</pre></details><p id="authority-expiry-error" role="status">${esc(response.receipt?.receipt_hash || response.receipt_hash || 'Saved receipt recorded in owner history.')}</p><div class="modal-actions"><button class="button primary" type="button" data-expiry-done>Done</button></div></div>`,
          'EXTENSION SAVED',
        );
        config.document.querySelector('[data-expiry-done]')?.addEventListener('click', () => {
          config.done?.();
          config.refresh?.();
        });
      } catch (errorValue) {
        if (current() && form.isConnected) {
          error.textContent =
            errorValue.message +
            ' Review the saved history before retrying an uncertain confirmation.';
          button.disabled = false;
        }
      } finally {
        working = false;
      }
    }
    async function history() {
      if (!current()) return;
      try {
        const result = await config.api(endpoint('history'), { kind, id });
        if (!current()) return;
        const rows = receiptRows(result.receipts);
        config.modal(
          'Extension history',
          `<div class="modal-content"><p>${esc(kind)} ${esc(id)} · ${rows.length} saved owner extension receipts.</p>${rows.length ? `<pre>${esc(JSON.stringify(rows, null, 2))}</pre>` : '<p>No extension has been recorded for this approval.</p>'}<div class="modal-actions"><button class="button outline" type="button" data-expiry-back>Back to review</button></div></div>`,
          'OWNER HISTORY',
        );
        config.document.querySelector('[data-expiry-back]')?.addEventListener('click', renderForm);
      } catch (error) {
        config.modal(
          'Could not read extension history',
          `<div class="modal-content"><p role="alert">${esc(error.message)}</p><p>The saved approval remains unchanged.</p></div>`,
          'OWNER HISTORY',
        );
      }
    }
    function renderForm() {
      render('Extend this approval', controls());
      const form = config.document.querySelector('#authority-expiry-form');
      form.dataset.mode = 'preview';
      form.querySelector('[data-expiry-history]').addEventListener('click', history);
    }
    renderForm();
    return { kind, id };
  }
  return {
    DAY,
    localInput,
    expiryInput,
    consentMarkup,
    consentRequired,
    validateExpiry,
    bindConsent,
    dateLine,
    remaining,
    deadlineRows,
    readiness,
    reviewMarkup,
    receiptRows,
    open,
  };
});
