const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const publicationSource=fs.readFileSync(path.join(__dirname,'../mission_control/static/publication.js'),'utf8');
const socialSource=fs.readFileSync(path.join(__dirname,'../mission_control/static/social-access.js'),'utf8');
const reportingModule={exports:{}};new Function('module',fs.readFileSync(path.join(__dirname,'../mission_control/static/page-reporting.js'),'utf8'))(reportingModule);
const uuid='00000000-0000-4000-8000-000000000001';
const account={id:uuid,version:3,provider:'linkedin',status:'CONNECTED_READ_TESTED',reconnect_required:false,data:{destination:{id:'member1',name:'<Member>'}}};
function fixture(){
 const calls=[],modals=[],timers=new Map(),records={isConnected:true,innerHTML:''},container={isConnected:true,innerHTML:'',querySelector:s=>s==='.publication-records'?records:null};
 const state={app:'sample-one',workspace:{app:{id:'sample-one',version:4,data:{name:'<App>'}},identity:{principal:'owner-1'},social_access:{accounts:[account]}}};
 let timerId=0,visibilityHandler=null;
 const c={console,Date,Math,Number,String,Set,Map,WeakSet,encodeURIComponent,JSON,FormData:class {constructor(form){return Object.entries(form.values||{})}},
   window:{},state,document:{hidden:false,visibilityState:'visible',querySelector:s=>s==='#publication-panel-content'?container:null,
    addEventListener:(name,fn)=>{if(name==='visibilitychange')visibilityHandler=fn;},removeEventListener:()=>{}},
   setTimeout:(fn,delay)=>{const id=++timerId;timers.set(id,{fn,delay});return id;},clearTimeout:id=>timers.delete(id),
   api:async(path,body)=>{calls.push({path,body});return{}},modal:(...args)=>modals.push(args),close:()=>{},refresh:async()=>{},toast:()=>{},esc:s=>String(s).replace(/[&<>"']/g,x=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[x])),
   button:(text,action,extra='')=>`<button data-action="${action}" ${extra}>${text}</button>`,label:s=>String(s),stateCache:null};
 c.window=c;vm.createContext(c);vm.runInContext(publicationSource,c);return {c,calls,modals,container,state,timers,records,get visibilityHandler(){return visibilityHandler;}};
}
function accountDraftValues(overrides={}){return {provider:'linkedin',kind:'linkedin_video',connection_id:uuid,artifact_id:'render1',title:'A title',caption:'Clear product update',link:'',visibility:'PUBLIC',...overrides};}
const model={channels:[{provider:'linkedin',name:'LinkedIn',kinds:['linkedin_video','linkedin_text']}],renders:[{id:'render1',sha256:'a'.repeat(64),duration_seconds:12,width:720,height:1280}],authorities:[],intents:[],instagram_accounts:[]};

test('connections panel is safe and makes no request until its explicit load action',()=>{
 const h=fixture(),html=h.c.WMMPublicationUI.panel(h.state);
 assert.match(html,/Organic publishing/);assert.match(html,/data-action="publication-load"/);assert.doesNotMatch(html,/<App>/);assert.equal(h.calls.length,0);
});
test('saved queue and provider phases stay distinct and persist after approval',()=>{
 const h=fixture(),due=1790000000,next=1790003600;
 const item={id:uuid,status:'APPROVED',version:2,review_hash:'review',calls_used:0,max_calls:120,
  draft:{provider:'linkedin',kind:'linkedin_video',destination_id:'member1',caption:'Exact post'},
  schedule:{status:'QUEUED',job_status:'QUEUED',provider_status:null,due,next_due:next}};
 h.c.WMMPublicationUI.test.setCache(h.state,{...model,authorities:[item]});
 const html=h.c.WMMPublicationUI.panel(h.state);
 assert.match(html,/APPROVED/);assert.match(html,/Queue state: QUEUED · Worker: QUEUED · Provider phase: NOT STARTED/);
 assert.match(html,new RegExp(new Date(due*1000).toISOString()));assert.match(html,new RegExp(new Date(next*1000).toISOString()));
 assert.match(html,/data-action="publication-report-json"/);assert.match(html,/data-action="publication-report-pdf"/);
 assert.doesNotMatch(html,/PUBLISHED/);
});
test('publication reports use the exact owner GET, JSON export and escaped page-reporting print helper',async()=>{
 const h=fixture(),record={id:uuid,app_id:'sample-one',status:'PUBLISHED',review_hash:'review',approval_hash:'approval',app_version:4,updated:'now',
  draft:{provider:'linkedin',kind:'linkedin_text',destination_id:'member1',title:'<img src=x>',caption:'<script>private()</script>',link:null,settings:{visibility:'PUBLIC'},rights_hashes:['rights'],source_hashes:[]},
  report:{channel:{provider:'linkedin',kind:'linkedin_text',destination_id:'member1'},schedule:{status:'COMPLETE',due:1790000000,next_due:1790000000,job:{status:'SUCCEEDED'}},intent:{status:'PUBLISHED',remote_id:'remote1',observation:{metrics:{views:12}}},events:[{sequence:1,action:'PUBLISHED',status:'PUBLISHED',observed_at:'now',hash:'a'.repeat(64)}],latest_metrics:{views:12},attribution:{installs:null,revenue:null,reason:'NOT_MEASURED_BY_PUBLICATION_PROVIDER'},public_visibility:'NOT_INDEPENDENTLY_VERIFIED'}};
 const calls=[],downloads=[],opened=[];const deps={state:h.state,document:h.c.document,api:async path=>{calls.push(path);return record;},download:(...args)=>downloads.push(args),browser:{location:{origin:'http://127.0.0.1'}},
  pageReports:{openReport:(...args)=>opened.push(args)}};
 const node={dataset:{id:uuid}};
 await h.c.WMMPublicationUI.action({...node,dataset:{...node.dataset,action:'publication-report-json'}},deps);
 assert.deepEqual(calls,[`/api/apps/sample-one/publications/${uuid}`]);assert.equal(downloads[0][0],`sample-one-publication-${uuid}.json`);assert.equal(downloads[0][1],record);
 await h.c.WMMPublicationUI.action({...node,dataset:{...node.dataset,action:'publication-report-pdf'}},deps);
 assert.equal(opened.length,1);assert.equal(opened[0][0].metrics.some(row=>row.label==='Event 1 · PUBLISHED'),true);
 const html=reportingModule.exports.reportHTML(opened[0][0],'http://127.0.0.1');
 assert.doesNotMatch(html,/<script>|<img src=x>/);assert.match(html,/&lt;script&gt;private\(\)&lt;\/script&gt;/);assert.match(html,/NOT_INDEPENDENTLY_VERIFIED/);
});
test('late publication report response is discarded after owner/app context changes',async()=>{
 const h=fixture();let finish,opened=0;const deps={state:h.state,document:h.c.document,api:()=>new Promise(resolve=>finish=resolve),browser:{location:{origin:'http://127.0.0.1'}},pageReports:{openReport:()=>opened++}};
 const pending=h.c.WMMPublicationUI.action({dataset:{action:'publication-report-pdf',id:uuid}},deps);
 h.state.app='different';finish({id:uuid,app_id:'sample-one',report:{}});await pending;assert.equal(opened,0);
});
test('panel refresh is single-shot bounded, pauses when hidden, and discards late replies off page',async()=>{
 const h=fixture();h.state.view='connections';
 const queued={...model,authorities:[{id:uuid,status:'APPROVED',version:2,schedule:{status:'QUEUED',job_status:'QUEUED',due:1790000000,next_due:1790003600}}]};
 h.c.WMMPublicationUI.test.setCache(h.state,queued);
 const deps={state:h.state,document:h.c.document,api:async()=>({ ...queued,authorities:[{...queued.authorities[0],schedule:{...queued.authorities[0].schedule,job_status:'RUNNING'}}]})};
 h.c.WMMPublicationUI.mount(h.state,deps);
 assert.equal(h.timers.size,1);assert.equal([...h.timers.values()][0].delay,8000);assert.equal(h.calls.length,0);
 h.c.document.hidden=true;h.c.document.visibilityState='hidden';h.visibilityHandler();assert.equal(h.timers.size,0);
 h.c.document.hidden=false;h.c.document.visibilityState='visible';h.visibilityHandler();assert.equal(h.timers.size,1);
 const timer=[...h.timers.entries()][0];h.timers.delete(timer[0]);
 let finish;deps.api=()=>new Promise(resolve=>finish=resolve);
 const pending=timer[1].fn();h.state.view='activity';h.c.WMMPublicationUI.mount(h.state,deps);
 finish({...queued,authorities:[{...queued.authorities[0],schedule:{...queued.authorities[0].schedule,job_status:'RUNNING',provider_status:'CREATED'}}]});
 await pending;assert.equal(h.records.innerHTML,'');assert.equal(h.timers.size,0);
});
test('verified account and render picker escape untrusted labels',()=>{
 const h=fixture();h.c.WMMPublicationUI.test.setCache(h.state,{...model,form_values:{provider:'linkedin'},renders:[{id:'render1',sha256:'a'.repeat(64),duration_seconds:12,width:720,height:1280,title:'<script>alert(1)</script>'}]});
 const html=h.c.WMMPublicationUI.panel(h.state);assert.match(html,/&lt;Member&gt;/);assert.doesNotMatch(html,/<script>/);assert.match(html,/Choose verified account/i);assert.match(html,/artifact_id/);
});
test('draft builder requires explicit settings and emits a closed hash-free local preview request',()=>{
 const h=fixture(),deps={state:h.state,FormData:cFormData};
 function cFormData(form){return Object.entries(form.values);}
 const form={values:accountDraftValues()};
 const built=h.c.WMMPublicationUI.test.draftInput(form,deps,model);
 assert.deepEqual(JSON.parse(JSON.stringify(built.settings)),{visibility:'PUBLIC'});
 assert.equal(built.destination_id,'member1');assert.equal(built.artifact_id,'render1');
 assert.equal('rights_hashes' in built,false);assert.equal('source_hashes' in built,false);assert.equal('sha256' in built,false);
 assert.throws(()=>h.c.WMMPublicationUI.test.draftInput({values:accountDraftValues({visibility:''})},deps,model),/visibility/);
});
test('TikTok draft needs explicit privacy and disclosure selections plus same-account fresh preflight',()=>{
 const h=fixture();h.state.workspace.social_access.accounts=[{...account,provider:'tiktok',data:{destination:{id:'tt1',name:'Creator'}}}];
 const tiktokModel={...model,channels:[{provider:'tiktok',name:'TikTok',kinds:['tiktok_video']}],preflight:{id:uuid,connection_id:uuid,destination_id:'tt1',info:{privacy_level_options:['SELF_ONLY'],max_video_post_duration_sec:60}}};
 const values={provider:'tiktok',kind:'tiktok_video',connection_id:uuid,artifact_id:'render1',caption:'Video copy',privacy_level:'SELF_ONLY',disable_duet:'false',disable_comment:'true',disable_stitch:'true',brand_content_toggle:'false',brand_organic_toggle:'false',is_aigc:'true'};
 const deps={state:h.state,FormData:form=>Object.entries(form.values)};
 const built=h.c.WMMPublicationUI.test.draftInput({values},deps,tiktokModel);
 assert.equal(built.preflight_id,uuid);assert.equal(built.settings.is_aigc,true);assert.equal(built.settings.disable_comment,true);
 assert.throws(()=>h.c.WMMPublicationUI.test.draftInput({values:{...values,privacy_level:''}},deps,tiktokModel),/privacy level/);
 assert.throws(()=>h.c.WMMPublicationUI.test.draftInput({values},deps,{...tiktokModel,preflight:{...tiktokModel.preflight,connection_id:'other'}}),/preflight/);
});
test('async UI response is discarded after app, owner, version or panel context changes',()=>{
 const h=fixture(),panel={isConnected:true},ctx=h.c.WMMPublicationUI.test.ticket(h.state);
 assert.equal(h.c.WMMPublicationUI.test.valid(h.state,ctx,panel),true);
 for(const change of [s=>s.app='sample-two',s=>s.workspace.app.version++,s=>s.workspace.identity.principal='owner-2']){
   const fresh=fixture(),ticket=fresh.c.WMMPublicationUI.test.ticket(fresh.state);change(fresh.state);assert.equal(fresh.c.WMMPublicationUI.test.valid(fresh.state,ticket,panel),false);
 }
 panel.isConnected=false;assert.equal(h.c.WMMPublicationUI.test.valid(h.state,ctx,panel),false);
});
test('TikTok preflight action is explicit and never prepares or publishes',async()=>{
 const h=fixture(),row={...account,provider:'tiktok',data:{destination:{id:'tt1',name:'Creator'}}};h.state.workspace.social_access.accounts=[row];
 h.c.WMMPublicationUI.test.setCache(h.state,{...model,channels:[{provider:'tiktok',name:'TikTok',kinds:['tiktok_video']}]});
 h.c.api=async(path,body)=>{h.calls.push({path,body});return{id:'preflight1',hash:'review-hash',info:{creator_nickname:'Creator',privacy_level_options:['SELF_ONLY'],max_video_post_duration_sec:60}};};
 const form={isConnected:true,id:'publication-draft-form',dataset:{app:'sample-one',version:'4',principal:'owner-1'},values:{provider:'tiktok',connection_id:uuid},closest:()=>form};
 const node={dataset:{action:'publication-preflight'},closest:()=>form};
 await h.c.WMMPublicationUI.action(node,{state:h.state,FormData:f=>Object.entries(f.values),api:h.c.api,document:h.c.document});
 assert.equal(h.calls.length,1);assert.match(h.calls[0].path,/publications\/preflight$/);assert.deepEqual(JSON.parse(JSON.stringify(h.calls[0].body)),{connection_id:uuid,connection_version:3,destination_id:'tt1'});
 assert.match(h.container.innerHTML,/Creator/);assert.doesNotMatch(h.calls.map(x=>x.path).join(' '),/prepare|execute/);
});
test('workspace change while draft builder is pending prevents prepare and approval',async()=>{
 const h=fixture();h.c.WMMPublicationUI.test.setCache(h.state,{...model});
 let resolve;const form={id:'publication-draft-form',isConnected:true,dataset:{app:'sample-one',version:'4',principal:'owner-1'},values:accountDraftValues(),querySelectorAll:()=>[],querySelector:()=>null};
 const calls=[];const deps={state:h.state,FormData:class {constructor(f){return Object.entries(f.values)}},api:(path,body)=>{calls.push({path,body});return new Promise(r=>resolve=r);},modal:(...args)=>h.modals.push(args),toast:()=>{},document:h.c.document};
 const pending=h.c.WMMPublicationUI.submit(form,{},deps);h.state.workspace.app.version=5;
 resolve({draft:{schema:'server-bound'},summary:{}});await pending;
 assert.equal(calls.length,1);assert.match(calls[0].path,/publications\/draft$/);assert.equal(h.modals.length,0);
});
test('exact review escapes content and exposes rights, destination, privacy, time and zero spend',()=>{
 const h=fixture(),item={id:uuid,review_hash:'review',draft:{provider:'linkedin',kind:'linkedin_text',destination_id:'<dest>',title:'',caption:'<script>x</script>',link:null,artifact:null,settings:{visibility:'PUBLIC'},source_hashes:[],rights_hashes:['rights']},summary:{preview_hash:'preview'}};
 const html=h.c.WMMPublicationUI.test.reviewMarkup(item,h.state);
 assert.match(html,/&lt;dest&gt;/);assert.doesNotMatch(html,/<script>/);assert.match(html,/PUBLIC/);assert.match(html,/rights/);assert.match(html,/Advertising spend: \$0/);assert.match(html,/Approved call ceiling: 120/);assert.match(html,/value="120"/);assert.match(html,/due_at/);assert.match(html,/name="mode" value="queue"/);
});
test('social access permission request offers publish modes with exact scopes and no approval claims',()=>{
 let handler;const scopeNode={textContent:''};const c={state:{app:'sample-one',workspace:{social_access:{setup:{configurations:[]}}}},label:s=>s,esc:s=>String(s),button:()=>'',
  $:selector=>selector==='#social-requested-scopes'?scopeNode:({elements:{campaign_access:{addEventListener:(name,fn)=>handler=fn}}}),
  api:async()=>({app_name:'Sample',suggested_developer_name:'Sample',steps:[],official_setup:'https://example.com',scopes:['https://www.googleapis.com/auth/youtube.readonly'],redirect_uri:'https://example.com/cb/youtube'}),modal:(title,html)=>c.html=html};
 vm.createContext(c);vm.runInContext(socialSource,c);
 return c.socialSetup('youtube').then(()=>{assert.match(c.html,/Request reviewed organic publish access/);assert.match(c.html,/Exact requested scopes:/);assert.match(c.html,/Saving or connecting grants no post approval or spending authority/);handler({target:{value:'publish'}});assert.equal(scopeNode.textContent,'https://www.googleapis.com/auth/youtube.readonly, https://www.googleapis.com/auth/youtube.upload');});
});
test('Instagram login remains read-only and points publishing through the linked Facebook Page',async()=>{
 const form={elements:{campaign_access:{addEventListener(){}}}};
 const c={state:{app:'sample-one',workspace:{social_access:{setup:{configurations:[]}}}},label:s=>s,esc:s=>String(s),button:()=>'',
  $:selector=>selector==='#social-setup-form'?form:null,
  api:async()=>({app_name:'Sample',suggested_developer_name:'Sample',steps:[],official_setup:'https://example.com',scopes:['instagram_business_basic'],redirect_uri:'https://example.com/cb/instagram'}),modal:(title,html)=>c.html=html};
 vm.createContext(c);vm.runInContext(socialSource,c);await c.socialSetup('instagram');
 assert.match(c.html,/Read account information/);assert.doesNotMatch(c.html,/Request reviewed organic publish access/);
 assert.match(c.html,/connected Facebook Page with the Instagram publishing permission/);
});
test('social setup persists selected permission mode for non-Facebook providers',async()=>{
 const c={state:{app:'sample-one',workspace:{social_access:{setup:{configurations:[]}}}},FormData:class {constructor(form){return Object.entries(form.values)}},api:async(path,body)=>{c.sent={path,body};return{provider:'youtube',version:2};},refresh:async()=>{},modal:()=>{},toast:()=>{},label:s=>s,esc:s=>String(s),button:()=>''};
 vm.createContext(c);vm.runInContext(socialSource,c);c.socialStart=async()=>{};
 const form={id:'social-setup-form',dataset:{app:'sample-one',provider:'youtube',version:'0'},values:{client_id:'client',client_secret:'secret',redirect_uri:'https://example.com/cb/youtube',campaign_access:'publish',native_enabled:''},querySelector:()=>({disabled:false}),elements:{client_secret:{value:''}}};
 await c.socialSubmit(form);assert.equal(c.sent.body.campaign_access,'publish');
});
test('approve-and-queue requires explicit copy and rights checks and sends exact schedule',async()=>{
 const h=fixture(),calls=[];h.c.api=async(path,body)=>{calls.push({path,body});return{};};
 const form={id:'publication-approval-form',isConnected:true,dataset:{app:'sample-one',version:'4',principal:'owner-1',id:uuid,reviewHash:'review'},
   values:{expiry_hours:'24',max_calls:'120',due_at:'2027-01-01T12:00',confirm_publish:'on',confirm_rights:'on'},querySelectorAll:()=>[],querySelector:()=>null};
 const event={submitter:{value:'queue'}};await h.c.WMMPublicationUI.submit(form,event,{state:h.state,FormData:f=>Object.entries(f.values),api:h.c.api,close:()=>{},refresh:async()=>{},toast:()=>{},document:h.c.document});
 assert.equal(calls[0].body.confirm_publish,true);assert.equal(calls[0].body.confirm_rights,true);assert.equal(calls[0].body.due_at,new Date(form.values.due_at).toISOString());assert.match(calls[1].path,/publications\/execute$/);
});
test('approval longer than 24 hours requires explicit extended-expiry consent',async()=>{
 const h=fixture(),calls=[],alert={textContent:''},form={id:'publication-approval-form',isConnected:true,dataset:{app:'sample-one',version:'4',principal:'owner-1',id:uuid,reviewHash:'review'},
   values:{expiry_hours:'48',max_calls:'60',due_at:'',confirm_publish:'on',confirm_rights:'on'},querySelectorAll:()=>[],querySelector:()=>alert};
 await h.c.WMMPublicationUI.submit(form,{submitter:{value:'approve'}},{state:h.state,FormData:class {constructor(f){return Object.entries(f.values)}},api:async(...args)=>calls.push(args),toast:()=>{},document:h.c.document});
 assert.equal(calls.length,0);assert.match(alert.textContent,/longer than 24 hours/);
});


test('retained engagement and provider visibility are explicit without inventing installs',()=>{
 const h=fixture();h.c.WMMPublicationUI.test.setCache(h.state,{...model,intents:[{id:uuid,authority_id:uuid,status:'PUBLISHED',remote_id:'video1',observation:{privacy_status:'private',requested_privacy_status:'public',metrics:{source:'youtube.videos.list.statistics',observed_at:'2026-11-07T00:00:00Z',counts:{views:123,likes:null,comments:0}}}}]});
 const html=h.c.WMMPublicationUI.panel(h.state);
 assert.match(html,/Provider visibility: private/);assert.match(html,/requested public/);
 assert.match(html,/Views: 123/);assert.match(html,/Likes: Not returned/);assert.match(html,/Comments: 0/);
 assert.match(html,/do not establish app installs or revenue/);assert.doesNotMatch(html,/\[object Object\]/);
});

test('the printable report distinguishes missing provider metrics from zero',()=>{
 const h=fixture(),reportModel=h.c.WMMPublicationUI.test.reportModel;
 const observed_at='2026-11-07T00:00:00Z',receipt_hash='test-receipt';
 const missing={observed_at,receipt_hash,metrics:null,reason:'PROVIDER_READ_RETURNED_NO_METRICS'};
 const row=sample=>reportModel({report:{latest_metric_sample:sample}},h.state).metrics.find(x=>x.label==='Latest channel metrics');
 assert.equal(row(missing).value,'The channel returned no metrics.');
 assert.ok(row(missing).source.includes(observed_at));
 assert.ok(row(missing).source.includes(receipt_hash));
 assert.equal(row({...missing,metrics:{counts:{views:0}},reason:null}).value,'{"counts":{"views":0}}');
});

test('guided Instagram destinations reuse only the verified mapping for this connection version',()=>{
 const h=fixture(),fb={...account,provider:'facebook',config_version:1,data:{destination:{id:'123',name:'Page'}}};
 h.state.workspace.social_access={accounts:[fb],setup:{configurations:[{provider:'facebook',version:1,data:{campaign_access:'instagram_publish'}}]}};
 h.c.WMMPublicationUI.test.setCache(h.state,{...model,instagram_accounts:[
  {connection_id:uuid,connection_version:3,destination_id:'ig-1',name:'Creator'},
  {connection_id:uuid,connection_version:2,destination_id:'ig-old',name:'Stale'}]});
 assert.deepEqual(Array.from(h.c.WMMPublicationUI.eligibleDestinations('instagram',h.state,{}),r=>r.destination_id),['ig-1']);
 h.state.workspace.identity.principal='other-owner';
 assert.equal(h.c.WMMPublicationUI.eligibleDestinations('instagram',h.state,{}).length,0);
});
