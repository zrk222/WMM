/* Human controls over the same versioned timeline and renderer used by agents. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.WMMVideoEditor=api;})(typeof globalThis==='object'?globalThis:this,function(){
 'use strict';
 const FPS=24,MAX_CLIPS=24;
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const clone=v=>JSON.parse(JSON.stringify(v));
 const button=(title,action,extra='')=>`<button type="button" class="button outline" data-action="veditor-${action}" ${extra}>${esc(title)}</button>`;
 const field=(name,title,value,type='number',extra='')=>`<label class="field">${esc(title)}<input name="${esc(name)}" type="${type}" value="${esc(value)}" ${extra}></label>`;
 const choice=(name,title,value,options)=>`<label class="field">${esc(title)}<select name="${esc(name)}">${options.map(([id,label])=>`<option value="${esc(id)}" ${id===value?'selected':''}>${esc(label)}</option>`).join('')}</select></label>`;
 let active=null;
 function clear(){active=null;}
 function scope(state){return {app:state.app,version:state.workspace?.app?.version??null};}
 function same(a,b){return a.app===b.app&&a.version===b.version;}
 function invalidate(state){if(active&&!same(active.scope,scope(state)))clear();}
 function valid(ticket,deps){return active===ticket&&same(ticket.scope,scope(deps.state))&&ticket.node.open;}
 function base(ticket){return '/api/apps/'+encodeURIComponent(ticket.scope.app);}
 function projectPath(ticket,id){return base(ticket)+'/video-projects/'+encodeURIComponent(id);}
 function show(deps,title,kind,data,html,captured){
  const identity=captured||scope(deps.state);
  deps.modal(title,`<div class="modal-content video-editor">${html}<p id="editor-error" class="field-error" role="alert"></p></div>`);
  active={scope:identity,kind,data,node:deps.document.querySelector('#modal'),pending:false};return active;
 }
 function panel(){return `<section class="panel" aria-label="Shared video editor"><p class="eyebrow">MAKE THE VIDEO FIT YOUR CAMPAIGN</p><h2>Edit a video for your audience</h2><p>Use a saved app-screen video as your source. Choose the scenes and timing, change framing and color, then render a new MP4. Your agent and you work on the same saved project revisions.</p><p>Start with the message and action you want viewers to take. Preview the actual result before using it.</p>${button('Open video projects','open')}<p>This editor uses silent native app-screen videos. Picture edits affect the whole source frame, including its existing captions.</p></section>`;}
 async function open(deps){
  const ticket=show(deps,'Your video projects','loading',null,'<p role="status">Loading saved projects, source videos and rendered edits…</p>');ticket.pending=true;
  try{
   const [projects,native,renders,jobs]=await Promise.all(['/video-projects','/native-renders','/video-edit-renders','/jobs'].map(p=>deps.api(base(ticket)+p)));
   if(valid(ticket,deps))library(deps,{projects:projects.items,sources:native.items.filter(r=>r.status==='CURRENT'),renders:renders.items,jobs},ticket.scope);
  }catch(e){if(valid(ticket,deps)){ticket.node.querySelector('#editor-error').textContent=e.message+' Close and reopen to retry.';}}
  finally{ticket.pending=false;}
 }
 function library(deps,data,captured){
  const rows=data.projects.map(p=>`<article class="next-step"><div><h3>${esc(p.data.definition.title)}</h3><p>Revision ${p.revision} · ${p.timing.total_frames/FPS} seconds · ${p.data.definition.clips.length} clips · ${esc(p.source_status)}</p>${button('Edit project','project',`data-id="${esc(p.id)}"`)}</div></article>`).join('');
  return show(deps,'Your video projects','library',data,`<p>Open a project to customize its message, clip order, timing, framing and color. Saved revisions let you undo, redo and restore earlier work.</p>${button('Create video project','create')}<p>${data.sources.length} current source videos · ${data.renders.length} saved edited videos.</p>${rows||'<p>No projects yet. Render an app-screen source video in Research, then create your first edit.</p>'}`,captured);
 }
 function sourceOptions(data){return data.sources.map(r=>[r.id,`${r.data.request.brief.data.app.name} · ${r.data.artifact.metadata.duration_seconds} seconds · ${r.id.slice(0,8)}`]);}
 function createForm(deps,ticket){
  if(!ticket.data.sources.length){ticket.node.querySelector('#editor-error').textContent='Render a current app-screen video first, then reopen this editor. Your saved projects remain available.';return;}
  show(deps,'Create a video project','create',ticket.data,`<form id="video-project-create-form"><p>Choose a source you own, name this edit and state the audience action it should support. Creation saves a draft; it does not render or publish.</p><div class="form-grid">${field('title','Project title',deps.state.workspace.app.data.name+' video edit','text','required maxlength="200"')}${field('purpose','Audience and intended action','','text','required maxlength="2000"')}${choice('source_id','Source video',ticket.data.sources[0].id,sourceOptions(ticket.data))}</div><button class="button primary" type="submit">Create project</button></form>`,ticket.scope);
 }
 function newClip(source,id){
  return {id,source:{kind:'NATIVE',id:source.id,sha256:source.data.artifact.sha256},role:'HOOK',in_frame:0,
   out_frame:Math.min(120,Math.round(source.data.artifact.metadata.duration_seconds*FPS)),speed_percent:100,
   transform:{crop:{x:0,y:0,width:10000,height:10000},rotation:0,flip_x:false,flip_y:false,fit:'CONTAIN',background:'#102124'},effects:{brightness:0,contrast:100,saturation:100}};
 }
 function newData(values,source,locale,id){return {title:values.title,purpose:values.purpose,locale,output:'PORTRAIT',clips:[newClip(source,id)]};}
 function number(values,key){const value=Number(values[key]);if(values[key]===''||!Number.isFinite(value))throw new Error('Complete every timing and appearance number.');return value;}
 function edited(project,values){
  const value=clone(project.data.definition);value.title=values.title;value.purpose=values.purpose;value.output=values.output;
  value.clips.forEach((c,i)=>readClip(c,values,'c'+i+'.'));return value;
 }
 function readClip(c,v,p){
  c.role=v[p+'role'];for(const key of ['in_frame','out_frame','speed_percent'])c[key]=number(v,p+key);
  c.transform.rotation=number(v,p+'rotation');c.transform.flip_x=v[p+'flip_x']==='true';c.transform.flip_y=v[p+'flip_y']==='true';c.transform.fit=v[p+'fit'];c.transform.background=v[p+'background'];
  for(const key of ['x','y','width','height'])c.transform.crop[key]=Math.round(number(v,p+'crop.'+key)*100);
  for(const key of ['brightness','contrast','saturation'])c.effects[key]=number(v,p+key);
 }
 function clipMarkup(c,i,total){
  const p='c'+i+'.',attrs=`data-clip="${esc(c.id)}"`,transform=c.transform;
  const timing=field(p+'in_frame','Source start frame',c.in_frame,'number','required min="0" step="1"')+field(p+'out_frame','Source end frame',c.out_frame,'number','required min="1" step="1"')+field(p+'speed_percent','Speed percent',c.speed_percent,'number','required min="25" max="400" step="25"')+choice(p+'role','Scene role',c.role,['HOOK','PROBLEM','DEMO','PROOF','OBJECTION','CTA','OTHER'].map(x=>[x,x]));
  const appearance=choice(p+'rotation','Rotation',transform.rotation,[0,90,180,270].map(x=>[x,x+' degrees']))+choice(p+'fit','Frame fit',transform.fit,[['CONTAIN','Fit whole picture'],['COVER','Fill and crop']])+field(p+'background','Background color',transform.background,'color')+choice(p+'flip_x','Flip horizontally',String(transform.flip_x),[['false','Off'],['true','On']])+choice(p+'flip_y','Flip vertically',String(transform.flip_y),[['false','Off'],['true','On']]);
  const crop=['x','y','width','height'].map(key=>field(p+'crop.'+key,'Crop '+key+' percent',transform.crop[key]/100,'number',`required min="${key==='width'||key==='height'?'0.01':'0'}" max="100" step="0.01"`)).join('');
  const color=['brightness','contrast','saturation'].map(key=>field(p+key,key[0].toUpperCase()+key.slice(1),c.effects[key],'number',`required min="${key==='brightness'?-100:0}" max="${key==='brightness'?100:250}" step="1"`)).join('');
  return `<fieldset><legend>Clip ${i+1} · ${esc(c.id.slice(0,8))}</legend><p>Source ${esc(c.source.id.slice(0,8))}. Timing uses original source frames at 24 frames per second.</p><div class="form-grid">${timing}</div><details><summary>Framing, crop and color</summary><div class="form-grid">${appearance}${crop}${color}</div></details><div class="button-row">${button('Move earlier','move',`${attrs} data-index="${i-1}" ${i===0?'disabled':''}`)}${button('Move later','move',`${attrs} data-index="${i+1}" ${i===total-1?'disabled':''}`)}${button('Duplicate clip','duplicate',attrs)}${button('Delete clip','delete',`${attrs} ${total===1?'disabled':''}`)}</div>${field(p+'split','Split at source frame',Math.floor((c.in_frame+c.out_frame)/2),'number','step="1"')}${button('Split clip','split',`${attrs} data-prefix="${p}"`)}</fieldset>`;
 }
 function editor(deps,data,captured){
  const p=data.project,d=p.data.definition;
  const clips=d.clips.map((c,i)=>clipMarkup(c,i,d.clips.length)).join('');
  const history=(p.history||[]).map(r=>[String(r.revision),'Revision '+r.revision+' · '+r.action]);
  const html=`<p>Current revision ${p.revision} · ${p.timing.total_frames/FPS} seconds · ${esc(p.source_status)} · ${esc(d.locale)}</p><form id="video-project-edit-form"><div class="form-grid">${field('title','Project title',d.title,'text','required maxlength="200"')}${field('purpose','Audience and intended action',d.purpose,'text','required maxlength="2000"')}${choice('output','Output shape',d.output,[['PORTRAIT','Portrait 720 × 1280'],['LANDSCAPE','Landscape 1280 × 720'],['SQUARE','Square 720 × 720']])}</div>${clips}<p>Save current field edits before using clip commands, history or rendering. These actions use the exact saved revision.</p><button class="button primary" type="submit">Save edits</button><div class="button-row">${button('Undo','undo',p.can_undo?'':'disabled')}${button('Redo','redo',p.can_redo?'':'disabled')}${button('Render saved revision','render')}${button('Rendered videos','outputs')}</div><details><summary>Add a source clip or restore an earlier revision</summary>${choice('insert_source','Source for new clip',data.sources[0]?.id||'',sourceOptions(data))}${button('Add source clip','insert',d.clips.length>=MAX_CLIPS?'disabled':'')}${choice('restore_revision','Earlier revision',history[0]?.[0]||'',history)}${button('Restore selected revision','restore')}</details></form><div class="button-row">${button('PDF edit report','report')}${button('Download edit settings','download')}${button('Reload saved project','project',`data-id="${esc(p.id)}"`)}</div>`;
  return show(deps,'Edit your video','edit',data,html,captured);
 }
 function values(form,deps){return Object.fromEntries(new deps.FormData(form));}
 function draft(ticket,deps){return edited(ticket.data.project,values(ticket.node.querySelector('#video-project-edit-form'),deps));}
 function clean(ticket,deps){
  if(JSON.stringify(draft(ticket,deps))!==JSON.stringify(ticket.data.project.data.definition))throw new Error('Save your current field edits first. Your inputs are preserved.');
 }
 async function loadProject(deps,ticket,id){
  const project=await deps.api(projectPath(ticket,id));if(valid(ticket,deps))editor(deps,{...ticket.data,project},ticket.scope);
 }
 function report(data,state,reports){
  const p=data.project,d=p.data.definition,outputs=data.renders.filter(r=>r.data.request.selection.project_id===p.id);
  const baseModel=reports.model({...state,view:'research'});
  return {...baseModel,title:'Video edit report',purpose:'Check the saved edit, source proof and actual rendered outputs before using this video.',next_step:'Preview the exact rendered MP4 and review it before publication.',filters:{project:p.id,revision:String(p.revision)},
   metrics:[['Clips',d.clips.length,'count'],['Output duration',p.timing.total_frames/FPS,'seconds'],['Output frames',p.timing.total_frames,'frames'],['Saved renders',outputs.length,'count']].map(([label,value,unit])=>({label,value,unit,source:'Saved app-owned project and render history'})),cohorts:[],
   notes:[`Project ${d.title}; revision ${p.revision}; hash ${p.hash}; source ${p.source_status}.`,`Output ${d.output}; locale ${d.locale}.`,...d.clips.map((c,i)=>`Clip ${i+1}: ${c.role}; source ${c.source.id}; frames ${c.in_frame}–${c.out_frame}; speed ${c.speed_percent}%.`),...outputs.map(r=>`Render ${r.id}: ${r.status}; source revision ${r.data.request.selection.revision}; ${r.data.artifact.metadata.duration_seconds} seconds; hash ${r.data.artifact.sha256}.`),'Native source profile is silent. Model API charge is 0; machine cost is not measured. Final artifact review is required; publication and business outcomes are not established.']};
 }
 function outputs(deps,ticket,renders,jobs){
  const p=ticket.data.project,files=renders.filter(r=>r.data.request.selection.project_id===p.id),runs=jobs.filter(j=>j.action==='edit_render'&&j.data.selection.project_id===p.id);
  const rows=files.map(r=>{const url=base(ticket)+'/video-edit-renders/'+encodeURIComponent(r.id);return `<article class="panel"><h3>Rendered revision ${r.data.request.selection.revision}</h3><p>${esc(r.status)} · ${r.data.artifact.metadata.duration_seconds} seconds · ${r.data.artifact.metadata.width} × ${r.data.artifact.metadata.height}</p><video controls preload="metadata" style="width:100%;max-height:24rem" src="${url}/preview" aria-label="Rendered video preview"></video><p><a class="button secondary" href="${url}/download" download>Download MP4</a></p><p>Final human review required. Publication has not run.</p></article>`;}).join('');
  show(deps,'Rendered video results','outputs',{...ticket.data,renders,jobs},`<p>Follow actual worker progress on Research or Activity. Refresh these results after the job finishes. Seeking and download use the saved MP4 bytes.</p>${runs.map(j=>`<p>Job ${esc(j.id)} · <strong>${esc(j.status)}</strong></p>`).join('')}${rows||'<p>No saved edited MP4 for this project yet.</p>'}${button('Refresh render results','outputs')}${button('Return to project','project',`data-id="${esc(p.id)}"`)}${button('PDF edit report','report')}${button('Download edit settings','download')}`,ticket.scope);
 }
 async function submit(form,deps){
  const ticket=active;if(!ticket||ticket.pending||!valid(ticket,deps))return;ticket.pending=true;
  const submit=form.querySelector('[type=submit]');submit.disabled=true;
  try{
   const v=values(form,deps);let body;
   if(ticket.kind==='create'){
    const source=ticket.data.sources.find(s=>s.id===v.source_id);if(!source)throw new Error('Choose a current source video.');
    body={id:deps.uuid(),revision:0,manifest_version:ticket.scope.version,data:newData(v,source,deps.state.workspace.app.data.locale,deps.uuid()),request_key:deps.uuid()};
   }else body={id:ticket.data.project.id,revision:ticket.data.project.revision,manifest_version:ticket.scope.version,data:edited(ticket.data.project,v),request_key:deps.uuid()};
   const result=await deps.api(base(ticket)+'/video-projects',body);
   if(valid(ticket,deps))await loadProject(deps,ticket,result.id);
  }catch(e){if(valid(ticket,deps))ticket.node.querySelector('#editor-error').textContent=e.message+' Your fields are retained. If a response was interrupted, reload the saved project before retrying.';}
  finally{ticket.pending=false;submit.disabled=false;}
 }
 function command(node,ticket,deps){
  const action=node.dataset.action.slice(8),p=ticket.data.project;
  if(['undo','redo','restore'].includes(action))return {suffix:'/history',body:{operation:action.toUpperCase(),...(action==='restore'?{target_revision:Number(values(ticket.node.querySelector('form'),deps).restore_revision)}:{})}};
  if(action==='insert'){
   const v=values(ticket.node.querySelector('form'),deps),source=ticket.data.sources.find(s=>s.id===v.insert_source);if(!source)throw new Error('Choose a current native source.');
   return {suffix:'/edits',body:{command:{operation:'insert',index:p.data.definition.clips.length,clip:newClip(source,deps.uuid())}}};
  }
  const change={operation:action,clip_id:node.dataset.clip};
  if(action==='move')change.index=Number(node.dataset.index);
  if(['split','duplicate'].includes(action))change.new_id=deps.uuid();
  if(action==='split')change.at_frame=Number(values(ticket.node.querySelector('form'),deps)[node.dataset.prefix+'split']);
  return {suffix:'/edits',body:{command:change}};
 }
 function download(ticket,deps){
  const p=ticket.data.project,value={schema:'wmm.video-edit-settings.v1',app_id:ticket.scope.app,project_id:p.id,revision:p.revision,hash:p.hash,definition:p.data.definition,report:report(ticket.data,deps.state,deps.pageReports),media_bundle:'NOT_INCLUDED_SETTINGS_ONLY'};
  const url=deps.browser.URL.createObjectURL(new deps.browser.Blob([JSON.stringify(value,null,2)],{type:'application/json'}));const a=deps.document.createElement('a');a.href=url;a.download=ticket.scope.app+'-video-settings.json';a.click();deps.browser.URL.revokeObjectURL(url);
 }
 async function action(node,deps){
  const name=node.dataset.action.slice(8);if(name==='open')return open(deps);
  const ticket=active;if(!ticket||ticket.pending||!valid(ticket,deps))return;
  if(name==='create')return createForm(deps,ticket);
  if(name==='download')return download(ticket,deps);
  if(name==='report')return deps.pageReports.openReport(report(ticket.data,deps.state,deps.pageReports),deps.browser);
  ticket.pending=true;
  try{
   if(name==='project')return await loadProject(deps,ticket,node.dataset.id);
   if(name==='outputs'){
    if(ticket.kind==='edit')clean(ticket,deps);
    const [r,j]=await Promise.all([deps.api(base(ticket)+'/video-edit-renders'),deps.api(base(ticket)+'/jobs')]);if(valid(ticket,deps))outputs(deps,ticket,r.items,j);return;
   }
   clean(ticket,deps);const p=ticket.data.project;
   if(name==='render'){
    await deps.api(base(ticket)+'/video-edit-renders',{data:{project_id:p.id,revision:p.revision,project_hash:p.hash},request_key:deps.uuid()});
    if(valid(ticket,deps)){ticket.node.querySelector('#editor-error').textContent='Render queued. Open Rendered videos and refresh after the worker finishes; live steps are recorded on Research and Activity.';}return;
   }
   const operation=command(node,ticket,deps);await deps.api(projectPath(ticket,p.id)+operation.suffix,{...operation.body,revision:p.revision,manifest_version:ticket.scope.version,request_key:deps.uuid()});
   if(valid(ticket,deps))await loadProject(deps,ticket,p.id);
  }catch(e){if(valid(ticket,deps))ticket.node.querySelector('#editor-error').textContent=e.message+' If saved state changed, reload the project. Current fields are preserved.';}
  finally{ticket.pending=false;}
 }
 return {panel,open,action,submit,clear,invalidate,newClip,newData,edited,report,clipMarkup};
});
