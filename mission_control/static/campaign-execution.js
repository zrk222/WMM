"use strict";
/* Owner scope is authority; this view cannot issue authority for an agent. */
function campaignPanel() {
  return `<section class="panel"><h2>Campaign automation</h2><p>Approve your exact posts, Page, audience, time window and media budget. Your agent can then publish and run supported Meta campaigns inside that scope. Inspect saved delivery receipts and stop future work here.</p>${button('Review campaign automation','campaign-open')}</section>`;
}

function campaignStable(value) {
  if(Array.isArray(value))return '['+value.map(campaignStable).join(',')+']';
  if(value&&typeof value==='object')return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+campaignStable(value[k])).join(',')+'}';
  return JSON.stringify(value);
}

async function campaignHash(value) {
  const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(campaignStable(value)));
  return Array.from(new Uint8Array(bytes),x=>x.toString(16).padStart(2,'0')).join('');
}

function campaignBound(form) {
  if(form.dataset.app!==state.app||Number(form.dataset.version)!==state.workspace.app.version)
    throw new Error('App changed. Reopen campaign automation and review its current scope.');
}

async function campaignOpen() {
  const app=state.app,history=await api(`/api/apps/${app}/campaigns/history`,{});
  if(app!==state.app)return;
  const accounts=(state.workspace.social_access?.accounts||[]).filter(r=>r.provider==='facebook'&&r.status==='CONNECTED_READ_TESTED');
  modal('Campaign automation',`<form id="campaign-scope-form" class="modal-content" data-app="${esc(app)}" data-version="${state.workspace.app.version}"><p>Choose the work once, review its exact limits, then let your agent operate within them. Account permissions are checked separately before execution.</p><label class="field">Facebook Page connection<select name="connection_id" required><option value="">Choose a connected Page</option>${accounts.map(r=>`<option value="${esc(r.id)}">${esc(r.data.destination.name)} · ${esc(r.data.destination.id)}</option>`).join('')}</select></label>${accounts.length?'':notice('Connect a Facebook Page first. Select publishing or ad access during setup, complete official login, then return here.','warning')}<label class="field">Approved post copy<textarea name="posts" rows="6" maxlength="50000" required placeholder="Write one post. Separate additional posts with a line containing ---"></textarea></label><p>Up to 20 exact posts per review. The workflow uses your approved words; it does not invent product claims.</p><label class="field">App or landing-page link<input name="link" type="url" placeholder="https://your-app.example" maxlength="2048"></label><label class="field">Rights and claims evidence<textarea name="rights" maxlength="2000" required placeholder="Explain your authority to use this copy and media, and where its app claims are substantiated."></textarea></label><label class="field">Authority expires in hours<input name="hours" type="number" min="1" max="24" value="1" required></label><details><summary>Optional paid Meta campaign</summary><p>Leave the ad account empty for free organic publishing. Media limits exclude taxes, fees and currency conversion; provider reports may lag. A campaign's maximum approved media budget is reserved before activation.</p><label class="field">Numeric ad-account ID<input name="ad_account_id" inputmode="numeric" pattern="[0-9]+" maxlength="40"></label><label class="field">Currency<input name="currency" pattern="[A-Z]{3}" maxlength="3" value="${esc(state.workspace.app.data.currency||'USD')}" required></label><label class="field">Maximum media budget in minor units<input name="budget" type="number" min="0" max="100000000" value="0" step="1"></label><label class="field">Audience country codes<input name="countries" value="CA" maxlength="100" placeholder="CA, US"></label><label class="check-row"><input name="billing" type="checkbox"> I approve this media commitment and understand separate provider taxes, fees and billing delays.</label><label class="check-row"><input name="ordinary" type="checkbox"> I confirm this is outside Meta special ad categories (including housing, employment, financial products and political or social-issue advertising).</label></details><p id="campaign-error" role="alert"></p><div class="modal-actions"><button class="button primary" type="submit">Review exact automation scope</button>${button('Cancel','close')}</div></form><section class="modal-content"><h3>Saved scopes</h3>${history.scopes.length?history.scopes.map(s=>`<p>${esc(s.page_id)} · ${esc(s.status)} · expires ${esc(s.expires_at)} ${button('Inspect saved scope','campaign-status',`data-id="${esc(s.scope_id)}"`)}</p>`).join(''):'<p>No saved scopes for this owner and app yet.</p>'}</section>`);
}

async function campaignSubmit(form) {
  const submit=form.querySelector('[type=submit]');submit.disabled=true;
  try {
    campaignBound(form);const app=state.app,values=Object.fromEntries(new FormData(form));
    const selected=state.workspace.social_access.accounts.find(r=>r.id===values.connection_id&&r.provider==='facebook');
    if(!selected)throw new Error('Choose a connected Facebook Page.');
    const messages=values.posts.split(/\r?\n---\r?\n/).map(s=>s.trim()).filter(Boolean);
    if(!messages.length||messages.length>20||messages.some(s=>s.length>5000))throw new Error('Use 1–20 posts, with at most 5,000 characters each.');
    const hours=Number(values.hours),paid=Boolean(values.ad_account_id),budget=Number(values.budget);
    if(!Number.isInteger(hours)||hours<1||hours>24)throw new Error('Choose 1–24 hours.');
    if(!Number.isSafeInteger(budget)||budget<0||(!paid&&budget!==0))throw new Error('Select an ad account for a paid budget, or use zero for organic publishing.');
    const link=values.link.trim()||null,rights=values.rights.trim();
    if(!rights)throw new Error('Explain your rights and claim evidence before approving use.');
    const rightsHash=await campaignHash({app_id:app,attestation:rights});
    const posts=await Promise.all(messages.map(async message=>({request_id:crypto.randomUUID(),message,link,content_hash:await campaignHash({message,link}),rights_hash:rightsHash})));
    const targeting={countries:[...new Set(values.countries.split(',').map(s=>s.trim().toUpperCase()).filter(Boolean))].sort()};
    const targetingHash=await campaignHash(targeting),expires=new Date(Date.now()+hours*3600000).toISOString();
    const scope={connection_id:selected.id,page_id:selected.data.destination.id,ad_account_id:values.ad_account_id.trim()||null,currency:values.currency.trim(),expires_at:expires,max_posts:posts.length,max_calls:500,max_campaigns:paid?1:0,max_campaign_minor:paid?budget:0,max_total_minor:paid?budget:0,approved_content_hashes:[...new Set(posts.map(p=>p.content_hash))],approved_rights_hashes:[rightsHash],approved_targeting_hashes:paid?[targetingHash]:[],billing_acknowledged:values.billing==='on',ordinary_ad_attestation:values.ordinary==='on'};
    const saved=await api(`/api/apps/${app}/campaigns/prepare`,{scope});campaignBound(form);
    modal('Approve your campaign scope',`<div id="campaign-review" class="modal-content" data-app="${esc(app)}" data-version="${state.workspace.app.version}"><p>Page ${esc(saved.page_id)} · ${posts.length} exact posts · expires ${esc(saved.expires_at)}.</p><p>Ad account: ${esc(saved.ad_account_id||'None — organic publishing only')}. Maximum media commitment: ${saved.max_total_minor} minor units ${esc(saved.currency)}. ${esc(saved.billing_notice)}</p><p>Rights evidence: ${esc(rights)}. ${esc(saved.rights_notice)}</p>${posts.map(p=>`<section class="panel"><p>${esc(p.message)}</p><p>${esc(p.link||'No link')}</p><small>Content hash: ${esc(p.content_hash)}</small></section>`).join('')}<details><summary>Exact authority and limits</summary><pre>${esc(JSON.stringify(saved,null,2))}</pre></details><p>Approval permits these supported effects without reviewing each post again. It does not guarantee reach, installs or revenue.</p><p id="campaign-error" role="alert"></p>${button('Approve scope and enable automation','campaign-activate','', 'primary')}${button('Cancel','close')}</div>`);
    $('#campaign-review').campaign={scope:saved,posts,targeting,targetingHash,budget,expires,adRequestID:crypto.randomUUID()};
  } catch(error) {if(form.isConnected)form.querySelector('#campaign-error').textContent=error.message;}
  finally {submit.disabled=false;}
}

async function campaignStatus(scopeID,plan=null) {
  const app=state.app,result=await api(`/api/apps/${app}/campaigns/status`,{scope_id:scopeID});
  if(app!==state.app)return;
  const scope=result.scope;
  modal('Campaign progress',`<div id="campaign-progress" class="modal-content" data-app="${esc(app)}" data-version="${state.workspace.app.version}" data-id="${esc(scopeID)}"><p>Scope: <strong>${esc(scope.status)}</strong> · Page ${esc(scope.page_id)} · expires ${esc(scope.expires_at)}.</p><p>Media ceiling: ${scope.max_total_minor} minor units ${esc(scope.currency)}. Calls used: ${esc(scope.call_allowance_units_used??scope.calls_used??'Unknown')}/${scope.max_calls}.</p><p id="campaign-activity" role="status">Saved provider states shown below. A post ID or ad status does not establish app sales.</p>${result.intents.map(row=>`<section class="panel"><h3>${esc(row.status)}</h3><p>Receipt: ${esc(row.id)}</p><p>Provider ID: ${esc(row.remote_id||(row.ids?Object.values(row.ids).join(', '):'Not confirmed'))}</p><pre>${esc(JSON.stringify(row.result,null,2))}</pre>${button('Read provider status','campaign-reconcile',`data-intent="${esc(row.id)}"`)}${button('Pause owned paid campaign','campaign-pause',`data-intent="${esc(row.id)}"`)}</section>`).join('')||'<p>No effects have been dispatched for this scope.</p>'}<p id="campaign-error" role="alert"></p><div class="button-row">${plan&&scope.status==='ACTIVE'?button('Run approved workflow','campaign-run','','primary'):''}${button('Campaign report / Save PDF','campaign-report')}${button('Refresh saved receipts','campaign-status',`data-id="${esc(scopeID)}"`)}${button('Turn off this scope','campaign-revoke')}</div></div>`);
  $('#campaign-progress').campaign={...(plan||{}),scope,snapshot:result,read_at:new Date().toISOString()};
}

async function campaignAction(node) {
  const action=node.dataset.action;
  if(action==='campaign-open')return campaignOpen();
  if(action==='campaign-status')return campaignStatus(node.dataset.id);
  if(action==='campaign-report')return campaignReport($('#campaign-progress'));
  const panel=$('#campaign-review')||$('#campaign-progress');if(!panel)return;
  if(panel.dataset.busy==='true')return;
  panel.dataset.busy='true';panel.querySelectorAll('button').forEach(b=>b.disabled=true);
  let stopWatching=()=>{};
  try {
    campaignBound(panel);const app=state.app,plan=panel.campaign,scope=plan.scope;
    if(action==='campaign-activate') {
      await api(`/api/apps/${app}/campaigns/activate`,{scope_id:scope.scope_id,approval_hash:scope.approval_hash});
      campaignBound(panel);return campaignStatus(scope.scope_id,plan);
    }
    if(action==='campaign-run') {
      stopWatching=campaignWatch(panel,scope.scope_id);
      let firstPost=null;
      for(let i=0;i<plan.posts.length;i++) {
        campaignBound(panel);$('#campaign-activity').textContent=`Publishing approved post ${i+1} of ${plan.posts.length}…`;
        const result=await api(`/api/apps/${app}/campaigns/publish`,{scope_id:scope.scope_id,request:plan.posts[i]});
        campaignBound(panel);
        if(result.status!=='VERIFIED')throw new Error('Delivery needs reconciliation. Inspect the saved receipt; do not create a replacement request.');
        if(i===0)firstPost=result;
      }
      if(scope.ad_account_id&&firstPost) {
        $('#campaign-activity').textContent='Creating, verifying and activating the approved paid campaign…';
        await api(`/api/apps/${app}/campaigns/ad-launch`,{scope_id:scope.scope_id,request:{request_id:plan.adRequestID,post_id:firstPost.remote_id,content_hash:plan.posts[0].content_hash,rights_hash:plan.posts[0].rights_hash,targeting_hash:plan.targetingHash,targeting:plan.targeting,lifetime_budget_minor:plan.budget,end_time:plan.expires,name:'WMM approved app campaign'}});
      }
      campaignBound(panel);return campaignStatus(scope.scope_id);
    }
    const operation=action==='campaign-revoke'?'revoke':action==='campaign-pause'?'pause':action==='campaign-reconcile'?'reconcile':null;
    if(!operation)return;
    await api(`/api/apps/${app}/campaigns/${operation}`,{scope_id:scope.scope_id,...(operation==='revoke'?{}:{intent_id:node.dataset.intent})});
    campaignBound(panel);return campaignStatus(scope.scope_id);
  } catch(error) {if(panel.isConnected)panel.querySelector('#campaign-error').textContent=error.message;}
  finally {stopWatching();panel.dataset.busy='false';if(panel.isConnected)panel.querySelectorAll('button').forEach(b=>b.disabled=false);}
}

function campaignWatch(panel,scopeID) {
  const app=state.app;let stopped=false,timer=null,attempts=0;
  const poll=async()=>{
    if(stopped||!panel.isConnected||state.app!==app||attempts++>=120)return;
    try {
      if(!document.hidden) {
        const saved=await api(`/api/apps/${app}/campaigns/status`,{scope_id:scopeID});
        if(stopped||!panel.isConnected||state.app!==app)return;
        const latest=saved.intents.at(-1),activity=panel.querySelector('#campaign-activity');
        if(latest&&activity)activity.textContent=`Live saved stage: ${latest.status}. ${saved.intents.length} delivery intents recorded. ${latest.remote_id?'Provider ID: '+latest.remote_id:latest.ids?'Saved provider objects: '+Object.keys(latest.ids).join(', '):'Provider ID not yet confirmed.'}`;
      }
    } catch(error) {
      if(panel.isConnected&&!stopped)panel.querySelector('#campaign-error').textContent='Progress refresh failed. Existing work continues; inspect saved receipts before any retry.';
    }
    if(!stopped)timer=setTimeout(poll,5000);
  };
  timer=setTimeout(poll,1500);
  return ()=>{stopped=true;clearTimeout(timer);};
}

function campaignReport(panel) {
  if(!panel)throw new Error('Open the current campaign receipts first.');
  campaignBound(panel);
  const saved=panel.campaign.snapshot,scope=saved.scope;
  const report=WMMPageReports.model(state);
  report.title='Campaign delivery';report.purpose='Inspect saved provider delivery and approved media commitments for this scope.';
  report.next_step='Reconcile uncertain effects and compare source app KPIs in the declared experiment window.';
  report.loaded_at=panel.campaign.read_at;
  const source='Current authorized campaign scope and saved intent receipts';
  report.metrics=[
    {label:'Scope status',value:scope.status,unit:'state',source},
    {label:'Verified Page posts',value:saved.intents.filter(r=>!r.kind&&r.status==='VERIFIED').length,unit:'count',source},
    {label:'Paid intents',value:saved.intents.filter(r=>r.kind==='AD').length,unit:'count',source},
    {label:'Retained media commitments in this scope',value:saved.intents.filter(r=>r.kind==='AD').reduce((sum,r)=>sum+r.commitment,0),unit:`minor units ${scope.currency}`,source},
    {label:'Approved scope media ceiling',value:scope.max_total_minor,unit:`minor units ${scope.currency}`,source},
    {label:'Provider boundary allowance used',value:scope.call_allowance_units_used??null,unit:'conservative units',source}
  ];
  for(const row of saved.intents.filter(r=>r.kind==='AD'))report.metrics.push({label:`Reported spend · ${row.id}`,value:row.result?.reported_spend??null,unit:scope.currency,source:'Last saved provider report; may lag'});
  report.notes=['Scope '+scope.scope_id+'; exact approval hash '+scope.approval_hash,
    'Saved delivery is distinct from public reach, app installs, purchases and causal growth.',
    'Media commitments remain held after pause or uncertain responses. Taxes, fees and currency conversion are separate.',
    'No post copy, rights-attestation prose, credentials or raw creative payloads are included in this report.',
    'Refresh/reconcile provider observations before treating this saved view as current.'];
  report.cohorts=[];
  return WMMPageReports.openReport(report,window);
}
