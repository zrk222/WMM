"use strict";
(() => {
  const escText = value => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const labelText = value => String(value ?? "").replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase());
  const providers = ["instagram", "tiktok", "youtube", "linkedin"];
  const stateCache = new Map();
  const pendingForms = new WeakSet();
  const pollState = {timer:null,context:null,count:0,state:null,deps:null,visibilityDocument:null,visibilityHandler:null};
  const POLL_DELAY_MS=8000,MAX_PANEL_POLLS=60;

  function owner(state) { return state.workspace?.identity?.principal || ""; }
  function version(state) { return state.workspace?.app?.version; }
  function ticket(state) { return {app: state.app, version: version(state), principal: owner(state)}; }
  function valid(state, value, panel) {
    return Boolean(value && state.app === value.app && state.workspace?.app?.id === value.app
      && version(state) === value.version && owner(state) === value.principal
      && (!panel || panel.isConnected !== false));
  }
  function currentContext(state) {
    if (!state?.workspace?.app?.id || !owner(state)) throw new Error("Open this app as its owner to review publishing.");
    return ticket(state);
  }
  function roots(state, model) {
    const accounts = (state.workspace?.social_access?.accounts || []).filter(row =>
      row.status === "CONNECTED_READ_TESTED" && !row.reconnect_required && row.data?.destination?.id);
    const mapped = (model?.instagram_accounts || []).filter(row => row.available !== false
      && row.destination_id && row.connection_id);
    return {accounts, mapped};
  }
  function instagramReady(state, row) {
    const config=state.workspace?.social_access?.setup?.configurations?.find(item=>
      item.provider==="facebook"&&item.version===row.config_version);
    return Boolean(config?.data?.campaign_access==="instagram_publish");
  }
  function channels(model) {
    const available = new Set((model?.channels || []).map(item => item.provider));
    return providers.filter(provider => available.has(provider)).map(provider =>
      model.channels.find(item => item.provider === provider));
  }
  function connectionOptions(provider, state, model) {
    const {accounts, mapped} = roots(state, model);
    if (provider === "instagram") return mapped.map(item => {
      const linked=accounts.find(row=>row.id===item.connection_id&&row.provider==="facebook");
      if(!linked||!instagramReady(state,linked))return null;
      return {id:linked.id,version:linked.version,destination_id:item.destination_id,
        name:item.name||item.destination_name||item.destination_id,mapping:item};
    }).filter(Boolean);
    return accounts.filter(item => item.provider === provider).map(item => ({id:item.id, version:item.version,
      destination_id:item.data.destination.id, name:item.data.destination.name, row:item}));
  }
  function select(name, title, options, selected="", required=true) {
    return `<label class="field">${escText(title)}<select name="${name}" ${required?"required":""}><option value="">Choose ${escText(title.toLowerCase())}</option>${options.map(item=>`<option value="${escText(item.value)}" ${String(item.value)===String(selected)?"selected":""}>${escText(item.label)}</option>`).join("")}</select></label>`;
  }
  function booleanSelect(name, title, selected) {
    return select(name,title,[{value:"true",label:"Yes"},{value:"false",label:"No"}],selected,true);
  }
  function settingsFields(provider, preflight, values={}) {
    if (provider === "instagram") return select("share_to_feed","Share to feed",[
      {value:"true",label:"Yes"},{value:"false",label:"No"}],values.share_to_feed);
    if (provider === "tiktok") {
      const info=preflight?.info, options=Array.isArray(info?.privacy_level_options)?info.privacy_level_options:[];
      const privacy=select("privacy_level","TikTok privacy",options.map(value=>({value,label:labelText(value)})),values.privacy_level);
      const booleans=["disable_duet","disable_comment","disable_stitch","brand_content_toggle","brand_organic_toggle","is_aigc"]
        .map(name=>booleanSelect(name,labelText(name),values[name])).join("");
      const inspected=info?`<p role="status">Creator ${escText(info.creator_nickname || info.creator_username || "Account")} · maximum ${escText(info.max_video_post_duration_sec)} seconds. This live creator preflight is required for each reviewed TikTok draft.</p>`:
        `<p>Check this creator’s current privacy options and video limit before preparing a draft.</p>`;
      return `${inspected}${privacy}${booleans}`;
    }
    if (provider === "youtube") return `${select("privacy_status","YouTube visibility",[
      {value:"public",label:"Public"},{value:"unlisted",label:"Unlisted"},{value:"private",label:"Private"}],values.privacy_status)}${booleanSelect("self_declared_made_for_kids","Made for kids",values.self_declared_made_for_kids)}${booleanSelect("contains_synthetic_media","Contains synthetic media",values.contains_synthetic_media)}`;
    if (provider === "linkedin") return select("visibility","LinkedIn visibility",[
      {value:"PUBLIC",label:"Public"},{value:"CONNECTIONS",label:"Connections"}],values.visibility);
    return "";
  }
  function formHtml(state, model, saved={}) {
    const channelList=channels(model), provider=saved.provider || "";
    const channel=channelList.find(item=>item.provider===provider);
    const kinds=channel?.kinds || [];
    const connections=connectionOptions(provider,state,model);
    const selectedConnection=connections.find(item=>item.id===saved.connection_id) || null;
    const renderItems=(model.renders||[]).filter(item=>item && item.id && item.sha256);
    const kind=saved.kind || "";
    const isText=kind === "linkedin_text";
    const artifactOptions=renderItems.map(item=>({value:item.id,label:`${item.id} · ${item.duration_seconds ?? "?"} sec · ${item.width ?? "?"}×${item.height ?? "?"}`}));
    const accessTicket=ticket(state);
    return `<form id="publication-draft-form" data-app="${escText(accessTicket.app)}" data-version="${escText(accessTicket.version)}" data-principal="${escText(accessTicket.principal)}">
      <div class="form-grid">${select("provider","Channel",channelList.map(row=>({value:row.provider,label:row.name})),provider)}
      ${select("kind","Post type",kinds.map(value=>({value,label:labelText(value)})),kind)}
      ${select("connection_id","Verified account",connections.map(row=>({value:row.id,label:row.name})),saved.connection_id)}
      ${selectedConnection?`<p class="description">Verified destination: <strong>${escText(selectedConnection.name)}</strong></p>`:""}
      ${provider==="tiktok"?`<div class="field-wide">${saved.preflight?.id?`<p role="status">TikTok creator options checked. ${escText(saved.preflight.info?.max_video_post_duration_sec)} second maximum.</p>`:`<button type="button" class="button outline" data-action="publication-preflight">Check TikTok posting options</button>`}</div>`:""}
      ${select("artifact_id",isText?"Video file":"App-owned finished video",isText?[]:artifactOptions,saved.artifact_id||"",!isText)}
      <label class="field">Title<input name="title" maxlength="100" value="${escText(saved.title||"")}" ${provider==="youtube"?"required":""}></label>
      <label class="field field-wide">Caption<textarea name="caption" maxlength="${provider==="instagram"?2200:5000}" required>${escText(saved.caption||"")}</textarea></label>
      <label class="field field-wide">Public link (optional)<input type="url" name="link" maxlength="2048" value="${escText(saved.link||"")}" placeholder="https://example.com"></label>
      <fieldset class="field-wide"><legend>Posting settings</legend>${settingsFields(provider,saved.preflight,saved)}</fieldset>
      </div><p class="field-error" role="alert" id="publication-form-error"></p>
      <div class="modal-actions"><button type="submit" class="button primary">Review this post</button></div></form>`;
  }
  function timestamp(value) {
    return typeof value==="number"&&Number.isFinite(value)&&value>0?new Date(value*1000).toISOString():"Unavailable";
  }
  function scheduleStatus(item) {
    const schedule=item.schedule;
    if(!schedule)return `<p>Queue state: NOT QUEUED · Worker: NOT STARTED · Provider phase: NOT STARTED.</p>`;
    const queue=schedule.status||"UNKNOWN",worker=schedule.job_status||"NOT CREATED";
    const provider=schedule.provider_status||"NOT STARTED";
    return `<p>Queue state: ${escText(queue)} · Worker: ${escText(worker)} · Provider phase: ${escText(provider)}. Due: ${escText(timestamp(schedule.due))} · Next due: ${escText(timestamp(schedule.next_due))}</p>`;
  }
  function needsRefresh(model) {
    return (model.authorities||[]).some(item=>{
      const schedule=item.schedule;
      return schedule&&(schedule.status==="READY"||schedule.status==="QUEUED"&&["QUEUED","RUNNING"].includes(schedule.job_status));
    });
  }
  function nextPollDelay(model) {
    const now=Date.now(),due=[];
    for(const item of model.authorities||[]){
      const schedule=item.schedule;if(!schedule)continue;
      const point=schedule.status==="READY"?schedule.due:
        schedule.status==="QUEUED"&&schedule.job_status==="QUEUED"?schedule.next_due:null;
      if(typeof point==="number"&&Number.isFinite(point)&&point*1000>now)
        due.push(point*1000-now);
    }
    return due.length?Math.min(...due):POLL_DELAY_MS;
  }
  function buttonMarkup(text,action,id) {
    return `<button type="button" class="button outline" data-action="${action}" data-id="${escText(id)}">${text}</button>`;
  }
  function reportModel(record,state) {
    const detail=record.report||{},draft=record.draft||{},channel=detail.channel||{},metrics=[];
    const add=(label,value,source="Saved publication record")=>metrics.push({label,value:value==null?"Unavailable":String(value),unit:"recorded",source});
    add("Approval status",record.status);add("Review hash",record.review_hash);add("Approval hash",record.approval_hash);
    add("Approval deadline",detail.approval?.expires||record.expires);add("Provider-call allowance",`${detail.approval?.calls_used??record.calls_used??0} / ${detail.approval?.max_calls??record.max_calls??"Unavailable"}`);
    add("Channel",`${channel.provider||draft.provider||"Unknown"} · ${draft.kind||"Unknown"}`);
    add("Channel hash",detail.channel_hash);add("Rights basis",JSON.stringify(detail.content?.rights_basis||{}));
    add("Destination",channel.destination_id||draft.destination_id);add("Approved title",draft.title);
    add("Approved copy",draft.caption);add("Public link",draft.link);add("Media artifact",draft.artifact?.id);
    add("Media SHA-256",draft.artifact?.sha256);add("Rights hashes",(draft.rights_hashes||[]).join(", "));
    add("Source hashes",(draft.source_hashes||[]).join(", "));add("Posting settings",JSON.stringify(draft.settings||{}));
    const schedule=detail.schedule;
    if(schedule){add("Schedule state",schedule.status,"Saved worker schedule");add("Schedule due",schedule.due,"Saved worker schedule");add("Next due",schedule.next_due,"Saved worker schedule");add("Worker job",JSON.stringify(schedule.job||{}),"Saved worker queue");}
    const intent=detail.intent,events=Array.isArray(detail.events)?detail.events:[];
    if(intent){add("Provider phase",intent.status,"Saved provider observation");add("Remote ID",intent.remote_id,"Saved provider observation");add("Latest observation",JSON.stringify(intent.observation||{}),"Saved provider observation");}
    const visibleEvents=events.length>500?events.slice(-500):events;
    for(const event of visibleEvents)add(`Event ${event.sequence} · ${event.action}`,`${event.status||""} · ${event.observed_at||""} · hash ${event.hash||""} · previous ${event.previous_hash||""}`,"Verified retained event chain");
    const sample=detail.latest_metric_sample;
    if(sample?.observed_at){
      add("Latest channel metrics",sample.metrics==null?"The channel returned no metrics.":JSON.stringify(sample.metrics),
        `Provider read at ${sample.observed_at} · receipt ${sample.receipt_hash}`);
    }else if(detail.latest_metrics!=null){
      add("Latest channel metrics",JSON.stringify(detail.latest_metrics),"Saved provider observation");
    }else if(sample?.reason==="NO_PROVIDER_READ_RECORDED"){
      add("Latest channel metrics","No provider read has been saved.");
    }
    if(detail.attribution)add("Attribution",JSON.stringify(detail.attribution),"WMM measurement boundary");
    const notes=["This report reflects retained approval and provider observations. Public visibility is not independently verified.","No installs or revenue are attributed by this publication report."];
    if(detail.public_visibility)notes.push(`Public visibility: ${detail.public_visibility}.`);
    if(events.length>visibleEvents.length)notes.push(`This printable report shows the latest ${visibleEvents.length} of ${events.length} retained events. Download JSON for the complete report.`);
    return {title:"Organic publication record",purpose:"Inspect the exact saved approval, queue state and provider observations for this app.",
      next_step:"Review any uncertain provider phase and verify the public post at the provider before relying on visibility.",
      app_name:state.workspace?.app?.data?.name||state.app,app_id:state.app,scope:"SELECTED_APP",
      generated_at:new Date().toISOString(),loaded_at:record.updated||"Saved time unavailable",manifest_version:record.app_version||draft.manifest_version||"Unavailable",
      filters:{publication_id:record.id,request_hash:draft.request_id||"Not shown"},metrics,cohorts:[],notes};
  }
  async function publicationReport(deps,node,format) {
    const ctx=currentContext(deps.state),identity=node.dataset.id;
    if(!identity)throw new Error("Choose a saved publication record first.");
    const record=await deps.api(`/api/apps/${encodeURIComponent(ctx.app)}/publications/${encodeURIComponent(identity)}`);
    if(!valid(deps.state,ctx,panelNode(deps)))return;
    if(record?.id!==identity||record?.app_id!==ctx.app||!record?.report)throw new Error("This report does not match the selected app and approval.");
    if(format==="json")return deps.download(`${ctx.app}-publication-${identity}.json`,record);
    return deps.pageReports.openReport(reportModel(record,deps.state),deps.browser,node);
  }
  function observationMarkup(item) {
    const observation=item.observation||{},metrics=observation.metrics||{};
    const counts=Object.entries(metrics.counts||{}).map(([name,value])=>
      `<li>${escText(labelText(name))}: ${typeof value==="number"&&Number.isSafeInteger(value)&&value>=0?escText(value):"Not returned"}</li>`).join("");
    const visibility=observation.privacy_status||observation.public_visibility||observation.visibility||"Not independently verified";
    const requested=observation.requested_privacy_status?` · requested ${escText(observation.requested_privacy_status)}`:"";
    const next=observation.next_action||item.next_action;
    return `<p>Provider visibility: ${escText(visibility)}${requested}</p>${counts?`<ul aria-label="Observed engagement">${counts}</ul><p class="description">${escText(metrics.source||"Provider observation")} · ${escText(metrics.observed_at||"Time unavailable")}. Video engagement counts do not establish app installs or revenue.</p>`:"<p>Engagement counts have not been returned yet.</p>"}${next?`<p>${escText(next)}</p>`:""}`;
  }
  function authorityMarkup(state, model) {
    const reportButtons=id=>`${buttonMarkup("Download report JSON","publication-report-json",id)}${buttonMarkup("Print / Save PDF","publication-report-pdf",id)}`;
    const auth=(model.authorities||[]).map(item=>`<article class="next-step"><div><h3>${escText(labelText(item.status))} · ${escText(item.id)}</h3><p>Review ${escText(item.review_hash||"Unavailable")} · version ${escText(item.version)} · calls ${escText(item.calls_used??0)} / ${escText(item.max_calls??"not set")}${item.due_at?` · approved for ${escText(item.due_at)}`:""}</p>${scheduleStatus(item)}${item.draft?`<p>${escText(labelText(item.draft.provider))} · ${escText(item.draft.destination_id)} · ${escText(item.draft.title||item.draft.caption||"")}</p>`:""}${item.status==="PREPARED"?`<button type="button" class="button primary" data-action="publication-review" data-id="${escText(item.id)}">Review and approve</button>`:""}${item.status==="APPROVED"&&item.schedule?.status!=="READY"?`<button type="button" class="button primary" data-action="publication-execute" data-id="${escText(item.id)}">${item.due_at?"Queue approved schedule":"Queue approved post"}</button>`:""}${item.status==="APPROVED"?`<button type="button" class="button outline" data-action="publication-revoke" data-id="${escText(item.id)}">Pause approval</button>`:""}<div class="button-row">${reportButtons(item.id)}</div></div></article>`).join("");
    const intents=(model.intents||[]).map(item=>`<article class="next-step"><div><h3>Publication · ${escText(labelText(item.status||"UNKNOWN"))}</h3><p>Receipt ${escText(item.id||"Unavailable")} · ${escText(item.remote_id||"Provider confirmation pending")}</p>${observationMarkup(item)}<button type="button" class="button outline" data-action="publication-reconcile" data-id="${escText(item.id)}">Check saved result</button><div class="button-row">${reportButtons(item.authority_id)}</div></div></article>`).join("");
    return `${auth}${intents}`;
  }
  function reviewMarkup(item, state) {
    const d=item.draft||{},summary=item.summary||{};
    const channelName={instagram:"Instagram Reel",tiktok:"TikTok video",youtube:"YouTube Short",linkedin:d.kind==="linkedin_text"?"LinkedIn text post":"LinkedIn video"}[d.provider]||labelText(d.provider);
    const account=state.workspace?.social_access?.accounts?.find(row=>row.id===d.connection_id);
    const mapping=(stateCache.get(`${state.app}:${owner(state)}`)?.instagram_accounts||[]).find(row=>row.connection_id===d.connection_id&&row.destination_id===d.destination_id);
    const destinationName=mapping?.name||mapping?.destination_name||account?.data?.destination?.name||d.destination_id;
    const destinationType={instagram:"professional account",tiktok:"creator account",youtube:"channel",linkedin:"member profile"}[d.provider]||"destination";
    const media=d.artifact?.id?`<video class="render-preview" controls playsinline preload="metadata" src="/api/apps/${encodeURIComponent(state.app)}/hypit-renders/${encodeURIComponent(d.artifact.id)}/preview" aria-label="Exact app-owned video being reviewed"></video>`:"<p>Text-only LinkedIn post.</p>";
    return `<form id="publication-approval-form" data-app="${escText(state.app)}" data-version="${escText(version(state))}" data-principal="${escText(owner(state))}" data-id="${escText(item.id)}" data-review-hash="${escText(item.review_hash)}">
      <div class="modal-content"><h3>Check the exact post</h3><p>Channel ${escText(channelName)} · ${escText(destinationType)} ${escText(destinationName)} · account ID ${escText(d.destination_id)}</p><p>Type ${escText(labelText(d.kind))} · title ${escText(d.title||"(none)")}</p><p>${escText(d.caption)}</p><p>Link ${escText(d.link||"None")}</p>${media}<p>Video ${escText(d.artifact?.id||"Text only")}${d.artifact?.sha256?` · SHA-256 ${escText(d.artifact.sha256)}`:""}</p><p>Privacy and disclosures: ${escText(JSON.stringify(d.settings||{}))}</p><p>Source fingerprints ${escText((d.source_hashes||[]).join(", "))}</p><p>Rights ${escText((d.rights_hashes||[]).join(", "))}</p><p>Preview ${escText(summary.preview_hash||summary.review_hash||item.review_hash)}</p><p>Approved call ceiling: 120 maximum across publish and recovery checks.</p>${summary.preflight?`<p>TikTok creator options: ${escText(JSON.stringify(summary.preflight))}</p>`:""}
      <fieldset><legend>Approval window</legend><label class="field">Expires in hours<input name="expiry_hours" type="number" min="1" max="168" value="24" required></label><label class="field">Publish at (optional, local time)<input name="due_at" type="datetime-local"></label><label class="field">Maximum publish/recovery calls<input name="max_calls" type="number" min="1" max="500" value="120" required></label><label class="check-row"><input name="extended_expiry_consent" type="checkbox"> Allow an approval longer than 24 hours</label></fieldset>
      <label class="check-row"><input name="confirm_publish" type="checkbox" required> I approve this exact post for this destination and time.</label><label class="check-row"><input name="confirm_rights" type="checkbox" required> I confirm I have the rights to this copy and media.</label>
      <p>Advertising spend: $0. Approval never enables ads.</p><p id="publication-approval-error" role="alert"></p></div>
      <div class="modal-actions"><button class="button outline" type="submit" name="mode" value="approve">Approve only</button><button class="button primary" type="submit" name="mode" value="queue">Approve and queue publish/schedule</button></div></form>`;
  }
  function instagramLinks(state) {
    const accounts=state.workspace?.social_access?.accounts||[];
    const facebook=accounts.filter(row=>row.provider==="facebook" && row.status==="CONNECTED_READ_TESTED"
      && !row.reconnect_required && instagramReady(state,row));
    return facebook.length?`<h3>Instagram account links</h3><p>Instagram publishing uses a connected Facebook Page with the Instagram publishing permission. Verify an account link before drafting.</p>${facebook.map(row=>`<button type="button" class="button outline" data-action="publication-instagram-account" data-id="${escText(row.id)}" data-version="${escText(row.version)}">Inspect linked Instagram account for ${escText(row.data.destination.name)}</button>`).join("")}`:"";
  }
  function panel(state) {
    return `<section class="panel publication-panel" aria-labelledby="publication-heading"><h2 id="publication-heading" tabindex="-1">Organic publishing</h2><p>Review and approve one exact post for Instagram, TikTok, YouTube Shorts or LinkedIn. Ad spend stays at $0. Account access alone never posts.</p><div id="publication-panel-content"><p>Load saved channel, video and approval details when you are ready.</p><button type="button" class="button outline" data-action="publication-load">Load publishing options</button>${instagramLinks(state)}</div></section>`;
  }
  function panelContent(state, model) {
    return `<p>Options loaded for ${escText(state.workspace.app.data.name)}. No post has been sent.</p>${instagramLinks(state)}${formHtml(state,model,model.form_values||{})}${recordsMarkup(state,model)}`;
  }
  function recordsMarkup(state,model) {
    const attention=(model.authorities||[]).some(item=>item.status==="PREPARED"||item.status==="APPROVED")||(model.intents||[]).length>0;
    return `<details class="publication-history"${attention?" open":""}><summary>Saved approvals, queues and results</summary><div class="publication-records">${authorityMarkup(state,model)}</div></details>`;
  }
  function panelFor(state, model) {
    let cached=stateCache.get(`${state.app}:${owner(state)}`);
    if(cached&&!valid(state,cached._context)){stateCache.delete(`${state.app}:${owner(state)}`);cached=null;}
    if(!cached)return panel(state);
    return panel(state).replace('<p>Load saved channel, video and approval details when you are ready.</p><button type="button" class="button outline" data-action="publication-load">Load publishing options</button>',panelContent(state,cached));
  }
  function setCache(state, model) { model._context=ticket(state);stateCache.set(`${state.app}:${owner(state)}`, model); }
  function formValues(form) { return Object.fromEntries(new FormData(form)); }
  function findPreflight(state, model, values) {
    const item=model.preflight;
    const selected=connectionOptions(values.provider,state,model).find(row=>row.id===values.connection_id);
    if (!item || values.provider!=="tiktok" || item.connection_id!==values.connection_id
      || selected?.destination_id!==item.destination_id) return null;
    return item;
  }
  function draftInput(form, deps, model) {
    const state=deps.state,values=formValues(form),connections=connectionOptions(values.provider,state,model);
    const connection=connections.find(item=>item.id===values.connection_id);
    if(!connection)throw new Error("Choose a currently verified account for this app.");
    if(values.provider==="tiktok"&&!findPreflight(state,model,values))throw new Error("TikTok preflight is missing, expired or belongs to a different creator; check posting options again.");
    const settings={};
    if(values.provider==="instagram"){
      if(!["true","false"].includes(values.share_to_feed))throw new Error("Choose whether to share this Reel to the feed.");
      settings.share_to_feed=values.share_to_feed==="true";
    }
    if(values.provider==="tiktok"){
      if(!values.privacy_level)throw new Error("Choose an explicit TikTok privacy level.");
      settings.privacy_level=values.privacy_level;
      for(const key of ["disable_duet","disable_comment","disable_stitch","brand_content_toggle","brand_organic_toggle","is_aigc"]){
        if(!["true","false"].includes(values[key]))throw new Error(`Choose Yes or No for ${labelText(key)}.`);
        settings[key]=values[key]==="true";
      }
    }
    if(values.provider==="youtube"){
      if(!values.privacy_status)throw new Error("Choose a YouTube visibility setting.");
      settings.privacy_status=values.privacy_status;
      for(const key of ["self_declared_made_for_kids","contains_synthetic_media"]){
        if(!["true","false"].includes(values[key]))throw new Error(`Choose Yes or No for ${labelText(key)}.`);
        settings[key]=values[key]==="true";
      }
    }
    if(values.provider==="linkedin"){
      if(!values.visibility)throw new Error("Choose an explicit LinkedIn visibility.");
      settings.visibility=values.visibility;
    }
    const kind=values.kind;
    const render=kind==="linkedin_text"?null:(model.renders||[]).find(item=>item.id===values.artifact_id);
    if(kind!=="linkedin_text"&&!render)throw new Error("Choose a finished app-owned video.");
    if(!kind)throw new Error("Choose a post type.");
    if(!values.caption?.trim())throw new Error("Write the caption or post text.");
    if(values.provider==="youtube"&&!values.title?.trim())throw new Error("YouTube Shorts need a title.");
    const mapping=connection.mapping;
    return {provider:values.provider,connection_id:connection.id,connection_version:connection.version,
      destination_id:connection.destination_id,kind,title:values.title||"",caption:values.caption,
      link:values.link||null,artifact_id:render?.id||null,settings,
      preflight_id:values.provider==="tiktok"?findPreflight(state,model,values).id:null,
      instagram_mapping:mapping||null};
  }
  function panelNode(deps) { return deps.document?.querySelector("#publication-panel-content") || null; }
  function clearPoll(reset=true) {
    if(pollState.timer!==null){clearTimeout(pollState.timer);pollState.timer=null;}
    if(reset){pollState.context=null;pollState.count=0;}
  }
  function pollingActive(state,deps,ctx) {
    const doc=deps?.document,panel=panelNode(deps);
    return state?.view==="connections"&&Boolean(panel)&&panel.isConnected!==false
      &&doc?.hidden!==true&&doc?.visibilityState!=="hidden"&&valid(state,ctx,panel);
  }
  function schedulePoll(delay=POLL_DELAY_MS) {
    if(pollState.timer!==null||pollState.count>=MAX_PANEL_POLLS)return;
    pollState.timer=setTimeout(()=>pollSavedRecords(),Math.max(1000,Math.min(delay,2147483647)));
  }
  async function pollSavedRecords() {
    pollState.timer=null;
    const {state,deps,context}=pollState,ctx=context;
    if(!ctx||!pollingActive(state,deps,ctx)){clearPoll();return;}
    const key=`${ctx.app}:${ctx.principal}`,previous=stateCache.get(key);
    if(!previous||!needsRefresh(previous)){clearPoll();return;}
    try {
      const data=await deps.api(`/api/apps/${encodeURIComponent(ctx.app)}/publications`);
      if(!pollingActive(state,deps,ctx)){clearPoll();return;}
      const latest=stateCache.get(key);
      if(!latest||!valid(state,ctx,panelNode(deps))){clearPoll();return;}
      const merged={...latest,...data,form_values:latest.form_values,preflight:latest.preflight,
        instagram_accounts:latest.instagram_accounts};
      setCache(state,merged);
      const records=panelNode(deps)?.querySelector?.(".publication-records");
      if(records&&records.isConnected!==false)records.innerHTML=authorityMarkup(state,merged);
    } catch(_) { /* Keep the saved view and retry on the next bounded poll. */ }
    pollState.count++;
    const current=stateCache.get(key);
    if(pollingActive(state,deps,ctx)&&current&&needsRefresh(current)&&pollState.count<MAX_PANEL_POLLS)schedulePoll(nextPollDelay(current));
    else clearPoll(false);
  }
  function mount(state,deps) {
    if(deps?.document&&pollState.visibilityDocument!==deps.document){
      if(pollState.visibilityDocument&&pollState.visibilityHandler)
        pollState.visibilityDocument.removeEventListener?.("visibilitychange",pollState.visibilityHandler);
      pollState.visibilityDocument=deps.document;
      pollState.visibilityHandler=()=>{
        if(pollState.visibilityDocument?.hidden===true||pollState.visibilityDocument?.visibilityState==="hidden")clearPoll(false);
        else if(pollState.state&&pollState.deps)mount(pollState.state,pollState.deps);
      };
      deps.document.addEventListener?.("visibilitychange",pollState.visibilityHandler);
    }
    pollState.state=state;pollState.deps=deps;
    let ctx;
    try{ctx=currentContext(state);}catch(_){clearPoll();return;}
    const model=stateCache.get(`${ctx.app}:${ctx.principal}`);
    if(!pollingActive(state,deps,ctx)||!model||!needsRefresh(model)){clearPoll();return;}
    const same=pollState.context&&pollState.context.app===ctx.app&&pollState.context.version===ctx.version&&pollState.context.principal===ctx.principal;
    if(!same){clearPoll();pollState.context=ctx;}
    schedulePoll(nextPollDelay(model));
  }
  function requireContext(deps, formOrPanel) {
    const ctx={app:formOrPanel?.dataset?.app,version:Number(formOrPanel?.dataset?.version),principal:formOrPanel?.dataset?.principal};
    if(!valid(deps.state,ctx,formOrPanel))throw new Error("This review belongs to an older app or owner session. Reload the current workspace.");
    return ctx;
  }
  async function loadOptions(deps, panel) {
    const ctx=currentContext(deps.state),data=await deps.api(`/api/apps/${encodeURIComponent(ctx.app)}/publications`);
    if(!valid(deps.state,ctx,panel))return;
    setCache(deps.state,data);panel.innerHTML=panelContent(deps.state,data);
    mount(deps.state,deps);
  }
  async function preflight(deps, form) {
    const ctx=requireContext(deps,form),data=formValues(form),model=stateCache.get(`${ctx.app}:${ctx.principal}`)||{};
    if(data.provider!=="tiktok")throw new Error("TikTok creator preflight is only for a TikTok draft.");
    const account=connectionOptions(data.provider,deps.state,model).find(item=>item.id===data.connection_id);
    if(!account)throw new Error("Choose a currently verified TikTok account first.");
    const selection={connection_id:account.id,connection_version:account.version,destination_id:account.destination_id};
    const result=await deps.api(`/api/apps/${encodeURIComponent(ctx.app)}/publications/preflight`,{
      connection_id:selection.connection_id,connection_version:selection.connection_version,destination_id:selection.destination_id});
    if(!valid(deps.state,ctx,form))return;
    model.preflight={...result,connection_id:selection.connection_id,destination_id:selection.destination_id};
    setCache(deps.state,model);
    const saved=formValues(form);saved.preflight=model.preflight;
    model.form_values=saved;
    const container=deps.document.querySelector("#publication-panel-content");
    if(container&&container.isConnected!==false)container.innerHTML=panelContent(deps.state,{...model,form_values:saved});
  }
  function fieldState(form) {
    const values=formValues(form);return values;
  }
  function onChange(deps, form) {
    const values=fieldState(form), model=stateCache.get(`${deps.state.app}:${owner(deps.state)}`)||{};
    const saved={...values};
    if(model.preflight && (values.provider!=="tiktok" || values.connection_id!==model.preflight.connection_id))model.preflight=null;
    saved.preflight=model.preflight;
    model.form_values=saved;
    setCache(deps.state,model);
    const container=deps.document.querySelector("#publication-panel-content");
    if(container)container.innerHTML=panelContent(deps.state,{...model,form_values:saved});
  }
  async function submitDraft(deps, form) {
    const ctx=requireContext(deps,form),model=stateCache.get(`${ctx.app}:${ctx.principal}`)||{};
    const input=draftInput(form,deps,model);
    const result=await deps.api(`/api/apps/${encodeURIComponent(ctx.app)}/publications/draft`,{
      provider:input.provider,connection_id:input.connection_id,connection_version:input.connection_version,
      destination_id:input.destination_id,kind:input.kind,title:input.title,caption:input.caption,
      link:input.link,artifact_id:input.artifact_id,settings:input.settings});
    if(!valid(deps.state,ctx,form))return;
    const prepared=await deps.api(`/api/apps/${encodeURIComponent(ctx.app)}/publications/prepare`,
      {draft:result.draft,preflight_id:input.preflight_id});
    if(!valid(deps.state,ctx,form))return;
    deps.modal("Review this exact post",reviewMarkup({...prepared,draft:result.draft,summary:{...result.summary,preflight:model.preflight?.info}},deps.state),"ORGANIC POST REVIEW");
  }
  async function submitApproval(deps, form, event) {
    const ctx=requireContext(deps,form),values=formValues(form),mode=event.submitter?.value||"approve";
    if(values.confirm_publish!=="on"||values.confirm_rights!=="on")throw new Error("Confirm this exact post and its rights before approval.");
    const hours=Number(values.expiry_hours),calls=Number(values.max_calls);
    if(!Number.isInteger(hours)||hours<1||hours>168||!Number.isInteger(calls)||calls<1||calls>500)throw new Error("Choose a valid approval window and call limit.");
    if(hours>24&&values.extended_expiry_consent!=="on")throw new Error("Explicitly confirm an approval longer than 24 hours.");
    const due=values.due_at?new Date(values.due_at):null;
    if(values.due_at&&(!due||!Number.isFinite(due.getTime())))throw new Error("Choose a valid local time for scheduling.");
    const body={review_hash:form.dataset.reviewHash,expires_at:new Date(Date.now()+hours*3600000).toISOString(),
      max_calls:calls,extended_expiry_consent:values.extended_expiry_consent==="on",
      confirm_publish:true,confirm_rights:true,due_at:due?due.toISOString():null};
    const approved=await deps.api(`/api/apps/${encodeURIComponent(ctx.app)}/publications/${encodeURIComponent(form.dataset.id)}/activate`,body);
    if(!valid(deps.state,ctx,form))return;
    if(mode==="queue"){
      try {
        await deps.api(`/api/apps/${encodeURIComponent(ctx.app)}/publications/execute`,{id:form.dataset.id});
        if(!valid(deps.state,ctx,form))return;
      } catch(error) {
        deps.close();await deps.refresh();await reloadAfterMutation(deps,ctx);
        deps.toast(`Approved; queueing needs a retry: ${error.message}`);return approved;
      }
    }
    deps.close();await deps.refresh();await reloadAfterMutation(deps,ctx);deps.toast(mode==="queue"?"Approved and queued. Check the saved receipt for provider confirmation.":"Approved only. Queue publishing from this app when ready.");
    return approved;
  }
  async function inspectInstagram(deps, node) {
    const ctx=currentContext(deps.state),row=deps.state.workspace.social_access.accounts.find(item=>item.id===node.dataset.id);
    if(!row||row.provider!=="facebook"||row.version!==Number(node.dataset.version)||row.status!=="CONNECTED_READ_TESTED"||row.reconnect_required||!instagramReady(deps.state,row))
      throw new Error("Choose a current Facebook connection configured for Instagram publishing.");
    const result=await deps.api(`/api/apps/${encodeURIComponent(ctx.app)}/publications/instagram-account`,
      {connection_id:row.id,connection_version:row.version});
    if(!valid(deps.state,ctx,panelNode(deps)))return;
    const model=stateCache.get(`${ctx.app}:${ctx.principal}`)||{channels:[],renders:[],authorities:[],intents:[],instagram_accounts:[]};
    model.instagram_accounts=[...(model.instagram_accounts||[]).filter(item=>item.connection_id!==row.id),result];
    setCache(deps.state,model);
    const content=panelNode(deps);if(content)content.innerHTML=panelContent(deps.state,model);
    deps.toast("Verified Instagram account link saved for this Facebook Page.");
  }
  async function reloadAfterMutation(deps, ctx) {
    if(!valid(deps.state,ctx))return;
    const panel=panelNode(deps);
    if(panel)await loadOptions(deps,panel);
  }
  async function action(node, deps) {
    const actionName=node.dataset.action,ctx=currentContext(deps.state),panel=panelNode(deps);
    if(actionName==="publication-load")return loadOptions(deps,panel);
    if(actionName==="publication-instagram-account")return inspectInstagram(deps,node);
    if(actionName==="publication-preflight")return preflight(deps,node.closest("form"));
    if(actionName==="publication-report-json")return publicationReport(deps,node,"json");
    if(actionName==="publication-report-pdf")return publicationReport(deps,node,"pdf");
    const model=stateCache.get(`${ctx.app}:${ctx.principal}`)||{};
    if(actionName==="publication-review"){
      const item=(model.authorities||[]).find(row=>row.id===node.dataset.id);
      if(!item)throw new Error("Refresh the saved post before approving it.");
      return deps.modal("Review this exact post",reviewMarkup(item,deps.state),"ORGANIC POST REVIEW");
    }
    if(actionName==="publication-execute"){
      await deps.api(`/api/apps/${encodeURIComponent(ctx.app)}/publications/execute`,{id:node.dataset.id});
      if(!valid(deps.state,ctx,panel))return;
      await deps.refresh();await reloadAfterMutation(deps,ctx);return deps.toast("Approved post queued. Check the saved receipt for provider confirmation.");
    }
    if(actionName==="publication-revoke"){
      const item=(model.authorities||[]).find(row=>row.id===node.dataset.id);if(!item)throw new Error("Reload the saved approval before pausing it.");
      await deps.api(`/api/apps/${encodeURIComponent(ctx.app)}/publications/${encodeURIComponent(item.id)}/revoke`,{version:item.version});
      if(!valid(deps.state,ctx,panel))return;
      await deps.refresh();await reloadAfterMutation(deps,ctx);return deps.toast("Approval paused.");
    }
    if(actionName==="publication-reconcile"){
      const item=(model.intents||[]).find(row=>row.id===node.dataset.id);if(!item)throw new Error("Reload the saved publication before checking its receipt.");
      await deps.api(`/api/apps/${encodeURIComponent(ctx.app)}/publications/${encodeURIComponent(item.id)}/reconcile`,{id:item.id});
      if(!valid(deps.state,ctx,panel))return;
      await deps.refresh();await reloadAfterMutation(deps,ctx);return deps.toast("Saved publication status refreshed.");
    }
  }
  async function submit(form, event, deps) {
    if(pendingForms.has(form))return;
    pendingForms.add(form);
    const submitters=[...form.querySelectorAll('[type="submit"]')];submitters.forEach(node=>node.disabled=true);
    try {
      if(form.id==="publication-draft-form")return await submitDraft(deps,form);
      if(form.id==="publication-approval-form")return await submitApproval(deps,form,event);
    } catch(error) {
      const target=form.querySelector("[role=alert]");if(target)target.textContent=error.message;
      else deps.toast(error.message);
    } finally {pendingForms.delete(form);submitters.forEach(node=>node.disabled=false);}
  }
  function change(form, deps, target) {
    if(form?.id==="publication-draft-form"&&["provider","kind","connection_id"].includes(target?.name))onChange(deps,form);
  }
  function invalidate(state) {
    for(const [key,value] of stateCache.entries())if(!key.startsWith(`${state.app}:${owner(state)}`)||!valid(state,value._context))stateCache.delete(key);
    if(state.view!=="connections"||!owner(state)||pollState.context&&!valid(state,pollState.context))clearPoll();
  }
  window.WMMPublicationUI={panel:panelFor,action,submit,change,invalidate,mount,
    test:{channels,connectionOptions,formHtml,reviewMarkup,draftInput,ticket,valid,setCache,authorityMarkup,needsRefresh,reportModel}};
})();
