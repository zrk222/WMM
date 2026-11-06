/* Private owner controls for one-post campaign attribution. */
const WMMObservationalCampaign = (() => {
  let active;

  function identity() {
    const w = state.workspace;
    return JSON.stringify([state.app, w?.app?.version, w?.identity?.principal, state.boot?.csrf]);
  }

  function valid(task) {
    return active === task && task.identity === identity() && task.node?.isConnected && $('#modal').open;
  }

  function call(task, operation, body) {
    return api('/api/apps/' + encodeURIComponent(task.app) + '/observational-campaign/' + operation, body);
  }

  function field(name, label, type='text', extra='') {
    return '<label class="field">' + label + '<input required name="' + name + '" type="' + type + '" ' + extra + '></label>';
  }

  function panel(task, content) {
    modal('Measure one organic post', '<div id="observational-campaign-panel" class="modal-content">' +
      content + '<p id="observational-campaign-status" role="status"></p>' +
      '<button type="button" class="button" data-action="observational-campaign-pdf" id="observational-campaign-pdf" hidden>Save private report as PDF</button>' +
      '<pre id="observational-campaign-receipt" hidden></pre></div>');
    task.node = $('#observational-campaign-panel');
  }

  async function open(offset=0) {
    const task = active = {app:state.app, version:state.workspace?.app?.version, identity:identity(), studies:[]};
    panel(task, '<p>Loading saved studies…</p>');
    try {
      const saved = await call(task, 'history', {offset});
      if (!valid(task)) return;
      task.studies = saved.records.filter(row => row.kind === 'REGISTERED').map(row => row.data);
      const rows = task.studies.map((study, i) =>
        '<p>' + esc(study.study_id) + ' · app version ' + esc(study.app_version) + ' ' +
        button('Open study', 'observational-campaign-study', 'data-id="' + i + '"') + '</p>').join('');
      panel(task, '<p>Prepare a tagged link, then count eligible landing visits and linked registrations for a fixed window. Launch approval is separate.</p>' +
        '<h3>Saved studies</h3>' + (rows || '<p>No registered studies on this page.</p>') +
        (saved.records.length === saved.limit ? button('Older activity','observational-campaign-page','data-id="' + (offset + saved.limit) + '"') : '') +
        '<details><summary>Register a study</summary><form id="observational-campaign-register">' +
        field('name','Study name','text','maxlength="120"') + field('hypothesis','What will you learn?','text','maxlength="1000"') +
        '<label class="field">Channel<select name="source"><option value="facebook">Facebook</option><option value="instagram">Instagram</option><option value="tiktok">TikTok</option><option value="youtube">YouTube</option></select></label>' +
        field('creative_id','Creative reference','text','pattern="[A-Za-z0-9_-]{1,128}"') +
        field('landing_path','Landing path on your app website','text','value="/" maxlength="1024"') +
        field('starts_at','Starts (local time)','datetime-local') + field('ends_at','Ends (local time)','datetime-local') +
        field('landing_event','Landing event in your source','text','maxlength="128"') +
        field('registration_event','Registration event in your source','text','maxlength="128"') +
        '<button class="button primary" type="submit">Save study</button></form></details>');
    } catch (error) {
      if (valid(task)) $('#observational-campaign-status').textContent = error.message;
    }
  }

  function showStudy(task, study) {
    task.study = study;
    task.report = null;
    panel(task, '<p>Study ' + esc(study.study_id) + '</p>' +
      button('Preview tagged link', 'observational-campaign-link') +
      button('Read results', 'observational-campaign-report') +
      button('All studies', 'observational-campaign-open') +
      ['ingest','correct'].map(operation => {
        const label = operation === 'ingest' ? 'Import a private source batch' : 'Append a correction';
        return '<details><summary>' + label + '</summary><form id="observational-campaign-' + operation + '">' +
          '<label class="field">Evidence JSON<textarea required name="payload" maxlength="524288"></textarea></label>' +
          '<button class="button" type="submit">' + label + '</button></form></details>';
      }).join(''));
  }

  function showResult(task, result) {
    const node = $('#observational-campaign-receipt');
    node.hidden = false;
    node.textContent = JSON.stringify(result, null, 2);
    let message = 'Receipt ready.';
    if (result.url) message = 'Tagged link prepared. Review the exact link before scheduling.';
    task.report = result.schema === 'growth.observational-campaign-report.v1' ? result : null;
    $('#observational-campaign-pdf').hidden = !task.report;
    if (task.report) {
      message = 'Observed landing subjects: ' + (result.landing_subjects ?? 'Unavailable') +
        '. Linked registrations: ' + (result.linked_registration_subjects ?? 'Unavailable') +
        '. Source-reported attribution.';
    }
    $('#observational-campaign-status').textContent = message;
  }

  function pdf(report) {
    const model = WMMPageReports.model(state);
    WMMPageReports.openReport({
      ...model,
      title:'Organic campaign attribution',
      purpose:'Review tagged visits and linked registrations in the saved source records.',
      loaded_at:report.as_of,
      next_step:'Review source coverage before comparing this campaign with another.',
      cohorts:[],
      metrics:[
        {label:'Tagged landing subjects',value:report.landing_subjects,unit:'subjects',source:'Saved landing observations'},
        {label:'Linked registration subjects',value:report.linked_registration_subjects,unit:'subjects',source:'Saved source-scoped registration observations'},
      ],
      notes:['Window: ' + report.starts_at + ' to ' + report.ends_at,
        'Study hash: ' + report.study_hash, 'Source hash: ' + report.source_hash,
        'Coverage: ' + JSON.stringify(report.coverage), ...report.limits],
    }, window);
  }

  function binding(task) {
    return {study_id:task.study.study_id, study_hash:task.study.study_hash, manifest_version:task.version};
  }

  async function perform(task, control, work) {
    if (!task || !valid(task) || task.pending) return;
    task.pending = true;
    if (control) control.disabled = true;
    try { await work(); }
    catch (error) {
      if (valid(task)) $('#observational-campaign-status').textContent = error.message;
    } finally {
      task.pending = false;
      if (control) control.disabled = false;
    }
  }

  function action(node) {
    const operation = node.dataset.action.slice('observational-campaign-'.length);
    if (operation === 'open') return open();
    const task = active;
    if (!task || !valid(task) || task.pending) return;
    if (operation === 'page') return open(Number(node.dataset.id));
    if (operation === 'study') return showStudy(task, task.studies[Number(node.dataset.id)]);
    if (operation === 'pdf' && task.report) {
      return perform(task, node, () => pdf(task.report));
    }
    if (operation !== 'link' && operation !== 'report') return;
    return perform(task, node, async () => {
      const result = await call(task, operation, binding(task));
      if (valid(task)) showResult(task, result);
    });
  }

  function submit(form) {
    const task = active;
    const operation = form.id.slice('observational-campaign-'.length);
    return perform(task, form.querySelector('button[type=submit]'), async () => {
      const fields = Object.fromEntries(new FormData(form));
      if (operation === 'register') {
        for (const field of ['starts_at','ends_at']) fields[field] = new Date(fields[field]).toISOString();
        const key = JSON.stringify(fields);
        if (task.registration?.key !== key) {
          task.registration = {key, request_id:crypto.randomUUID(), id:crypto.randomUUID()};
        }
        const result = await call(task, operation, {request_id:task.registration.request_id,
          manifest_version:task.version, definition:{...fields, id:task.registration.id, attribution_model:'FIRST_TOUCH'}});
        if (valid(task)) showStudy(task, result);
      } else if (operation === 'ingest' || operation === 'correct') {
        const key = operation === 'ingest' ? 'batch' : 'correction';
        const result = await call(task, operation, {...binding(task), [key]:JSON.parse(fields.payload)});
        if (valid(task)) showResult(task, result);
      }
    });
  }

  return {action, submit};
})();
