/* Original footage intake and reuse attestations over exact local routes. */
(function(root,factory){const value=factory();if(typeof module==='object'&&module.exports)module.exports=value;else root.WMMMedia=value;})(typeof globalThis==='object'?globalThis:this,function(){
 'use strict';
 const MAX_BYTES=67108864,esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const button=(label,action,extra='')=>`<button type="button" class="button outline" data-action="media-${action}" ${extra}>${esc(label)}</button>`;
 let active=null;const uploads=new Map(),reviews=new Set();
 const scope=s=>({app:s.app,version:s.workspace?.app?.version,principal:s.workspace?.identity?.principal||null});
 const same=(a,b)=>a.app===b.app&&a.version===b.version&&a.principal===b.principal;
 const key=s=>JSON.stringify([s.app,s.version,s.principal]);
 const valid=(t,d)=>active===t&&same(t.scope,scope(d.state))&&t.node.open;
 const owned=d=>d.state.workspace?.access?.members?.some(m=>m.principal===d.state.workspace?.identity?.principal&&m.status==='ACTIVE'&&m.role==='OWNER');
 const base=t=>'/api/apps/'+encodeURIComponent(t.scope.app)+'/media';
 function clear(){active?.node.querySelectorAll('video').forEach(v=>v.pause());active=null;}
 function invalidate(state){if(active&&!same(active.scope,scope(state)))clear();}
 function panel(){return `<section class="panel" aria-label="Original video library"><p class="eyebrow">KEEP THE FOOTAGE. CHOOSE ITS USE.</p><h2>Bring your clips into the project</h2><p>Select local videos, inspect their picture and sound, and keep the originals together. Before derivative work, record why this app may reuse each clip.</p>${button('Open video library','open')}<p>MP4, MOV and WebM, up to 64 MiB each. Upload and playback do not establish reuse rights. Use approved clips in Video projects to trim, stitch and retain or mute source sound. Optional Drive selection is not available yet.</p></section>`;}
 function show(d,title,kind,data,html,captured){
  const selected=captured||scope(d.state);d.modal(title,`<div class="modal-content managed-media" tabindex="-1">${html}<p id="media-progress" role="status" aria-live="polite"></p><p id="media-error" class="field-error" role="alert"></p></div>`);
  active={scope:selected,kind,data,node:d.document.querySelector('#modal'),pending:false,loadedAt:new Date().toISOString()};
  active.node.querySelector('.managed-media')?.focus();return active;
 }
 function busy(t,value,message=''){
  if(active!==t)return;t.pending=value;t.node.querySelector('.managed-media')?.setAttribute('aria-busy',String(value));
  t.node.querySelector('#media-progress').textContent=message;
  t.node.querySelectorAll('[data-media-write]').forEach(n=>n.disabled=value||n.dataset.locked==='true');
 }
 function error(t,d,e){if(valid(t,d))t.node.querySelector('#media-error').textContent=e.message+(e.uncertain?' Outcome unknown. Inspect saved state; this page will not resend the operation.':' Inspect the current app, owner access and file requirements, then choose your next step.');}
 async function request(d,t,path,method='GET',body,headers={}){
  const send=d.fetch||d.browser.fetch.bind(d.browser);let response,result;
  try{response=await send(base(t)+path,{method,credentials:'same-origin',redirect:'error',headers:method==='POST'?{'X-CSRF-Token':d.state.boot?.csrf,...headers}:headers,...(body===undefined?{}:{body})});}
  catch(e){const problem=new Error('The local response was not received.');problem.uncertain=method==='POST';throw problem;}
  try{result=await response.json();}catch(e){const problem=new Error('The local response could not be read.');problem.uncertain=method==='POST';throw problem;}
  if(!response.ok){const problem=new Error(result.error||'The media operation was rejected.');problem.uncertain=method==='POST'&&(response.status>=500||result.outcome==='UNKNOWN');throw problem;}
  return result;
 }
 async function hash(d,bytes){const result=await d.browser.crypto.subtle.digest('SHA-256',bytes);return Array.from(new Uint8Array(result),b=>b.toString(16).padStart(2,'0')).join('');}
 function validateFile(file){if(!file||!Number.isSafeInteger(file.size)||file.size<1||file.size>MAX_BYTES||!/\.(mp4|mov|webm)$/i.test(file.name))throw new Error('Choose a nonempty MP4, MOV or WebM file up to 64 MiB.');}
 function pending(t){return Array.from(uploads.values()).filter(u=>same(u.scope,t.scope));}
 function reconcile(t,items){
  for(const [id,u] of uploads)if(u.status==='UNKNOWN'&&same(u.scope,t.scope)&&items.some(r=>r.upload_request_key_sha256===u.requestHash&&r.source_sha256===u.sourceHash&&r.filename===u.filename&&r.manifest_version===u.scope.version&&r.app_id===u.scope.app))uploads.delete(id);
 }
 function rights(row){return row.reuse_available===true?'Reuse allowed by owner attestation':row.rights_status==='REVOKED'?'Reuse revoked':row.rights_status==='STALE'?'Reuse review is stale':'Reuse not approved';}
 function library(d,t,data){
  if(!Array.isArray(data.items))throw new Error('Media inventory is unavailable. Reload the library to inspect current state.');
  reconcile(t,data.items);const waiting=pending(t),locked=!owned(d)||waiting.length>0;
  const rows=data.items.map(r=>`<article class="next-step"><div><h3>${esc(r.filename)}</h3><p>${esc(rights(r))} / ${esc(r.metadata?.duration_seconds??'Duration unavailable')} seconds / ${r.metadata?.audio===true?'Audio present':r.metadata?.audio===false?'No audio':'Audio unavailable'}</p>${button('Inspect original clip','inspect',`data-id="${esc(r.id)}"`)}</div></article>`).join('');
  const html=`<p>Your originals stay preserved. Choose clips, inspect what was decoded, then decide whether this app may reuse them.</p>${waiting.length?`<p role="status">${waiting.length} upload outcome(s) pending or unknown. Reload saved clips to check exact request receipts. Uploads stay paused until confirmed.</p>`:''}<form id="media-upload-form"><label class="field" for="media-files">Choose local videos<input id="media-files" name="files" type="file" accept=".mp4,.mov,.webm,video/mp4,video/quicktime,video/webm" multiple required ${locked?'disabled':''}></label><p>Each file is sent once and validated locally by WMM. A failed or uncertain clip stops the batch; remaining files are not sent. No reuse permission is inferred.</p><button type="submit" class="button" data-media-write data-locked="${locked}" ${locked?'disabled':''}>Upload selected clips</button></form>${!owned(d)?'<p>To upload or review reuse, sign in under Activity &amp; reviews as this app OWNER, then reopen the library.</p>':''}<div class="button-row">${button('Reload saved clips','open')}${button('Report / Save PDF','report')}${button('Download report JSON','json')}</div><p>${data.items.length} saved original clips observed.</p>${rows||'<p>No original clips yet. Choose a local file to begin.</p>'}`;
  return show(d,'Your original video library','library',data,html,t.scope);
 }
 async function open(d){
  const t=show(d,'Your original video library','loading',null,'<p>Reading saved original clips...</p>');busy(t,true,'Reading the selected app library...');
  try{const data=await request(d,t,'');if(valid(t,d))library(d,t,data);}catch(e){error(t,d,e);}finally{busy(t,false);}
 }
 function detail(d,t,row){
  const locked=!owned(d)||reviews.has(key(t.scope)+':'+row.id),url=base(t)+'/'+encodeURIComponent(row.id);
  const metadata=row.metadata||{},state=rights(row),last=row.latest_review||{},selected=(field,value)=>last[field]===value?' selected':'';
  const form=`<form id="media-review-form"><h3>Choose how this app may reuse the clip</h3><p>This saves an owner attestation, not independent legal verification. Revocation blocks new derivative use. Original footage and review history remain retained.</p><label class="field" for="media-decision">Reuse decision<select id="media-decision" name="status"><option value="ALLOWED"${selected('status','ALLOWED')}>Allow reuse by attestation</option><option value="REVOKED"${selected('status','REVOKED')}>Revoke reuse</option></select></label><label class="field" for="media-basis">Permission basis<select id="media-basis" name="basis"><option value="OWNED"${selected('basis','OWNED')}>I own the footage</option><option value="LICENSED"${selected('basis','LICENSED')}>Licensed for this use</option><option value="CONSENT"${selected('basis','CONSENT')}>Recorded consent for this use</option></select></label><label class="field" for="media-evidence">Permission evidence or revocation reason<textarea id="media-evidence" name="evidence" maxlength="1000" required rows="3"></textarea></label><button class="button" type="submit" data-media-write data-locked="${locked}" ${locked?'disabled':''}>Save reuse decision</button></form>`;
  const html=`<p>${esc(state)}. Technical decoding and playback do not establish permission to edit or publish this footage.</p><video class="render-preview" controls preload="metadata" src="${esc(url+'/preview')}" aria-label="Original uploaded clip"></video><p>${esc(row.filename)} / ${esc(row.bytes??'Size unavailable')} bytes</p><p>Picture: ${esc(metadata.width??'unavailable')} x ${esc(metadata.height??'unavailable')} / ${esc(metadata.frame_rate??'Frame rate unavailable')} / ${esc(metadata.codec??'Codec unavailable')} / ${esc(metadata.duration_seconds??'Duration unavailable')} seconds.</p><p>Sound: ${metadata.audio===true?'Audio present':metadata.audio===false?'No audio':'Unavailable'}. Decoded frames: picture ${esc(row.decoded?.video_frames??'unavailable')}, audio ${esc(row.decoded?.audio_frames??'unavailable')}.</p><p>Source: ${esc(row.provenance?.kind??'Unavailable')} / review version ${esc(row.review_version??'unavailable')}.</p><details><summary>Source hash and audio metadata</summary><pre>${esc(JSON.stringify({source_sha256:row.source_sha256,audio_metadata:metadata.audio_metadata??null},null,2))}</pre></details><div class="button-row"><a class="button outline" href="${esc(url+'/download')}" download>Download original</a>${button('Reload this clip','refresh')}${button('Back to library','open')}${button('Report / Save PDF','report')}${button('Download report JSON','json')}</div>${form}${locked?'<p>Reuse changes are unavailable: sign in as the app owner, or inspect retained history after an uncertain decision. This page will not repeat an uncertain review.</p>':''}<details><summary>Retained owner review history</summary>${Array.isArray(row.review_history)?`<pre>${esc(JSON.stringify(row.review_history,null,2))}</pre>`:'<p>Review history unavailable in this response.</p>'}</details>`;
  return show(d,'Inspect your original clip','detail',row,html,t.scope);
 }
 async function inspect(d,t,id){const row=await request(d,t,'/'+encodeURIComponent(id));if(valid(t,d))detail(d,t,row);}
 async function submit(form,d){
  const t=active;if(!t||!valid(t,d)||t.pending)return;
  try{
   if(!owned(d))throw new Error('This app OWNER must sign in before uploading or reviewing reuse.');
   if(form.id==='media-upload-form'){
    if(pending(t).length)throw new Error('Inspect exact saved upload receipts before sending another clip.');
    const files=Array.from(form.querySelector('[name="files"]').files||[]);if(!files.length)throw new Error('Choose at least one local clip.');files.forEach(validateFile);
    busy(t,true,'Checking selected local clips...');let completed=0;
    for(const file of files){
     if(!valid(t,d))return;
     const sourceHash=await hash(d,await file.arrayBuffer()),requestKey=d.uuid();if(!valid(t,d))return;
     const requestHash=await hash(d,new TextEncoder().encode(requestKey));if(!valid(t,d))return;
     const filename=file.name.split(/[\\/]/).at(-1),entry={scope:t.scope,sourceHash,requestHash,filename,status:'PENDING'};uploads.set(requestHash,entry);
     busy(t,true,`Sending clip ${completed+1} of ${files.length}; WMM then validates picture and sound. No percentage is inferred.`);
     try{
      const row=await request(d,t,'/uploads','POST',file,{'Content-Type':'application/octet-stream','X-Filename':encodeURIComponent(filename),'X-WMM-Manifest-Version':String(t.scope.version),'X-WMM-Request-Key':requestKey});
      if(!row||row.upload_request_key_sha256!==requestHash||row.source_sha256!==sourceHash||row.filename!==filename||row.manifest_version!==t.scope.version||row.app_id!==t.scope.app){const problem=new Error('The returned upload receipt did not match the selected file and request.');problem.uncertain=true;throw problem;}
      uploads.delete(requestHash);completed++;
     }catch(e){if(e.uncertain)entry.status='UNKNOWN';else uploads.delete(requestHash);throw e;}
    }
    if(valid(t,d)){const data=await request(d,t,'');if(valid(t,d)){const next=library(d,t,data);busy(next,false,`${completed} original clip(s) saved and decoded. Reuse remains subject to each clip review.`);}}return;
   }
   if(form.id==='media-review-form'){
    const identity=key(t.scope)+':'+t.data.id;if(reviews.has(identity))throw new Error('Inspect retained review history; this page cannot repeat an uncertain decision.');
    const values=new d.FormData(form),evidence=values.get('evidence');if(typeof evidence!=='string'||!evidence.trim()||evidence.length>1000)throw new Error('Describe permission evidence or the revocation reason in 1 to 1000 characters.');
    const body={expected_version:t.data.review_version,manifest_version:t.scope.version,source_sha256:t.data.source_sha256,status:values.get('status'),basis:values.get('basis'),evidence};
    if(!['ALLOWED','REVOKED'].includes(body.status)||!['OWNED','LICENSED','CONSENT'].includes(body.basis))throw new Error('Choose an explicit reuse decision and permission basis.');
    busy(t,true,'Saving the source-bound owner attestation...');reviews.add(identity);
    try{const row=await request(d,t,'/'+encodeURIComponent(t.data.id)+'/reviews','POST',JSON.stringify(body),{'Content-Type':'application/json'});if(!row||row.id!==t.data.id||row.app_id!==t.scope.app||row.source_sha256!==body.source_sha256||row.review_version!==body.expected_version+1){const problem=new Error('The returned reuse receipt did not match this clip and review version.');problem.uncertain=true;throw problem;}reviews.delete(identity);if(valid(t,d)){const next=detail(d,t,row);busy(next,false,'Reuse decision saved. Inspect the current state and retained history before derivative work.');}}
    catch(e){if(!e.uncertain)reviews.delete(identity);throw e;}
   }
  }catch(e){error(t,d,e);if(valid(t,d)&&(e.uncertain||(form.id==='media-upload-form'&&pending(t).length)))t.node.querySelectorAll('[data-media-write]').forEach(n=>n.dataset.locked='true');}
  finally{busy(t,false);}
 }
 function report(t,d){
  const rows=t.kind==='library'?t.data.items:t.kind==='detail'?[t.data]:null;
  return {title:'Original video library observation',app_name:d.state.workspace.app.data.name,app_id:t.scope.app,scope:'SELECTED_APP',manifest_version:t.scope.version,generated_at:new Date().toISOString(),loaded_at:t.loadedAt,purpose:'Inspect saved original footage and current reuse-attestation coverage.',next_step:'Inspect the clip and current owner attestation before derivative work.',filters:{view:t.kind},cohorts:[],metrics:[['Observed original clips',rows?rows.length:null],['Reuse allowed by attestation',rows?rows.filter(r=>r.reuse_available===true).length:null],['Audio present',rows&&rows.every(r=>typeof r.metadata?.audio==='boolean')?rows.filter(r=>r.metadata.audio).length:null]].map(([label,value])=>({label,value,source:'Selected app media readback',unit:'count'})),notes:['Original footage is preserved. Decoding is not reuse permission.','Owner attestations are not independently verified legal rights.','No filenames, video bytes, permission evidence, private paths or credentials are included.','Approved clips can be edited and stitched in Video projects. Optional Drive selection remains unfinished.']};
 }
 function jsonReport(t,d){const url=d.browser.URL.createObjectURL(new d.browser.Blob([JSON.stringify(report(t,d),null,2)],{type:'application/json'})),a=d.document.createElement('a');try{a.href=url;a.download=t.scope.app+'-original-video-report.json';a.click();}finally{d.browser.URL.revokeObjectURL(url);}}
 async function action(node,d){
  const name=node.dataset.action.slice(6);if(name==='open')return open(d);
  const t=active;if(!t||!valid(t,d)||t.pending)return;
  try{if(name==='report')return d.pageReports.openReport(report(t,d),d.browser);if(name==='json')return jsonReport(t,d);busy(t,true,'Reading the saved original clip...');if(name==='inspect')return await inspect(d,t,node.dataset.id);if(name==='refresh')return await inspect(d,t,t.data.id);}catch(e){error(t,d,e);}finally{busy(t,false);}
 }
 return {MAX_BYTES,panel,open,action,submit,clear,invalidate,validateFile,rights,report};
});
