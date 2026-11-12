'use strict';

function providerHealthPanel() {
  const value = state.workspace.provider_health,
    entries = value?.entries || [];
  const when = (epoch) => {
    if (!epoch) return 'Not recorded';
    const date = new Date(typeof epoch === 'number' ? epoch * 1000 : epoch);
    return Number.isNaN(date.getTime()) ? 'Not recorded' : date.toLocaleString();
  };
  const rows = entries
    .map(
      (item) =>
        `<tr><th scope="row">${esc(label(item.provider))}</th><td>${esc(label(item.kind))}</td><td>${status(item.state)}</td><td>${esc(label(item.permission_state))}</td><td>${esc(when(item.expires_at))}</td><td>${esc(item.failure || 'None recorded')}</td><td>${esc(item.next_action || 'No action')}</td></tr>`,
    )
    .join('');
  return `<section class="panel" aria-label="Provider health"><h2>Provider health</h2>${value?.recovery ? notice('Highest-priority recovery: ' + value.recovery.next_action, 'warning') : notice('No provider needs repair from the saved local state. Missing scope or delivery is not inferred.')}${entries.length ? `<div class="table-wrap"><table><caption>Saved provider state and one recovery path per row</caption><thead><tr><th scope="col">Provider</th><th scope="col">Kind</th><th scope="col">Observed state</th><th scope="col">Permission</th><th scope="col">Expires</th><th scope="col">Failure</th><th scope="col">Next action</th></tr></thead><tbody>${rows}</tbody></table></div>` : notice('No supported provider connection is saved for this app. A missing connection is not a successful or zero read.')}<p class="description">${esc(value?.scope || 'Login, key presence and publishing access are not analytics permission or measured outcomes.')}</p></section>`;
}

function cloudConnectionPanel() {
  const value = state.workspace?.cloud_connection || {
    mode: 'LOCAL',
    status: 'LOCAL',
    endpoint: null,
  };
  const local = value.mode === 'LOCAL';
  const statusText = local ? 'No personal cloud configured' : value.endpoint || 'Settings saved';
  return `<section class="panel" aria-label="Personal cloud connection"><div class="section-heading"><div><p class="eyebrow">PERSONAL CLOUD / OPTIONAL</p><h3>Personal cloud endpoint</h3><p>${esc(statusText)}</p></div>${status(value.status)}</div>${notice('Save and test an endpoint for external SDK use. The connection test sends no install data. Imports from WMM stay local.')}<form id="cloud-connection-form" data-app="${esc(state.app)}"><div class="form-grid"><label class="field">Cloud base URL<input name="endpoint" type="url" placeholder="https://cloud.example.com" value="${esc(value.endpoint || '')}" required></label><label class="field">Token (write-only)<input name="token" type="password" autocomplete="new-password" placeholder="${local ? 'Enter token' : 'Leave blank only if the URL stays the same'}"></label></div><div class="field-error" role="alert"></div><div class="modal-actions"><button class="button" type="submit">Save connection</button>${local ? '' : button('Test saved connection', 'cloud-connection-test')}${local ? '' : button('Return to local', 'cloud-connection-remove')}</div></form></section>`;
}

function mmpConnectionsPanel() {
  return `<section class="panel" aria-labelledby="mmp-connections-heading"><div class="section-heading"><div><p class="eyebrow">MEASUREMENT</p><h2 id="mmp-connections-heading" tabindex="-1">Connect install data</h2><p>Use a CSV or JSON export from your mobile measurement partner. No cloud account is needed.</p></div>${button('Import install export', 'install-import-open')}</div><details><summary>Optional personal cloud settings</summary>${cloudConnectionPanel()}</details></section>`;
}

function connectionsView() {
  return (
    heading('Connect with clarity', 'Connect each appâ€™s evidence, then verify actual access.') +
    mmpConnectionsPanel() +
    providerHealthPanel() +
    WMMOneSignal.panel() +
    WMMAppleAnalytics.panel() +
    WMMDrive.panel() +
    googlePlayPanel() +
    socialPanel() +
    WMMPublicationUI.panel(state) +
    campaignPanel() +
    releaseInventoryPanel() +
    subscriptionPanel() +
    attributionPanel() +
    storekitPanel() +
    insightsPanel() +
    legacyConnectionsView()
  );
}

function legacyConnectionsView() {
  return `${paymentSourcesPanel()}${notice('Protected keys stay on the machine running WMM, under the account that runs it. Exports include connection details without the keys. Publishing and spending need separate approval.')}<div class="connection-grid">${state.boot.providers
    .map((provider) => {
      const binding = state.workspace.records.find(
        (r) => r.kind === 'connection' && r.data.provider === provider.id,
      );
      const latest = binding
        ? state.workspace.jobs.find(
            (job) =>
              job.action === 'sync' &&
              job.data.connection_id === binding.id &&
              job.created >= binding.updated,
          )
        : null;
      const connectionInfo = state.workspace.connections?.[binding?.id];
      const protectedStatus = connectionInfo?.status;
      const cleanupNote =
        connectionInfo?.cleanup === 'REMOVAL_PENDING'
          ? notice(
              'Protected key removal is still pending. Use Disconnect locally to finish cleanup; provider access remains disabled.',
            )
          : connectionInfo?.cleanup === 'UNCONFIRMED'
            ? notice(
                'Local key cleanup could not be confirmed. Check protected storage, then use Disconnect locally; provider access remains disabled.',
              )
            : '';
      const unavailable = [
        'DISCONNECTED',
        'RECONNECT_REQUIRED',
        'PROTECTED_STORAGE_UNAVAILABLE',
      ].includes(protectedStatus);
      const connectionStatus = unavailable
        ? protectedStatus
        : latest?.status === 'SUCCEEDED'
          ? 'READ_SUCCEEDED'
          : latest?.status === 'BLOCKED'
            ? 'READ_BLOCKED'
            : binding
              ? 'CONFIGURED_UNTESTED'
              : 'SETUP_NEEDED';
      return `<section class="connection-card"><span class="provider-mark" aria-hidden="true">${provider.id === 'apple_ads' ? 'â†—' : provider.id === 'app_store' ? 'A' : esc(String(provider.name || provider.id).charAt(0))}</span><h2>${esc(provider.name)}</h2><p>${esc(provider.description)}</p>${status(connectionStatus)}${cleanupNote}${button(binding && !unavailable ? 'Test read access' : 'Set up connection', binding && !unavailable ? 'sync' : 'provider', `data-id="${esc(binding && !unavailable ? binding.id : provider.id)}"`)}${binding ? `<div class="toolbar">${button(provider.id === 'app_store' ? 'Read customer reviews' : 'Get campaign report', 'provider-report', `data-id="${esc(binding.id)}" ${unavailable ? 'disabled' : ''}`)}</div>${button('Rotate or reconnect', 'provider', `data-id="${esc(provider.id)}"`)}${button('Disconnect locally', 'disconnect-connection', `data-id="${esc(binding.id)}"`)}` : ''}${latest ? button('Inspect latest read', 'job', `data-id="${esc(latest.id)}"`) : ''}</section>`;
    })
    .join('')}`;
}

function connectionSetup(providerId, recordId) {
  if (providerId === 'aeo') return acquisitionForm('aeo');
  const binding =
    recordId === null
      ? undefined
      : state.workspace.records.find(
          (r) =>
            r.kind === 'connection' &&
            r.data.provider === providerId &&
            (recordId === undefined || r.id === recordId),
        );
  if (recordId != null && !binding)
    return toast('Connection changed. Reopen Apple analytics to select its current connection.');
  const ads = providerId === 'apple_ads';
  const guide = ads
    ? 'Register a P-256 public key in Apple Ads API settings. Copy the resulting team, client and key IDs, then upload the matching private PEM key here.'
    : 'In App Store Connect, open Users and Access â†’ Integrations â†’ App Store Connect API. Use a team API key, copy its issuer and key IDs, and upload the downloaded .p8 file. Individual keys use a different contract and are not accepted here.';
  const link = ads
    ? 'https://searchads.apple.com/'
    : 'https://appstoreconnect.apple.com/access/api';
  modal(
    ads ? 'Connect Apple Ads' : 'Connect App Store Connect',
    `<form id="connection-setup-form" data-provider="${esc(providerId)}" data-app="${esc(state.app)}" data-record="${esc(binding?.id || '')}" data-version="${binding?.version || ''}"><div class="modal-content"><ol><li>${esc(guide)}</li><li>Enter the exact Store app ID${ads ? ' and ad account ID' : ''} for ${esc(state.workspace.app.data.name)}.</li><li>Save the protected key, then use Test read access. Saving does not prove provider access.</li></ol><p><a class="text-button" href="${link}" target="_blank" rel="noopener noreferrer">Open provider key settings â†—</a></p>${notice('WMM saves this key in protected storage on the machine running WMM. On Linux, unlock that machine’s Secret Service keyring if prompted. The key stays out of workspace records and exports. WMM removes the previous local key only after the new connection is saved.')}<div class="form-grid">${field('store_app_id', binding?.data.store_app_id || state.workspace.app.data.store_app_id || '', 'text', 'Numeric App Store ID')}${ads ? field('account_id', binding?.data.account_id || '', 'text', 'Numeric Apple Ads ad account ID; not the organization or team ID') : ''}${field('issuer_id', '', 'text', ads ? 'Team ID from Apple Ads' : 'Team issuer ID from App Store Connect')}${ads ? field('client_id', '', 'text', 'Client ID from Apple Ads') : ''}${field('key_id', '', 'text', 'ID of the uploaded private key')}<label class="field" for="private-key-file">Private key file<input id="private-key-file" name="key_file" type="file" accept=".p8,.pem" required autocomplete="off"><small>P-256 private key only. Upload again after an unsuccessful attempt; secret inputs are cleared.</small></label></div><div class="field-error" id="form-error" role="alert"></div></div><div class="modal-actions"><button type="submit" class="button">Save protected connection</button></div></form>`,
    'PROTECTED PROVIDER SETUP',
  );
}

function disconnectForm(id) {
  const record = state.workspace.records.find((r) => r.id === id && r.kind === 'connection');
  modal(
    'Disconnect this local connection',
    `<div class="modal-content">${notice('This removes the local protected key and disables new reads. It does not revoke the API key at Apple. Revoke it in provider settings if needed. Saved reports remain available.')}<div class="field-error" id="form-error" role="alert"></div></div><div class="modal-actions">${button('Keep connection', 'close')}${button('Remove local access', 'confirm-disconnect', `data-id="${esc(record.id)}" data-version="${record.version}"`)}</div>`,
  );
}

async function saveConnection(form) {
  const values = Object.fromEntries(new FormData(form));
  const file = values.key_file;
  delete values.key_file;
  try {
    if (!file?.size || file.size > 2000)
      throw new Error('Upload a private key file between 1 and 2000 bytes.');
    const data = {
      ...values,
      provider: form.dataset.provider,
      private_key: new TextDecoder('utf-8', { fatal: true }).decode(await file.arrayBuffer()),
    };
    if (form.dataset.record)
      Object.assign(data, { id: form.dataset.record, version: Number(form.dataset.version) });
    const result = await api(`/api/apps/${form.dataset.app}/connections`, data);
    $('#modal').close();
    await refresh();
    toast(
      result.cleanup === 'PRIOR_LOCAL_KEY_CLEANUP_REQUIRED'
        ? 'New connection saved; prior local key cleanup needs attention.'
        : 'Protected connection saved. Test read access to verify permissions.',
    );
  } finally {
    form.querySelector('[name="key_file"]').value = '';
  }
}
