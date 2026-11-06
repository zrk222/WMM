/* Presentation only: provider effects and owner authority stay in the engine. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.WMMFeedback=api;})(typeof globalThis==='object'?globalThis:this,function(){
  'use strict';
  const reasons=new Map();
  function define(messages,code,title,next){
    for(const message of messages)reasons.set(message,Object.freeze({code,title,next}));
  }
  define(['Protected batch admission is required','Batch source admission is unavailable','Current scoped agent admission is required','A scoped agent admission is required','A valid scoped WMM agent grant is required','Agent grant is unknown','Agent grant is unavailable','Agent grant does not allow this app or operation'],
    'AGENT_APPROVAL_NEEDED','Your agent needs permission for this task.','Open Your agents and ask the owner to review access for this app and task.');
  define(['Agent grant is revoked or expired','Batch authority changed or expired'],
    'ACCESS_ENDED','This agent approval has ended.','Ask the owner to review a new approval. The agent cannot renew its own access.');
  define(['Agent grant app scope changed; request a new grant','Batch admission does not match the exact plan','Batch plan or expiry differs from the admitted request','Batch source grant changed','Batch review is no longer current','Post content changed since review','Targeting changed since review','Campaign authority is unavailable or changed'],
    'REVIEW_CHANGED','The work changed after it was reviewed.','Refresh the draft and its supporting evidence, then ask the owner to review the current version before continuing.');
  define(['Agent grant call ceiling is exhausted','Campaign call ceiling is exhausted','Campaign post ceiling is exhausted','Approved post count is exhausted'],
    'APPROVED_LIMIT_REACHED','The approved work allowance is used up.','Review the saved work before asking the owner for a new allowance. Increasing a limit needs their approval.');
  define(['Paid lifecycle verification is incomplete'],
    'PAID_VERIFICATION_NEEDED','Paid campaign execution is not ready.','Complete the paid-campaign verification checks before approving a launch. Connecting an ad account does not complete those checks.');
  define(['Facebook connection expired','Facebook connection changed or became unavailable','This app connection is disconnected'],
    'ACCOUNT_RECONNECT_NEEDED','This account connection needs attention.','Open Connections, reconnect the intended account, then review campaign approval before continuing.');
  define(['Campaign approval is OFF or expired','Campaign review expired','Agent task approval expired'],
    'APPROVAL_ENDED','This work no longer has current approval.','Open the saved work and ask the owner to review it again. Reconnecting an account does not renew approval.');
  define(['App manifest changed; prepare a new scope','Facebook Page changed','Facebook developer configuration changed','Facebook connection changed; prepare a new scope','Campaign review changed; prepare the exact scope again','Campaign review changed during verification','App, route or connection changed; review a new proposal','Agent app facts changed; approve the current task','Agent output contract or recipe changed; review the current task','Agent route or connection changed; approve a new task','Agent evidence changed or approved context is absent; review a new proposal','Approved agent source index changed'],
    'REVIEW_CHANGED','The work changed after it was reviewed.','Refresh the draft and its supporting evidence, then ask the owner to review the current version before continuing.');
  define(['GitHub browser sign-in is not configured on this WMM installation.'],
    'SIGN_IN_SETUP_NEEDED','Browser sign-in is not configured for this installation.','You can prepare and download a local packet now. Ask the publisher to configure browser sign-in before connecting agent or campaign authority.');
  define(['Fresh native owner and host verification are required','Fresh native protected-access verification is required'],
    'OWNER_CHECK_NEEDED','Confirm the owner on this computer.','Open Your agents and complete the owner and protected-account checks before continuing.');
  define(['Campaign content, rights or targeting is outside scope','Campaign budget exceeds the approved per-campaign amount','Advertising account currency differs from scope','Only the scope owner may activate','Batch deadline exceeds its standing execution','Batch deadline exceeds standing approval','Batch deadline exceeds the source grant'],
    'REQUEST_OUTSIDE_APPROVAL','This request is outside the owner’s approval.','Review the content, account, audience, amount and dates against the saved agreement. Ask the owner to approve any changes before continuing.');
  define(['Fresh Facebook permissions do not cover this scope; reconnect','Facebook Page does not grant CREATE_CONTENT','Page creation task is absent'],
    'PAGE_PERMISSION_NEEDED','This connection cannot publish to the selected Facebook Page.','Open Connections and review the selected Page and posting permissions. Reconnect the intended account if needed, then review campaign approval.');
  define(['Campaign safety allowance exhausted; inspect provider directly'],
    'PROVIDER_CHECK_NEEDED','WMM cannot complete another campaign safety check.','Inspect the campaign directly in Meta and confirm its current state. Do not assume it is paused or launch a replacement.');
  const uncertain=Object.freeze({code:'RESULT_NOT_CONFIRMED',title:'WMM could not confirm the result.',next:'Check Watch the work and the saved result before submitting again. The action may already have run; do not create a duplicate.'});
  function error(value,context={}){
    const original=value instanceof Error?value:new Error(String(value||'The action could not be completed.'));
    if(original.feedback)return original;
    const raw=original.technicalMessage||original.message;
    let explanation;
    // Machine-readable uncertainty always wins over a less cautious text match.
    if(context.outcome==='UNKNOWN'||context.reconciliation_required===true||context.interrupted&&context.method!=='GET'||context.status>=500&&context.method!=='GET'||context.unreadable&&context.status<400&&context.method!=='GET')explanation=uncertain;
    else if(context.unreadable&&context.status>=400&&context.status<500)explanation={code:'REQUEST_REJECTED',title:'WMM rejected this request.',next:'The response details could not be read. Check your inputs and account access, then review the request before trying again.'};
    else if(context.interrupted||context.unreadable)explanation={code:'LATEST_VIEW_UNAVAILABLE',title:'WMM could not load the latest information.',next:'Check that WMM is running, then reload this view. The displayed information may be out of date.'};
    else explanation=reasons.get(raw);
    if(!explanation)return original; // Keep ordinary field-validation messages intact.
    original.technicalMessage=raw;
    original.feedback=Object.freeze({...explanation,status:Number.isInteger(context.status)?context.status:null});
    original.message=explanation.title+' '+explanation.next;
    return original;
  }
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function view(value){
    const issue=value.feedback;
    if(!issue)return '<p>'+esc(value.message||value)+'</p>';
    // Details use fixed reason codes and allowlisted text. Unknown provider text
    // remains on the Error for local diagnosis, never in this richer panel.
    const known=reasons.has(value.technicalMessage)?'<p>'+esc(value.technicalMessage)+'</p>':'';
    return '<div class="operation-feedback"><p><strong>'+esc(issue.title)+'</strong></p><p>'+esc(issue.next)+'</p><details><summary>Technical details</summary><p>Reason: '+esc(issue.code)+(issue.status?' · HTTP '+esc(issue.status):'')+'</p>'+known+'</details></div>';
  }
  return Object.freeze({error,view});
});
