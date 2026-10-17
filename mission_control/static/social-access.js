"use strict";
function socialPanel() {
  const access=state.workspace.social_access;if(!access)return '';
  const configs=access.setup.configurations;
  const providers=Object.entries(access.setup.providers).map(([id,p])=>{
    const saved=configs.find(row=>row.provider===id);
    return `<section class="panel"><h3>${esc(p.name)}</h3><p>${saved?'Setup saved. Confirm an account through official login.':'Prepare this app’s official setup, then connect your account.'}</p>${button(saved?'Connect an account':'Set up connection','social-setup',`data-provider="${id}"`)}${saved?button('Edit setup','social-edit',`data-provider="${id}"`):''}</section>`;
  }).join('');
  const accounts=access.accounts.filter(row=>row.status!=='DISCONNECTED').map(row=>`<section class="panel"><h3>${esc(row.data.destination.name)}</h3><p>${esc(label(row.provider))} · ${esc(label(row.status))}${row.reconnect_required?' · Access expired':''}</p><p>Selected destination: ${esc(row.data.destination.kind.toLowerCase())}. ${row.data.facts.renewal==='OFFICIAL_REAUTHORIZATION'?'The provider will sometimes require official login again.':'Provider-supported renewal keeps this account connected while valid.'}</p><div class="button-row">${button('Test saved access','social-test',`data-id="${row.id}"`)}${button('Reconnect','social-reconnect',`data-id="${row.id}"`)}${button('Disconnect locally','social-disconnect',`data-id="${row.id}"`)}</div></section>`).join('');
  return `<section aria-labelledby="social-heading"><h2 id="social-heading">Social accounts</h2><p>Connect once for this app. Login is retained in protected storage, with supported renewal. Account access does not post, message or spend.</p><div class="connection-grid">${providers}</div>${accounts?`<h3>Saved accounts</h3><div class="connection-grid">${accounts}</div>`:''}${button('Recover old connection setup','social-cleanup')}</section>`;
}

async function socialSetup(provider,edit=false,reconnect='') {
  const app=state.app,row=state.workspace.social_access.setup.configurations.find(r=>r.provider===provider);
  if(row&&!edit)return socialStart(provider,row.version,reconnect);
  const packet=await api(`/api/apps/${app}/social-access/packet`,{provider,native_enabled:row?.data.native_enabled||false});
  if(app!==state.app)return;
  const data=row?.data||{};
  modal(`Connect ${label(provider)}`,`<form id="social-setup-form" class="modal-content" data-app="${esc(app)}" data-provider="${provider}" data-version="${row?.version||0}"><p>Prepared for <strong>${esc(packet.app_name)}</strong>. Recommended developer-app name: ${esc(packet.suggested_developer_name)}.</p><ol>${packet.steps.map(step=>`<li>${esc(step)}</li>`).join('')}</ol><p><a href="${esc(packet.official_setup)}" target="_blank" rel="noopener noreferrer">Open official developer setup ↗</a></p>${button('Find existing app setup','social-discover',`data-provider="${provider}"`)}<label class="field">Provider app / client ID<input name="client_id" required maxlength="128" autocomplete="off" value="${esc(data.client_id||'')}"></label><label class="field">Provider client secret<input type="password" name="client_secret" maxlength="2048" autocomplete="off" ${data.native_enabled?'':'required'}></label><label class="field">Exact callback URL<input name="redirect_uri" type="url" ${packet.redirect_uri?'readonly':'required'} value="${esc(data.redirect_uri||packet.redirect_uri)}" placeholder="https://your-deployed-relay/cb/${provider}"></label>${provider==='linkedin'?'<label class="check-row"><input type="checkbox" name="native_enabled" '+(data.native_enabled?'checked':'')+'> LinkedIn has explicitly enabled native PKCE for this app. Use the system browser; no client secret is sent.</label>':''}<p>Requested read permissions: ${packet.scopes.map(esc).join(', ')}. Tokens and secrets stay protected on this workstation. Supported authentication renewals run automatically; uncertain attempts require reconnection.</p><p id="social-error" role="alert"></p><div class="modal-actions"><button class="button primary" type="submit">Approve setup and continue</button>${button('Cancel','close')}</div></form>`,'APP-SPECIFIC CONNECTION');
  if(provider==='linkedin') {
    const form=$('#social-setup-form'),checkbox=form.elements.native_enabled;
    checkbox.addEventListener('change',()=>{form.elements.client_secret.required=!checkbox.checked;form.elements.client_secret.value='';form.elements.redirect_uri.readOnly=checkbox.checked;form.elements.redirect_uri.required=!checkbox.checked;form.elements.redirect_uri.value=checkbox.checked?`${location.origin}/social/callback/linkedin`:'';});
  }
}

async function socialStart(provider,version,reconnect='') {
  const app=state.app,result=await api(`/api/apps/${app}/social-access/start`,{provider,version});
  if(app!==state.app)return;
  modal('Finish official login',`<div class="modal-content" id="social-progress" data-app="${esc(app)}" data-flow="${result.flow_id}" data-reconnect="${esc(reconnect)}"><p>Review ${esc(label(provider))}’s own consent screen. When it returns, confirm the detected destination here.</p><p>For desktop/native authorization, open this link in your default system browser. Keep Mission Control running.</p><p><a class="button primary" href="${esc(result.authorization_url)}" target="_blank" rel="noopener noreferrer">Open official ${esc(label(provider))} login ↗</a></p>${button('Copy login link for system browser','social-copy-login')}<div id="social-progress-result" role="status">Waiting for official login…</div>${button('Check login result','social-check')}${button('Cancel this login','social-cancel')}<p id="social-error" role="alert"></p></div>`,'OFFICIAL PROVIDER CONSENT');
  $('#social-progress').loginUrl=result.authorization_url;
  clearTimeout(socialPoll.timer);socialPoll.timer=setTimeout(()=>socialPoll(app,result.flow_id),1200);
}

async function socialPoll(app,id) {
  const panel=$('#social-progress');if(!panel||!$('#modal').open||panel.dataset.app!==app||state.app!==app||panel.dataset.flow!==id)return;
  try {
    const result=await api(`/api/apps/${app}/social-access/flows/${id}`);
    if($('#social-progress')!==panel||state.app!==app)return;
    $('#social-progress-result').textContent=label(result.status);
    if(result.status==='AWAITING_DESTINATION')return socialDestinations(result,panel.dataset.reconnect);
    if(['PENDING','EXCHANGING'].includes(result.status))socialPoll.timer=setTimeout(()=>socialPoll(app,id),1500);
    else panel.insertAdjacentHTML('beforeend',`<p>Your previous account access is preserved. Review setup or start a fresh official login.</p>${button('Review provider setup','social-edit',`data-provider="${result.provider}"`)}`);
  } catch(error) {$('#social-error').textContent=error.message;}
}

function socialDestinations(flow,reconnect) {
  const choices=flow.data.identity.destinations,app=state.app;
  const normalized=value=>String(value).trim().toLocaleLowerCase();
  const matches=choices.filter(item=>normalized(item.name)===normalized(state.workspace.app.data.name));
  const recommended=matches.length===1?matches[0].id:'';
  const saved=state.workspace.social_access.accounts.filter(row=>row.provider===flow.provider&&row.subject_id===flow.data.identity.subject_id&&row.status!=='DISCONNECTED');
  modal('Confirm this app’s destination',`<form id="social-confirm-form" class="modal-content" data-app="${esc(app)}" data-flow="${flow.id}"><p>Official provider account: <strong>${esc(flow.data.identity.name)}</strong>. ${recommended?'One destination exactly matches this app name. Please confirm it.':'Choose the account or Page this app should use. No destination has been selected automatically.'}</p><label class="field">Account or Page<select name="destination_id" required><option value="">Choose a verified destination</option>${choices.map(item=>`<option value="${esc(item.id)}" ${item.id===recommended?'selected':''}>${esc(item.name)} · ${esc(item.kind.toLowerCase())}</option>`).join('')}</select></label>${!choices.length?notice('No permitted destination was found. Review official permissions, then reconnect.','warning'):''}<label class="field">Save as<select name="connection_id"><option value="">A separate saved account</option>${saved.map(row=>`<option value="${row.id}" ${row.id===reconnect?'selected':''}>Reconnect ${esc(row.data.destination.name)}</option>`).join('')}</select></label><p>Confirming retains only this app’s grant. Read access has been checked; posting, messaging and ad spending are not enabled.</p><p id="social-error" role="alert"></p><div class="modal-actions"><button type="submit" class="button primary" ${choices.length?'':'disabled'}>Approve destination</button>${button('Cancel this login','social-cancel',`data-flow="${flow.id}"`)}${button('Review setup','social-edit',`data-provider="${flow.provider}"`)}</div></form>`,'VERIFIED ACCOUNT · YOUR CHOICE');
}

async function socialAction(node) {
  const action=node.dataset.action,app=state.app,id=node.dataset.id;
  if(action==='social-setup'||action==='social-edit')return socialSetup(node.dataset.provider,action==='social-edit');
  if(action==='social-reconnect') {
    const row=state.workspace.social_access.accounts.find(r=>r.id===id),config=state.workspace.social_access.setup.configurations.find(r=>r.provider===row.provider);
    return socialStart(row.provider,config.version,id);
  }
  if(action==='social-discover') {
    const provider=node.dataset.provider,result=await api(`/api/apps/${app}/social-access/discover`,{provider});
    if(app!==state.app)return;
    if(result.status==='SETUP_REQUIRED')return toast('No app-specific setup found. Use the official setup steps and enter that app’s credentials.');
    modal('Approve discovered setup',`<div class="modal-content"><p>Found client ${esc(result.configuration.client_id)} for this app only.</p><p>Callback: ${esc(result.configuration.redirect_uri)}. Protected secret: ${result.secret_present?'present':'not required for native PKCE'}.</p>${button('Approve this discovered setup','social-approve-discovered')}${button('Edit instead','social-edit',`data-provider="${provider}"`)}</div>`);
    $('#modal-body').socialDiscovered=result;return;
  }
  if(action==='social-approve-discovered') {
    const result=$('#modal-body').socialDiscovered,previous=state.workspace.social_access.setup.configurations.find(r=>r.provider===result.configuration.provider);
    const saved=await api(`/api/apps/${app}/social-access/approve-discovered`,{provider:result.configuration.provider,configuration:result.configuration,version:previous?.version||0});
    await refresh();return socialStart(saved.provider,saved.version);
  }
  if(action==='social-copy-login')return navigator.clipboard.writeText($('#social-progress').loginUrl).then(()=>toast('Login link copied. Open it in your default system browser.'));
  if(action==='social-check') {const panel=$('#social-progress');return socialPoll(app,panel.dataset.flow);}
  if(action==='social-cancel') {
    const flow=node.dataset.flow||$('#social-progress')?.dataset.flow;
    await api(`/api/apps/${app}/social-access/cancel`,{flow_id:flow});clearTimeout(socialPoll.timer);$('#modal').close();return refresh();
  }
  if(action==='social-cleanup') {const result=await api(`/api/apps/${app}/social-access/cleanup`,{});return toast(result.remaining?'Some setup stages need a later cleanup. Active accounts are protected.':'Unused local setup secrets removed. Active accounts are preserved.');}
  const row=state.workspace.social_access.accounts.find(r=>r.id===id);if(!row)return;
  if(action==='social-disconnect')return modal('Disconnect this local account?',`<div class="modal-content"><p>Remove this app’s retained access to ${esc(row.data.destination.name)}. Other apps and your provider login are unchanged. This does not revoke all provider sessions.</p>${button('Disconnect locally','social-confirm-disconnect',`data-id="${id}"`)}${button('Keep connected','close')}</div>`);
  if(action==='social-test'||action==='social-confirm-disconnect') {
    const result=await api(`/api/apps/${app}/social-access/${id}/${action==='social-test'?'test':'disconnect'}`,{version:row.version});
    if(app!==state.app)return;$('#modal').close();await refresh();return toast(action==='social-test'?'Saved provider read succeeded. Posting remains disabled.':result.cleanup==='LOCAL_CLEANUP_REQUIRED'?'Disconnected; retry local cleanup to remove old protected access.':'Disconnected for this app.');
  }
}

async function socialSubmit(form) {
  const submit=form.querySelector('[type=submit]');submit.disabled=true;
  try {
    const app=form.dataset.app;if(app!==state.app)throw new Error('App changed. Reopen this connection in the correct workspace.');
    const values=Object.fromEntries(new FormData(form));
    if(form.id==='social-setup-form') {
      const result=await api(`/api/apps/${app}/social-access/save`,{provider:form.dataset.provider,client_id:values.client_id,client_secret:values.client_secret||'',redirect_uri:values.redirect_uri||'',native_enabled:values.native_enabled==='on',version:Number(form.dataset.version)});
      form.elements.client_secret.value='';await refresh();return socialStart(result.provider,result.version);
    }
    const row=state.workspace.social_access.accounts.find(r=>r.id===values.connection_id);
    await api(`/api/apps/${app}/social-access/confirm`,{flow_id:form.dataset.flow,destination_id:values.destination_id,connection_id:values.connection_id,version:row?.version||0});
    if(app!==state.app)return;$('#modal').close();await refresh();toast('Account saved and read-tested. Provider-supported renewal is enabled.');
  } catch(error) {form.querySelector('#social-error').textContent=error.message;}
  finally {submit.disabled=false;}
}
