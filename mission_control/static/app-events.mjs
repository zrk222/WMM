import { WMMPublicationUI } from './publication.mjs';
import { status } from './app.mjs';
import { WMMMmpImport } from './feature-apis.mjs';
import { WMMCampaignPlan } from './feature-apis.mjs';
import {
  $,
  api,
  button,
  currentWorkspace,
  esc,
  initialize,
  json,
  refresh,
  render,
  showActionError,
  state,
  toast,
} from './app.mjs';
import {
  WMMAgreement,
  WMMGoalReadiness,
  goalAction,
  guidedAction,
  guidedNavigate,
  submitLaunchCheck,
} from './guided-workflow.mjs';
import { WMMCampaignMonitor } from './campaign-monitor.mjs';
import { WMMObservationalCampaign } from './observational-campaign.mjs';
import { WMMOwnerReports } from './campaign-owner-reports.mjs';
import { acquisitionAction } from './acquisition.mjs';
import { activityAction } from './app-research.mjs';
import { aeoAction, aeoSubmit } from './aeo.mjs';
import { agentAction, agentSubmit } from './agent-access.mjs';
import {
  appForm,
  booleanFields,
  download,
  evidenceForm,
  modal,
  money,
  numberFields,
  openJob,
  openRecord,
  openReview,
  openStage,
  prepareReview,
  queue,
  releaseForm,
  reportForm,
  selectPromotionRelease,
  serverDownload,
} from './app-ui.mjs';
import { attributionAction, attributionSubmit } from './attribution.mjs';
import { automaticPreparationAction } from './automatic-preparation.mjs';
import { automationAction, automationCheckForm } from './workflow-automation.mjs';
import {
  briefForm,
  previewReferences,
  productionAction,
  referenceAction,
  saveBrief,
  saveInspection,
  saveReference,
} from './app-production.mjs';
import {
  campaignAction,
  campaignOpen,
  campaignScheduleSubmit,
  campaignSubmit,
} from './campaign-execution.mjs';
import {
  campaignPlanOpen,
  firstMeasuredPost,
  manageAutomationRules,
  nextAnswer,
  ruleStudySelection,
  runAutomationRulePreview,
  selectedMeasuredPost,
  showAutomationVersions,
} from './app-campaign.mjs';
import { capabilityAction } from './production-feasibility.mjs';
import {
  cohortForm,
  growthReviewServices,
  handleExperiment,
  historicalForm,
  measurementIntegrityInspect,
  saveExperiment,
  saveExperimentAction,
  saveExperimentSchedule,
} from './app-results.mjs';
import { connectionSetup, disconnectForm, saveConnection } from './app-connections.mjs';
import { followupAction } from './followup.mjs';
import { insightsAction, saveInsights, saveInsightsEvents } from './insights.mjs';
import {
  installImportConfirm,
  installImportDetect,
  installImportForm,
  installReportOpen,
  previewInstallFromForm,
  saveCloudConnection,
} from './app-install.mjs';
import { paymentAction, savePaymentAction, savePaymentSource } from './signed-payments.mjs';
import { playAction, playRetry, playSubmit } from './google-play.mjs';
import { rankingAction } from './creative-ranking.mjs';
import { renderingAction } from './creative-rendering.mjs';
import { saveJourneyFields } from './journey-readiness.mjs';
import { setupAction } from './setup-discovery.mjs';
import { socialAction, socialSubmit } from './social-access.mjs';
import { spiraAction } from './spira-workflow.mjs';
import { spyTokAction } from './spytok-workflow.mjs';
import { storekitAction, storekitSubmit } from './storekit.mjs';
import { subscriptionAction } from './subscriptions.mjs';
import {
  WMMAgentControl,
  WMMAppleAnalytics,
  WMMCompleteAutomation,
  WMMCustomerWorkflow,
  WMMDiscovery,
  WMMDrive,
  WMMFunnels,
  WMMGrowthReview,
  WMMMedia,
  WMMOneSignal,
  WMMOrganicPolicy,
  WMMOrganicResearch,
  WMMPackaging,
  WMMStudio,
  WMMSubscriptionAuthoring,
  WMMTelemetry,
  WMMVideoEditor,
} from './feature-apis.mjs';
('use strict');

function cohortPayload(values) {
  const data = { ...values };
  const keys = [
    'cost_basis',
    'revenue_basis',
    'attribution_status',
    'spend_source',
    'currency',
    'coverage_through',
  ];
  const economics = Object.fromEntries(
    keys.map((key) => [key, String(data[`economics_${key}`] ?? '').trim()]),
  );
  for (const key of keys) delete data[`economics_${key}`];
  if (economics.cost_basis) {
    if (keys.some((key) => !economics[key]))
      throw new Error(
        'Complete all six acquisition economics fields, or leave cost basis unselected.',
      );
    data.economics = economics;
  }
  return data;
}

async function formSubmit(event) {
  const form = event.target;
  const formId = form.getAttribute('id');
  if (formId?.startsWith('publication-')) {
    event.preventDefault();
    return WMMPublicationUI.submit(form, event, growthReviewServices());
  }
  if (
    !form.isConnected ||
    (!currentWorkspace() && !(formId === 'app-form' && form.dataset.new === 'true'))
  ) {
    event.preventDefault();
    toast('App changed. Wait for this app to load and reopen the form.');
    return;
  }
  if (formId === 'install-import-form') {
    event.preventDefault();
    return previewInstallFromForm(form);
  }
  if (formId === 'cloud-connection-form') {
    event.preventDefault();
    return saveCloudConnection(form);
  }
  if ((formId || '').startsWith('onesignal-')) {
    event.preventDefault();
    return WMMOneSignal.submit(form, growthReviewServices());
  }
  if (formId === 'apple-analytics-form') {
    event.preventDefault();
    return WMMAppleAnalytics.submit(form, growthReviewServices());
  }
  if (formId === 'agreement-form') {
    event.preventDefault();
    return WMMAgreement.submit(form);
  }
  if (formId === 'goal-readiness-form') {
    event.preventDefault();
    return WMMGoalReadiness.submit(form);
  }
  if (formId === 'goal-launch-check') {
    event.preventDefault();
    return submitLaunchCheck(form);
  }
  if (formId === 'standing-scope-form') {
    event.preventDefault();
    return WMMCompleteAutomation.submit(form, growthReviewServices());
  }
  if (['video-project-create-form', 'video-project-edit-form'].includes(formId)) {
    event.preventDefault();
    return WMMVideoEditor.submit(form, growthReviewServices());
  }
  if (formId === 'studio-source-form' || form.hasAttribute('data-studio-parameter')) {
    event.preventDefault();
    return WMMStudio.submit(form, growthReviewServices());
  }
  if (
    [
      'drive-setup-form',
      'drive-import-form',
      'drive-confirm-form',
      'drive-disconnect-form',
    ].includes(formId)
  ) {
    event.preventDefault();
    return WMMDrive.submit(form, growthReviewServices());
  }
  if (
    [
      'packaging-variant-form',
      'packaging-shots-form',
      'packaging-preview-form',
      'packaging-taste-form',
    ].includes(formId)
  ) {
    event.preventDefault();
    return WMMPackaging.submit(form, growthReviewServices());
  }
  if (['discovery-query-form', 'discovery-source-form'].includes(formId)) {
    event.preventDefault();
    return WMMDiscovery.submit(form, growthReviewServices());
  }
  if (
    [
      'oresearch-task-form',
      'oresearch-adopt-form',
      'oresearch-render-form',
      'oresearch-artifact-form',
      'oresearch-schedule-form',
    ].includes(formId)
  ) {
    event.preventDefault();
    return WMMOrganicResearch.submit(form, growthReviewServices());
  }
  if (formId === 'opolicy-form') {
    event.preventDefault();
    return WMMOrganicPolicy.submit(form, growthReviewServices());
  }
  if (['media-upload-form', 'media-review-form'].includes(formId)) {
    event.preventDefault();
    return WMMMedia.submit(form, growthReviewServices());
  }
  if ((formId || '').startsWith('control-')) {
    event.preventDefault();
    return WMMAgentControl.submit(form, growthReviewServices());
  }
  if (formId === 'subscription-plan-form') {
    event.preventDefault();
    return WMMSubscriptionAuthoring.submit(form, growthReviewServices());
  }
  if (['funnel-plan-form', 'funnel-observation-form', 'funnel-batch-form'].includes(formId)) {
    event.preventDefault();
    return WMMFunnels.submit(form, growthReviewServices());
  }
  if (formId === 'customer-workflow-form') {
    event.preventDefault();
    return WMMCustomerWorkflow.submit(form, growthReviewServices());
  }
  if (formId === 'growth-review-form') {
    event.preventDefault();
    return WMMGrowthReview.submit(form, growthReviewServices());
  }
  if ((formId || '').startsWith('agent-')) {
    event.preventDefault();
    return agentSubmit(form);
  }
  if (formId === 'owner-report-form') {
    event.preventDefault();
    return WMMOwnerReports.submit(form);
  }
  if ((formId || '').startsWith('observational-campaign-')) {
    event.preventDefault();
    return WMMObservationalCampaign.submit(form);
  }
  if (formId === 'campaign-monitor-form') {
    event.preventDefault();
    return WMMCampaignMonitor.submit(form);
  }
  if (formId === 'campaign-schedule-form') {
    event.preventDefault();
    return campaignScheduleSubmit(form);
  }
  if (formId === 'campaign-scope-form') {
    event.preventDefault();
    return campaignSubmit(form);
  }
  if ((formId || '').startsWith('social-')) {
    event.preventDefault();
    return socialSubmit(form);
  }
  if (formId === 'play-setup-form') {
    event.preventDefault();
    return playSubmit(form);
  }
  if (formId === 'aeo-form') {
    event.preventDefault();
    return aeoSubmit(form);
  }
  if (
    ['storekit-setup-form', 'storekit-intake-form', 'storekit-disconnect-form'].includes(formId)
  ) {
    event.preventDefault();
    return storekitSubmit(form);
  }
  if ((formId || '').startsWith('attribution-')) {
    event.preventDefault();
    return attributionSubmit(form);
  }
  if (formId === 'insights-setup-form') {
    event.preventDefault();
    return saveInsights(form);
  }
  if (formId === 'insights-events-form') {
    event.preventDefault();
    return saveInsightsEvents(form);
  }
  if (
    ![
      'app-form',
      'evidence-form',
      'review-form',
      'cohort-form',
      'history-form',
      'provider-report-form',
      'release-inventory-form',
      'connection-setup-form',
      'experiment-form',
      'experiment-action-form',
      'experiment-schedule-form',
      'reference-form',
      'reference-import-form',
      'inspection-form',
      'brief-form',
      'payment-setup-form',
      'payment-action-form',
    ].includes(formId)
  )
    return;
  event.preventDefault();
  const submit = form.querySelector('[type="submit"]');
  submit.disabled = true;
  try {
    if (formId === 'release-inventory-form') {
      if (form.dataset.app !== state.app)
        throw new Error('App changed. Reopen this release in the selected workspace.');
      const values = Object.fromEntries(new FormData(form)),
        version = values.manual_version_id.trim() || values.version_id;
      if (!/^[A-Za-z0-9-]{1,80}$/.test(version))
        throw new Error('Choose a release or enter its App Store version ID.');
      return await queue('sync', {
        connection_id: form.dataset.connection,
        connection_version: Number(form.dataset.version),
        options: { operation: 'release_inventory', version_id: version },
      });
    }
    if (formId === 'payment-setup-form') return await savePaymentSource(form);
    if (formId === 'payment-action-form') return await savePaymentAction(form);
    if (formId === 'connection-setup-form') return await saveConnection(form);
    if (formId === 'reference-import-form') return await previewReferences(form);
    const data = Object.fromEntries(new FormData(form));
    if (
      ['app-form', 'evidence-form', 'experiment-form'].includes(formId) &&
      !(formId === 'app-form' && form.dataset.new === 'true' && !currentWorkspace())
    )
      automationCheckForm(form);
    if (formId === 'provider-report-form') {
      if (form.dataset.app !== state.app)
        throw new Error(
          'App changed. Close this form and reopen the report in the selected workspace.',
        );
      await queue('sync', {
        connection_id: form.dataset.connection,
        connection_version: Number(form.dataset.version),
        options: {
          operation: data.operation,
          start: data.start,
          end: data.end,
          campaign_ids: data.campaign_ids
            .split(',')
            .map((v) => v.trim())
            .filter(Boolean),
        },
      });
      return;
    }
    if (formId === 'history-form') {
      const reports = await api(
        `/api/apps/${encodeURIComponent(state.app)}/measurement?as_of=${encodeURIComponent(data.as_of)}`,
      );
      const report = reports.find((r) => r.cohort.cohort_id === form.dataset.cohort);
      modal(
        'Historical cohort report',
        `<div class="modal-content">${status(report.status)}<p>As of ${esc(report.as_of)}</p><p>Contribution after costs: <strong>${money(report.contribution_after_acquisition_minor, report.cohort.currency)}</strong></p><pre>${json(report)}</pre></div><div class="modal-actions">${button('Close report', 'close')}</div>`,
      );
      return;
    }
    if (formId === 'app-form') await saveApp(data, form.dataset.new === 'true', form);
    if (formId === 'evidence-form') await saveEvidence(data, form);
    if (formId === 'review-form') await api(`/api/apps/${state.app}/reviews`, data);
    if (formId === 'cohort-form') await api(`/api/apps/${state.app}/cohorts`, cohortPayload(data));
    if (formId === 'experiment-form') await saveExperiment(form);
    if (formId === 'experiment-action-form') await saveExperimentAction(form);
    if (formId === 'experiment-schedule-form') await saveExperimentSchedule(form);
    if (formId === 'reference-form') await saveReference(form);
    if (formId === 'inspection-form') await saveInspection(form);
    if (formId === 'brief-form') await saveBrief(form);
    await initialize();
    $('#modal').close();
    toast('Saved with source and workspace history.');
  } catch (error) {
    showActionError(error);
  } finally {
    submit.disabled = false;
  }
}

async function saveApp(data, isNew, form) {
  let id = data.id.trim();
  if (isNew && !id) {
    const base =
      data.name
        .normalize('NFKD')
        .replace(/\p{M}/gu, '')
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .replace(/^-|-$/g, '') || 'app';
    const taken = new Set((state.boot?.apps ?? []).map((app) => app.id));
    id = base.slice(0, 60).replace(/-$/, '');
    for (let next = 2; taken.has(id); next++) {
      const suffix = `-${next}`;
      id = base.slice(0, 60 - suffix.length).replace(/-$/, '') + suffix;
    }
  }
  delete data.id;
  const previous = isNew ? {} : state.workspace.app.data;
  await api('/api/apps', {
    id,
    data: { ...previous, ...data },
    version: isNew ? null : Number(form.dataset.manifestVersion),
  });
  state.app = id;
  if (isNew) state.view = 'overview';
}

async function saveEvidence(data, form) {
  const id = form.dataset.id,
    previous = state.workspace.records.find((r) => r.id === id);
  const title = data.title,
    source = data.source;
  delete data.title;
  delete data.source;
  if (form.dataset.kind === 'readiness') saveJourneyFields(data);
  if (form.dataset.worksheet) {
    const mode = form.dataset.worksheet;
    if (mode === 'asa') {
      for (const key of [
        'taps',
        'paid',
        'contribution_per_payer_minor',
        'non_media_cost_per_tap_minor',
        'owner_cpt_cap_minor',
        'acquisition_share',
      ])
        data[key] = Number(data[key]);
      for (const key of ['mature', 'counts_verified', 'contribution_verified'])
        data[key] = data[key] === 'true';
    } else {
      for (const key of ['mention', 'citation', 'correct_citation'])
        data[key] = data[key] === 'true';
      data.status = 'ok';
    }
    data.app_id = state.app;
    data.source_ref = source;
    const analysis = {
      app_id: state.app,
      as_of: new Date().toISOString(),
      [mode]: mode === 'asa' ? data : [data],
    };
    return api(`/api/apps/${state.app}/records`, {
      kind: 'acquisition',
      title,
      source,
      data: { analysis },
    });
  }
  for (const key of Object.keys(data)) {
    if (booleanFields.has(key)) data[key] = data[key] === 'true';
    if (numberFields.has(key)) data[key] = Number(data[key]);
    if (key === 'analysis') data[key] = JSON.parse(data[key]);
  }
  await api(`/api/apps/${form.dataset.app}/records`, {
    id: id || undefined,
    version: previous?.version,
    manifest_version: Number(form.dataset.manifestVersion),
    kind: form.dataset.kind,
    title,
    source,
    data: { ...previous?.data, ...data },
  });
}

async function handleAction(node) {
  if (node.dataset.action === 'agreement-report') return WMMAgreement.report();
  if (node.dataset.action?.startsWith('publication-'))
    return WMMPublicationUI.action(node, growthReviewServices());
  if (node.dataset.action.startsWith('veditor-'))
    return WMMVideoEditor.action(node, growthReviewServices());
  if (node.dataset.action.startsWith('studio-'))
    return WMMStudio.action(node, growthReviewServices());
  if (node.dataset.action.startsWith('drive-'))
    return WMMDrive.action(node, growthReviewServices());
  if (node.dataset.action.startsWith('packaging-'))
    return WMMPackaging.action(node, growthReviewServices());
  if (node.dataset.action.startsWith('discovery-'))
    return WMMDiscovery.action(node, growthReviewServices());
  if (node.dataset.action.startsWith('oresearch-'))
    return WMMOrganicResearch.action(node, growthReviewServices());
  if (node.dataset.action.startsWith('opolicy-'))
    return WMMOrganicPolicy.action(node, growthReviewServices());
  if (node.dataset.action.startsWith('media-'))
    return WMMMedia.action(node, growthReviewServices());
  if (node.dataset.action.startsWith('standing-'))
    return WMMCompleteAutomation.action(node, growthReviewServices());
  if (node.dataset.action === 'retry-workspace') return refresh();
  if (!currentWorkspace() && !['reload', 'close', 'add-app'].includes(node.dataset.action))
    return toast('Wait for this app to load, then try again.');
  if (node.dataset.action.startsWith('onesignal-'))
    return WMMOneSignal.action(node, growthReviewServices());
  if (node.dataset.action.startsWith('apple-analytics-'))
    return WMMAppleAnalytics.action(node, growthReviewServices());
  if (node.dataset.action.startsWith('control-'))
    return WMMAgentControl.action(node, growthReviewServices());
  if (node.dataset.action.startsWith('growth-'))
    return WMMGrowthReview.action(node, growthReviewServices());
  if (node.dataset.action.startsWith('subscription-plan-'))
    return WMMSubscriptionAuthoring.action(node, growthReviewServices());
  if (node.dataset.action.startsWith('funnel-'))
    return WMMFunnels.action(node, growthReviewServices());
  if (node.dataset.action.startsWith('customer-'))
    return WMMCustomerWorkflow.action(node, growthReviewServices());
  if (node.dataset.action.startsWith('goal-')) return goalAction(node);
  if (node.dataset.action.startsWith('agent-')) return agentAction(node);
  if (node.dataset.action.startsWith('owner-report-')) return WMMOwnerReports.action(node);
  if (node.dataset.action.startsWith('observational-campaign-'))
    return WMMObservationalCampaign.action(node);
  if (node.dataset.action.startsWith('campaign-monitor-')) return WMMCampaignMonitor.action(node);
  if (node.dataset.action.startsWith('social-')) return socialAction(node);
  if (node.dataset.action.startsWith('play-')) return playAction(node);
  if (node.dataset.action.startsWith('setup-')) return setupAction(node);
  if (node.dataset.action.startsWith('subscriptions-')) return subscriptionAction(node);
  if (node.dataset.action.startsWith('followup-')) return followupAction(node);
  if (node.dataset.action === 'rerun-report') {
    const job = state.workspace.jobs.find((j) => j.id === node.dataset.id);
    if (!job) throw new Error("Reload this app's saved reports.");
    if (['play_releases', 'play_subscriptions'].includes(job.data.options?.operation))
      return playRetry(job);
    return reportForm(job.data.connection_id, job.data.options);
  }
  const action = node.dataset.action,
    id = node.dataset.id;
  if (action === 'measurement-inspect') return measurementIntegrityInspect();
  if (action === 'measurement-download')
    return download(`${state.app}-payment-comparison.json`, state.workspace.measurement_integrity);
  if (action === 'measurement-connections') {
    $('#modal').close();
    state.view = 'connections';
    return render();
  }
  if (action === 'first-post-open') return firstMeasuredPost();
  if (action === 'first-post-evidence') {
    const study = ruleStudySelection();
    if (!study) throw new Error('Select the study again to review its evidence.');
    return WMMObservationalCampaign.openBoundStudy(study.binding);
  }
  if (action === 'first-post-results') {
    const study = selectedMeasuredPost();
    if (!study.report) throw new Error('Refresh the study report first.');
    state.ruleStudy = study;
    return guidedNavigate('results', '#results-decision-heading');
  }
  if (action === 'next-answer') return nextAnswer();
  if (action === 'automation-rules-load' || action === 'automation-rules-save')
    return manageAutomationRules(node, action);
  if (action === 'automation-rules-run') return runAutomationRulePreview(node);
  if (action === 'automation-rules-history') return showAutomationVersions(node);
  if (action === 'cloud-connection-test' || action === 'cloud-connection-remove') {
    const form = node.closest('#cloud-connection-form'),
      app = form?.dataset.app;
    if (!app || state.app !== app || !form.isConnected || node.disabled) return;
    const test = action === 'cloud-connection-test';
    const controls = [...form.querySelectorAll('button')];
    if (controls.some((control) => control.disabled)) return;
    controls.forEach((control) => (control.disabled = true));
    try {
      const value = await api(
        `/api/apps/${encodeURIComponent(app)}/cloud-connection/${test ? 'test' : 'remove'}`,
        {},
      );
      if (state.app !== app || !form.isConnected) return;
      await refresh();
      if (state.app === app && state.view === 'connections')
        toast(
          test
            ? 'Cloud health check passed. No install data was sent.'
            : value.cleanup === 'REMOVED'
              ? 'Personal cloud removed. Install imports stay local.'
              : 'Local mode restored; protected token cleanup needs attention.',
        );
    } catch (error) {
      if (state.app === app && form.isConnected)
        form.querySelector('.field-error').textContent = error.message;
    } finally {
      controls.forEach((control) => (control.disabled = false));
    }
    return;
  }
  if (action === 'campaign-plan-open') return campaignPlanOpen();
  if (action === 'campaign-plan-download-md') {
    if (!state.campaignPlan) throw new Error('Open the campaign plan first.');
    return download(
      `${state.app}-campaign-plan.md`,
      WMMCampaignPlan.markdown(state.campaignPlan),
      'text/markdown',
    );
  }
  if (action === 'campaign-plan-download-json') {
    if (!state.campaignPlan) throw new Error('Open the campaign plan first.');
    return download(`${state.app}-campaign-plan.json`, state.campaignPlan);
  }
  if (action.startsWith('campaign-')) return campaignAction(node);
  if (action === 'next-answer-workflow') {
    $('#modal').close();
    state.view = 'workflow';
    return render();
  }
  if (action === 'next-answer-results') {
    $('#modal').close();
    state.view = 'results';
    return render();
  }
  if (action === 'next-answer-publishing') {
    $('#modal').close();
    return guidedNavigate('connections', '#publication-heading');
  }
  if (action === 'first-post-page') return firstMeasuredPost(Number(node.dataset.offset));
  if (action === 'first-post-report-pdf') {
    const { report } = selectedMeasuredPost();
    if (!report) throw new Error('Reopen the study to load its report.');
    return WMMObservationalCampaign.pdf(report, node);
  }
  if (action === 'first-post-import') return installImportForm(selectedMeasuredPost().link);
  if (action === 'first-post-brief') {
    const { link } = selectedMeasuredPost();
    const analysis = (state.workspace.analyses || []).find(
      (a) =>
        a.source_status === 'CURRENT' &&
        (a.id === link.study.creative_id ||
          a.current?.data?.reference_id === link.study.creative_id),
    );
    if (analysis)
      return briefForm(null, null, {
        analysis_id: analysis.id,
        objective: `${link.study.hypothesis} Use one call to action: ${link.url}`,
      });
    const listing = (state.workspace.records || []).find(
      (row) => row.kind === 'store' && row.id === link.study.creative_id,
    );
    if (!listing)
      throw new Error(
        'Choose a current creative inspection or saved store listing observation as the study’s creative reference.',
      );
    return modal(
      'Review acquisition draft outline',
      `<div class="modal-content">
      <h3>${esc(link.study.name)}</h3><p>Hypothesis: ${esc(link.study.hypothesis)}</p>
      <p>Audience: ${esc(state.workspace.app.data.audience || 'Confirm your audience')}</p>
      <p>Evidence: ${esc(listing.title)} · ${esc(listing.hash || 'Fingerprint unavailable')}</p>
      <p>Use one claim you can demonstrate in the current app. Confirm the exact copy, proof and destination during review.</p>
      <label class="field">One call to action<input readonly value="${esc(link.url)}"></label>
      ${button('Prepare tagged draft', 'first-post-publishing')}</div>`,
      'DRAFT OUTLINE',
    );
  }
  if (action === 'first-post-publishing') {
    const current = selectedMeasuredPost();
    if (!current.destination)
      throw new Error('Choose the destination for this study before opening a draft.');
    if (current.link.study.source === 'facebook') return campaignOpen(node, current);
    guidedNavigate('connections', '#publication-heading');
    return WMMPublicationUI.action(
      { dataset: { action: 'publication-load', fromStudy: 'true' } },
      growthReviewServices(),
    );
  }
  if (action === 'mmp-connections')
    return guidedNavigate('connections', '#mmp-connections-heading');
  if (action === 'install-import-open') return installImportForm();
  if (action === 'install-import-detect') {
    const form = document.getElementById('install-import-form');
    if (!form) throw new Error('Open the install import form first.');
    return installImportDetect(form);
  }
  if (action === 'install-import-template')
    return download('mmp-install-template.csv', WMMMmpImport.templateCsv(), 'text/csv');
  if (action === 'install-import-confirm') return installImportConfirm(node);
  if (action === 'install-report') return installReportOpen(id, node.dataset.day);
  if (action.startsWith('activity-')) return activityAction(node);
  if (action.startsWith('guided-')) return guidedAction(node);
  if (action.startsWith('automation-')) return automationAction(node);
  if (action.startsWith('spira-')) return spiraAction(node);
  if (action.startsWith('capability-')) return capabilityAction(node);
  if (action.startsWith('spytok-')) return spyTokAction(node);
  if (action.startsWith('automatic-')) return automaticPreparationAction(node);
  if (action.startsWith('storekit-')) return storekitAction(node);
  if (action.startsWith('attribution-')) return attributionAction(node);
  if (action.startsWith('insights-')) return insightsAction(node);
  if (action.startsWith('payment-')) return paymentAction(node);
  if (action.startsWith('experiment-')) return handleExperiment(node);
  if (action.startsWith('ranking-')) return rankingAction(node);
  if (action.startsWith('production-')) return productionAction(node);
  if (action.startsWith('render-')) return renderingAction(node);
  if (action.startsWith('acq-')) return acquisitionAction(node);
  if (action.startsWith('aeo-')) return aeoAction(node);
  if (action.startsWith('reference-')) return referenceAction(node);
  const simple = {
    'telemetry-open-job': () => WMMTelemetry.openResult(node, growthReviewServices()),
    reload: initialize,
    close: () => $('#modal').close(),
    'edit-app': () => appForm(false),
    'add-app': () => appForm(true),
    'run-all': () => queue('pipeline', { stage: 0 }),
    'run-stage': () => queue('pipeline', { stage: Number(id) }),
    stage: () => openStage(id),
    record: () => openRecord(id),
    job: () => openJob(id),
    provider: () => connectionSetup(id),
    upload: () => $('#asset-file').click(),
    restore: () => $('#restore-file').click(),
    'add-evidence': () => evidenceForm(node.dataset.kind || 'readiness'),
    'add-connection': () =>
      evidenceForm('connection', null, {
        provider: id,
        env_ref: `GROWTH_${state.app.toUpperCase().replaceAll('-', '_')}_${id.toUpperCase()}_TOKEN`,
      }),
    sync: () => queue('sync', { connection_id: id }),
    'prepare-review': prepareReview,
    review: () => openReview(id),
  };
  if (simple[action]) return simple[action]();
  if (action === 'disconnect-connection') return disconnectForm(id);
  if (action === 'confirm-disconnect') {
    const result = await api(`/api/apps/${state.app}/connections/${id}/disconnect`, {
      version: Number(node.dataset.version),
    });
    $('#modal').close();
    await refresh();
    return toast(
      result.cleanup === 'PRIOR_LOCAL_KEY_CLEANUP_REQUIRED'
        ? 'Connection disabled; protected key cleanup needs attention. Use Disconnect locally again to remove it. Provider revocation was not performed.'
        : 'Local access removed. Provider key revocation was not performed.',
    );
  }
  if (action === 'release-select') return selectPromotionRelease(node);
  if (action === 'release-inventory') return releaseForm(id);
  if (action === 'provider-report') return reportForm(id);
  if (action === 'download-report')
    return download(
      `${state.app}-provider-report.json`,
      state.workspace.jobs.find((j) => j.id === id).result,
    );
  if (action === 'define-cohort') return cohortForm();
  if (action === 'import-events') {
    $('#event-file').dataset.cohort = id;
    $('#event-file').dataset.app = state.app;
    return $('#event-file').click();
  }
  if (action === 'event-template')
    return download(
      'event-import-template.csv',
      'provider,event_id,type,subject_id,occurred_at,amount_minor,currency,related_event_id,source\n',
      'text/csv',
    );
  if (action === 'ledger-report')
    return download(
      `${state.app}-${id}-report.json`,
      state.workspace.ledger.find((r) => r.cohort.cohort_id === id),
    );
  if (action === 'ledger-covered') {
    const app = state.app;
    const workspace = state.workspace;
    const current = workspace.ledger.find((r) => r.cohort.cohort_id === id);
    const cutoff = current?.cohort.economics?.coverage_through;
    if (!cutoff || !Number.isFinite(Date.parse(cutoff)) || Date.parse(cutoff) > Date.now())
      throw new Error(
        'Supply a completed, past coverage timestamp before viewing its economics snapshot.',
      );
    const reports = await api(
      `/api/apps/${encodeURIComponent(state.app)}/measurement?as_of=${encodeURIComponent(cutoff)}`,
    );
    if (state.app !== app || state.workspace !== workspace) return;
    const covered = reports.find((r) => r.cohort.cohort_id === id);
    if (!covered) throw new Error('The covered cohort report is unavailable. Refresh and retry.');
    state.workspace.ledger = state.workspace.ledger.map((r) =>
      r.cohort.cohort_id === id ? covered : r,
    );
    render();
    return;
  }
  if (action === 'ledger-history') return historicalForm(id);
  if (action === 'export')
    return serverDownload(
      `/api/apps/${encodeURIComponent(state.app)}/export`,
      `${state.app}-snapshot.json`,
    );
  if (action === 'cancel-job') {
    await api(`/api/apps/${state.app}/jobs/${id}/cancel`, {});
    await refresh();
    return openJob(id);
  }
  if (action === 'download-packet') {
    const job = state.workspace.jobs.find((j) => j.id === node.dataset.job);
    return download(
      `${state.app}-stage-${node.dataset.stage}.json`,
      job.result.outputs.find((o) => o.stage === Number(node.dataset.stage)).packet,
    );
  }
  if (action === 'download-review')
    return download(
      `${state.app}-review.json`,
      state.workspace.approvals.find((r) => r.id === id),
    );
  if (action === 'record-review') {
    const review = state.workspace.approvals.find((r) => r.id === id);
    await api(`/api/apps/${state.app}/reviews/${id}/record`, { hash: review.hash });
    await refresh();
    return openReview(id);
  }
}

export { formSubmit, saveApp, saveEvidence, handleAction };
