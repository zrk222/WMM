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
  return `<div class="section-heading"><div><h2>Render an original video</h2><p>Choose actual app screens or a Hypit text composition from the same approved brief. Both create a local MP4 without a video-generation API.</p></div>${button("Render a video","render-create")}</div><section class="panel"><h3>App screens</h3>${status(media.capability.status)}<p class="description">Silent H.264 MP4 with approved screens and captions; ${esc(media.capability.script_support||"verify native caption support")}</p>${media.capability.status!=="READY"?notice(media.capability.repair||"Check local native tools.","warning"):""}<h3>Hypit caption composition</h3>${status(hypit.capability?.status||"UNAVAILABLE")}<p>Creates a title and timed approved text. It does not include app screens, generated footage or narration. ${esc(hypit.capability?.repair||"Prepare the optional local Hypit runtime.")}</p><p>Preview every scene before use. Interrupted Hypit attempts retain their build identity for inspection; repeating a render request does not restart uncertain work.</p>${jobs}${files||"<p>No rendered videos yet. Prepare a current short-video brief, then choose its renderer and frame shape.</p>"}</section>`;
}

function renderForm() {
  const briefs=(state.workspace.briefs||[]).filter(b=>b.evidence_status==="CURRENT"&&b.current.data.definition.channel==="SHORT_VIDEO");
  if(!briefs.length)return modal("Prepare a video brief first",`<div class="modal-content">${notice("A video needs current approved claims, actual rights-cleared screens and a tested route. Your other work is preserved.")}</div><div class="modal-actions">${button("Prepare original brief","production-prepare")}</div>`);
  const choices=briefs.map(b=>({id:b.id,title:b.current.data.definition.objective+" · "+b.current.data.definition.duration_seconds+" seconds"}));
  modal("Render an original video",`<form id="render-form" data-app="${esc(state.app)}" data-key="${crypto.randomUUID()}"><div class="modal-content">${notice("App screens creates a silent screen-and-caption video. Hypit creates a title and timed text composition using its installed local runtime. Both preserve the selected brief; preview and review the result before publishing.")}<div class="form-grid">${choiceField("renderer",[{id:"NATIVE_FFMPEG",title:"App screens and captions"},{id:"HYPIT_LOCAL",title:"Hypit caption composition"}])}${choiceField("brief_id",choices)}${choiceField("shape",[{id:"PORTRAIT",title:"Portrait · 720 × 1280"},{id:"LANDSCAPE",title:"Landscape · 1280 × 720"}])}</div><div class="field-error" id="form-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit">Queue local render</button></div></form>`);
}

function openRender(id) {
  const row=renderRows().find(r=>r.id===id);if(!row)throw new Error("Video is unavailable in this app.");
  const d=row.data,request=videoRequest(row),base=`/api/apps/${encodeURIComponent(state.app)}/${renderEndpoint(d.renderer)}/${encodeURIComponent(id)}`;
  modal("Review rendered video",`<div class="modal-content">${notice("Check every screen, caption, language and final CTA. This local artifact has not been published or visually approved.")}${row.status!=="CURRENT"?notice("Source proof or media changed. Repair the current brief and render a fresh version before publication.","warning"):""}<video class="render-preview" controls playsinline preload="metadata" src="${base}/preview" aria-label="Original captioned marketing video"></video><p id="video-error" class="field-error" role="alert"></p><h3>Exact original captions</h3>${request.captions.map(t=>`<p>${esc(t).replaceAll("\n","<br>")}</p>`).join("")}<details><summary>Source binding and decoded video receipt</summary><pre>${json(row)}</pre></details><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><a class="button" download href="${base}/download">Download MP4</a>${button("Download render receipt","render-receipt",`data-id="${esc(id)}"`)}</div>`);
  $("#modal video").addEventListener("error",()=>{$("#video-error").textContent="Video could not load. Check the saved artifact in Activity, then render a fresh version if it is missing or changed.";});
}

async function renderingAction(node) {
  const action=node.dataset.action,id=node.dataset.id;
  if(action==="render-create")return renderForm();
  if(action==="render-open")return openRender(id);
  if(action==="render-receipt")return download(`${state.app}-${id}-render.json`,renderRows().find(r=>r.id===id));
  if(action==="render-cancel"){
    await api(`/api/apps/${state.app}/jobs/${id}/cancel`,{});await refresh();return toast("Render cancelled. Source evidence remains saved.");
  }
  throw new Error("Unknown render action");
}

document.addEventListener("submit",async event=>{
  const form=event.target;if(form.id!=="render-form")return;
  event.preventDefault();const submit=form.querySelector('[type="submit"]');submit.disabled=true;
  try {
    if(form.dataset.app!==state.app)throw new Error("App changed. Reopen the render form in the selected app.");
    const data=Object.fromEntries(new FormData(form)),endpoint=renderEndpoint(data.renderer);delete data.renderer;
    data.brief_hash=state.workspace.briefs.find(b=>b.id===data.brief_id).current.hash;
    await api(`/api/apps/${form.dataset.app}/production/${endpoint}`,{data,request_key:form.dataset.key});
    $("#modal").close();await refresh();toast("Video queued. The render status will update here; publication remains unexecuted.");
  } catch(error){$("#form-error").textContent=error.message;}finally{submit.disabled=false;}
});
