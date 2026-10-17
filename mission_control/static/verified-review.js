"use strict";

function reviewIdentity() {return state.workspace.identity || {status:"SIGNED_OUT"};}
function myReviewRole() {return (state.workspace.access?.members || []).find(r=>r.principal===reviewIdentity().principal&&r.status==="ACTIVE");}
function verifiedReviewPanel() {
  const w=state.workspace,identity=reviewIdentity(),access=w.access || {configured:false,members:[]},role=myReviewRole();
  const signed=identity.status==="AUTHENTICATED";
  const action=signed?button("Sign out of review session","identity-logout"):button("Sign in for verified review","identity-login");
  const setup=!access.configured?button("Establish app owner","access-bootstrap"):role?.role==="OWNER"?button("Assign a reviewer","access-member"):"";
  const members=access.members.map(r=>`<div class="record-row"><span class="record-main"><strong>${esc(r.login)}</strong><small>${esc(r.principal)} · ${esc(r.role)} · version ${r.version}</small></span>${status(r.status)}${role?.role==="OWNER"&&r.role!=="OWNER"?button("Edit access","access-member",`data-id="${esc(r.principal)}"`):""}</div>`).join("");
  const reviews=(w.verified_reviews || []).map(r=>`<button class="record-row" data-action="verified-review-open" data-id="${esc(r.id)}"><span class="record-main"><strong>${esc(r.packet.record.title)}</strong><small>Maker ${esc(r.preparer)} · ${esc(new Date(r.expires).toLocaleString())}</small></span>${status(r.availability==="CURRENT"?r.status:"UNAVAILABLE")}</button>`).join("");
  return `<section class="panel"><p class="eyebrow">VERIFIED REVIEW ACCESS</p><h2>Your app's maker and checker</h2><p class="description">${signed?`Signed in as ${esc(identity.login)} (${esc(identity.principal)}). ${role?`App role: ${esc(role.role)}.`:"No active role in this app."}`:"Sign in with your own GitHub account to prepare or independently review exact packets."}</p>${notice("Identity is rechecked for every protected action. Tokens stay in server memory for 15 minutes. Recorded review does not execute a provider action or authorize spending.")}<div class="toolbar">${action}${setup}</div>${members?`<details><summary>App access (${access.members.length})</summary>${members}</details>`:notice("The first verified owner must establish this app's local access policy.")}</section><div class="section-heading"><h2>Verified review inbox</h2>${button("Prepare verified review","verified-review-prepare")}</div>${reviews?`<div class="record-list">${reviews}</div>`:notice("No verified packets yet. Add distribution, store or experiment evidence, then prepare its exact contents for a different authenticated checker.")}`;
}

function identityLogin() {
  modal("Sign in for verified review",`<form id="identity-form"><div class="modal-content">${notice("Use your own GitHub fine-grained token with no repository permissions. This verifies your numeric account ID through GitHub; it does not connect product data or repositories.")}<p><a href="https://github.com/settings/personal-access-tokens/new" target="_blank" rel="noopener noreferrer">Create a GitHub identity token</a> · <a href="https://docs.github.com/en/rest/users/users#get-the-authenticated-user" target="_blank" rel="noopener noreferrer">Review the identity permissions</a></p><label class="field" for="identity-token">GitHub identity token<input id="identity-token" name="token" type="password" autocomplete="off" minlength="20" maxlength="256" required></label><p class="description">The token is cleared from this form after submission and never saved to workspace files or browser storage. Sign-out or server restart clears the session.</p><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit">Verify my identity</button></div></form>`,"EPHEMERAL REVIEW SESSION");
}

function accessBootstrap() {
  if(reviewIdentity().status!=="AUTHENTICATED")return identityLogin();
  modal("Establish this app's owner",`<form id="access-bootstrap-form" data-app="${esc(state.app)}"><div class="modal-content">${notice(`This establishes ${reviewIdentity().login} as the fixed local owner of ${state.workspace.app.data.name}. Use the actual app owner's account on this trusted workstation. It cannot replace an existing owner.`)}<label class="check-label"><input type="checkbox" name="confirm_owner" required> I am establishing the first owner for this local app.</label><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit">Establish verified owner</button></div></form>`);
}

function accessMember(principal) {
  const row=(state.workspace.access.members || []).find(r=>r.principal===principal);
  modal("Assign app review access",`<form id="access-member-form" data-app="${esc(state.app)}" data-version="${row?.version || ""}"><div class="modal-content">${notice("The authenticated owner assigns a separate maker or checker by their verified GitHub account ID. Revoking or changing access invalidates that role's earlier packets. This does not grant access to Apple or other providers.")}<label class="field" for="member-login">GitHub username<input id="member-login" name="login" maxlength="39" value="${esc(row?.login || "")}" ${row?"readonly":""} required></label><label class="field" for="member-role">App role<select id="member-role" name="role"><option value="CHECKER" ${row?.role==="CHECKER"?"selected":""}>Checker: independently inspect packets</option><option value="MAKER" ${row?.role==="MAKER"?"selected":""}>Maker: prepare exact packets</option></select></label><label class="field" for="member-status">Access status<select id="member-status" name="status"><option value="ACTIVE">Active</option><option value="REVOKED" ${row?.status==="REVOKED"?"selected":""}>Revoked</option></select></label><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit">Save app access</button></div></form>`);
}

function verifiedPrepare() {
  if(reviewIdentity().status!=="AUTHENTICATED")return identityLogin();
  const records=state.workspace.records.filter(r=>["distribution","store","experiment"].includes(r.kind));
  if(!records.length)return modal("Add review evidence first",`<div class="modal-content">${notice("Add this app's distribution, store or experiment record before freezing a packet.")}</div><div class="modal-actions">${button("Add store evidence","add-evidence",'data-kind="store"')}</div>`);
  modal("Prepare verified review",`<form id="verified-prepare-form" data-app="${esc(state.app)}"><div class="modal-content">${notice("Freeze this app's current manifest, exact record and your authenticated maker role for 24 hours. A different authorized checker must review the hash. External execution remains unimplemented.")}<label class="field" for="verified-record">Source evidence<select id="verified-record" name="record_id">${records.map(r=>`<option value="${esc(r.id)}">${esc(r.title)}</option>`).join("")}</select></label><div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions"><button class="button" type="submit">Freeze exact review packet</button></div></form>`);
}

function verifiedOpen(id) {
  const row=state.workspace.verified_reviews.find(r=>r.id===id);if(!row)return;
  const user=reviewIdentity(),role=myReviewRole();
  const allowed=user.status==="AUTHENTICATED"&&["OWNER","CHECKER"].includes(role?.role)&&row.preparer!==user.principal&&row.availability==="CURRENT"&&row.status==="WAITING_REVIEW";
  modal("Inspect verified packet",`<div class="modal-content">${status(row.status)}${status(row.availability)}${notice(row.unavailable_reason || "Review only the frozen contents and exact hash below. Recorded review alone does not execute or publish.",row.availability==="CURRENT"?"info":"warning")}<div class="details-list"><p><strong>Maker:</strong> ${esc(row.preparer)}</p><p><strong>Checker:</strong> ${esc(row.checker || "Not recorded")}</p><p><strong>Expires:</strong> ${esc(new Date(row.expires).toLocaleString())}</p></div><p class="app-mono">SHA256 ${esc(row.hash)}</p><details open><summary>Exact frozen evidence</summary><pre>${json(row.packet)}</pre></details>${!allowed&&row.status==="WAITING_REVIEW"?notice("A different authenticated, active checker is required; the packet and its source must still be current."):""}<div id="form-error" class="field-error" role="alert"></div></div><div class="modal-actions">${button("Download verified receipt","verified-review-download",`data-id="${esc(id)}"`)}${allowed?button("Record independent verified review","verified-review-approve",`data-id="${esc(id)}"`,""):""}</div>`);
}

async function verifiedSubmit(event) {
  const form=event.target,id=form.id;
  if(!["identity-form","access-bootstrap-form","access-member-form","verified-prepare-form"].includes(id))return;
  event.preventDefault();const submit=form.querySelector('[type="submit"]');submit.disabled=true;
  const data=Object.fromEntries(new FormData(form)),app=form.dataset.app || state.app;
  let result;
  try {
    if(id==="identity-form") {const token=data.token;form.reset();await api("/api/identity/login",{token});}
    if(id==="access-bootstrap-form")await api(`/api/apps/${app}/access/bootstrap`,{confirm_owner:!!data.confirm_owner});
    if(id==="access-member-form")await api(`/api/apps/${app}/access/members`,{...data,version:form.dataset.version?Number(form.dataset.version):null});
    if(id==="verified-prepare-form")result=await api(`/api/apps/${app}/verified-reviews`,data);
    const active=form.isConnected&&$("#modal").open;
    if(active)$("#modal").close();await refresh();if(result&&active&&state.app===app)verifiedOpen(result.id);
  } catch(error) {const field=form.querySelector("#form-error");if(form.isConnected&&field)field.textContent=error.message;else toast(error.message);} finally {submit.disabled=false;}
}

async function verifiedClick(event) {
  const node=event.target.closest("[data-action]");if(!node)return;
  const action=node.dataset.action,id=node.dataset.id;
  const simple={"identity-login":identityLogin,"access-bootstrap":accessBootstrap,"access-member":()=>accessMember(id),"verified-review-prepare":verifiedPrepare,"verified-review-open":()=>verifiedOpen(id)};
  if(simple[action])return simple[action]();
  if(action==="verified-review-download")return download(`${state.app}-verified-review.json`,state.workspace.verified_reviews.find(r=>r.id===id));
  try {
    if(action==="identity-logout") {await api("/api/identity/logout",{});return refresh();}
    if(action==="verified-review-approve") {node.disabled=true;const app=state.app,row=state.workspace.verified_reviews.find(r=>r.id===id);await api(`/api/apps/${app}/verified-reviews/${id}/approve`,{hash:row.hash});await refresh();if(state.app===app&&node.isConnected&&$("#modal").open)verifiedOpen(id);}
  } catch(error) {const field=$("#form-error");if(field)field.textContent=error.message;else toast(error.message);} finally {node.disabled=false;}
}

document.addEventListener("submit",verifiedSubmit);
document.addEventListener("click",verifiedClick);
