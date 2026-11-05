/* Human controls for scoped grants and independent agent review. */
(function(root,factory){
  "use strict";
  const value=factory();
  if(typeof module==="object"&&module.exports)module.exports=value;
  else root.WMMAgentControl=value;
})(typeof globalThis==="object"?globalThis:this,function(){
  "use strict";
  const esc=v=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const text=v=>String(v??"").slice(0,1000);
  const readEffects=new Set(["READ_PRIVATE_LOCAL_DATA","READ_LOCAL_POLICY","READ_PRIVATE_EXECUTION_PLAN","READ_PRIVATE_LOCAL_ARTIFACT","READ_OWNED_PROVIDER_STATUS"]);
  const button=(name,action,extra="")=>`<button type="button" class="button outline" data-action="control-${esc(action)}" ${extra}>${esc(name)}</button>`;
  const errorBox='<p id="control-error" role="alert"></p>';
  let active=null,serial=0;

  function identity(state){return state.workspace?.identity?.principal||"";}
  function role(state){return state.workspace?.access?.members?.find(r=>r.principal===identity(state)&&r.status==="ACTIVE")?.role;}
  function scope(state){
    if(state.workspace?.app.id!==state.app)throw new Error("Load the selected app first.");
    return {app:state.app,version:state.workspace.app.version,principal:identity(state)};
  }
  function same(saved,state){return saved.app===state.app&&saved.version===state.workspace?.app.version&&saved.principal===identity(state);}
  function requireScope(saved,state){if(!same(saved,state))throw new Error("App setup or review identity changed. Reopen this control.");}
  function valid(ticket,deps){return active===ticket&&same(ticket.scope,deps.state)&&ticket.node?.isConnected&&deps.document.querySelector('#modal').open;}
  function clear(){
    if(active?.node)active.node.querySelectorAll('input[data-grant-secret]').forEach(input=>input.value="");
    active=null;serial++;
  }
  function invalidate(state){if(active&&!same(active.scope,state))clear();}
  function setupMarkup(){
    return '<details class="panel"><summary>Connect your agent through CLI or MCP</summary><p>Review configuration for this running installation. Setup review issues no grant, installs nothing and changes no host settings. Sign in as this app owner to review setup.</p></details>';
  }
  function setupReportMarkup(data){
    return '<p>Setup review only: no grant issued, host registered or command executed.</p><p>'+esc(data.runtime_kind==='PACKAGED_DESKTOP'?'Installed WMM uses its bundled executable; no separate Python is needed.':'Source runtime: use the interpreter and dependencies reported below.')+'</p>'
      +'<h3>CLI catalog command</h3><pre>'+esc(JSON.stringify(data.cli.catalog,null,2))+'</pre><h3>MCP host configuration</h3><pre>'+esc(JSON.stringify(data.mcp_config,null,2))+'</pre><p>MCP: '+esc(data.mcp.status)+'</p>'+(data.runtime_kind==='SOURCE_PYTHON'&&data.mcp.install?'<details><summary>Source dependencies</summary><pre>'+esc(JSON.stringify(data.mcp.install,null,2))+'</pre></details>':'')
      +'<p>Review registration in your chosen host separately. Supply WMM_AGENT_GRANT only through protected host environment input; this configuration contains no grant token. Missing grant never falls back to browser-session authority.</p>'
      +button('Download reviewed setup JSON','setup-download');
  }
  function setupValid(ticket,deps){
    return valid(ticket,deps)&&role(deps.state)==='OWNER';
  }
  async function setup(deps){
    if(role(deps.state)!=='OWNER')throw new Error('Sign in as this app owner to review setup.');
    const ticket=show(deps,'Review agent setup','setup-loading',null,'<p role="status">Reading this installation configuration...</p>');
    try{
      const data=await deps.api(`/api/apps/${ticket.scope.app}/agent-grants/setup`,{});
      if(setupValid(ticket,deps)){
        show(deps,'Review agent setup','setup',data,setupReportMarkup(data),ticket.scope);
      }
    }catch(e){
      if(setupValid(ticket,deps)){
        ticket.node.innerHTML='<p>'+esc(e.message)+' Saved settings are unchanged.</p>'
          +button('Retry setup review','setup')+errorBox;
      }
    }
  }
  function setupDownload(deps){
    const ticket=active;
    if(!ticket||ticket.kind!=='setup'||!setupValid(ticket,deps)){
      throw new Error('Reopen setup for the current app and owner.');
    }
    const browser=deps.browser;
    const url=browser.URL.createObjectURL(new browser.Blob(
      [JSON.stringify(ticket.data,null,2)],{type:'application/json'}));
    try{
      const link=deps.document.createElement('a');
      link.href=url;
      link.download=ticket.scope.app+'-agent-setup.json';
      link.click();
    }finally{
      browser.URL.revokeObjectURL(url);
    }
  }
  function panel(state){
    const owner=role(state)==="OWNER",signed=!!identity(state);
    return `<section class="panel" aria-label="Agent permissions and checkpoints"><p class="eyebrow">HUMAN CONTROL</p><h2>Delegate work. Review exact changes.</h2><p>Give an agent access to selected local operations, a deadline and a call allowance. Require a different signed-in checker before selected writes run. Inspect the saved result here after the agent resumes.</p><p>${signed?`Your app role: ${esc(role(state)||"No active role")}.`:"Sign in under Activity & reviews, then ask the app owner to assign your role."} Grant management requires the app owner. Approvals require a distinct owner or checker.</p><div class="button-row">${button("Inspect agent review queue","queue",signed?"":"disabled")}${owner?button("Manage agent grants","grants"):""}</div>${owner?button("Review agent setup","setup"):""}${setupMarkup()}</section>`;
  }
  function show(deps,title,kind,data,markup,saved=scope(deps.state)){
    clear();deps.modal(title,`<div id="agent-control-dialog" class="modal-content">${markup}${errorBox}</div>`,"AGENT PERMISSIONS & REVIEW");
    active={id:++serial,scope:saved,kind,data,node:deps.document.querySelector('#agent-control-dialog')};
    return active;
  }
  function reportButton(){return button("Report / Save PDF","report");}
  function expiryUI(){return globalThis.WMMAuthorityExpiry||(typeof require==='function'?require('./authority-expiry.js'):null);}
  function grantMarkup(data){
    const rows=data.grants;
    return `<p>These grants delegate selected operations in this app. Revocation blocks future admissions; it does not stop work already running.</p><p>${rows.length} saved grants · ${rows.filter(r=>r.status==="ACTIVE").length} marked active. Expiry, app version and remaining calls are rechecked at admission.</p><div class="button-row">${button("Issue an agent grant","new")}${reportButton()}</div>${rows.map(r=>{const expiry=r.permission_expires_at||r.expires;return `<section class="panel"><h3>${esc(r.agent_id)}</h3><p>${esc(r.status)} · ${esc(r.used)} / ${esc(r.max_calls)} attempts used · expires ${esc(expiry)}</p><p>Allowed: ${esc(r.operations.join(", "))}</p><p>Independent review: ${esc(r.review_operations.join(", "))||"None"}</p>${r.status==="ACTIVE"?`${button("Extend expiry","extend",`data-id="${esc(r.id)}" data-expires="${esc(expiry)}"`)}${button("Review revocation","revoke-open",`data-id="${esc(r.id)}"`)}`:""}</section>`;}).join("")||"<p>No grants issued. Issue one to connect a generic agent through the CLI or MCP.</p>"}`;
  }
  async function load(deps,kind,body={}){
    const ticket=show(deps,kind==="grants"?"Agent grants":"Agent review queue",kind,null,'<p role="status">Loading saved controls…</p>');
    try{
      const suffix=kind==="grants"?'agent-grants/list':'agent-reviews/list';
      const data=await deps.api(`/api/apps/${ticket.scope.app}/${suffix}`,body);
      if(!valid(ticket,deps))return;
      show(deps,kind==="grants"?"Agent grants":"Agent review queue",kind,data,kind==="grants"?grantMarkup(data):queueMarkup(data),ticket.scope);
    }catch(e){if(valid(ticket,deps))ticket.node.innerHTML=`<p>Saved work is preserved. ${esc(e.message)}</p>${button("Retry loading",kind)}${errorBox}`;}
  }
  function queueMarkup(data){
    return `<p>Inspect the exact proposed change before approving it. A different authenticated checker approves; the original agent then resumes the approved request once.</p><p>${data.items.length} requests displayed · ${data.total} saved in this app · offset ${data.offset}.</p><div class="button-row">${reportButton()}${button("Refresh queue","queue")}</div>${data.items.map(r=>`<section class="panel"><h3>${esc(r.operation)}</h3><p>${esc(r.state)} · agent ${esc(r.agent_id)} · maker ${esc(r.maker)}</p><p>Expires ${esc(r.expires)} · revision ${esc(r.revision)}</p>${button("Inspect exact request","inspect",`data-id="${esc(r.id)}"`)}</section>`).join("")||"<p>No agent requests in this app. An agent prepares one through review-prepare before a checker can approve it.</p>"}<div class="button-row">${data.offset?button("First requests","queue"):""}${data.next_offset!==null?button("Next requests","queue",`data-offset="${data.next_offset}"`):""}</div>`;
  }
  function permissions(view,state){
    const row=view.checkpoint,who=identity(state),member=role(state),distinct=who!==row.packet.maker;
    const checker=distinct&&["OWNER","CHECKER"].includes(member);
    return {approve:checker&&row.state==="WAITING_REVIEW",cancel:["WAITING_REVIEW","APPROVED","RUNNING"].includes(row.state)&&(member==="OWNER"||[row.packet.maker,row.checker].includes(who)),reconcile:checker&&["UNKNOWN","CANCEL_REQUESTED"].includes(row.state)};
  }
  function detailMarkup(view,state){
    const r=view.checkpoint,p=r.packet,allowed=permissions(view,state);
    return `<p>Review this frozen input, its app and its hashes. Approval authorizes this local operation once; the agent must resume it. Result and transition history remain below.</p><p>State: <strong>${esc(r.state)}</strong> · revision ${esc(r.revision)} · maker ${esc(p.maker)} · checker ${esc(r.checker||"Waiting")}</p><p>Agent ${esc(p.agent_id)} · expires ${esc(p.expires)}</p><p class="app-mono">Packet SHA256 ${esc(r.hash)}<br>Input SHA256 ${esc(view.input_hash)}</p><details open><summary>Exact frozen operation input</summary><pre>${esc(JSON.stringify(view.envelope,null,2))}</pre></details><details><summary>Saved result and transitions (${r.history.length})</summary><pre>${esc(JSON.stringify({result:view.result,history:r.history},null,2))}</pre></details><p>The PDF contains operational metadata and hashes. Private input and result bodies stay in this inspection dialog.</p><div class="button-row">${reportButton()}${button("Refresh exact request","inspect",`data-id="${esc(view.id)}"`)}${allowed.approve?button("Approve this exact request","approve"):""}${allowed.cancel?button(r.state==="RUNNING"?"Request cancellation":"Cancel this request","cancel"):""}${allowed.reconcile?button("Record reconciled outcome","reconcile-open"):""}</div>${allowed.approve?"<p>A changed packet, expired grant or revoked role is rejected by the server.</p>":"<p>Only a distinct active owner or checker can approve waiting work. Approval never changes the frozen input.</p>"}`;
  }
  async function inspect(deps,id){
    const ticket=show(deps,"Inspect agent request","detail",null,'<p role="status">Loading exact request…</p>');
    try{
      const data=await deps.api(`/api/apps/${ticket.scope.app}/agent-reviews/inspect`,{id});
      if(valid(ticket,deps))show(deps,"Inspect agent request","detail",data,detailMarkup(data,deps.state),ticket.scope);
    }catch(e){if(valid(ticket,deps))ticket.node.innerHTML=`<p>${esc(e.message)} Saved work is preserved.</p>${button("Retry inspection","inspect",`data-id="${esc(id)}"`)}${errorBox}`;}
  }
  const taskProfiles={
    research:{label:"Research only",operations:{"workspace.read":"READ_PRIVATE_LOCAL_DATA","operations.read":"READ_LOCAL_POLICY","report.read":"READ_PRIVATE_LOCAL_DATA","measurement.read":"READ_PRIVATE_LOCAL_DATA","growth.read":"READ_PRIVATE_LOCAL_DATA","growth.history":"READ_PRIVATE_LOCAL_DATA","customer.history":"READ_PRIVATE_LOCAL_DATA","discovery.history":"READ_PRIVATE_LOCAL_DATA","discovery.read":"READ_PRIVATE_LOCAL_DATA","discovery.handoff":"READ_PRIVATE_LOCAL_DATA","hypit.read":"READ_PRIVATE_LOCAL_DATA","hypit.plan":"READ_PRIVATE_EXECUTION_PLAN","editor.list":"READ_PRIVATE_LOCAL_DATA","editor.read":"READ_PRIVATE_LOCAL_DATA","editor.renders":"READ_PRIVATE_LOCAL_DATA","media.sources":"READ_PRIVATE_LOCAL_DATA","jobs.read":"READ_PRIVATE_LOCAL_DATA","campaign.history":"READ_PRIVATE_LOCAL_DATA","campaign.status":"READ_PRIVATE_LOCAL_DATA","campaign.reconcile":"READ_OWNED_PROVIDER_STATUS"}},
    organic:{label:"Organic marketing",operations:{"workspace.read":"READ_PRIVATE_LOCAL_DATA","report.read":"READ_PRIVATE_LOCAL_DATA","measurement.read":"READ_PRIVATE_LOCAL_DATA","growth.read":"READ_PRIVATE_LOCAL_DATA","discovery.history":"READ_PRIVATE_LOCAL_DATA","discovery.read":"READ_PRIVATE_LOCAL_DATA","discovery.collect":"WRITE_LOCAL_EVIDENCE","discovery.review":"WRITE_LOCAL_EVIDENCE","discovery.handoff":"READ_PRIVATE_LOCAL_DATA","creative.brief.save":"WRITE_LOCAL_PLAN","packaging.checklist":"READ_PRIVATE_LOCAL_DATA","hypit.read":"READ_PRIVATE_LOCAL_DATA","hypit.plan":"READ_PRIVATE_EXECUTION_PLAN","hypit.queue":"QUEUE_LOCAL_PREPARATION","editor.list":"READ_PRIVATE_LOCAL_DATA","editor.read":"READ_PRIVATE_LOCAL_DATA","editor.edit":"WRITE_LOCAL_PLAN","editor.queue":"QUEUE_LOCAL_PREPARATION","editor.renders":"READ_PRIVATE_LOCAL_DATA","jobs.read":"READ_PRIVATE_LOCAL_DATA","organic-video.policy-read":"READ_PRIVATE_LOCAL_DATA","organic-video.policy-reserve":"RESERVE_APPROVED_LOCAL_GENERATION","organic-video.policy-admit":"ADMIT_OUTPUT_UNDER_EXACT_OWNER_POLICY","organic-video.claim":"WRITE_LOCAL_EVIDENCE","organic-video.submit":"WRITE_LOCAL_EVIDENCE","organic-video.workflow-prepare":"READ_PRIVATE_EXECUTION_PLAN","organic-video.intent-create":"PREPARE_ADMITTED_EXTERNAL_EFFECT","organic-video.intent-read":"READ_PRIVATE_LOCAL_DATA","organic-video.intent-execute":"PUBLISH_WITH_EXACT_ORGANIC_POLICY"}},
    meta:{label:"Bounded Meta media buyer",operations:{"workspace.read":"READ_PRIVATE_LOCAL_DATA","report.read":"READ_PRIVATE_LOCAL_DATA","measurement.read":"READ_PRIVATE_LOCAL_DATA","campaign.history":"READ_PRIVATE_LOCAL_DATA","campaign.status":"READ_PRIVATE_LOCAL_DATA","growth.read":"READ_PRIVATE_LOCAL_DATA","growth.save":"WRITE_LOCAL_EVIDENCE","discovery.history":"READ_PRIVATE_LOCAL_DATA","discovery.read":"READ_PRIVATE_LOCAL_DATA","discovery.collect":"WRITE_LOCAL_EVIDENCE","discovery.handoff":"READ_PRIVATE_LOCAL_DATA","creative.brief.save":"WRITE_LOCAL_PLAN","packaging.checklist":"READ_PRIVATE_LOCAL_DATA","hypit.plan":"READ_PRIVATE_EXECUTION_PLAN","hypit.queue":"QUEUE_LOCAL_PREPARATION","editor.read":"READ_PRIVATE_LOCAL_DATA","editor.edit":"WRITE_LOCAL_PLAN","editor.queue":"QUEUE_LOCAL_PREPARATION","campaign.publish":"PUBLISH_WITH_STANDING_CAMPAIGN_AUTHORITY","campaign.ad-launch":"SPEND_WITH_STANDING_CAMPAIGN_AUTHORITY","campaign.reconcile":"READ_OWNED_PROVIDER_STATUS","campaign.pause":"PAUSE_OWNED_EXTERNAL_CAMPAIGN","experiment.evaluate":"WRITE_LOCAL_ASSESSMENT","experiment.action":"WRITE_LOCAL_DECISION","jobs.read":"READ_PRIVATE_LOCAL_DATA"}}
  };
  function resolveTaskProfile(profile,operations){
    if(profile==="custom")return {available:true,selected:[],missing:[]};
    const contract=taskProfiles[profile];if(!contract)return {available:false,selected:[],missing:["Unknown task profile"]};
    const missing=Object.entries(contract.operations).filter(([name,effect])=>!operations[name]||operations[name].effect!==effect).map(([name,effect])=>`${name} (${effect})`);
    return {available:missing.length===0,selected:Object.keys(contract.operations),missing,label:contract.label};
  }
  function grantSummary(form){
    const selected=[...form.querySelectorAll('input[name="operations"]:checked')].map(input=>input.value),profile=form.querySelector('#grant-task-profile'),id=profile.value;
    const details={research:"Reads saved app evidence, source research and campaign receipts. No local writes, rendering, publication or spending.",organic:"Prepares organic research, briefs, Hypit/editor work and delivery reports, including policy-gated publication. Source reuse, exact artifacts and destination approval remain required; this is not an automatic workflow.",meta:"Supports Meta research, creative preparation, reporting and existing campaign operations. Paid account scope and budget need separate exact owner approval; selection grants no provider authority."};
    const classes=new Set(selected.map(name=>form._grantOperations[name].effect)),groups=[];
    if([...classes].some(effect=>effect.startsWith("READ_")))groups.push("reads");
    if([...classes].some(effect=>["WRITE_LOCAL_PLAN","WRITE_LOCAL_EVIDENCE","WRITE_LOCAL_ASSESSMENT","WRITE_LOCAL_DECISION"].includes(effect)))groups.push("local evidence or plans");
    if([...classes].some(effect=>["QUEUE_LOCAL_PREPARATION","RESERVE_APPROVED_LOCAL_GENERATION","ADMIT_OUTPUT_UNDER_EXACT_OWNER_POLICY","PREPARE_ADMITTED_EXTERNAL_EFFECT"].includes(effect)))groups.push("local preparation");
    if([...classes].some(effect=>effect.startsWith("PUBLISH_")))groups.push("policy-gated publication");
    if([...classes].some(effect=>effect.startsWith("SPEND_")))groups.push("separately approved spending");
    if([...classes].some(effect=>effect.startsWith("PAUSE_")))groups.push("owned campaign controls");
    const label=taskProfiles[id]?.label||"Custom scope",summary=details[id]||`${selected.length} selected operations: ${groups.join(", ")||"none"}. Review the exact operation list under Advanced scope.`;
    form.querySelector('[data-task-summary]').textContent=`${label} · ${summary} Selecting or editing a task never issues a grant.`;
  }
  function reviewMarkup(name,rule){
    return rule.method==="POST"&&!readEffects.has(rule.effect)?`<label class="check-label"><input type="checkbox" name="reviews" value="${esc(name)}" checked> Require independent review for ${esc(name)}</label>`:"";
  }
  function bindGrantPresets(form,operations){
    form._grantOperations=operations;
    const profile=form.querySelector('#grant-task-profile');
    profile.addEventListener('change',()=>{
      if(profile.value==="custom"){grantSummary(form);return;}
      const result=resolveTaskProfile(profile.value,operations);
      if(!result.available){profile.value="custom";const message=result.missing.join(", ");form.querySelector('[data-task-summary]').textContent=`${result.label||"Task preset"} unavailable: required operation/effect changed or missing: ${message}. Custom scope is available; no operation was silently removed.`;return;}
      form.querySelectorAll('input[name="operations"]').forEach(input=>{input.checked=result.selected.includes(input.value);});
      form.querySelectorAll('input[name="reviews"]').forEach(input=>{const rule=operations[input.value];input.checked=result.selected.includes(input.value)&&rule.method==="POST"&&!readEffects.has(rule.effect);});
      grantSummary(form);
    });
    form.addEventListener('change',event=>{if(event.target.name==="operations"){profile.value="custom";grantSummary(form);}});
    grantSummary(form);
  }
  function grantForm(operations){
    const expiry=expiryUI(),profiles=Object.entries(taskProfiles).map(([id,p])=>{const available=resolveTaskProfile(id,operations).available;return `<option value="${id}"${available?"":" disabled"}>${esc(p.label)}${available?"":" — unavailable (catalog changed)"}</option>`;}).join("");
    return `<form id="control-grant-form"><p>Select an editable operation proposal. Selection only changes this form; it does not issue a grant or start work.</p><label class="field" for="grant-task-profile">Task preset<select id="grant-task-profile" name="task_profile"><option value="custom" selected>Custom</option>${profiles}</select></label><p data-task-summary role="status" aria-live="polite">No operations selected. Selecting or editing a task never issues a grant.</p><label class="field" for="grant-agent">Agent identifier<input id="grant-agent" name="agent_id" pattern="[a-z0-9][a-z0-9-]*" maxlength="200" required></label>${expiry.expiryInput('expires_at',Date.now()+60*60*1000,'Grant expires — device local time')}${expiry.consentMarkup()}<label class="field" for="grant-calls">Maximum admitted attempts<input id="grant-calls" name="max_calls" type="number" min="1" max="10000" value="20" required></label><p>The chosen attempt limit is total for this grant until expiry. Default: 20; no automatic weekly refill.</p><details data-task-advanced><summary>Advanced scope · full operation catalog</summary><fieldset><legend>Allowed operations and required checkpoints</legend>${Object.entries(operations).map(([name,rule])=>`<div><label class="check-label"><input type="checkbox" name="operations" value="${esc(name)}"> ${esc(name)} · ${esc(rule.effect)}</label>${reviewMarkup(name,rule)}</div>`).join("")}</fieldset></details><p>Non-read operations require independent review by default. Clearing a review checkbox delegates that operation without a checker, including publication or spending where selected. Exact campaign or organic-policy approval, accounts and budget still apply; choosing a preset grants none.</p><p id="control-form-error" role="alert"></p><button class="button" type="submit">Issue scoped grant</button></form>`;
  }
  async function newGrant(deps){
    const ticket=show(deps,"Issue an agent grant","new",null,'<p role="status">Loading available operations…</p>');
    try{
      const data=await deps.api(`/api/apps/${ticket.scope.app}/agent-operations`);
      if(valid(ticket,deps)){const next=show(deps,"Issue an agent grant","new",data.local_catalog.operations,grantForm(data.local_catalog.operations),ticket.scope),form=next.node.querySelector('#control-grant-form');expiryUI().bindConsent(form);bindGrantPresets(form,data.local_catalog.operations);}
    }catch(e){if(valid(ticket,deps))ticket.node.innerHTML=`<p>${esc(e.message)}</p>${button("Retry operation discovery","new")}${errorBox}`;}
  }
  function issueBody(values,operations,saved,now=Date.now()){
    const selected=values.operations||[],hours=Number(values.hours),calls=Number(values.max_calls);
    if(!selected.length||selected.some(name=>!Object.hasOwn(operations,name)))throw new Error("Select at least one available operation.");
    let expires,extended=false;if(values.expires_at){const selectedExpiry=expiryUI().validateExpiry(values.expires_at,values.extended_expiry_consent==='on',now);expires=selectedExpiry.expires;extended=selectedExpiry.extended;}else{if(!validLimits(hours,calls))throw new Error("Use up to 24 hours and 1–10000 admitted attempts.");expires=new Date(now+hours*3600000).toISOString();}
    if(!Number.isInteger(calls)||calls<1||calls>10000)throw new Error("Use 1–10000 admitted attempts.");
    return {agent_id:values.agent_id,manifest_version:saved.version,operations:selected,review_operations:(values.reviews||[]).filter(name=>selected.includes(name)&&operations[name].method==="POST"),max_calls:calls,expires,...(extended?{extended_expiry_consent:true}:{})};
  }
  function validLimits(hours,calls){return Number.isFinite(hours)&&hours>0&&hours<=24&&Number.isInteger(calls)&&calls>=1&&calls<=10000;}
  function tokenMarkup(issued){
    return `<p>The grant is saved. Copy the token into your agent's protected credential input now; WMM will not show it again. Closing this dialog or changing app or review identity clears it.</p><label class="field" for="grant-secret">Once-only agent bearer token<input id="grant-secret" data-grant-secret type="password" readonly autocomplete="off"></label>${button("Show or hide token","reveal")}<p>Grant ${esc(issued.grant.id)} · expires ${esc(issued.grant.expires)} · ${esc(issued.grant.max_calls)} admitted attempts.</p><p>Use the CLI's --use-grant mode or the MCP server's grant configuration. The token cannot sign in as a human checker.</p>${button("Return to grant list","grants")}`;
  }
  function reconciliationForm(){
    return '<form id="control-reconcile-form"><p>Inspect the actual saved effect before recording its known outcome. This records evidence and never retries the operation.</p><label class="field" for="reconcile-outcome">Verified outcome<select id="reconcile-outcome" name="outcome"><option value="SUCCEEDED">Succeeded</option><option value="FAILED">Failed</option></select></label><label class="field" for="reconcile-hash">Evidence SHA256<input id="reconcile-hash" name="evidence_hash" pattern="[a-f0-9]{64}" minlength="64" maxlength="64" required></label><p id="control-form-error" role="alert"></p><button class="button" type="submit">Record outcome without retry</button></form>';
  }
  async function submit(form,deps){
    const ticket=active;
    if(!ticket||form.dataset.pending==="true")return;
    const submit=form.querySelector('[type=submit]');form.dataset.pending="true";submit.disabled=true;
    try{
      requireScope(ticket.scope,deps.state);
      if(!valid(ticket,deps))throw new Error("Reopen this control before submitting.");
      const fields=new deps.FormData(form),values=Object.fromEntries(fields);
      let result;
      if(form.id==="control-grant-form"){
        values.operations=fields.getAll('operations');values.reviews=fields.getAll('reviews');
        result=await deps.api(`/api/apps/${ticket.scope.app}/agent-grants/issue`,issueBody(values,ticket.data,ticket.scope));
        if(!valid(ticket,deps)){deps.toast("Grant was issued. Its token was cleared after the scope changed; revoke it before issuing a replacement.");return;}
        const delivery=show(deps,"Copy your agent token now","token",{grant:result.grant},tokenMarkup(result),ticket.scope);
        delivery.node.querySelector('[data-grant-secret]').value=result.token;
      }else if(form.id==="control-reconcile-form"){
        const r=ticket.data.checkpoint;
        await deps.api(`/api/apps/${ticket.scope.app}/agent-reviews/reconcile`,{id:ticket.data.id,revision:r.revision,...values});
        if(valid(ticket,deps))await inspect(deps,ticket.data.id);
      }
    }catch(e){formError(ticket,form,e);}
    finally{form.dataset.pending="false";submit.disabled=false;}
  }
  function formError(ticket,form,error){if(active===ticket&&form.isConnected)form.querySelector('#control-form-error').textContent=error.message+" Inputs are preserved.";}
  async function transition(deps,command){
    const ticket=active;if(!ticket||ticket.pending)return;
    requireScope(ticket.scope,deps.state);if(!valid(ticket,deps))return;
    ticket.pending=true;ticket.node.querySelectorAll('button').forEach(n=>n.disabled=true);
    try{
      const r=ticket.data.checkpoint,body={id:ticket.data.id,revision:r.revision};
      if(command==="approve")body.packet_hash=r.hash;
      await deps.api(`/api/apps/${ticket.scope.app}/agent-reviews/${command}`,body);
      if(valid(ticket,deps))await inspect(deps,ticket.data.id);
    }catch(e){if(valid(ticket,deps))ticket.node.querySelector('#control-error').textContent=e.message+" Refresh the exact request before retrying.";}
    finally{ticket.pending=false;ticket.node?.querySelectorAll('button').forEach(n=>n.disabled=false);}
  }
  function report(ticket,state,reports){
    requireScope(ticket.scope,state);
    const base=reports.model({...state,view:"activity"}),data=ticket.data;
    let notes=[],metrics=[];
    if(ticket.kind==="grants"){
      metrics=[{label:"Saved grants",value:data.grants.length,source:"authenticated owner grant list",unit:"count"}];
      notes=data.grants.map(r=>`${r.agent_id}: ${r.status}; attempts ${r.used}/${r.max_calls}; expires ${r.expires}; allowed ${r.operations.join(', ')}; review ${r.review_operations.join(', ')||'none'}.`);
    }else if(ticket.kind==="queue"){
      metrics=[{label:"Saved requests",value:data.total,source:"authenticated review queue",unit:"count"},{label:"Displayed requests",value:data.items.length,source:"current queue page",unit:"count"}];
      notes=data.items.map(r=>`${r.id}: ${r.operation}; ${r.state}; revision ${r.revision}; packet ${r.checkpoint_hash}.`);
    }else if(ticket.kind==="detail"){
      const r=data.checkpoint;
      metrics=[{label:"Recorded transitions",value:r.history.length,source:"exact saved checkpoint",unit:"count"}];
      notes=[`Request ${data.id}; operation ${data.envelope.operation}; state ${r.state}; revision ${r.revision}; maker ${r.packet.maker}; checker ${r.checker||'none'}; expires ${r.packet.expires}.`,`Packet SHA256 ${r.hash}; input SHA256 ${data.input_hash}.`,...r.history.map(h=>`${h.state}: ${h.observed_at}; evidence ${h.evidence_hash||'none'}.`)];
    }else throw new Error("Close the credential or entry form before preparing a metadata report.");
    return {...base,title:"Agent controls: "+ticket.kind,purpose:"Inspect saved delegation and independent checkpoint metadata for this app.",next_step:"Review current permissions and exact input in WMM before acting.",filters:{scope:ticket.kind,offset:data.offset??"not paged"},metrics,cohorts:[],notes:notes.map(text).concat("Metadata only. Bearer tokens, raw operation input and private result bodies are excluded. This report grants no execution authority.")};
  }
  async function revoke(deps){
    const ticket=active;if(!ticket||ticket.pending)return;requireScope(ticket.scope,deps.state);
    if(!valid(ticket,deps))return;ticket.pending=true;
    try{
      await deps.api(`/api/apps/${ticket.scope.app}/agent-grants/revoke`,{id:ticket.data.id,version:ticket.data.version});
      if(valid(ticket,deps))await load(deps,"grants");
    }catch(e){if(valid(ticket,deps))ticket.node.querySelector('#control-error').textContent=e.message;}
    finally{ticket.pending=false;}
  }
  function revokeOpen(node,deps,ticket){
    const row=ticket.data.grants.find(r=>r.id===node.dataset.id);if(!row)throw new Error("Reload this grant list.");
    return show(deps,"Revoke this grant?","revoke",row,`<p>Block future admissions for ${esc(row.agent_id)} in this app. Work already running retains its receipt and may need reconciliation.</p>${button("Revoke this grant","revoke")}`,ticket.scope);
  }
  function reveal(ticket){const input=ticket.node.querySelector('[data-grant-secret]');input.type=input.type==="password"?"text":"password";}
  async function savedAction(command,node,deps){
    const ticket=active;if(!ticket)return;requireScope(ticket.scope,deps.state);if(!valid(ticket,deps))return;
    const actions={report:()=>deps.pageReports.openReport(report(ticket,deps.state,deps.pageReports),deps.browser),
      reveal:()=>reveal(ticket),approve:()=>transition(deps,'approve'),cancel:()=>transition(deps,'cancel'),
      'reconcile-open':()=>show(deps,"Reconcile uncertain work","reconcile",ticket.data,reconciliationForm(),ticket.scope),
      'revoke-open':()=>revokeOpen(node,deps,ticket),revoke:()=>revoke(deps)};
    if(Object.hasOwn(actions,command))return actions[command]();
  }
  async function action(node,deps){
    const command=node.dataset.action.slice(8);
    try{
      if(command==='extend'){
        const ticket=active,grant=ticket?.data?.grants?.find(row=>row.id===node.dataset.id&&row.status==='ACTIVE');if(!ticket||!grant)throw new Error('Reload the active grant before extending it.');
        return expiryUI().open({kind:'AGENT_GRANT',id:grant.id,expires:grant.expires,app:ticket.scope.app,api:deps.api,modal:deps.modal,document:deps.document,FormData:deps.FormData,uuid:deps.uuid,owner:()=>role(deps.state)==='OWNER',current:()=>same(ticket.scope,deps.state),done:()=>load(deps,'grants')});
      }
      const actions={setup:()=>setup(deps),'setup-download':()=>setupDownload(deps),grants:()=>load(deps,'grants'),queue:()=>load(deps,'queue',{offset:Number(node.dataset.offset||0)}),inspect:()=>inspect(deps,node.dataset.id),new:()=>newGrant(deps)};
      if(Object.hasOwn(actions,command))return await actions[command]();
      return await savedAction(command,node,deps);
    }catch(e){if(active?.node?.isConnected)active.node.querySelector('#control-error').textContent=e.message;else deps.toast(e.message);}
  }
  return {panel,setupMarkup,setupReportMarkup,scope,same,requireScope,permissions,issueBody,report,clear,invalidate,action,submit,grantMarkup,queueMarkup,detailMarkup,grantForm,tokenMarkup,taskProfiles,resolveTaskProfile,bindGrantPresets};
});
