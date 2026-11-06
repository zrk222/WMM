/* Actual job events; no simulated percentages or elapsed-time progress. */
(function(root,factory){
  const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.WMMTelemetry=api;
})(typeof globalThis==='object'?globalThis:this,function(){
  'use strict';
  const POLL_MS=2000,esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let generation=0,timer=null,mounted=null,opening=null;
  function panel(){return `<section class="panel" id="workflow-monitor" aria-label="Live workflow progression">
    <h2>See what your agent is doing</h2><p>Follow the recorded stage, current activity and saved result.</p>
    <p data-live-worker role="status">Checking the worker on this host…</p><p data-live-status>Loading saved observations…</p>
    <details><summary>Keep approved work running</summary>
      <p>Leave WMM running on an awake computer. Closing this browser leaves the worker running. Quitting WMM or putting its host to sleep stops new scheduled work.</p>
      <p>For unattended operation, you can install WMM on a private host you control. Connect accounts and review approvals on that host. Your credentials stay in their existing protected store.</p>
      <p><a href="https://github.com/zrk222/WMM/blob/main/docs/always-on-runtime.md" target="_blank" rel="noopener noreferrer">Open the private-host setup guide (new tab)</a></p>
    </details>
    <button class="button outline" type="button" data-action="telemetry-refresh">Refresh progress</button><div data-live-runs></div>
    </section>`;}
  function workerMessage(status){
    switch(status){
      case 'STARTING':return 'Worker starting. Refresh progress after its first completed poll.';
      case 'RUNNING':return 'Worker reported healthy. Open a run to verify what was actually delivered.';
      case 'RECOVERING':return 'Worker needs attention. Open Advanced tools → Guided workflow to check which work needs recovery.';
      case 'STOPPED':return 'Worker stopped. Start WMM on the host where this workspace is installed, then refresh progress.';
      default:return 'Worker status unavailable. Check WMM on this workspace’s host before relying on scheduled work.';
    }
  }
  function nextAction(status){
    const actions={QUEUED:'Waiting for the worker. Inspect the run to check its saved status.',RUNNING:'Work is running. Inspect its recorded steps and any saved output.',RETRY_WAIT:'Waiting for a permitted worker retry. Inspect the previous attempt before taking action.',FAILED:'Inspect the job status and any saved output before deciding whether to retry.',BLOCKED:'Inspect the job status and missing evidence or access before trying again.',SUCCEEDED:'Review the saved output and choose your next action. Completion alone does not establish app sales.',CANCELLED:'Work was cancelled. Inspect receipts for work that already completed.',UNKNOWN:'Inspect and reconcile the job status. Do not automatically resend uncertain work.',CANCEL_REQUESTED:'Cancellation is pending. Inspect the job status before starting replacement work.'};
    return actions[status]||'Inspect the recorded status and any saved output. Unrecognized states do not establish completion.';
  }
  function waitingForReports(run){return run.action==='sync'&&run.status==='SUCCEEDED'&&run.outcome_code==='WAITING_FOR_REPORTS';}
  function waitingResultMarkup(result){
    const hash=typeof result?.source_hash==='string'&&/^[a-f0-9]{64}$/.test(result.source_hash)?result.source_hash:null;
    return '<h3>Read completed · waiting for reports</h3><p>The provider returned no report data. This read supplied no app metrics.</p><p>Check the refresh schedule in Connections. An enabled schedule checks again at its saved due time.</p><p>Source receipt hash: '+(hash?esc(hash):'Not supplied by this read')+'</p>';
  }
  function markup(data){
    if(!data.runs.length)return '<p>No workflow runs yet. Start an approved workflow to see its stages here.</p>';
    return data.runs.map(run=>`<article class="panel"><h3>${waitingForReports(run)?'Read completed · waiting for reports':`${esc(run.action)} · ${esc(run.status)}`}</h3><p>Attempt ${esc(run.attempts)} · ${esc(run.processed_stages)} stages processed · ${esc(run.blocked_stages)} blocked</p><p>${waitingForReports(run)?'The source read completed, but the provider has no report data available yet. This read supplied no app metrics.':`${run.latest?.stage?`Stage ${esc(run.latest.stage)}: ${esc(run.latest.stage_title)} · `:''}${esc(run.activity)}`}</p><p>Last worker event: ${esc(run.latest?.observed_at||'No event recorded')}. Job updated: ${esc(run.updated)}.</p><p><strong>Next action:</strong> ${esc(waitingForReports(run)?'Inspect the saved source result and check its refresh schedule in Connections. An enabled schedule checks again at its saved due time.':nextAction(run.status))}</p>${typeof run.id==='string'&&run.id?`<button type="button" class="button outline" data-action="telemetry-open-job" data-id="${esc(run.id)}">Inspect run and saved output</button>`:''}<details><summary>Observed steps (${run.events.length})</summary><ol>${run.events.map(event=>`<li>${esc(event.observed_at)} · ${event.stage?`Stage ${esc(event.stage)} · `:''}${esc(event.message)}</li>`).join('')}</ol></details></article>`).join('');
  }
  async function openResult(node,deps){
    if(node.disabled||opening)return;
    const app=deps.state.app,view=deps.state.view,principal=deps.state.workspace?.identity?.principal,id=node.dataset.id;
    const expectedGeneration=(deps.state.refreshGeneration||0)+1;
    const current=()=>deps.state.app===app&&deps.state.view===view&&deps.state.workspace?.identity?.principal===principal&&deps.state.refreshGeneration===expectedGeneration;
    const operation={app,view,principal,id};opening=operation;node.disabled=true;
    try{
      const receipt=await deps.refresh();
      if(!current())return;
      if(!receipt||receipt.app!==app||receipt.generation!==expectedGeneration||receipt.workspace!==deps.state.workspace||receipt.workspace.app?.id!==app)throw new Error('Current refresh did not apply.');
      if(!deps.state.workspace.jobs.some(job=>job.id===id))return deps.toast('This run is outside the current saved history. Refresh progress to inspect current runs.');
      return deps.openJob(id);
    }catch(error){if(current())deps.toast('The saved run could not refresh. Your observations are preserved. Refresh progress and try again.');}
    finally{if(opening===operation)opening=null;if(node.isConnected)node.disabled=false;}
  }
  function clear(){generation++;if(timer!==null)clearTimeout(timer);timer=null;mounted=null;}
  function mount(deps){
    clear();const node=deps.document.querySelector('#workflow-monitor');if(!node)return;
    const ticket={node,app:deps.state.app,version:++generation,pending:false,failures:0};mounted=ticket;
    const worker=node.querySelector('[data-live-worker]');
    const announce=message=>{if(worker.textContent!==message)worker.textContent=message;};
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
          ticket.failures=0;
          announce(workerMessage(data.worker?.status));
          const healthyPoll=data.worker?.last_success;
          node.querySelector('[data-live-status]').textContent=`Last refresh ${data.observed_at}. Last healthy worker poll ${healthyPoll||'unavailable'}. Updates checked every two seconds while visible.`;
        }catch(error){if(valid()){ticket.failures++;announce(workerMessage());node.querySelector('[data-live-status]').textContent='Updates unavailable — showing the last saved observations. Automatic retries slow down after failed reads. Select Refresh progress to retry.';}}
        finally{ticket.pending=false;}
      }
      if(valid())timer=setTimeout(poll,Math.min(32000,POLL_MS*2**Math.min(ticket.failures,4)));
    }
    node.querySelector('[data-action=telemetry-refresh]').onclick=()=>{if(timer!==null)clearTimeout(timer);timer=null;poll();};
    poll();
  }
  return {panel,markup,mount,clear,openResult,nextAction,waitingResultMarkup,POLL_MS};
});
