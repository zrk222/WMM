/* Owner-managed Apple inventory and refresh controls; no provider writes. */
(function(root,factory){const value=factory();if(typeof module==='object'&&module.exports)module.exports=value;else root.WMMAppleAnalytics=value;})(typeof globalThis==='object'?globalThis:this,function(){
 'use strict';
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const button=(text,action,extra='')=>`<button type="button" class="button outline" data-action="apple-analytics-${action}" ${extra}>${esc(text)}</button>`;
 let active=null;
 function scope(state){
  const w=state.workspace||{}, app=w.app||{}, id=w.identity||{}, role=(w.access?.members||[]).find(m=>m.principal===id.principal&&m.status==='ACTIVE');
  const bindings=(w.records||[]).filter(r=>r.kind==='connection'&&r.data?.provider==='app_store'&&r.data?.store_app_id===app.data?.store_app_id&&r.data?.auth_mode!=='disconnected').map(r=>[r.id,r.version,r.hash]).sort((a,b)=>String(a[0]).localeCompare(String(b[0])));
  return {app:state.app,workspace:app.id,version:app.version,store:app.data?.store_app_id??null,principal:id.principal,status:id.status,expires:id.expires_at_epoch,identityRef:w.identity||null,role:role?.role,roleVersion:role?.version,csrf:state.boot?.csrf,bindings};
 }
 const same=(a,b)=>a.identityRef===b.identityRef&&JSON.stringify(a)===JSON.stringify(b);
 function clear(){active=null;}
 function invalidate(state){if(active&&!same(active.scope,scope(state)))clear();}
 function current(t){return active===t&&same(t.scope,scope(t.d.state))&&t.node?.isConnected&&t.d.document.querySelector('#modal')?.open;}
 function panel(){return `<section class="panel" aria-label="Apple analytics"><p class="eyebrow">APP STORE / ANALYTICS</p><h2>Keep Apple analytics current</h2><p>Check report availability and choose whether to refresh the downloads report. Missing report instances do not mean zero downloads.</p>${button('Review Apple analytics','open')}</section>`;}
 function show(d,title,html,data=null){
  d.modal(title,`<div id="apple-analytics-root" class="modal-content">${html}<p id="apple-analytics-status" role="status" aria-live="polite"></p><p id="apple-analytics-error" class="field-error" role="alert"></p></div>`, 'APP STORE / ANALYTICS');
  active={d,scope:scope(d.state),node:d.document.querySelector('#apple-analytics-root'),data,pending:false};return active;
 }
 function friendly(value){return value?String(value).replaceAll('_',' '):'Not recorded';}
 function time(value,epoch=false){if(value===null||value===undefined||value==='')return 'Not recorded';const d=new Date(epoch?Number(value)*1000:value);return Number.isNaN(d.getTime())?'Not recorded':d.toLocaleString();}
 function details(data){
  const s=data.schedule, reports=data.reports||[], options=reports.filter(r=>r.name==='App Downloads Standard');
  const state=s?`<p><strong>Refresh:</strong> ${esc(friendly(s.status))} · ${s.enabled?'On':'Off'}<br>Last job: ${esc(s.last_job||'Not recorded')} · ${esc(s.last_job_status?friendly(s.last_job_status):'No status')} · Failures: ${esc(s.failures)}<br>Last metrics collected: ${esc(time(s.last_success))} · Next due: ${s.enabled?esc(time(s.next_due,true)):'Not scheduled'}</p>${['BLOCKED','FAILED'].includes(s.last_job_status)?'<p>Inspect the latest refresh and repair the reported issue before trying again.</p>':''}${s.last_job?button('Inspect latest refresh','job'):''}`:'<p>No saved refresh schedule.</p>';
  const rows=reports.map(r=>`<li>${esc(r.name)}: ${esc(r.instance_count)} report instances · ${esc(friendly(r.coverage))}</li>`).join('');
  const selects=options.map(r=>`<option value="${esc(r.id)}" ${s?.report_id===r.id?'selected':''}>${esc(r.name)}</option>`).join('');
  const form=options.length?`<form id="apple-analytics-form"><div class="field"><label for="apple-analytics-report">Report</label><select id="apple-analytics-report" name="report_id" required>${selects}</select></div><div class="field"><label for="apple-analytics-interval">Refresh every (hours)</label><input id="apple-analytics-interval" type="number" name="interval_hours" min="24" max="168" step="1" value="${esc(s?.interval_hours||24)}" required></div><button class="button" type="submit">${s?.enabled?'Save refresh settings':'Enable refresh'}</button></form>`:'<p>Read the current inventory to choose the App Downloads Standard report.</p>';
  const source=data.connection?(data.inventory?'Saved for this app. The successful inventory below records access at that time, not a guarantee of current access.':'Saved for this app. No successful current-source inventory is recorded.'):'Not connected for this app.';
  return `<p>Apple source: ${esc(source)}</p><p>Inventory: ${esc(data.inventory?friendly(data.inventory.status):'Not read')} · observed ${esc(time(data.inventory?.observed_at))}.</p>${rows?`<ul>${rows}</ul>`:'<p>No current report inventory is available.</p>'}<p>Report instance counts describe available files, not downloads, revenue, retention or other metrics. Missing metrics remain unknown.</p>${state}${data.connection?button('Read Apple inventory','inventory'):button('Set up App Store connection','setup')}${button('Refresh saved status','refresh')}${data.connection?form:''}${s?.enabled?button('Pause refresh','pause'):''}${button('Report / Save PDF','report')}<p>Scheduled reads run only while the WMM worker is running. Pausing stops future scheduled reads; it does not remove saved evidence.</p>`;
 }
 function validate(t,data){
  if(!data||data.app_id!==t.scope.app||data.manifest_version!==t.scope.version||data.store_app_id!==t.scope.store||!Array.isArray(data.reports))throw Error('App setup changed. Reopen Apple analytics.');
  if(data.connection&&(!t.scope.bindings.some(b=>b[0]===data.connection.id&&b[1]===data.connection.version)||t.scope.bindings.length!==1))throw Error('Apple connection changed. Refresh this workspace and reopen analytics.');
  return data;
 }
 async function open(d){
  const initial=scope(d.state);
  if(initial.status!=='AUTHENTICATED'||!initial.principal){show(d,'Apple analytics','<p>Sign in with the app owner account to inspect and manage Apple analytics.</p><button type="button" class="button outline" data-action="identity-login">Sign in</button>');return;}
  if(initial.role!=='OWNER'){show(d,'Apple analytics','<p>This action requires the current app owner. Ask the owner to review app access, or establish the first owner if this workspace has none.</p>'+(d.state.workspace.access?.configured?button('Review app access','access'):'<button type="button" class="button outline" data-action="access-bootstrap">Establish first owner</button>'));return;}
  const t=show(d,'Apple analytics','<p role="status">Reading saved Apple analytics…</p>');
  try{const data=await d.api('/api/apps/'+encodeURIComponent(t.scope.app)+'/apple-analytics/view',{});if(!current(t))return;validate(t,data);show(d,'Apple analytics',details(data),data);}
  catch(e){if(current(t))t.node.querySelector('#apple-analytics-error').textContent=e.message+' Check owner access and App Store setup, then reopen.';}
 }
 function busy(t,on){t.pending=on;if(current(t)){t.node.setAttribute('aria-busy',String(on));t.node.querySelectorAll('button,select,input').forEach(n=>n.disabled=on);}}
 function fail(t,e){if(current(t))t.node.querySelector('#apple-analytics-error').textContent=e.message+' No request was repeated. Check saved Activity and refresh before trying again.';}
 function report(data,state,pages){const base=pages.model(state),s=data.schedule;return {...base,title:'Apple analytics inventory',purpose:'Review saved Apple report availability and refresh settings.',cohorts:[],metrics:(data.reports||[]).map(r=>({label:r.name+' report instances',value:r.instance_count,unit:'instances',source:'Saved Apple inventory'})),notes:['Inventory observed: '+(data.inventory?.observed_at||'Not recorded'),'Inventory state: '+friendly(data.inventory?.status),'Refresh state: '+friendly(s?.status),'Latest job: '+(s?.last_job||'Not recorded')+' · '+friendly(s?.last_job_status),'Consecutive failures: '+(s?.failures??'Not recorded'),'Next due: '+(s?.enabled?time(s.next_due,true):'Not scheduled'),'Last metrics collected: '+(s?.last_success||'Not recorded'),'Report instance counts are not downloads or other app metrics; unavailable measurements remain unknown.']};}
 async function action(node,d){
  const kind=node.dataset.action;
  if(kind==='apple-analytics-open')return open(d);
  const t=active;if(!t||!current(t)||t.pending)return;
  if(kind==='apple-analytics-setup'){d.close();return d.connectionSetup('app_store');}
  if(kind==='apple-analytics-access'){d.close();return d.openAccess();}
  if(kind==='apple-analytics-job'&&t.data?.schedule?.last_job)return d.openJob(t.data.schedule.last_job);
  if(kind==='apple-analytics-refresh')return open(d);
  if(kind==='apple-analytics-report')return d.pageReports.openReport(report(t.data,d.state,d.pageReports),d.browser);
  if(!t.data)return;
  let body,path;
  if(kind==='apple-analytics-inventory'){
   if(!t.data.connection)return;
   path='inventory';body={manifest_version:t.scope.version,connection_id:t.data.connection.id,connection_version:t.data.connection.version};
  }else if(kind==='apple-analytics-pause'){
   if(!t.data.schedule?.enabled)return;
   path='schedule';body={manifest_version:t.scope.version,enabled:false,version:t.data.schedule.version};
  }else return;
  busy(t,true);
  try{const result=await d.api('/api/apps/'+encodeURIComponent(t.scope.app)+'/apple-analytics/'+path,body);if(!current(t))return;if(path==='inventory'){t.node.querySelector('#apple-analytics-status').textContent='Inventory queued. Check Activity for job '+result.job_id+', then refresh saved status.';}else{busy(t,false);return open(d);}}
  catch(e){fail(t,e);}finally{busy(t,false);}
 }
 async function submit(form,d){
  const t=active;if(!t||!current(t)||t.pending||!form.isConnected||form.id!=='apple-analytics-form'||!t.data?.connection)return;
  const values=new d.FormData(form),reportId=values.get('report_id'),hours=Number(values.get('interval_hours'));
  if(!Number.isSafeInteger(hours)||hours<24||hours>168||!t.data.reports.some(r=>r.id===reportId&&r.name==='App Downloads Standard')){fail(t,Error('Choose the displayed downloads report and an interval from 24 to 168 hours.'));return;}
  const body={manifest_version:t.scope.version,enabled:true,interval_hours:hours,report_id:reportId,version:t.data.schedule?.version??null};
  busy(t,true);try{await d.api('/api/apps/'+encodeURIComponent(t.scope.app)+'/apple-analytics/schedule',body);if(current(t)){busy(t,false);return open(d);}}catch(e){fail(t,e);}finally{busy(t,false);}
 }
 return {panel,scope,same,clear,invalidate,details,report,open,action,submit};
});
