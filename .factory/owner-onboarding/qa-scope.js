/** identityLogin: Collect an ephemeral identity token and optionally retain the explicit first-owner task. */
export function identityLogin(next="") {
  modal("Sign in for verified review",`<form id="identity-form" data-app="${esc(state.app)}" data-app-version="${state.workspace.app.version}" data-next="${next==='owner-bootstrap'?'owner-bootstrap':''}"><div class="modal-content">${notice("Use your own GitHub fine-grained token with no repository permissions. This verifies your numeric account ID through GitHub; it does not connect product data or repositories.")}<p><a href="https://github.com/settings/personal-access-tokens/new" target="_blank" rel="noopener noreferrer">Create a GitHub identity token</a> · <a href="https://docs.github.com/en/rest/users/users#get-the-authenticated-user" target="_blank" rel="noopener noreferrer">Review the identity permissions</a></p><label class="field" for="identity-token">GitHub identity token<input id="identity-token" name="token" type="password" autocomplete="off" minlength="20" maxlength="256" required></label><p class="description">The token is cleared from this form after submission and never saved to workspace files or browser storage. Sign-out or server restart clears the session.</p><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit">Verify my identity</button></div></form>`,"EPHEMERAL REVIEW SESSION");
}

/** accessBootstrap: Require an authenticated identity and explicit checkbox before establishing the first app owner. */
export function accessBootstrap() {
  if(reviewIdentity().status!=="AUTHENTICATED")return identityLogin("owner-bootstrap");
  modal("Establish this app's owner",`<form id="access-bootstrap-form" data-app="${esc(state.app)}"><div class="modal-content">${notice(`This establishes ${reviewIdentity().login} as the fixed local owner of ${state.workspace.app.data.name}. Use the actual app owner's account on this trusted workstation. It cannot replace an existing owner.`)}<label class="check-label"><input type="checkbox" name="confirm_owner" required> I am establishing the first owner for this local app.</label><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit">Establish verified owner</button></div></form>`);
}

/** ownerContinuation: Resume only the still-connected original app task after authenticated sign-in. */
export function ownerContinuation(form,app,active) {
  return active&&form.isConnected&&!$('#modal').open&&form.dataset.next==='owner-bootstrap'&&state.app===app&&
    String(state.workspace.app.version)===form.dataset.appVersion&&
    reviewIdentity().status==='AUTHENTICATED'&&state.workspace.access?.configured===false;
}

/** verifiedRequest: Submit one selected review form through its existing closed API route. */
export async function verifiedRequest(form,id,data,app) {
  if(id==='identity-form'){const token=data.token;form.reset();return api('/api/identity/login',{token});}
  const requests={
    'access-bootstrap-form':()=>api(`/api/apps/${app}/access/bootstrap`,{confirm_owner:!!data.confirm_owner}),
    'access-member-form':()=>api(`/api/apps/${app}/access/members`,{...data,version:form.dataset.version?Number(form.dataset.version):null}),
    'verified-prepare-form':()=>api(`/api/apps/${app}/verified-reviews`,data)
  };
  return requests[id]();
}

/** verifiedSubmitted: Refresh current authority before returning to the intended owner step or saved review. */
export async function verifiedSubmitted(form,id,data,app) {
  const result=await verifiedRequest(form,id,data,app);
  const active=form.isConnected&&$('#modal').open;
  if(active)$('#modal').close();
  await refresh();
  if(ownerContinuation(form,app,active))return accessBootstrap();
  if(id==='verified-prepare-form'&&result&&active&&state.app===app)return verifiedOpen(result.id);
}

/** verifiedSubmit: Retain form error handling and prevent a second submit while a request is pending. */
export async function verifiedSubmit(event) {
  const form=event.target,id=form.id;
  if(!['identity-form','access-bootstrap-form','access-member-form','verified-prepare-form'].includes(id))return;
  event.preventDefault();const submit=form.querySelector('[type="submit"]');submit.disabled=true;
  const data=Object.fromEntries(new FormData(form)),app=form.dataset.app||state.app;
  try {await verifiedSubmitted(form,id,data,app);}
  catch(error){const field=form.querySelector('#form-error');if(form.isConnected&&field)field.textContent=error.message;else toast(error.message);}
  finally {submit.disabled=false;}
}
