/* Private owner controls for one-post campaign attribution. */
const WMMObservationalCampaign = (() => {
  let active;

  function identity() {
    const w = state.workspace;
    return JSON.stringify([state.app, w?.app?.version, w?.identity?.principal,
      w?.identity?.expires_at_epoch, state.boot?.csrf]);
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

  function localInput(date) {
    const pad = value => String(value).padStart(2, '0');
    return date.getFullYear() + '-' + pad(date.getMonth() + 1) + '-' + pad(date.getDate()) +
      'T' + pad(date.getHours()) + ':' + pad(date.getMinutes());
  }

  function windowDefaults() {
    const start = new Date(Date.now() + 3600 * 1000);
    const end = new Date(Date.now() + 10 * 86400 * 1000);
    return {start: localInput(start), end: localInput(end)};
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
      const window = windowDefaults();
      const rows = task.studies.map((study, i) =>
        '<p>' + esc(study.study_id) + ' · app version ' + esc(study.app_version) + ' ' +
        button('Open study', 'observational-campaign-study', 'data-id="' + i + '"') + '</p>').join('');
      panel(task, '<p>Prepare a tagged link, then count eligible landing visits and linked registrations for a fixed window. Launch approval is separate.</p>' +
        '<h3>Saved studies</h3>' + (rows || '<p>No registered studies on this page.</p>') +
        (saved.records.length === saved.limit ? button('Older activity','observational-campaign-page','data-id="' + (offset + saved.limit) + '"') : '') +
        '<details><summary>Register a study</summary><form id="observational-campaign-register">' +
        field('name','Study name','text','maxlength="120"') + field('hypothesis','What will you learn?','text','maxlength="1000"') +
        '<label class="field">Channel<select name="source"><option value="facebook">Facebook</option><option value="instagram">Instagram</option><option value="tiktok">TikTok</option><option value="youtube">YouTube</option></select></label>' +
        field('creative_id','Creative reference','text','pattern="[A-Za-z0-9_-]{1,128}" list="observational-creative-options"') +
        '<datalist id="observational-creative-options">' +
        (state.workspace.analyses||[]).filter(row=>row.source_status==='CURRENT').map(row=>
          '<option value="' + esc(row.id) + '">' + esc(row.current?.data?.format_family||'Saved creative inspection') + '</option>').join('') +
        (state.workspace.records||[]).filter(row=>row.kind==='store').map(row=>
          '<option value="' + esc(row.id) + '">' + esc(row.title||'Saved store listing evidence') + '</option>').join('') +
        '</datalist><p class="description">Choose a saved creative inspection or store listing observation, or enter your own creative reference.</p>' +
        field('landing_path','Landing path on your app website','text','value="/" maxlength="1024"') +
        field('starts_at','Starts (local time)','datetime-local','value="' + window.start + '"') +
        field('ends_at','Ends (local time)','datetime-local','value="' + window.end + '"') +
        field('collector_source_id','Collector source ID','text','pattern="[A-Za-z0-9_-]{1,64}" maxlength="64"') +
        '<p class="description">Use the non-secret source ID that appears in your analytics export. Both events must come from this collector. This is separate from the social channel.</p>' +
        field('landing_event','Landing event in your source','text','maxlength="128"') +
        field('registration_event','Registration event in your source','text','maxlength="128"') +
        '<p class="description">The window defaults to starting in one hour and ending in ten days. Adjust both before saving; the source events must be the names your export actually records.</p>' +
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
        const formId = operation === 'ingest' ? 'observational-campaign-ingest' : 'observational-campaign-correct';
        return '<details><summary>' + label + '</summary><form id="' + formId + '">' +
          '<label class="field">Evidence JSON<textarea required name="payload" maxlength="524288"></textarea></label>' +
          '<button class="button" type="submit">' + label + '</button></form></details>';
      }).join(''));
  }

  function checkpointModel(report) {
    const c=report.checkpoint||{state:'SOURCE_NOT_DECLARED',coverage_issues:{}};
    const guidance={
      COLLECTING:['Still collecting','After the fixed window ends, import the final export for both events.','Decide when to measure before looking at the result.'],
      SOURCE_NOT_DECLARED:['Collector was not declared','Use a new study with a named collector for a complete read.','Name the source before the test starts.'],
      COVERAGE_INCOMPLETE:['Coverage incomplete','Import or reconcile the final evidence from the declared collector.','Missing evidence is not a zero.'],
      NO_ELIGIBLE_LANDINGS:['Complete coverage, no eligible landings','Check the tagged link and landing event before trying a new post.','A rate needs a positive denominator.'],
      DESCRIPTIVE_READY:['Ready for descriptive review','Review the linked registrations against the eligible landings before choosing a next test.','A tracked result describes this post; it does not establish lift.'],
    };
    const [title,next,rule]=guidance[c.state]||guidance.COVERAGE_INCOMPLETE;
    const names={LANDING:'Landing',REGISTRATION:'Registration'};
    const issues={MISSING_RECEIPT:'No receipt',BEFORE_CLOSE:'Receipt predates the end of the window',
      COUNT_MISMATCH:'Source total does not match the saved records',INCOMPLETE:'Source did not report complete coverage'};
    const observations=Object.entries(report.coverage||{}).flatMap(([kind,entry])=>
      (entry.sources||[]).map(source=>(names[kind]||kind)+' receipt: '+source.observed_at+
        ' · reported '+(source.reported_count??'Unknown')+' / saved '+source.stored_count));
    const gaps=Object.entries(c.coverage_issues||{}).map(([kind,issue])=>(names[kind]||kind)+': '+(issues[issue]||issue));
    const counts=c.ratio_counts;
    const ratio=c.state==='DESCRIPTIVE_READY'&&counts&&counts.eligible_landings>0?
      'Linked registration rate: '+counts.linked_registrations+' of '+counts.eligible_landings+' eligible landings ('+
        new Intl.NumberFormat(undefined,{style:'percent',maximumFractionDigits:2}).format(counts.linked_registrations/counts.eligible_landings)+').':null;
    const excluded=Object.entries(report.exclusions||{}).filter(([,count])=>count>0)
      .map(([key,count])=>key.toLowerCase().replaceAll('_',' ')+': '+count);
    return {title,next,rule,ratio,notes:[...(c.collector_source_id?['Collector: '+c.collector_source_id]:[]),
      ...gaps,...observations,...(excluded.length?['Excluded events: '+excluded.join(', ')]:[])]};
  }

  function checkpointMarkup(report) {
    const m=checkpointModel(report);
    return '<section class="next-step" aria-label="Study measurement checkpoint"><div><h3>'+esc(m.title)+'</h3>'+
      '<p><strong>What we learned:</strong> Eligible landings: '+esc(report.landing_subjects??'Unavailable')+
      '. Linked registrations: '+esc(report.linked_registration_subjects??'Unavailable')+'. '+(m.ratio?esc(m.ratio):'')+'</p>'+
      '<p><strong>Next step:</strong> '+esc(m.next)+'</p><p><strong>Rule to reuse:</strong> '+esc(m.rule)+'</p>'+
      '<details><summary>Source evidence and exclusions</summary>'+
      m.notes.map(line=>'<p>'+esc(line)+'</p>').join('')+'<p>Source hash: '+esc(report.source_hash)+'</p></details></div></section>';
  }

  function showResult(task, result) {
    const node = $('#observational-campaign-receipt');
    node.hidden = false;
    node.textContent = JSON.stringify(result, null, 2);
    let message = 'Receipt ready.';
    if (result.url) message = 'Tagged link prepared. Review the exact link before scheduling.';
    task.report = result.schema === 'growth.observational-campaign-report.v1' ? result : null;
    task.node.querySelector('[aria-label="Study measurement checkpoint"]')?.remove();
    if(task.report)node.insertAdjacentHTML('beforebegin',checkpointMarkup(task.report));
    $('#observational-campaign-pdf').hidden = !task.report;
    if (task.report) {
      message = 'Observed landing subjects: ' + (result.landing_subjects ?? 'Unavailable') +
        '. Linked registrations: ' + (result.linked_registration_subjects ?? 'Unavailable') +
        '. Source-reported attribution.';
    }
    $('#observational-campaign-status').textContent = message;
  }

  function pdf(report, trigger) {
    const model = WMMPageReports.model(state), checkpoint=checkpointModel(report);
    WMMPageReports.openReport({
      ...model,
      title:'Organic campaign attribution',
      purpose:'Review tagged visits and linked registrations in the saved source records.',
      loaded_at:report.as_of,
      next_step:checkpoint.next,
      cohorts:[],
      metrics:[
        {label:'Tagged landing subjects',value:report.landing_subjects,unit:'subjects',source:'Saved landing observations'},
        {label:'Linked registration subjects',value:report.linked_registration_subjects,unit:'subjects',source:'Saved source-scoped registration observations'},
      ],
      notes:['Window: ' + report.starts_at + ' to ' + report.ends_at,
        'Study hash: ' + report.study_hash, 'Source hash: ' + report.source_hash,
        'What we learned: '+checkpoint.title,...(checkpoint.ratio?[checkpoint.ratio]:[]),
        'Rule to reuse: '+checkpoint.rule,...checkpoint.notes,...report.limits],
    }, window, trigger);
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
      return perform(task, null, () => pdf(task.report, node));
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

  return {action, submit, checkpointMarkup, pdf};
})();
