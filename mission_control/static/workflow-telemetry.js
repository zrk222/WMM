/* Actual job events; no simulated percentages or elapsed-time progress. */
(function(root,factory){
  const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.WMMTelemetry=api;
})(typeof globalThis==='object'?globalThis:this,function(){
  'use strict';
  const POLL_MS=2000,esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let generation=0,timer=null,mounted=null;
  function panel(){return '<section class="panel" id="workflow-monitor" aria-label="Live workflow progression"><h2>Live workflow progression</h2><p>Follow the actual stage, current activity and saved outcome. Updates arrive every two seconds while this view is visible.</p><p data-live-status role="status">Loading worker observations…</p><button class="button outline" type="button" data-action="telemetry-refresh">Refresh progress</button><div data-live-runs></div></section>';}
  function markup(data){
    if(!data.runs.length)return '<p>No workflow runs yet. Start an approved workflow to see its stages here.</p>';
    return data.runs.map(run=>`<article class="panel"><h3>${esc(run.action)} · ${esc(run.status)}</h3><p>Attempt ${esc(run.attempts)} · ${esc(run.processed_stages)} stages processed · ${esc(run.blocked_stages)} blocked</p><p>${run.latest?.stage?`Stage ${esc(run.latest.stage)}: ${esc(run.latest.stage_title)} · `:''}${esc(run.activity)}</p><p>Last worker event: ${esc(run.latest?.observed_at||'No event recorded')}. Job updated: ${esc(run.updated)}.</p><details><summary>Observed steps (${run.events.length})</summary><ol>${run.events.map(event=>`<li>${esc(event.observed_at)} · ${event.stage?`Stage ${esc(event.stage)} · `:''}${esc(event.message)}</li>`).join('')}</ol></details></article>`).join('');
  }
  function clear(){generation++;if(timer!==null)clearTimeout(timer);timer=null;mounted=null;}
  function mount(deps){
    clear();const node=deps.document.querySelector('#workflow-monitor');if(!node)return;
    const ticket={node,app:deps.state.app,version:++generation,pending:false};mounted=ticket;
    const valid=()=>mounted===ticket&&generation===ticket.version&&deps.state.app===ticket.app&&node.isConnected;
    async function poll(){
      if(!valid())return;
      if(ticket.pending)return;
      if(!deps.document.hidden){
        ticket.pending=true;
        try{
          const data=await deps.api(`/api/apps/${encodeURIComponent(ticket.app)}/workflow-telemetry`);
          if(!valid())return;if(data.app_id!==ticket.app)throw new Error('Wrong app progress received.');
          const target=node.querySelector('[data-live-runs]');
          if(!target.contains(deps.document.activeElement))target.innerHTML=markup(data);
          node.querySelector('[data-live-status]').textContent=`Connected · last refresh ${data.observed_at}. Processed stages are observations, not a success percentage.`;
        }catch(error){if(valid())node.querySelector('[data-live-status]').textContent='Updates unavailable — showing the last saved observations. Refresh to retry.';}
        finally{ticket.pending=false;}
      }
      if(valid())timer=setTimeout(poll,POLL_MS);
    }
    node.querySelector('[data-action=telemetry-refresh]').onclick=()=>{if(timer!==null)clearTimeout(timer);timer=null;poll();};
    poll();
  }
  return {panel,markup,mount,clear,POLL_MS};
});
