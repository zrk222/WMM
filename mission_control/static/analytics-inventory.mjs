/* Read-only analytics availability. No collector, estimate, comparison or causal inference. */
/**
 * @typedef {{kind?: string, created?: string|null}} SavedRecord
 * @typedef {{records?: SavedRecord[], metrics?: {cohorts?: {status?: string}[], retention?: WorksheetRetention[], event_ledger?: LedgerRetention[]}, install_attribution?: {campaigns?: {last_observed_at?: string|null}[]}, experiments?: {updated?: string|null, created?: string|null}[], measurement_integrity?: {state: string, rows?: unknown[]}}} AnalyticsWorkspace
 */
/** @typedef {{cohort?: {cohort_id?:string, ends_at?:string, matures_at?:string}, as_of?:string|null, mature?:boolean, status?:string, observability?:string, costs_complete?:boolean, installs?:number, retained?:number, retention_rate?:number|null}} LedgerRetention */
/** @typedef {{mature?:boolean, rate?:number|null, eligible?:number, retained?:number, window?:string}} WorksheetRetention */
export const WMMAnalyticsInventory = (() => {
  /** @param {(string|null|undefined)[]} values */
  function latestSaved(values) {
    return values.filter(Boolean).sort().pop() || null;
  }

  /** @param {AnalyticsWorkspace} workspace @param {string} kind */
  function latestRecord(workspace, kind) {
    return latestSaved(
      (workspace.records || []).filter((row) => row.kind === kind).map((row) => row.created),
    );
  }

  /** @param {AnalyticsWorkspace} workspace */
  function summary(workspace = {}) {
    const metrics = workspace.metrics || {};
    const cohorts = metrics.cohorts || [];
    const retention = metrics.retention || [];
    const ledger = metrics.event_ledger || [];
    const ledgerRetention = ledger.filter((r) => r.cohort?.cohort_id);
    const availableLedger = ledgerRetention.filter(
      (r) =>
        r.mature === true &&
        r.status === 'SUPPLIED_RECONCILED' &&
        r.observability === 'OBSERVED' &&
        r.costs_complete === true &&
        typeof r.retention_rate === 'number' &&
        Number.isFinite(r.retention_rate) &&
        (r.installs || 0) > 0,
    );
    const availableWorksheets = retention.filter(
      (r) =>
        r.mature === true &&
        typeof r.rate === 'number' &&
        Number.isFinite(r.rate) &&
        (r.eligible || 0) > 0,
    );
    const retentionCount = retention.length + ledgerRetention.length;
    const retentionAvailable = availableLedger.length + availableWorksheets.length;
    /** @param {number|null|undefined} value */
    const percent = (value) =>
      typeof value === 'number' && Number.isFinite(value)
        ? `${Number((value * 100).toFixed(2))}%`
        : 'unavailable';
    const retentionText = [
      ...ledgerRetention.map(
        (r) =>
          `Event ledger ${r.cohort?.cohort_id}: ${availableLedger.includes(r) ? `${r.retained}/${r.installs} (${percent(r.retention_rate)})` : 'unavailable'}; follow-up ${r.cohort?.ends_at || 'unknown'} to ${r.cohort?.matures_at || 'unknown'}; ${r.mature ? 'mature' : 'not mature'}`,
      ),
      ...retention.map(
        (r) =>
          `Worksheet ${r.window || 'window not supplied'}: ${availableWorksheets.includes(r) ? `${r.retained}/${r.eligible} (${percent(r.rate)})` : 'unavailable'}; ${r.mature ? 'mature' : 'not mature'}`,
      ),
    ].join(' � ');
    const campaigns = workspace.install_attribution?.campaigns || [];
    const experiments = workspace.experiments || [];
    const integrity = workspace.measurement_integrity || { state: 'UNAVAILABLE' };
    const measured = cohorts.filter((row) => row.status === 'MEASURED').length;
    const areas = [
      {
        id: 'cohorts',
        name: 'Acquisition cohorts',
        saved: cohorts.length ? `${cohorts.length} saved · ${measured} measured` : 'None',
        latest: latestRecord(workspace, 'cohort'),
        next: cohorts.length ? 'Review below' : 'Add cohort evidence',
      },
      {
        id: 'ledger',
        name: 'Event-level results',
        saved: ledger.length ? `${ledger.length} report(s)` : 'None',
        latest: latestSaved(ledger.map((row) => row.as_of)),
        next: ledger.length ? 'Review below' : 'Import a cohort with events',
      },
      {
        id: 'retention',
        name: 'Value retention',
        saved: retentionCount ? retentionText : 'None',
        latest: latestSaved([
          latestRecord(workspace, 'retention'),
          ...ledgerRetention.map((r) => r.as_of),
        ]),
        next: ledgerRetention.length
          ? `Inspect event cohort ${ledgerRetention[0].cohort?.cohort_id} below${retentionAvailable ? '' : '; repair maturity, coverage or eligible population'}`
          : retention.length
            ? 'Inspect worksheet maturity and eligible population below'
            : 'Add retention evidence',
      },
      {
        id: 'installs',
        name: 'Install attribution',
        saved: campaigns.length ? `${campaigns.length} campaign token(s)` : 'None',
        latest: latestSaved(campaigns.map((row) => row.last_observed_at)),
        next: campaigns.length ? 'Review coverage below' : 'Import the MMP export',
      },
      {
        id: 'payments',
        name: 'Payment comparison',
        saved:
          integrity.state === 'UNAVAILABLE'
            ? 'Unavailable'
            : `${(integrity.rows || []).length} row(s)`,
        latest: null,
        next: integrity.state === 'UNAVAILABLE' ? 'Review connections' : 'Inspect comparison',
      },
      {
        id: 'experiments',
        name: 'Experiments',
        saved: experiments.length ? `${experiments.length} saved` : 'None',
        latest: latestSaved(experiments.map((row) => row.updated || row.created)),
        next: experiments.length ? 'Review below' : 'Plan one bounded test',
      },
    ];
    const savedCount = areas.filter(
      (row) => row.saved !== 'None' && row.saved !== 'Unavailable',
    ).length;
    let step;
    if (!cohorts.length && !ledger.length) {
      step = {
        id: 'add_acquisition',
        title: 'Add one mature acquisition result',
        detail:
          'Import a complete cohort with its source, currency, costs and mature follow-up. Until then CAC and conversion stay unavailable.',
      };
    } else if (cohorts.length && !measured) {
      step = {
        id: 'repair_cohort',
        title: 'Repair the non-measured cohort',
        detail:
          'The saved cohort is not measured. Add corrected evidence; WMM does not fill gaps with zero or a prior result.',
      };
    } else if (!campaigns.length) {
      step = {
        id: 'import_installs',
        title: 'Import the install export for the frozen window',
        detail:
          "Use the study's campaign token and window. Missing installs stay unknown; engagement is not an install.",
      };
    } else if (integrity.state === 'UNAVAILABLE') {
      step = {
        id: 'repair_payments',
        title: 'Repair the payment comparison',
        detail:
          'Connect or refresh the payment and imported-ledger sources. An unavailable comparison is not a zero.',
      };
    } else if (retentionCount && !retentionAvailable) {
      step = {
        id: 'repair_retention',
        title: 'Inspect the saved retention evidence',
        detail:
          'Review the source window, maturity, coverage and nonzero eligible population below. Unavailable retention stays unknown; do not import a duplicate worksheet.',
      };
    } else if (!retentionCount) {
      step = {
        id: 'add_retention',
        title: 'Add a value-retention window',
        detail:
          'Use the useful value your app delivers and a mature eligible population. A zero denominator stays unavailable.',
      };
    } else {
      step = {
        id: 'inspect_result',
        title: 'Open the measured result and record one decision',
        detail:
          'Inspect the source, window and coverage before deciding. Saved counts do not prove causality or growth.',
      };
    }
    return {
      areas,
      savedCount,
      total: areas.length,
      step,
      counts: {
        cohorts: cohorts.length,
        measured,
        retention: retentionCount,
        ledger: ledger.length,
        campaigns: campaigns.length,
        experiments: experiments.length,
      },
    };
  }

  return { summary, latestSaved };
})();
