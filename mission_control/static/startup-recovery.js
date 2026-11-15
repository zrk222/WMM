/* Recover a failed dashboard module fetch before any workspace code runs. */
(() => {
  const retryKey = 'wmm-dashboard-load-retried';
  const entryId = 'workspace-entry';
  function clearRetry() {
    try {
      globalThis.sessionStorage.removeItem(retryKey);
    } catch {
      // A manual reload is still available when private browser storage is disabled.
    }
  }
  function showRetry() {
    const heading = document.getElementById('workspace-boot-heading');
    const message = document.getElementById('workspace-boot-message');
    const retry = document.getElementById('workspace-boot-retry');
    if (heading) heading.textContent = 'Your workspace could not open';
    if (message)
      message.textContent =
        'A local screen file did not load. Your saved work is intact. Try loading it again.';
    if (retry) {
      retry.textContent = 'Retry loading';
      retry.addEventListener('click', clearRetry);
    }
  }
  document.addEventListener(
    'error',
    (event) => {
      if (event.target?.id !== entryId) return;
      try {
        if (globalThis.sessionStorage.getItem(retryKey) !== '1') {
          globalThis.sessionStorage.setItem(retryKey, '1');
          globalThis.location.reload();
          return;
        }
      } catch {
        // Do not repeat automatically if the one-retry limit cannot be stored.
      }
      if (document.readyState === 'loading')
        document.addEventListener('DOMContentLoaded', showRetry, { once: true });
      else showRetry();
    },
    true,
  );
  document.addEventListener(
    'load',
    (event) => {
      if (event.target?.id === entryId) clearRetry();
    },
    true,
  );
})();
