"use strict";

async function finishPlayCallback() {
  const values=new URLSearchParams(location.search);
  history.replaceState(null,"",location.pathname);
  const status=document.querySelector('#play-callback-status');
  try {
    const states=values.getAll('state'),codes=values.getAll('code'),errors=values.getAll('error');
    if(states.length!==1||codes.length+errors.length!==1||!states[0].startsWith('play_'))throw new Error('This callback is incomplete or ambiguous. Return to Connections and start again.');
    const response=await fetch('/api/bootstrap');
    if(!response.ok)throw new Error('The local session is unavailable. Return to Mission Control and reconnect.');
    const session=await response.json();
    const body={state:states[0],...(codes.length?{code:codes[0]}:{error:errors[0]})};
    const result=await fetch('/api/play/callback',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':session.csrf},body:JSON.stringify(body)});
    const saved=await result.json();
    if(!result.ok)throw new Error(saved.error||'The connection could not be verified. Return to Connections and retry.');
    if(saved.status!=='CONNECTED'||typeof saved.app_id!=='string')throw new Error('Connection verification is incomplete. Check saved progress in Connections.');
    localStorage.setItem('growth-app',saved.app_id);
    document.querySelector('#connection-title').textContent='Google Play read access verified';
    status.textContent=`${saved.observation.package_name} · ${saved.observation.track}. Your protected login is saved. Return to Connections to inspect the dated observation.`;
  } catch(error) {
    document.querySelector('#connection-title').textContent='Connection needs attention';
    status.setAttribute('role','alert');status.textContent=error.message;
  }
}

finishPlayCallback();
