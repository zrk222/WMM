"use strict";
// Scrub code/state before any fetch. Never persist credentials or raw callbacks.
const callbackParameters=new URLSearchParams(location.hash?location.hash.slice(1):location.search);
const callbackProvider=location.pathname.split('/').at(-1);
history.replaceState(null,'',location.pathname);
async function finishSocialCallback() {
  const output=document.querySelector('#social-result');
  try {
    const keys=[...callbackParameters.keys()];
    if(new Set(keys).size!==keys.length)throw new Error('This callback is duplicated. Start a fresh login from Mission Control.');
    const body={provider:callbackProvider,state:callbackParameters.get('state')||'',code:callbackParameters.get('code')||'',error:callbackParameters.get('error')||''};
    for(const key of keys)callbackParameters.delete(key);
    const boot=await (await fetch('/api/bootstrap',{cache:'no-store'})).json();
    const response=await fetch('/api/social/callback',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':boot.csrf},body:JSON.stringify(body)});
    body.state='';body.code='';
    const result=await response.json();
    if(!response.ok)throw new Error(result.error||'Connection could not be confirmed. Start a new official login.');
    output.textContent=result.status==='AWAITING_DESTINATION'?'Official login checked. Return to the original Mission Control tab and confirm the detected account.':`Login ${result.status.toLowerCase().replaceAll('_',' ')}. Your previous connection is preserved. Return to Mission Control for recovery options.`;
  } catch(error) {output.textContent=error.message||'Connection could not be confirmed. Return to Mission Control and start a new official login.';}
}
finishSocialCallback();
