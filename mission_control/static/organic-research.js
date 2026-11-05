/* Operational owner research; collectors keep separately scoped CLI/MCP access. */
(function(root,factory){const value=factory(root.WMMDiscoveryModel||(typeof require==='function'?require('./discovery-model.js'):null));if(typeof module==='object'&&module.exports)module.exports=value;else root.WMMOrganicResearch=value;})(globalThis,function(m){
  'use strict';
  const HOSTS={tiktok:['tiktok.com','www.tiktok.com'],facebook:['facebook.com','www.facebook.com'],instagram:['instagram.com','www.instagram.com']};
  const RESEARCH_REQUEST_TIMEOUT_MS=30000,RESEARCH_PENDING_LIMIT=25,RESEARCH_MAX_CARD_TEXT=4000;
  let active=null;
  const pending=new Map();
  const member=s=>s.workspace?.access?.members?.find(r=>r.principal===s.workspace?.identity?.principal);
  const owner=s=>member(s)?.role==='OWNER'&&member(s)?.status==='ACTIVE';
  const scope=s=>({app:s.app,version:s.workspace?.app?.version,principal:s.workspace?.identity?.principal,role:member(s)?.role,roleVersion:member(s)?.version,roleStatus:member(s)?.status,session:s.boot?.csrf});
  const current=t=>active===t&&t.node.open&&m.equal(t.scope,scope(t.d.state))&&owner(t.d.state);
  const label=s=>String(s??'').replaceAll('_',' ').toLowerCase();
  const button=(text,action,id='',primary=false)=>`<button type="button" class="button ${primary?'':'outline'}" data-action="oresearch-${action}" data-id="${m.esc(id)}">${m.esc(text)}</button>`;
  const field=(name,title,value='',type='text',extra='')=>`<label class="field" for="oresearch-${name}">${m.esc(title)}<input id="oresearch-${name}" name="${name}" type="${type}" value="${m.esc(value)}" ${extra}></label>`;
  const area=(name,title,value='',limit=RESEARCH_MAX_CARD_TEXT)=>`<label class="field" for="oresearch-${name}">${m.esc(title)}<textarea id="oresearch-${name}" name="${name}" maxlength="${limit}" required>${m.esc(value)}</textarea></label>`;
  const select=(name,title,values)=>`<label class="field" for="oresearch-${name}">${m.esc(title)}<select id="oresearch-${name}" name="${name}">${values.map(([value,text])=>`<option value="${m.esc(value)}">${m.esc(text)}</option>`).join('')}</select></label>`;
  const check=(name,title,value='on')=>`<label class="check-row"><input type="checkbox" name="${name}" value="${m.esc(value)}"> ${m.esc(title)}</label>`;
  function clear(){active=null;}
  function invalidate(state){if(active&&!m.equal(active.scope,scope(state))){const node=active.node;clear();node.close();node.querySelector('#modal-body').replaceChildren();}}
  function panel(){return `<section class="panel" aria-label="Agent video research"><p class="eyebrow">FROM ATTENTION TO AN APP EXPERIMENT</p><h2>Give your agent a focused video search</h2><p>Choose your audience, platforms and research limits. Your connected agent returns source observations; you inspect the hook, confirm app relevance and save the next experiment.</p>${button('Find viral ideas for my app','open','',true)}<p>Viral-only requires 100,000 views AND 10× a documented creator baseline. Your own UGC stays available through the media library without that cutoff. Research approval grants no reuse or publication rights.</p></section>`;}
  function show(d,title,kind,html,data=null,captured=null){
    const savedScope=captured||scope(d.state);
    d.modal(title,`<div class="modal-content organic-research-workspace" tabindex="-1">${html}<p id="oresearch-progress" role="status" aria-live="polite"></p><p id="oresearch-error" class="field-error" role="alert"></p><div id="oresearch-recovery"></div></div>`,'AGENT VIDEO RESEARCH');
    active={d,node:d.document.querySelector('#modal'),scope:savedScope,kind,data,busy:false};
    active.node.querySelector('.organic-research-workspace').focus({preventScroll:true});
    return active;
  }
  function busy(t,value,message=''){t.busy=value;if(!current(t))return;t.node.querySelector('.organic-research-workspace').setAttribute('aria-busy',String(value));if(message)t.node.querySelector('#oresearch-progress').textContent=message;t.node.querySelectorAll('button,input,textarea,select').forEach(n=>n.disabled=value);}
  function fail(t,e){if(current(t))t.node.querySelector('#oresearch-error').textContent=e.message+' Your saved work is preserved.';}
  function validation(node,d,invalid=false){const t=active;if(!t||!current(t)||!node.closest('form[id^="oresearch-"]'))return;if(invalid){node.setAttribute('aria-invalid','true');t.node.querySelector('#oresearch-error').textContent=(node.labels?.[0]?.textContent.trim()||'Research field')+': '+node.validationMessage;}else if(node.validity?.valid){node.removeAttribute('aria-invalid');if(!t.node.querySelector('[aria-invalid="true"]'))t.node.querySelector('#oresearch-error').textContent='';}}
  async function hash(value,browser=globalThis){return Array.from(new Uint8Array(await browser.crypto.subtle.digest('SHA-256',new TextEncoder().encode(m.stable(value)))),b=>b.toString(16).padStart(2,'0')).join('');}
  async function request(t,action,body){
    const allowed=['task-list','task-read','prepare','intake'];if(!allowed.includes(action))throw new Error('Unsupported research action.');
    const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),RESEARCH_REQUEST_TIMEOUT_MS);let response,value;
    try{response=await (t.d.fetch||t.d.browser.fetch.bind(t.d.browser))('/api/apps/'+encodeURIComponent(t.scope.app)+'/organic-video/'+action,{method:'POST',credentials:'same-origin',redirect:'error',headers:{'Content-Type':'application/json','X-CSRF-Token':t.d.state.boot.csrf},body:JSON.stringify(body),signal:controller.signal});value=await response.json();}
    catch(cause){const e=new Error('The local research response was not received. Inspect the saved request before sending it again.');e.uncertain=true;throw e;}finally{clearTimeout(timer);}
    if(!response.ok){const e=new Error(value.error||'Research request rejected.');e.uncertain=response.status>=500;throw e;}return value;
  }
  const retained=t=>[...pending.values()].filter(r=>m.equal(r.scope,t.scope));
  function recovery(t){if(current(t))t.node.querySelector('#oresearch-recovery').innerHTML=retained(t).map(r=>`<section class="notice"><p>Save outcome unknown. Keep this exact request until inspected.</p>${button('Inspect saved request','inspect',r.body.request_id)}${button('Retry this identical save','retry',r.body.request_id)}</section>`).join('');}
  async function open(d,offset=0){
    if(!owner(d.state))throw new Error('Sign in as this app owner to assign or approve research.');
    const t=show(d,'Your agent research','history','<p>Reading saved tasks for this app and owner.</p>');busy(t,true,'Loading research history');
    try{const page=await request(t,'task-list',{offset,request_id:null});if(!current(t))return;
      const html=`<p>Start with a clear marketing question. Your agent gathers permitted public evidence; you decide which idea deserves an original app creative.</p>${button('Assign a new search','new','',true)}<h3>Saved research tasks</h3>${page.items.map(r=>`<section class="next-step"><h4>${m.esc(r.query.genre)}</h4><p>${m.esc(r.query.search_terms)}</p><p>${m.esc(label(r.status))} · saved ${m.esc(r.created)}</p><p>${r.intakes.length} saved research approvals</p>${r.intakes.map(x=>`<p>Research card ${m.esc(x.id)} · source ${m.esc(x.source_id)}</p>`).join('')}${button('Inspect task and research cards','read',r.id)}</section>`).join('')||'<p>No research task is saved for this app and owner. Assign a search to an agent with research access. You can review permitted sources manually in the saved-source research workspace.</p>'}<div class="button-row">${offset?button('First tasks','page','0'):''}${page.next_offset!==null?button('More tasks','page',String(page.next_offset)):''}</div>`;
      const next=show(d,'Your agent research','history',html,page,t.scope);recovery(next);
    }catch(e){fail(t,e);}finally{busy(t,false);}
  }
  function eligible(grant,s,at=Date.now()){
    return owner(s)&&grant.status==='ACTIVE'&&grant.owner===s.workspace.identity.principal&&grant.owner_version===member(s)?.version&&grant.app_id===s.app&&grant.app_version===s.workspace.app.version&&Date.parse(grant.expires)>at&&grant.used<grant.max_calls&&['organic-video.claim','organic-video.submit'].every(op=>grant.operations.includes(op));
  }
  async function assignment(t){
    if(retained(t).length)throw new Error('Inspect the uncertain save before assigning another search.');busy(t,true,'Reading your existing agent grants');
    try{const result=await t.d.api('/api/apps/'+encodeURIComponent(t.scope.app)+'/agent-grants/list',{});if(!current(t))return;
      const grants=result.grants.filter(g=>eligible(g,t.d.state));
      if(!grants.length){show(t.d,'Connect an agent for research','empty',`<p>No current owner-issued grant can both claim and submit video research. Open Agent permissions, choose this app and enable those two research operations for your connected agent. Its external browsing/API access is configured in that agent.</p><button class="button" type="button" data-action="control-grants">Open agent permissions</button>${button('Back to research','open')}`,null,t.scope);return;}
      const app=t.d.state.workspace.app.data;
      const html=`<p>This assigns metadata research to an existing agent. It creates no credential, downloads no video and publishes nothing. The agent's own permitted source access is required.</p><form id="oresearch-task-form"><div class="form-grid">${select('grant','Connected research agent',grants.map(g=>[g.id,g.agent_id+' · '+(g.max_calls-g.used)+' grant calls left']))}${field('genre','Genre or audience problem',app.job||'','text','required maxlength="120"')}${field('app_type','App type',app.category||'','text','required maxlength="120"')}${field('search_terms','Search terms','','text','required maxlength="500"')}</div><fieldset><legend>Platforms to research</legend>${Object.keys(HOSTS).map(p=>check('platform',p,p)).join('')}</fieldset><div class="form-grid">${select('access','Permitted source access',[['PUBLIC_WEB','Public web'],['OWNER_AUTHORIZED_PLATFORM','Owner-authorized platform session'],['PERMITTED_API','Permitted platform API']])}${field('minutes','Task expires after minutes',30,'number','required min="1" max="1440"')}${field('max_candidates','Maximum candidates',5,'number','required min="1" max="20"')}${field('max_reads','Maximum source reads',100,'number','required min="1" max="500"')}${field('max_seconds','Maximum collection seconds',600,'number','required min="1" max="3600"')}</div><p>Host scope is limited to the selected platforms' public domains. Task expiry is shortened to the selected grant's expiry. WMM does not delegate its stored credentials to the collector.</p><button type="submit" class="button">Review search assignment</button></form>${button('Back to research','open')}`;
      show(t.d,'Give your agent a focused search','assignment',html,{grants},t.scope);
    }catch(e){fail(t,e);}finally{busy(t,false);}
  }
  function taskBody(fd,grants,state,uuid,at=Date.now()){
    const grant=grants.find(g=>g.id===fd.get('grant'));if(!grant||!eligible(grant,state,at))throw new Error('Select a current research agent grant.');
    const platforms=fd.getAll('platform');if(!platforms.length||new Set(platforms).size!==platforms.length||platforms.some(p=>!HOSTS[p]))throw new Error('Select at least one supported research platform.');
    const access=fd.get('access');if(!['PUBLIC_WEB','OWNER_AUTHORIZED_PLATFORM','PERMITTED_API'].includes(access))throw new Error('Choose permitted source access.');
    const expires=new Date(Math.min(at+m.integer(fd.get('minutes'),'Expiry minutes',1,1440)*60000,Date.parse(grant.expires))).toISOString();
    return {request_id:uuid(),query:{genre:m.text(fd.get('genre'),'Genre',120),app_type:m.text(fd.get('app_type'),'App type',120),search_terms:m.text(fd.get('search_terms'),'Search terms',500)},policy:{recipient_grant_id:grant.id,platforms,hosts:platforms.flatMap(p=>HOSTS[p]).sort(),expires,max_candidates:m.integer(fd.get('max_candidates'),'Candidates',1,20),max_reads:m.integer(fd.get('max_reads'),'Source reads',1,500),max_seconds:m.integer(fd.get('max_seconds'),'Collection seconds',1,3600),access}};
  }
  function counts(saved){const rows=saved.result?.items||[];return {observed_candidates:saved.submission?.candidates?.length||0,qualified_by_reported_counts:rows.filter(r=>r.qualification?.qualification==='QUALIFIED_BY_REPORTED_COUNTS').length,baseline_missing:rows.filter(r=>r.qualification?.qualification==='INSUFFICIENT_BASELINE').length,reuse_rights_not_established:rows.filter(r=>r.reuse_permission!=='APPROVED').length,ugc_review:rows.filter(r=>r.status==='UGC_OWNER_REVIEW_REQUIRED').length,failed_sources:saved.result?.source_failures?.length||0};}
  function safeURL(url){try{const u=new URL(url);return u.protocol==='https:'&&Object.values(HOSTS).flat().includes(u.hostname)&&!u.username&&!u.password&&(!u.port||u.port==='443')?u.href:null;}catch(e){return null;}}
  function adoptable(saved,row,entry,state){return owner(state)&&saved.status==='SUBMITTED'&&saved.task.app.version===state.workspace.app.version&&row.status==='COLLECTION_REVIEW_REQUIRED'&&saved.submission.candidates.filter(x=>x.candidate.post_id===row.candidate_id).length===1&&!saved.intakes.some(x=>x.data.provenance.candidate_hash===row.qualification.candidate_hash)&&entry.kind==='REFERENCE';}
  function taskHTML(saved,state){
    const c=counts(saved),policy=saved.task.policy;
    const cards=(saved.result?.items||[]).map((row,index)=>{const entry=saved.submission.candidates[index],obs=entry.candidate,url=safeURL(obs.url),q=row.qualification;
      return `<article class="panel"><h3>${m.esc(obs.creator_id)} · ${m.esc(label(obs.platform))}</h3><p>${url?`<a href="${m.esc(url)}" target="_blank" rel="noopener noreferrer">Inspect original source</a>`:'Source link unavailable'}</p><p>Observed views: ${m.esc(obs.views??'Unavailable')} · observed ${m.esc(obs.observed_at)}</p><p>Qualification: ${m.esc(label(q.qualification))} · comparable baseline posts: ${m.esc(q.baseline_count??'Not required for UGC')}</p><p>App relevance: ${m.esc(label(entry.relevance))} · collector's rights claim: ${m.esc(label(entry.rights))}. Reuse permission remains unestablished.</p><p>${m.esc((q.reasons||[]).map(label).join('; '))}</p>${adoptable(saved,row,entry,state)?button('Review this research idea','adopt',row.candidate_id):'<p>Keep as a candidate until the reported evidence, app relevance and current review requirements are satisfied. Bring owned UGC through the media library.</p>'}</article>`;
    }).join('');
    return `<p><strong>${m.esc(label(saved.status))}</strong> · ${m.esc(saved.task.query.genre)} · ${m.esc(saved.task.query.app_type)}</p><p>Search: ${m.esc(saved.task.query.search_terms)}</p><p>${m.esc(policy.platforms.join(', '))} · access ${m.esc(label(policy.access))} · expires ${m.esc(policy.expires)}</p><p>Limits: ${policy.max_candidates} candidates, ${policy.max_reads} source reads, ${policy.max_seconds} collection seconds. Collector access is externally configured and not independently verified by this receipt.</p><dl>${Object.entries(c).map(([k,v])=>`<dt>${m.esc(label(k))}</dt><dd>${v}</dd>`).join('')}</dl>${saved.status==='READY'?'<p>Your agent can now claim this exact task through its existing scoped CLI/MCP grant. No collection has run yet.</p>':''}${saved.status==='CLAIMED'?`<p>The agent has claimed this task until ${m.esc(saved.claim_until)}. Refresh for its submitted evidence.</p>`:''}${cards}<h3>Source failures</h3>${(saved.result?.source_failures||[]).map(f=>`<p>${m.esc(f.source)} · ${m.esc(label(f.code))}</p>`).join('')||'<p>No source failures recorded. A ready task with no submission has no collection coverage.</p>'}<h3>Saved research approvals</h3>${saved.intakes.map(r=>`<p>Research card saved: ${m.esc(r.id)}. Source ${m.esc(r.data.source.id)} · collection ${m.esc(r.data.collection.id)}. </p>${saved.task.app.version===state.workspace.app.version?button('Prepare original brief','brief',r.id):'<p>This card belongs to an earlier app version. Start a fresh search to use current app proof.</p>'}`).join('')||'<p>No research candidate adopted yet.</p>'}<p>Research approval creates a source card and proposed experiment. It grants no foreign-media reuse, production execution, publication or measured app sales.</p><div class="button-row">${button('Refresh saved task','read',saved.id)}${button('Report / Save PDF','pdf')}${button('Download report JSON','json')}${button('Back to tasks','open')}</div>`;
  }
  function details(t,saved){const next=show(t.d,'Review agent research','detail',taskHTML(saved,t.d.state),saved,t.scope);recovery(next);return next;}
  async function prepareBrief(t,id){
    const intake=t.data.intakes.find(item=>item.id===id);
    if(!intake||t.data.task.app.version!==t.scope.version)throw new Error('Use a research card from the current app version.');
    const {review,collection,source,analysis}=intake.data;
    const base='/api/apps/'+encodeURIComponent(t.scope.app)+'/discovery/read';
    busy(t,true,'Checking the saved research and app proof');
    try{
      const checked=await t.d.api(base,{kind:'REVIEW',id:review.id},{signal:AbortSignal.timeout(RESEARCH_REQUEST_TIMEOUT_MS)});
      if(!current(t))return;
      if(checked.hash!==review.hash||checked.version!==review.version||!checked.currentness.current_app_context||
        checked.data.reference_id!==source.id||checked.data.source_hash!==source.hash)throw new Error('The source review changed. Inspect current research before preparing a brief.');
      await t.d.refresh();
      if(!current(t))return;
      t.d.openResearchBrief({analysis_id:analysis.id,analysis_hash:analysis.hash,channel:'SHORT_VIDEO',
        asset_ids:checked.data.review.card.authentic_evidence_ids,objective:checked.data.review.card.next_experiment,
        discovery:{schema:'wmm.brief-discovery.v1',mode:'ORIGINAL_RECREATION',manifest_version:t.scope.version,
          collection_id:collection.id,collection_hash:collection.hash,reference_id:source.id,review_hash:review.hash}});
    }finally{busy(t,false);}
  }
  async function read(t,id){busy(t,true,'Reading retained task and evidence');try{const saved=await request(t,'task-read',{task_id:id});if(current(t))details(t,saved);}catch(e){fail(t,e);}finally{busy(t,false);}}
  async function adoption(t,id){
    if(retained(t).length)throw new Error('Inspect the uncertain save before adopting another source.');
    const saved=t.data,row=saved.result.items.find(x=>x.candidate_id===id),entry=saved.submission.candidates.find(x=>x.candidate.post_id===id);
    if(!row||!entry||!adoptable(saved,row,entry,t.d.state))throw new Error('This candidate is not eligible for current research adoption.');
    let contract;busy(t,true,'Reading the current research field contract');
    try{contract=t.d.state.workspace.agent_operations||await t.d.api('/api/apps/'+encodeURIComponent(t.scope.app)+'/agent-operations');}finally{busy(t,false);}
    if(!current(t))return;
    const c=contract.local_catalog?.domain_contracts?.discovery_research;
    if(!c)throw new Error('Reload the workspace to read the research taxonomy.');
    const assets=(t.d.state.workspace.records||[]).filter(r=>r.kind==='asset');
    const html=`<p>Inspect the permitted original source first. Describe what you observed and how an original creative will demonstrate your app. Counts remain collector-reported; source approval does not authorize copying or publishing.</p><form id="oresearch-adopt-form"><div class="form-grid">${field('title','Source title','','text','required maxlength="200"')}${select('industry','Industry',c.industries.map(x=>[x,label(x)]))}${select('narrative','Story or narrative',c.narratives.map(x=>[x,label(x)]))}${select('treatment','Production treatment',c.treatments.map(x=>[x,label(x)]))}${field('duration','Inspected duration in seconds',30,'number','required min="1" max="3600"')}${field('hook_end','Opening hook ends at second',3,'number','required min="1" max="3600"')}</div>${area('hook','What happens in the opening hook?','',2000)}${area('mechanism','Your interpretation: why does it attract attention?')}${area('rationale','Why does this fit your app and audience?')}${area('requirements','What must your original creative reproduce? One requirement per line.', '',2000)}<fieldset><legend>Authentic app proof used in your original creative</legend>${assets.map(r=>check('evidence',r.title||r.data?.title||r.id,r.id)).join('')||'<p>Add an authentic app evidence asset in the Evidence screen, then reopen this review.</p>'}</fieldset>${area('experiment','Proposed next app-marketing experiment')}${area('uncertainty','What is uncertain about your inspection?', 'Public counters do not establish installs, sales or causal lift.',2000)}${check('inspected','I directly inspected this permitted source and have permission to save its public reference metadata.')}<button type="submit" class="button">Review research approval</button></form>${button('Back to source results','read',saved.id)}`;
    return show(t.d,'Turn this source into an app experiment','adoption',html,{saved,row,entry},t.scope);
  }
  async function adoptionBody(fd,t){
    const {saved,row,entry}=t.data,state=t.d.state;
    if(!adoptable(saved,row,entry,state)||fd.get('inspected')!=='on')throw new Error('Confirm direct inspection and permission before approving research.');
    const evidence=fd.getAll('evidence'),available=(state.workspace.records||[]).filter(r=>r.kind==='asset').map(r=>r.id);
    if(!evidence.length||new Set(evidence).size!==evidence.length||evidence.some(id=>!available.includes(id)))throw new Error('Select authentic app evidence from this workspace.');
    const duration=m.integer(fd.get('duration'),'Inspected duration',1,3600),end=m.integer(fd.get('hook_end'),'Hook end',1,duration),hook=m.text(fd.get('hook'),'Observed hook',2000);
    const rationale=m.text(fd.get('rationale'),'App relevance',2000),mechanism=m.text(fd.get('mechanism'),'Interpretation'),experiment=m.text(fd.get('experiment'),'Next experiment');
    const requirements=m.list(fd.get('requirements'),'Reproduction requirements');if(!requirements.length||requirements.some(x=>x.length>1000))throw new Error('Describe at least one reproduction requirement within 1,000 characters.');
    const candidateHash=await hash(entry.candidate,t.d.browser);if(candidateHash!==row.qualification.candidate_hash)throw new Error('Candidate evidence changed. Refresh and review again.');
    const stamp=new Date().toISOString(),obs=entry.candidate,published=Date.parse(obs.published_at);
    const taxonomy={original_labels:[obs.format],industry:fd.get('industry'),narrative:fd.get('narrative'),treatment:fd.get('treatment'),classified_by:'HUMAN_SUPPLIED',rationale};
    return {request_id:t.d.uuid(),task_id:saved.id,task_hash:saved.task_hash,submission_hash:saved.submission_hash,result_hash:saved.result_hash,candidate_id:row.candidate_id,candidate_hash:candidateHash,
      source_metadata:{title:m.text(fd.get('title'),'Source title',200),locale:m.text(state.workspace.app.data.locale,'App locale; update app setup first',120),traffic_class:'UNKNOWN',topic:saved.task.query.genre,relevance_note:rationale,permission_confirmed:true},
      review:{taxonomy,duration_ms:duration*1000,transcript:null,metrics:null,card:{observed_hook:hook,observed_beats:[{start_ms:0,end_ms:end*1000,text:hook}],interpreted_mechanism:mechanism,relevance_rationale:rationale,reproduction_requirements:requirements,authentic_evidence_ids:evidence,rights_status:'REFERENCE_ONLY',rights_evidence:'Public reference metadata only; reuse is not approved.',next_experiment:experiment}},
      analysis:{inspection_kind:'DIRECT_VIEW',inspection_confirmed:true,inspected_at:stamp,analyst:state.workspace.identity.principal,format_family:obs.format,duration_seconds:duration,observations:[{role:'HOOK',basis:'OBSERVED',detail:hook,evidence_note:rationale,start_seconds:0,end_seconds:end}],uncertainty:m.text(fd.get('uncertainty'),'Inspection uncertainty',2000)},
      query:{outcome:state.workspace.app.data.job||saved.task.query.genre,audience:state.workspace.app.data.audience||saved.task.query.app_type,industries:[],narratives:[],treatments:[],published_after:new Date(published-1).toISOString(),published_before:stamp,freshness_seconds:86400,minimum_views:100000,baseline_required:true,viral_only:true,ranking:'REACH'}};
  }
  function reviewWrite(t,action,body){
    const html=action==='prepare'?`<p>Assign this exact search to your selected agent. The agent receives metadata-read authority only.</p><dl>${Object.entries(body.query).map(([k,v])=>`<dt>${m.esc(label(k))}</dt><dd>${m.esc(v)}</dd>`).join('')}</dl><p>Platforms: ${m.esc(body.policy.platforms.join(', '))}. Hosts: ${m.esc(body.policy.hosts.join(', '))}.</p><p>Access: ${m.esc(label(body.policy.access))}. Expires ${m.esc(body.policy.expires)}. At most ${body.policy.max_candidates} candidates, ${body.policy.max_reads} reads and ${body.policy.max_seconds} seconds.</p>`:`<p>Save a research card for ${m.esc(body.source_metadata.title)}.</p><p>Observed hook: ${m.esc(body.review.card.observed_hook)}</p><p>App relevance: ${m.esc(body.review.card.relevance_rationale)}</p><p>Next experiment: ${m.esc(body.review.card.next_experiment)}</p><dl>${Object.entries(body.review.taxonomy).filter(([k])=>k!=='original_labels').map(([k,v])=>`<dt>${m.esc(label(k))}</dt><dd>${m.esc(v)}</dd>`).join('')}<dt>Inspected duration</dt><dd>${body.analysis.duration_seconds} seconds</dd><dt>Interpretation</dt><dd>${m.esc(body.review.card.interpreted_mechanism)}</dd><dt>Reproduction requirements</dt><dd>${m.esc(body.review.card.reproduction_requirements.join('; '))}</dd><dt>Inspection uncertainty</dt><dd>${m.esc(body.analysis.uncertainty)}</dd></dl><p>Authentic app evidence: ${m.esc(body.review.card.authentic_evidence_ids.join(', '))}. Rights remain reference-only. No production or publication is approved.</p><details><summary>Inspect all exact saved inputs</summary><pre>${m.esc(JSON.stringify(body,null,2))}</pre></details>`;
    return show(t.d,action==='prepare'?'Review the search assignment':'Review this research approval','confirm',html+button(action==='prepare'?'Assign this exact search':'Approve this research card','confirm','',true)+button('Cancel and return to tasks','open'),{action,body},t.scope);
  }
  async function write(t,r){
    if(!current(t)||!m.equal(r.scope,t.scope))return;
    busy(t,true,'Saving the exact reviewed request');
    let acknowledged=false;
    try{const saved=await request(t,r.action,r.body);acknowledged=true;
      const detail=await request(t,'task-read',{task_id:r.action==='prepare'?saved.id:r.body.task_id}),expected=await hash(r.body,t.d.browser);
      const exact=r.action==='prepare'?detail.request_id===r.body.request_id&&detail.request_hash===expected:detail.intakes.some(x=>x.request_id===r.body.request_id&&x.request_hash===expected);
      if(!exact){const e=new Error('The save receipt differs from the exact request. Inspect saved history.');e.uncertain=true;throw e;}
      if(!current(t))return;pending.delete(r.body.request_id);details(t,detail);
    }catch(e){if(!e.uncertain&&!acknowledged)pending.delete(r.body.request_id);if(acknowledged)e.message='The save was acknowledged, but exact readback is not confirmed. '+e.message;fail(t,e);recovery(t);}finally{busy(t,false);}
  }
  async function inspect(t,r){busy(t,true,'Inspecting saved request identity without a retry');try{
    const expected=await hash(r.body,t.d.browser);let saved;
    if(r.action==='prepare'){const page=await request(t,'task-list',{offset:0,request_id:r.body.request_id});saved=page.items.find(x=>x.request_id===r.body.request_id&&x.request_hash===expected);if(saved){const detail=await request(t,'task-read',{task_id:saved.id});if(current(t)){pending.delete(r.body.request_id);details(t,detail);}return;}}
    else{const detail=await request(t,'task-read',{task_id:r.body.task_id});saved=detail.intakes.find(x=>x.request_id===r.body.request_id&&x.request_hash===expected);if(saved){if(current(t)){pending.delete(r.body.request_id);details(t,detail);}return;}}
    throw new Error('No matching saved request was observed. Keep this uncertainty, or explicitly retry the identical request.');
    }catch(e){fail(t,e);}finally{busy(t,false);}}
  async function submit(form,d){const t=active;if(!t||!current(t)||t.busy)return;try{
    if(retained(t).length)throw new Error('Inspect the uncertain save before another request.');
    if(t.kind==='assignment')return reviewWrite(t,'prepare',taskBody(new d.FormData(form),t.data.grants,d.state,d.uuid));
    if(t.kind==='adoption'){const fields=new d.FormData(form);busy(t,true,'Binding your review to the saved candidate');const body=await adoptionBody(fields,t);if(current(t))return reviewWrite(t,'intake',body);}
    }catch(e){fail(t,e);}finally{busy(t,false);}}
  function reportedRows(saved){
    const candidates=(saved.result?.items||[]).map((row,index)=>{const entry=saved.submission.candidates[index],source=entry.candidate,q=row.qualification;return {id:source.platform+'/'+row.candidate_id,status:row.status,horizon:source.observed_at,currency:'NOT_APPLICABLE',source_url:safeURL(source.url)||'Unavailable',creator:source.creator_id,reported_views:source.views,published_at:source.published_at,qualification:q.qualification,qualification_reasons:(q.reasons||[]).join('; '),baseline_posts:q.baseline_count??null,baseline_median_numerator:q.median?.numerator??null,baseline_median_denominator:q.median?.denominator??null,required_views:q.required_views??null,relevance:entry.relevance,collector_rights_claim:entry.rights,reuse_permission:row.reuse_permission,publication:row.publication};});
    const failures=(saved.result?.source_failures||[]).map(row=>({id:row.source,status:row.code,horizon:saved.submission?.collected_at||'Not recorded',currency:'NOT_APPLICABLE',kind:'SOURCE_READ_FAILURE'}));
    return [...candidates,...failures];
  }
  function report(saved,state){return {schema:'wmm.organic-research-report.v1',title:'Agent video research',app_id:state.app,app_name:state.workspace.app.data.name,scope:'SELECTED_APP',manifest_version:saved.task.app.version,generated_at:new Date().toISOString(),loaded_at:saved.submission?.collected_at||'No collection observed',purpose:'Inspect reported viral evidence, missing inputs and saved research decisions.',next_step:'Review current source evidence and authentic app proof before preparing original creative.',filters:saved.task.query,metrics:Object.entries(counts(saved)).map(([name,value])=>({label:label(name),value,unit:'count',source:'Saved research task '+saved.id})),cohorts:reportedRows(saved),notes:['Task '+saved.id+' / '+saved.task_hash,'Collection and counters are external-agent reports requiring inspection.','Viral eligibility requires 100,000 views AND 10 times a documented comparable creator baseline.','Research approval grants no media reuse, production, publication, app sales or causal-lift claim.',...saved.intakes.map(r=>'Saved research intake '+r.id+' / '+r.hash)]};}
  function download(t){const value=report(t.data,t.d.state),blob=new t.d.browser.Blob([JSON.stringify(value,null,2)],{type:'application/json'}),url=t.d.browser.URL.createObjectURL(blob);try{const a=t.d.document.createElement('a');a.href=url;a.download=t.scope.app+'-agent-research.json';a.click();}finally{t.d.browser.URL.revokeObjectURL(url);}}
  async function action(node,d){const mode=node.dataset.action.slice('oresearch-'.length);if(mode==='open'){if(!owner(d.state)){d.toast('Sign in as this app owner to assign or approve research.');return;}return open(d);}const t=active;if(!t||!current(t)||t.busy)return;try{
    if(mode==='new')return assignment(t);if(mode==='page')return open(d,m.integer(node.dataset.id,'History offset',0,100000));if(mode==='read')return read(t,node.dataset.id);if(mode==='adopt')return await adoption(t,node.dataset.id);
    if(mode==='brief'&&t.kind==='detail')return await prepareBrief(t,node.dataset.id);
    if(mode==='confirm'){if(t.kind!=='confirm'||retained(t).length)throw new Error('Review the current exact request before confirming.');if(pending.size>=RESEARCH_PENDING_LIMIT)throw new Error('Inspect existing uncertain saves before another request.');const r={scope:m.copy(t.scope),action:t.data.action,body:m.copy(t.data.body)};pending.set(r.body.request_id,r);return write(t,r);}
    if(mode==='inspect'||mode==='retry'){const r=pending.get(node.dataset.id);if(!r||!m.equal(r.scope,t.scope))throw new Error('No uncertain request belongs to this context.');return mode==='inspect'?inspect(t,r):write(t,r);}
    if(mode==='json'&&t.kind==='detail')return download(t);if(mode==='pdf'&&t.kind==='detail')return d.pageReports.openReport(report(t.data,d.state),d.browser);
    }catch(e){fail(t,e);}}
  return {owner,scope,current,clear,invalidate,panel,open,action,submit,validation,eligible,taskBody,counts,safeURL,adoptable,taskHTML,adoptionBody,report,request,show,pending};
});
