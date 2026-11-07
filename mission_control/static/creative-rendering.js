"use strict";
const watchedRenders=new Set();

function renderRows() {
  return [...(state.workspace.renders?.items||[]),...(state.workspace.hypit_renders?.items||[])];
}

function videoRequest(row) {
  return row.data.request||row.data.inputs.request;
}

function renderEndpoint(renderer) {
  if(renderer==="NATIVE_FFMPEG")return "renders";
  if(renderer==="HYPIT_LOCAL")return "hypit-renders";
  throw new Error("Choose one of the supported local renderers.");
}

function briefRenderState(brief) {
  const videos=renderRows().filter(r=>videoRequest(r).brief_id===brief.id&&videoRequest(r).brief_hash===brief.current.hash);
  if(videos.some(r=>r.status==="CURRENT"))return "RENDERED_LOCAL";
  return videos.length?"STALE_OR_UNAVAILABLE_VIDEO":"RENDER_NOT_RUN";
}

async function watchRender(app,id) {
  const key=app+":"+id;if(watchedRenders.has(key))return;watchedRenders.add(key);
  try {
    for(let attempt=0;attempt<120;attempt++){
      await new Promise(resolve=>setTimeout(resolve,2000));if(state.app!==app)return;
      await refresh();const job=state.workspace.jobs.find(j=>j.id===id);
      if(!job||!["RUNNING","QUEUED"].includes(job.status))return;
    }
  }catch(error){toast("Render status could not refresh: "+error.message+". Reopen Research or Activity to retry.");}
  finally{watchedRenders.delete(key);}
}

function renderingPanel() {
  const media=state.workspace.renders||{capability:{status:"UNAVAILABLE"},items:[]};
  const hypit=state.workspace.hypit_renders||{capability:{status:"UNAVAILABLE"},items:[]};
  const active=state.workspace.jobs.filter(j=>["render","hypit_render"].includes(j.action));
  for(const job of active)if(["RUNNING","QUEUED"].includes(job.status))watchRender(state.app,job.id);
  const jobs=active.map(j=>`<div class="next-step"><div><strong>Local video · ${esc(label(j.status))}</strong><p>${esc(j.result?.error||"Original captioned screens; publication remains unexecuted.")}</p>${["QUEUED","RUNNING"].includes(j.status)?button("Cancel render","render-cancel",`data-id="${esc(j.id)}"`):""}</div></div>`).join("");
  const files=renderRows().map(r=>`<div class="next-step"><div><strong>${r.data.renderer==="HYPIT_LOCAL"?"Hypit captions":"App screens"} · ${esc(label(videoRequest(r).shape))} · ${videoRequest(r).duration_seconds} seconds</strong><p>${esc(r.status)} · ${(r.data.artifact.bytes/1048576).toFixed(2)} MiB · visual review required</p>${button("Preview video","render-open",`data-id="${esc(r.id)}"`)}</div></div>`).join("");
  return `<div class="section-heading"><div><h2>Render an original video</h2><p>Choose actual app screens or a Hypit text composition from the same approved brief. Both create a local MP4 without a video-generation API.</p></div>${button("Render a video","render-create")}</div><section class="panel"><h3>Produce a finite batch</h3><p>Review exact briefs, shapes and a frame budget before creating local videos. Nothing is published.</p>${button("Review video batches","render-batch-list")}<h3>App screens</h3>${status(media.capability.status)}<p class="description">Silent H.264 MP4 with approved screens and captions; ${esc(media.capability.script_support||"verify native caption support")}</p>${media.capability.status!=="READY"?notice(media.capability.repair||"Check local native tools.","warning"):""}<h3>Hypit caption composition</h3>${status(hypit.capability?.status||"UNAVAILABLE")}<p>Creates a title and timed approved text. It does not include app screens, generated footage or narration. ${esc(hypit.capability?.repair||"Prepare the optional local Hypit runtime.")}</p><p>Preview every scene before use. Interrupted Hypit attempts retain their build identity for inspection; repeating a render request does not restart uncertain work.</p>${jobs}${files||"<p>No rendered videos yet. Prepare a current short-video brief, then choose its renderer and frame shape.</p>"}</section>`;
}

async function showCreativeBatches() {
  const app=state.app, result=await api(`/api/apps/${encodeURIComponent(app)}/production/batches/list`,{});
  if(state.app!==app)return;
  const rows=(result.items||[]).map(batch=>`<section class="next-step"><div><strong>${esc(label(batch.state))} · ${batch.variants.length} variants</strong><p>${batch.reserved_frames} frames reserved · publication not run</p><ul>${batch.variants.map(v=>`<li>${esc(label(v.request.shape))} · ${esc(label(v.status))}${v.inspection?` · ${esc(v.inspection.status)} · captions and framing need review`:''}</li>`).join('')}</ul>${['ACTIVE','BLOCKED_HOLD'].includes(batch.state)?button('Cancel batch','render-batch-cancel',`data-id="${esc(batch.id)}"`):''}</div></section>`).join('');
  modal('Video batches',`<div class="modal-content"><p>Queued videos are local. Check every caption, frame and sound before sharing. A running cancellation can retain its resource hold until the renderer stops.</p>${rows||'<p>No batches prepared yet.</p>'}<p id="form-error" role="alert"></p></div><div class="modal-actions">${button('Prepare a batch','render-batch-new')}${button('Refresh','render-batch-list')}${button('Close','close')}</div>`);
}

function creativeBatchForm() {
  const briefs=(state.workspace.briefs||[]).filter(b=>b.evidence_status==='CURRENT'&&b.current.data.definition.channel==='SHORT_VIDEO');
  if(!briefs.length)throw new Error('Prepare a current short-video brief first.');
  const choices=briefs.map(b=>`<label><input type="checkbox" name="brief" value="${esc(b.id)}"> ${esc(b.current.data.definition.objective)} · ${b.current.data.definition.duration_seconds} seconds</label>`).join('');
  modal('Prepare a video batch',`<form id="creative-batch-form" data-app="${esc(state.app)}" data-key="${crypto.randomUUID()}"><div class="modal-content"><p>Choose up to 8 distinct brief and frame-shape combinations. Videos are silent, locally rendered MP4s, with an existing 8 MiB output limit each.</p><fieldset><legend>Current briefs</legend>${choices}</fieldset><fieldset><legend>Frame shapes</legend><label><input type="checkbox" name="shape" value="PORTRAIT" checked> Portrait</label><label><input type="checkbox" name="shape" value="LANDSCAPE"> Landscape</label></fieldset><label>Run expiry <select name="hours"><option value="1">1 hour</option><option value="4">4 hours</option><option value="24">24 hours</option></select></label><p>Next you will review the exact variants and total frame allowance before queueing.</p><p id="form-error" role="alert"></p></div><div class="modal-actions"><button class="button" type="submit">Review batch</button>${button('Cancel','close')}</div></form>`);
}

async function reviewCreativeBatch(form) {
  const app=form.dataset.app, selected=new FormData(form), shapes=selected.getAll('shape'), ids=selected.getAll('brief');
  const briefs=(state.workspace.briefs||[]).filter(b=>ids.includes(b.id)&&b.evidence_status==='CURRENT');
  const variants=briefs.flatMap(b=>shapes.map(shape=>({brief_id:b.id,brief_hash:b.current.hash,shape})));
  if(!variants.length||variants.length>8)throw new Error('Choose between 1 and 8 distinct brief and shape combinations.');
  const frames=briefs.reduce((sum,b)=>sum+b.current.data.definition.duration_seconds*24*shapes.length,0);
  if(frames>11520)throw new Error('The batch exceeds the 11,520-frame active allowance.');
  const body={variants,max_total_frames:frames,runtime:'DESKTOP',expires:new Date(Date.now()+Number(selected.get('hours'))*3600000).toISOString()};
  const reviewed=await api(`/api/apps/${encodeURIComponent(app)}/production/batches/plan`,body);
  if(state.app!==app||!form.isConnected)return;
  const plan=reviewed.plan;
  modal('Review exact video batch',`<div id="creative-batch-review" class="modal-content" data-app="${esc(app)}"><p>${plan.variants.length} variants · ${plan.total_frames} frames at 24 fps · expires ${esc(plan.expires)} · local desktop</p><p>Current app, brief, claims, rights-cleared stills and source hashes are bound to this plan. Publication is separate. Each MP4 is limited to 8 MiB.</p><ol>${plan.variants.map(v=>`<li><strong>${esc(v.brief.data.definition.objective)} · ${esc(label(v.shape))}</strong><p>${v.duration_seconds} seconds · brief ${esc(v.brief_hash)}</p><ul>${v.captions.map(c=>`<li>${esc(c)}</li>`).join('')}</ul><details><summary>Bound source and cleared stills</summary><p>Source capture ${esc(v.brief.data.source.hash)}</p><ul>${v.brief.data.content.screens.map(s=>`<li>Asset ${esc(s.asset_id)} · file ${esc(s.file_id)} · SHA-256 ${esc(s.sha256)}</li>`).join('')}</ul><p>Selected claim and rights records:</p><ul>${v.brief.data.records.map(r=>`<li>${esc(r.kind)} · ${esc(r.id)} · version ${esc(r.version)}</li>`).join('')}</ul></details></li>`).join('')}</ol><p>Check captions and framing in the rendered videos; automated decoding does not approve their visual quality.</p><p id="form-error" role="alert"></p><div class="modal-actions">${button('Queue reviewed batch','render-batch-queue','', 'primary')}${button('Edit choices','render-batch-new')}${button('Cancel','close')}</div></div>`);
  $('#creative-batch-review').batch={plan:reviewed.plan_json,plan_hash:reviewed.plan_hash,request_key:form.dataset.key};
}

function renderForm(hypitBriefIds=null) {
  const briefs=(state.workspace.briefs||[]).filter(b=>b.evidence_status==="CURRENT"&&b.current.data.definition.channel==="SHORT_VIDEO"
    &&(!hypitBriefIds||hypitBriefIds.includes(b.id)));
  if(!briefs.length)return modal("Prepare a video brief first",`<div class="modal-content">${notice("A video needs current approved claims, actual rights-cleared screens and a tested route. Your other work is preserved.")}</div><div class="modal-actions">${button("Prepare original brief","production-prepare")}</div>`);
  const choices=briefs.map(b=>({id:b.id,title:b.current.data.definition.objective+" · "+b.current.data.definition.duration_seconds+" seconds"}));
  modal("Render an original video",`<form id="render-form" data-app="${esc(state.app)}" data-key="${crypto.randomUUID()}"><div class="modal-content">${notice("App screens creates a silent screen-and-caption video. Hypit creates a title and timed text composition using its installed local runtime. Both preserve the selected brief; preview and review the result before publishing.")}<div class="form-grid">${choiceField("renderer",[{id:"NATIVE_FFMPEG",title:"App screens and captions"},{id:"HYPIT_LOCAL",title:"Hypit caption composition"}],hypitBriefIds?"HYPIT_LOCAL":"")}${choiceField("brief_id",choices,hypitBriefIds&&choices.length===1?choices[0].id:"")}${choiceField("shape",[{id:"PORTRAIT",title:"Portrait · 720 × 1280"},{id:"LANDSCAPE",title:"Landscape · 1280 × 720"}])}</div><div class="field-error" id="form-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit">Queue local render</button></div></form>`);
}

function openRender(id) {
  const row=renderRows().find(r=>r.id===id);if(!row)throw new Error("Video is unavailable in this app.");
  const d=row.data,request=videoRequest(row),base=`/api/apps/${encodeURIComponent(state.app)}/${renderEndpoint(d.renderer)}/${encodeURIComponent(id)}`;
  modal("Review rendered video",`<div class="modal-content">${notice("Check every screen, caption, language and final CTA. This local artifact has not been published or visually approved.")}${row.status!=="CURRENT"?notice("Source proof or media changed. Repair the current brief and render a fresh version before publication.","warning"):""}<video class="render-preview" controls playsinline preload="metadata" src="${base}/preview" aria-label="Original captioned marketing video"></video><p id="video-error" class="field-error" role="alert"></p><h3>Exact original captions</h3>${request.captions.map(t=>`<p>${esc(t).replaceAll("\n","<br>")}</p>`).join("")}<details><summary>Source binding and decoded video receipt</summary><pre>${json(row)}</pre></details><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><a class="button" download href="${base}/download">Download MP4</a>${button("Download render receipt","render-receipt",`data-id="${esc(id)}"`)}</div>`);
  $("#modal video").addEventListener("error",()=>{$("#video-error").textContent="Video could not load. Check the saved artifact in Activity, then render a fresh version if it is missing or changed.";});
}

async function reviewHypitPlan(form,data) {
  const app=form.dataset.app,plan=await api(`/api/apps/${app}/production/hypit-plan`,{data});
  if(app!==state.app||!form.isConnected)return;
  const scene=plan.scene,issues=plan.readiness.remediation;
  modal('Review your Hypit production',`<div id="hypit-plan" class="modal-content" data-app="${esc(app)}"><p>${scene.width} × ${scene.height} · ${scene.frame_rate} fps · ${scene.duration_seconds} seconds. This preflight starts no build.</p><p>Text-density flags are advisory. Check actual frames, captions, sound and your app's call to action before accepting the result.</p><ol>${scene.scenes.map(s=>`<li>${s.start_seconds}–${s.end_seconds}s · ${s.words} words · ${s.words_per_second} words/second · ${esc(s.density_advisory)}</li>`).join('')}</ol>${issues.length?notice(issues.join(' '),'warning'):'<p>Local tools were detected. Compiler and browser readiness are checked at render time.</p>'}<h3>Reuse a matching video</h3>${plan.reuse_candidates.items.length?plan.reuse_candidates.items.map(r=>`<p>${esc(r.render_id)} · ${(r.artifact_bytes/1048576).toFixed(2)} MiB ${button('Reuse this verified artifact','render-reuse',`data-id="${esc(r.render_id)}"`)}</p>`).join(''):'<p>No matching verified artifact in this bounded search.</p>'}<p>Inspected ${plan.reuse_candidates.scanned} saved rows; ${plan.reuse_candidates.unavailable} unavailable.${plan.reuse_candidates.truncated?' Older matches may remain outside this scan.':''}</p><details><summary>Source binding and preflight details</summary><pre>${json(plan)}</pre></details><p id="form-error" role="alert"></p><div class="modal-actions">${button('Queue a new Hypit render','render-plan-queue',issues.length?'disabled':'','primary')}${button('Edit production choices','render-create')}${button('Cancel','close')}</div></div>`);
  $('#hypit-plan').production={data,source_hash:plan.source_hash,input_hash:plan.input_hash,request_key:form.dataset.key};
}

async function renderingAction(node) {
  const action=node.dataset.action,id=node.dataset.id;
  if(action==='render-batch-list')return showCreativeBatches();
  if(action==='render-batch-new')return creativeBatchForm();
  if(action==='render-batch-cancel'){
    const app=state.app;await api(`/api/apps/${encodeURIComponent(app)}/production/batches/cancel`,{batch_id:id});
    if(state.app===app)return showCreativeBatches();return;
  }
  if(action==='render-batch-queue'){
    const panel=$('#creative-batch-review');if(!panel||panel.dataset.app!==state.app)throw new Error('App changed; review the batch again.');
    if(panel.dataset.busy==='true')return;panel.dataset.busy='true';node.disabled=true;
    try {
      const app=state.app;await api(`/api/apps/${encodeURIComponent(app)}/production/batches/create`,panel.batch);
      if(state.app===app&&panel.isConnected){await refresh();await showCreativeBatches();}
    } finally {panel.dataset.busy='false';node.disabled=false;}
    return;
  }
  if(['render-reuse','render-plan-queue'].includes(action)) {
    const panel=$('#hypit-plan');if(!panel||panel.dataset.app!==state.app)throw new Error('App changed; review production again.');
    if(panel.dataset.busy==='true')return;
    panel.dataset.busy='true';node.disabled=true;
    try {
      const app=state.app,plan=panel.production;
      if(action==='render-reuse') {
        const reused=await api(`/api/apps/${app}/production/hypit-reuse`,{data:plan.data,render_id:id,source_hash:plan.source_hash});
        if(state.app!==app||!panel.isConnected)return;
        await refresh();return openRender(reused.render_id);
      }
      const current=await api(`/api/apps/${app}/production/hypit-plan`,{data:plan.data});
      if(state.app!==app||!panel.isConnected)return;
      if(current.source_hash!==plan.source_hash||current.input_hash!==plan.input_hash)throw new Error('Production changed; review the current plan before rendering.');
      await api(`/api/apps/${app}/production/hypit-renders`,{data:plan.data,request_key:plan.request_key});
      if(state.app!==app||!panel.isConnected)return;
      $('#modal').close();await refresh();toast('Hypit render queued. Inspect the saved result before using it.');
      return;
    } finally {panel.dataset.busy='false';node.disabled=false;}
  }
  if(action==="render-create")return renderForm();
  if(action==="render-open")return openRender(id);
  if(action==="render-receipt")return download(`${state.app}-${id}-render.json`,renderRows().find(r=>r.id===id));
  if(action==="render-cancel"){
    await api(`/api/apps/${state.app}/jobs/${id}/cancel`,{});await refresh();return toast("Render cancelled. Source evidence remains saved.");
  }
  throw new Error("Unknown render action");
}

document.addEventListener("submit",async event=>{
  const form=event.target;
  if(form.id==='creative-batch-form'){
    event.preventDefault();const submit=form.querySelector('[type="submit"]');submit.disabled=true;
    try {if(form.dataset.app!==state.app)throw new Error('App changed; reopen the batch form.');await reviewCreativeBatch(form);}
    catch(error){const target=$('#form-error');if(target)target.textContent=error.message;}finally{submit.disabled=false;}
    return;
  }
  if(form.id!=="render-form")return;
  event.preventDefault();const submit=form.querySelector('[type="submit"]');submit.disabled=true;
  try {
    if(form.dataset.app!==state.app)throw new Error("App changed. Reopen the render form in the selected app.");
    const data=Object.fromEntries(new FormData(form)),endpoint=renderEndpoint(data.renderer);delete data.renderer;
    data.brief_hash=state.workspace.briefs.find(b=>b.id===data.brief_id).current.hash;
    if(endpoint==='hypit-renders')return await reviewHypitPlan(form,data);
    await api(`/api/apps/${form.dataset.app}/production/${endpoint}`,{data,request_key:form.dataset.key});
    $("#modal").close();await refresh();toast("Video queued. The render status will update here; publication remains unexecuted.");
  } catch(error){$("#form-error").textContent=error.message;}finally{submit.disabled=false;}
});
