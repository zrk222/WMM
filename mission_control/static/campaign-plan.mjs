/* Deterministic campaign plan from saved app facts and planning choices; no external action. */
/**
 * @typedef {{name?: string, job?: string, audience?: string, activation?: string, currency?: string, release?: string, locale?: string, cadence?: string}} AppFacts
 * @typedef {{app?: {id?: string, version?: number, data?: AppFacts}, records?: {kind?: string}[], automation?: {drafts?: {experiment?: {hypothesis?: string, stop_rule?: string}, distribution?: {channel?: string, destination?: string, currency?: string}, registered_experiment?: {rollback_plan?: string}}, learning?: {change?: string}, metric?: {label?: string, value?: string}, baseline?: {status?: string, reason?: string}, channel?: {value?: string, alternatives?: string[], basis?: string}, cadence?: string}, workflow?: {next_action?: {title?: string}}}} CampaignWorkspace
 */
export const WMMCampaignPlan = (() => {
  /** @param {{kind?: string}[]} records @param {string} kind */
  function count(records, kind) {
    return records.filter((row) => row.kind === kind).length;
  }

  /** @param {AppFacts} app */
  function missingInputs(app = {}) {
    const missing = [];
    if (!app.job) missing.push('user job');
    if (!app.audience) missing.push('audience');
    if (!app.activation) missing.push('useful activation');
    if (!app.release) missing.push('release');
    if (!app.locale) missing.push('locale');
    return missing;
  }

  /** @param {CampaignWorkspace} workspace @param {{now?: string, goal?: string}} options */
  function build(workspace = {}, options = {}) {
    const app = workspace.app?.data || {};
    const automation = workspace.automation || {};
    const drafts = automation.drafts || {};
    const experiment = drafts.experiment || {};
    const distribution = drafts.distribution || {};
    const records = workspace.records || [];
    const generatedAt = options.now || new Date().toISOString();
    const missing = missingInputs(app);
    const proof = {
      claims: count(records, 'claim'),
      assets: count(records, 'asset'),
      readiness: count(records, 'readiness'),
      store: count(records, 'store'),
      route: count(records, 'route'),
    };
    const positioning = {
      audience: app.audience || '',
      job: app.job || '',
      activation: app.activation || '',
      hypothesis:
        experiment.hypothesis ||
        `Show ${app.job || 'the declared user job'} to ${app.audience || 'the declared audience'} and measure ${app.activation || 'the declared useful outcome'}.`,
    };
    return {
      schema: 'wmm.campaign-plan.v1',
      app_id: workspace.app?.id || '',
      app_version: workspace.app?.version ?? null,
      status: missing.length ? 'INPUTS_MISSING' : 'READY_FOR_REVIEW',
      generated_at: generatedAt,
      goal: options.goal || automation.learning?.change || '',
      positioning,
      objective: {
        metric: automation.metric?.label || 'Choose one primary outcome',
        metric_key: automation.metric?.value || '',
        baseline: automation.baseline?.status || 'UNAVAILABLE',
        baseline_reason: automation.baseline?.reason || 'No matching mature baseline is saved.',
      },
      channels: {
        pilot: automation.channel?.value || '',
        alternatives: automation.channel?.alternatives || [],
        cadence: automation.cadence || '',
        basis:
          automation.channel?.basis || 'Channel priority is a hypothesis, not a measured winner.',
      },
      proof,
      distribution: {
        channel: distribution.channel || automation.channel?.value || '',
        destination: distribution.destination || '',
        currency: distribution.currency || app.currency || '',
        budget_minor: 0,
        daily_cap_minor: 0,
        mode: 'MANUAL_HANDOFF',
      },
      measurement: {
        next_action: workspace.workflow?.next_action?.title || 'Review the saved workflow',
        stop_rule:
          experiment.stop_rule ||
          'Stop and repair if journey, privacy, billing or claim checks fail.',
        rollback:
          drafts.registered_experiment?.rollback_plan ||
          'Retain the prior reviewed packet and app version.',
        window: app.cadence || automation.cadence || 'Declare one useful-value window',
      },
      missing,
      boundaries: [
        'This is a planning draft, not a provider upload, publication or spend approval.',
        'Saved claims, screens and readiness checks still need current release/locale review.',
        'Ad budget stays at zero; any provider effect needs its own exact approval.',
        'Missing evidence stays unknown; no install, revenue, ranking or lift is inferred.',
      ],
    };
  }

  /** @param {ReturnType<typeof build>} plan */
  function markdown(plan) {
    const missing = plan.missing.length
      ? plan.missing.map((item) => `- ${item}`).join('\n')
      : '- None for planning; evidence review still applies.';
    return [
      `# ${plan.app_id || 'App'} campaign plan`,
      '',
      `Status: ${plan.status}`,
      `Generated: ${plan.generated_at}`,
      `Goal: ${plan.goal || 'Not selected'}`,
      '',
      '## Objective',
      `Primary outcome: ${plan.objective.metric}`,
      `Baseline: ${plan.objective.baseline} — ${plan.objective.baseline_reason}`,
      '',
      '## Audience and job',
      `Audience: ${plan.positioning.audience || 'Not supplied'}`,
      `User job: ${plan.positioning.job || 'Not supplied'}`,
      `Useful activation: ${plan.positioning.activation || 'Not supplied'}`,
      '',
      '## Positioning hypothesis',
      plan.positioning.hypothesis,
      '',
      '## Pilot channels',
      `Pilot: ${plan.channels.pilot || 'Not selected'}`,
      `Alternatives: ${plan.channels.alternatives.join(', ') || 'None supplied'}`,
      `Cadence: ${plan.channels.cadence || 'Not declared'}`,
      `Basis: ${plan.channels.basis}`,
      '',
      '## Proof to verify',
      `Saved claims: ${plan.proof.claims}`,
      `Saved screens/assets: ${plan.proof.assets}`,
      `Saved readiness checks: ${plan.proof.readiness}`,
      `Saved store destination evidence: ${plan.proof.store}`,
      `Saved first-value routes: ${plan.proof.route}`,
      '',
      '## Distribution',
      `Channel: ${plan.distribution.channel || 'Not selected'}`,
      `Destination: ${plan.distribution.destination || 'Not supplied'}`,
      `Budget: ${[plan.distribution.budget_minor, plan.distribution.currency].filter((part) => part !== '').join(' ')} (no spend authorized)`,
      `Mode: ${plan.distribution.mode}`,
      '',
      '## Measurement',
      `Next action: ${plan.measurement.next_action}`,
      `Window: ${plan.measurement.window}`,
      `Stop rule: ${plan.measurement.stop_rule}`,
      `Rollback: ${plan.measurement.rollback}`,
      '',
      '## Missing inputs',
      missing,
      '',
      '## Boundaries',
      ...plan.boundaries.map((item) => `- ${item}`),
      '',
    ].join('\n');
  }

  return { build, markdown, missingInputs };
})();

/** @typedef {{scopeId: string, scopeHash: string, messages: string[], link: string|null}} CampaignReuseDraft */

const settledBatches = new Set([
  'DELIVERY_VERIFIED',
  'OFF',
  'APPROVAL_EXPIRED',
  'APPROVAL_INACTIVE',
]);
const settledItems = new Set(['VERIFIED', 'BLOCKED', 'CANCELLED']);

/** @param {unknown} value @returns {value is Record<string, unknown>} */
function record(value) {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** @param {unknown} value @returns {value is string|null} */
function reusableLink(value) {
  if (value === null) return true;
  if (typeof value !== 'string' || value.length > 2048) return false;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' && !!url.hostname && !url.username && !url.password;
  } catch {
    return false;
  }
}

/** @param {unknown} value @returns {CampaignReuseDraft|null} */
function draft(value) {
  if (!record(value) || value.evidence_unavailable) return null;
  const { id, scope_id: scopeId, progress, items, summary } = value;
  if (
    typeof id !== 'string' ||
    !id ||
    typeof scopeId !== 'string' ||
    !scopeId ||
    typeof progress !== 'string' ||
    !settledBatches.has(progress) ||
    !record(summary) ||
    summary.batch_id !== id ||
    summary.scope_id !== scopeId ||
    typeof summary.scope_hash !== 'string' ||
    !/^[a-f0-9]{64}$/.test(summary.scope_hash) ||
    summary.kind === 'ADMITTED_ORGANIC_VIDEO_V1' ||
    !Array.isArray(items) ||
    !items.length ||
    items.length > 20 ||
    !Array.isArray(summary.items) ||
    items.length !== summary.items.length
  )
    return null;

  const receipts = new Set();
  for (const item of items) {
    if (
      !record(item) ||
      typeof item.item_id !== 'string' ||
      !item.item_id ||
      receipts.has(item.item_id) ||
      typeof item.effective_status !== 'string' ||
      !settledItems.has(item.effective_status)
    )
      return null;
    receipts.add(item.item_id);
  }
  /** @type {string[]} */
  const messages = [];
  /** @type {string|null} */
  let link = null;
  let messageLength = 0;
  for (const item of summary.items) {
    if (!record(item) || typeof item.item_id !== 'string' || !receipts.delete(item.item_id))
      return null;
    if (item.operation !== undefined && item.operation !== 'campaign.publish') return null;
    const request = item.request;
    if (
      !record(request) ||
      typeof request.message !== 'string' ||
      !request.message.trim() ||
      request.message.length > 5000 ||
      /\r?\n---\r?\n/.test(request.message) ||
      !reusableLink(request.link) ||
      (messages.length > 0 && request.link !== link)
    )
      return null;
    messageLength += request.message.length + (messages.length ? 5 : 0);
    if (messageLength > 50000) return null;
    messages.push(request.message);
    link = request.link;
  }
  return { scopeId, scopeHash: summary.scope_hash, messages, link };
}

export const WMMCampaignReuse = Object.freeze({ draft });
