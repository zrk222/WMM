/* Deterministic campaign plan from saved app facts and planning choices; no external action. */
const WMMCampaignPlan = (() => {
  function count(records, kind) {
    return records.filter((row) => row.kind === kind).length;
  }

  function build(workspace = {}, options = {}) {
    const app = workspace.app?.data || {};
    const automation = workspace.automation || {};
    const drafts = automation.drafts || {};
    const experiment = drafts.experiment || {};
    const distribution = drafts.distribution || {};
    const records = workspace.records || [];
    const generatedAt = options.now || new Date().toISOString();
    const missing = [];
    if (!app.job) missing.push('user job');
    if (!app.audience) missing.push('audience');
    if (!app.activation) missing.push('useful activation');
    if (!app.currency) missing.push('currency');
    if (!app.release) missing.push('release');
    if (!app.locale) missing.push('locale');
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
      `Budget: ${plan.distribution.budget_minor} ${plan.distribution.currency || ''} (no spend authorized)`,
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

  return { build, markdown };
})();

if (typeof module !== 'undefined') module.exports = WMMCampaignPlan;

if (typeof module === 'undefined') globalThis.WMMCampaignPlan = WMMCampaignPlan;
