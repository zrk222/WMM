import { status } from './app.mjs';
import { WMMMmpImport } from './feature-apis.mjs';
import { $, api, button, esc, notice, refresh, showActionError, state, toast } from './app.mjs';
import { modal } from './app-ui.mjs';
('use strict');

function installAttributionPanel() {
  const value = state.workspace.install_attribution,
    campaigns = value?.campaigns || [];
  const rows = campaigns
    .map(
      (item) =>
        `<div class="record-row"><span class="record-main"><strong>${esc(item.campaign_token)}</strong><small>${esc(item.batches)} batch(es) Â· coverage ${esc(item.coverage_status)} Â· study ${esc(item.study_status)} Â· last observed ${esc(item.last_observed_at || 'unknown')}</small></span>${button('Open install report', 'install-report', `data-id="${esc(item.campaign_token)}"`)}</div>`,
    )
    .join('');
  return `<section class="panel" aria-label="Install attribution"><div class="section-heading"><h2>Install attribution</h2><div class="toolbar">${button('Import install export', 'install-import-open')}${button('Connection options', 'mmp-connections')}</div></div>${campaigns.length ? `<div class="record-list">${rows}</div><p class="description">Open a report for counts, dates and the source receipt.</p>` : notice('No install export yet. The observation window may still be open, or no MMP export has been ingested. Engagement is not an install.')}</section>`;
}

function installMappingKey() {
  return `wmm.install-import-mapping.${state.app}`;
}
function savedInstallMapping() {
  try {
    const value = JSON.parse(localStorage.getItem(installMappingKey()) || 'null');
    return value && typeof value === 'object' ? value : null;
  } catch {
    return null;
  }
}
function rememberInstallMapping(payload) {
  try {
    localStorage.setItem(
      installMappingKey(),
      JSON.stringify({ source: payload.source, mapping: payload.mapping }),
    );
  } catch {}
}

function installImportForm(study = null) {
  state.installImport = null;
  const saved = savedInstallMapping() || {},
    mapping = saved.mapping || {};
  modal(
    'Import install export',
    `<form id="install-import-form" data-app="${esc(state.app)}"><div class="modal-content">${notice('1. Choose your MMP CSV or JSON export. 2. Enter the campaign token and the study’s dates. 3. Review the preview before saving. The file stays in this workspace.')}${saved.source ? '<p class="description">Using the source token and column names saved on this machine. You can change them for this import.</p>' : ''}<label class="field" for="install-export-file">Export file<input id="install-export-file" name="export_file" type="file" accept=".csv,.json" required></label><div class="toolbar">${button('Detect columns', 'install-import-detect')}${button('CSV template', 'install-import-template')}</div><p id="install-detect-status" class="description" role="status">Choose a file. WMM will suggest column matches automatically; review them before previewing.</p><div class="form-grid"><label class="field" for="install-source">Source token<input id="install-source" name="source" required value="${esc(saved.source || 'MMP')}"></label><label class="field" for="install-campaign">Campaign token<input id="install-campaign" name="campaign_token" required ${study ? `readonly value="${esc(study.study_id)}"` : ''}></label><label class="field" for="install-observed">Observed at (UTC ISO)<input id="install-observed" name="observed_at" required></label><label class="field" for="install-window-start">Window start (UTC ISO)<input id="install-window-start" name="window_start" required ${study ? `readonly value="${esc(study.study.starts_at)}"` : ''}></label><label class="field" for="install-window-end">Window end (UTC ISO)<input id="install-window-end" name="window_end" required ${study ? `readonly value="${esc(study.study.ends_at)}"` : ''}></label><label class="field" for="install-col-id">install_id column<input id="install-col-id" name="col_install_id" required value="${esc(mapping.install_id || 'install_id')}"></label><label class="field" for="install-col-state">state column<input id="install-col-state" name="col_state" required value="${esc(mapping.state || 'state')}"></label><label class="field" for="install-col-time">occurred_at column<input id="install-col-time" name="col_occurred_at" required value="${esc(mapping.occurred_at || 'occurred_at')}"></label><label class="field" for="install-state-values">Source status mapping (optional JSON)<textarea id="install-state-values" name="state_values" placeholder='{"install":"ATTRIBUTED"}'>${esc(mapping.state_values ? JSON.stringify(mapping.state_values) : '')}</textarea></label><label class="field" for="install-count">Source event count<input id="install-count" name="source_event_count" type="number" min="0" step="1"></label></div><label class="check-row"><input type="checkbox" name="coverage_complete"> Source coverage is complete</label><div class="field-error" role="alert"></div></div><div class="modal-actions"><button type="submit" class="button">Preview import</button></div></form>`,
    'INSTALL ATTRIBUTION',
  );
}

async function installImportDetect(form) {
  const picker = form.querySelector('[name="export_file"]'),
    file = picker.files[0];
  const status = form.querySelector('#install-detect-status');
  const active = () =>
    state.app === form.dataset.app &&
    form.isConnected &&
    form.closest('dialog')?.open &&
    picker.files[0] === file;
  if (!file) {
    if (status) status.textContent = 'Choose an export file first.';
    return;
  }
  if (file.size > 2000000) {
    if (status) status.textContent = 'Use an export smaller than 2 MB.';
    return;
  }
  const fields = {
    install_id: 'col_install_id',
    state: 'col_state',
    occurred_at: 'col_occurred_at',
  };
  const original = Object.fromEntries(
    Object.values(fields).map((name) => [name, form.elements[name]?.value]),
  );
  try {
    if (status) status.textContent = 'Checking export columns…';
    const text = await file.text();
    if (!active()) return;
    const format = file.name.toLowerCase().endsWith('.json') ? 'json' : 'csv';
    const headers = WMMMmpImport.parseHeaders(text, format);
    const value = WMMMmpImport.suggest(headers);
    for (const [key, name] of Object.entries(fields)) {
      const input = form.querySelector('[name="' + name + '"]');
      if (input && input.value === original[name] && value.mapping[key])
        input.value = value.mapping[key];
    }
    const found = Object.keys(value.mapping).length;
    if (status)
      status.textContent = `Detected ${found}/3 columns from ${headers.length} headers.${value.unmapped.length ? ` Unmapped: ${value.unmapped.join(', ')}.` : ' '}Review source states and coverage before previewing.`;
  } catch (error) {
    if (active() && status) status.textContent = error.message;
  }
}

async function saveCloudConnection(form) {
  const values = Object.fromEntries(new FormData(form)),
    button = form.querySelector('button[type="submit"]');
  const app = form.dataset.app;
  if (app !== state.app || button?.disabled) return;
  if (button) button.disabled = true;
  try {
    const saved = await api(`/api/apps/${encodeURIComponent(app)}/cloud-connection/save`, {
      endpoint: values.endpoint.trim(),
      token: values.token,
    });
    if (state.app !== app || !form.isConnected) return;
    await refresh();
    if (state.app === app && state.view === 'connections')
      toast(
        saved.mode === 'PERSONAL_CLOUD'
          ? 'Personal cloud settings saved. Test the connection to verify access.'
          : 'Connection saved.',
      );
  } catch (error) {
    if (state.app === app && form.isConnected)
      form.querySelector('.field-error').textContent = error.message;
  } finally {
    if (button) button.disabled = false;
  }
}

async function previewInstallFromForm(form) {
  const submit = form.querySelector('button[type="submit"]');
  if (!submit || submit.disabled) return;
  submit.disabled = true;
  try {
    await installImportSubmit(form);
  } catch (error) {
    if (form.isConnected && form.closest('dialog')?.open && state.app === form.dataset.app)
      form.querySelector('.field-error').textContent = error.message;
  } finally {
    if (submit.isConnected) submit.disabled = false;
  }
}

async function installImportSubmit(form) {
  const file = form.querySelector('[name="export_file"]').files[0];
  if (!file) throw new Error('Choose an export file.');
  if (file.size > 2000000) throw new Error('Use an export smaller than 2 MB.');
  const app = form.dataset.app;
  const active = () =>
    state.app === app &&
    form.isConnected &&
    form.closest('dialog')?.open &&
    form.elements.export_file.files[0] === file;
  const bytes = await file.arrayBuffer();
  const text = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(bytes);
  if (!active()) return;
  const mappingText = form.elements.state_values.value.trim();
  let stateValues = {};
  try {
    if (mappingText) stateValues = JSON.parse(mappingText);
  } catch {
    throw new Error('Enter the status mapping as a JSON object.');
  }
  const count = form.querySelector('[name="source_event_count"]').value;
  const payload = {
    text,
    format: file.name.toLowerCase().endsWith('.json') ? 'json' : 'csv',
    mapping: {
      install_id: form.querySelector('[name="col_install_id"]').value.trim(),
      state: form.querySelector('[name="col_state"]').value.trim(),
      occurred_at: form.querySelector('[name="col_occurred_at"]').value.trim(),
      state_values: stateValues,
    },
    source: form.querySelector('[name="source"]').value.trim(),
    campaign_token: form.querySelector('[name="campaign_token"]').value.trim(),
    request_id: crypto.randomUUID(),
    observed_at: form.querySelector('[name="observed_at"]').value.trim(),
    window: {
      starts_at: form.querySelector('[name="window_start"]').value.trim(),
      ends_at: form.querySelector('[name="window_end"]').value.trim(),
    },
    coverage: {
      complete: form.querySelector('[name="coverage_complete"]').checked,
      source_event_count: count === '' ? null : Number(count),
    },
  };
  const result = await api(
    `/api/apps/${encodeURIComponent(app)}/install-attribution/imports/preview`,
    payload,
  );
  if (!active()) return;
  rememberInstallMapping(payload);
  state.installImport = result.preview_id
    ? { app, payload: { ...payload, preview_id: result.preview_id } }
    : null;
  installImportPreview(result);
}

function installImportPreview(result) {
  const c = result.checklist,
    counts =
      Object.entries(c.counts || {})
        .map(([state, count]) => `${esc(state)} ${esc(count)}`)
        .join(' Â· ') || 'None';
  const rejected = (c.rejected || [])
    .map((row) => `<li>Row ${esc(row.row)}: ${esc(row.reason)}</li>`)
    .join('');
  const warnings = (c.warnings || []).map((text) => `<li>${esc(text)}</li>`).join('');
  const duplicate = (c.duplicates || []).length
    ? `<p>Duplicate row numbers ignored: ${esc(c.duplicates.join(', '))}</p>`
    : '';
  modal(
    'Review install import',
    `<div class="modal-content">${status(c.status)}<p>${esc(c.rows_read)} rows read Â· ${esc(c.rows_emitted)} install records Â· ${counts}</p>${c.reason ? notice(c.reason, 'warning') : ''}${duplicate}${rejected ? `<h3>Rows needing repair</h3><ul>${rejected}</ul>` : ''}${warnings ? `<h3>Warnings</h3><ul>${warnings}</ul>` : ''}${c.unmapped_column_count ? `<p class="description">Unmapped columns: ${esc(c.unmapped_column_count)}</p>` : ''}<p class="description">Review the checklist. Nothing has been stored yet.</p><div class="field-error" role="alert"></div></div><div class="modal-actions">${c.status === 'READY' ? button('Confirm import', 'install-import-confirm') : button('Close', 'close')}</div>`,
    'IMPORT / REVIEW / CONFIRM',
  );
}

async function installImportConfirm(node) {
  const saved = state.installImport;
  if (!saved || saved.app !== state.app)
    throw new Error('Preview the import again before confirming.');
  const dialog = $('#modal');
  const active = () =>
    state.app === saved.app && state.installImport === saved && dialog.open && node.isConnected;
  if (!active() || node.disabled) return;
  node.disabled = true;
  try {
    const result = await api(
      `/api/apps/${encodeURIComponent(saved.app)}/install-attribution/imports/confirm`,
      saved.payload,
    );
    if (!active()) return;
    await refresh();
    if (!active()) return;
    state.installImport = null;
    dialog.close();
    toast(
      `Install export imported: ${result.result.inserted} new, ${result.result.duplicates} duplicate.`,
    );
  } catch (error) {
    if (active()) showActionError(error);
  } finally {
    if (node.isConnected) node.disabled = false;
  }
}

async function installReportOpen(token, day) {
  const app = state.app;
  const endpoint = `/api/apps/${encodeURIComponent(app)}/install-attribution/reports/${encodeURIComponent(token)}`;
  const result = await api(endpoint + (day ? `?day=${encodeURIComponent(day)}` : ''));
  if (state.app !== app) return;
  const controls = [
    ['All observations', ''],
    ['Day 1', '1'],
    ['Day 3', '3'],
    ['Day 7', '7'],
  ]
    .map(([label, value]) =>
      button(label, 'install-report', `data-id="${esc(token)}" data-day="${value}"`),
    )
    .join('');
  const counts = Object.entries(result.counts)
    .map(([label, value]) => `<li>${esc(label)} <strong>${esc(value ?? 'Unknown')}</strong></li>`)
    .join('');
  const sources = result.batches
    .map(
      (batch) =>
        `<p>${esc(batch.source)} · ${esc(batch.window.starts_at)} to ${esc(batch.window.ends_at)} · observed ${esc(batch.observed_at)}<br>Source SHA-256 <code>${esc(batch.source_receipt_sha256)}</code></p>`,
    )
    .join('');
  const explanation = result.coverage_reasons
    .map(
      (reason) =>
        ({
          MULTIPLE_BATCH_DECLARATIONS: 'Multiple exports need coverage reconciliation.',
          INCOMPLETE_COVERAGE: 'An export reported incomplete coverage.',
          UNRECONCILED_COUNTS: 'The source total differs from imported and excluded rows.',
          STUDY_WINDOW_MISMATCH: 'An earlier export does not match the registered study dates.',
          WINDOW_NOT_FULLY_OBSERVED: 'The source does not cover this full window.',
        })[reason] || reason,
    )
    .join(' ');
  modal(
    'Owner install report',
    `<div class="modal-content"><h3>${day ? `Day ${esc(day)}` : 'All observations'}</h3>${status(result.coverage_status)}<p>${esc(explanation || 'Counts reflect only the retained source evidence.')}</p><ul>${counts}</ul><p>${esc(result.scope)}</p><details><summary>Export receipts and observation dates</summary>${sources || '<p>No export receipt is saved.</p>'}</details></div><div class="modal-actions">${controls}</div>`,
    'INSTALL ATTRIBUTION',
  );
}

async function digestText(text) {
  if (!globalThis.crypto?.subtle) return null;
  const bytes = new TextEncoder().encode(text);
  const hash = await crypto.subtle.digest('SHA-256', bytes);
  return [...new Uint8Array(hash)].map((value) => value.toString(16).padStart(2, '0')).join('');
}

export {
  installAttributionPanel,
  installMappingKey,
  savedInstallMapping,
  rememberInstallMapping,
  installImportForm,
  installImportDetect,
  saveCloudConnection,
  previewInstallFromForm,
  installImportSubmit,
  installImportPreview,
  installImportConfirm,
  installReportOpen,
  digestText,
};
