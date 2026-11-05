const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),{webcrypto}=require('node:crypto');
const folder=path.join(__dirname,'../mission_control/static');
const modelHolder={exports:{}};
new Function('module','globalThis',fs.readFileSync(path.join(folder,'discovery-model.js'),'utf8'))(modelHolder,{});
const m=modelHolder.exports;
const holder={exports:{}};
new Function('module','globalThis',fs.readFileSync(path.join(folder,'organic-research.js'),'utf8'))(holder,{WMMDiscoveryModel:m});
const ui=holder.exports;
const s=()=>({app:'sample-one',boot:{csrf:'fixture'},workspace:{app:{version:2,data:{name:'Synthetic App',locale:'en-US',job:'Rehearse a conversation',audience:'App users'}},identity:{principal:'github:123'},access:{members:[{principal:'github:123',role:'OWNER',status:'ACTIVE',version:1}]},records:[{id:'proof-one',kind:'asset'}]}});
const grant=()=>({id:'grant-one',owner:'github:123',owner_version:1,app_id:'sample-one',app_version:2,agent_id:'researcher',status:'ACTIVE',used:0,max_calls:100,expires:new Date(Date.now()+3600000).toISOString(),operations:['organic-video.claim','organic-video.submit']});
const fd=value=>({get:k=>value[k]??'',getAll:k=>Array.isArray(value[k])?value[k]:[]});
const values={grant:'grant-one',genre:'Conversation practice',app_type:'Coaching app',search_terms:'conversation opening',platform:['tiktok','instagram'],access:'PUBLIC_WEB',minutes:'30',max_candidates:'5',max_reads:'100',max_seconds:'600'};
const sha=async value=>Buffer.from(await webcrypto.subtle.digest('SHA-256',new TextEncoder().encode(m.stable(value)))).toString('hex');
async function saved(){
 const candidate={platform:'tiktok',post_id:'post-one',creator_id:'creator-one',format:'talking-head',url:'https://www.tiktok.com/@creator/video/100',views:100000,published_at:new Date(Date.now()-86400000).toISOString(),observed_at:new Date().toISOString()};
 const hash=await sha(candidate);
 return {id:'task-one',status:'SUBMITTED',task_hash:'a'.repeat(64),submission_hash:'b'.repeat(64),result_hash:'c'.repeat(64),task:{app:{version:2},query:{genre:'Conversation practice',app_type:'Coaching app',search_terms:'opening'},policy:{platforms:['tiktok'],access:'PUBLIC_WEB',expires:grant().expires,max_candidates:5,max_reads:100,max_seconds:600}},submission:{candidates:[{candidate,kind:'REFERENCE',relevance:'MATCH',rights:'UNKNOWN'}]},result:{items:[{candidate_id:'post-one',status:'COLLECTION_REVIEW_REQUIRED',qualification:{qualification:'QUALIFIED_BY_REPORTED_COUNTS',candidate_hash:hash,baseline_count:10,reasons:[]},reuse_permission:'NOT_ESTABLISHED',publication:'NOT_RUN'}],source_failures:[]},intakes:[]};
}

test('eligible recipient preserves owner, app, role version, expiry and quota boundaries',()=>{
 const good=grant();assert.ok(ui.eligible(good,s()));
 for(const change of [{owner:'other'},{owner_version:2},{app_id:'other'},{app_version:1},{status:'REVOKED'},{used:100},{expires:'2020-01-01'},{operations:['organic-video.claim']}])assert.equal(ui.eligible({...good,...change},s()),false);
 const state=s();state.workspace.access.members[0].role='CHECKER';assert.equal(ui.owner(state),false);
});
test('task assignment has exact metadata-only hosts and cannot outlast its grant',()=>{
 const g=grant(),at=Date.now();g.expires=new Date(at+5000).toISOString();
 const body=ui.taskBody(fd(values),[g],s(),()=> 'request-one',at);
 assert.equal(body.policy.expires,g.expires);assert.equal(body.request_id,'request-one');
 assert.deepEqual(body.policy.hosts,['instagram.com','tiktok.com','www.instagram.com','www.tiktok.com']);
 assert.equal(body.policy.max_reads,100);assert.ok(!JSON.stringify(body).includes('token'));
});
test('assignment rejects malformed, duplicate, unsupported or over-budget selections',()=>{
 for(const change of [{platform:[]},{platform:['tiktok','tiktok']},{platform:['unsupported']},{max_reads:'501'},{max_candidates:'0'},{max_seconds:'1.5'},{minutes:'1441'},{access:'BYPASS'},{genre:''}])assert.throws(()=>ui.taskBody(fd({...values,...change}),[grant()],s(),()=> 'one'));
});
test('scope changes include identity, app, role and browser session',()=>{
 const base=ui.scope(s());for(const change of ['app','role','principal','session']){const state=s();if(change==='app')state.app='other';if(change==='role')state.workspace.access.members[0].status='REVOKED';if(change==='principal')state.workspace.identity.principal='other';if(change==='session')state.boot.csrf='new';assert.equal(m.equal(base,ui.scope(state)),false);}
});
test('counted viral qualification, baseline gaps, UGC and reuse gaps remain independent',async()=>{
 const data=await saved();data.result.items.push({status:'INSUFFICIENT_BASELINE',qualification:{qualification:'INSUFFICIENT_BASELINE'},reuse_permission:'NOT_ESTABLISHED'},{status:'UGC_OWNER_REVIEW_REQUIRED',qualification:{qualification:'UGC_EXEMPT'},reuse_permission:'NOT_ESTABLISHED'});data.submission.candidates.push({},{});data.result.source_failures=[{source:'https://www.tiktok.com/',code:'EMPTY'}];
 assert.deepEqual(ui.counts(data),{observed_candidates:3,qualified_by_reported_counts:1,baseline_missing:1,reuse_rights_not_established:3,ugc_review:1,failed_sources:1});
});
test('unsafe source URLs and source text cannot become executable markup',async()=>{
 const data=await saved();data.task.query.genre='<script>attack</script>';data.submission.candidates[0].candidate.creator_id='<img src=x onerror=attack()>';
 const html=ui.taskHTML(data,s());assert.ok(!html.includes('<script>'));assert.ok(!html.includes('<img'));assert.ok(html.includes('&lt;script&gt;'));
 for(const url of ['javascript:alert(1)','https://evil.invalid/','https://www.tiktok.com.evil.invalid/','https://user:pass@www.tiktok.com/','https://www.tiktok.com:444/'])assert.equal(ui.safeURL(url),null);
 assert.equal(ui.safeURL('https://www.tiktok.com/@creator/video/100'),'https://www.tiktok.com/@creator/video/100');
});
test('only qualified relevant current references can be adopted and saved sources cannot be readopted',async()=>{
 const data=await saved(),row=data.result.items[0],entry=data.submission.candidates[0];assert.ok(ui.adoptable(data,row,entry,s()));
 assert.equal(ui.adoptable({...data,status:'INCOMPLETE'},row,entry,s()),false);
 assert.equal(ui.adoptable(data,{...row,status:'RELEVANCE_REVIEW_REQUIRED'},entry,s()),false);
 assert.equal(ui.adoptable(data,row,{...entry,kind:'UGC'},s()),false);
 data.intakes=[{data:{provenance:{candidate_hash:row.qualification.candidate_hash}}}];assert.equal(ui.adoptable(data,row,entry,s()),false);
});
test('structured adoption binds original source and proof without inventing rights or transcript',async()=>{
 const data=await saved(),t={data:{saved:data,row:data.result.items[0],entry:data.submission.candidates[0]},d:{state:s(),uuid:()=> 'intake-one',browser:{crypto:webcrypto}}};
 const v={title:'Synthetic source',industry:'BUSINESS',narrative:'APP_DEMO',treatment:'TALKING_HEAD',duration:'30',hook_end:'3',hook:'An opening question',mechanism:'Curiosity',rationale:'Our app demonstrates the next step',requirements:'Authentic app screen',evidence:['proof-one'],experiment:'Test an original app opening',uncertainty:'Reported counters only',inspected:'on'};
 const body=await ui.adoptionBody(fd(v),t);assert.equal(body.candidate_hash,data.result.items[0].qualification.candidate_hash);assert.equal(body.review.card.rights_status,'REFERENCE_ONLY');assert.equal(body.review.transcript,null);assert.equal(body.query.minimum_views,100000);assert.equal(body.query.baseline_required,true);assert.equal(body.query.viral_only,true);assert.deepEqual(body.review.card.authentic_evidence_ids,['proof-one']);
 for(const change of [{evidence:[]},{evidence:['foreign']},{inspected:''},{duration:'2',hook_end:'3'},{requirements:''}])await assert.rejects(()=>ui.adoptionBody(fd({...v,...change}),t));
 t.data.entry.candidate.views=999999;await assert.rejects(()=>ui.adoptionBody(fd(v),t),/changed/);
});
test('exports whitelist research evidence and omit undeclared private fields',async()=>{
 const data=await saved();data.private='PRIVATE_SENTINEL';data.submission.secret='SECRET_SENTINEL';const report=ui.report(data,s());assert.ok(!JSON.stringify(report).includes('SENTINEL'));assert.equal(report.metrics.find(x=>x.label==='reuse rights not established').value,1);assert.ok(report.notes.some(x=>x.includes('no media reuse')));assert.equal(report.schema,'wmm.organic-research-report.v1');
});
test('exports retain source-level reported evidence and named read failures',async()=>{
 const data=await saved();data.result.source_failures=[{source:'https://www.instagram.com/',code:'LOGIN'}];
 const rows=ui.report(data,s()).cohorts;assert.equal(rows[0].reported_views,100000);assert.equal(rows[0].source_url,data.submission.candidates[0].candidate.url);assert.equal(rows[0].baseline_posts,10);assert.equal(rows[1].status,'LOGIN');assert.equal(rows[1].kind,'SOURCE_READ_FAILURE');
});
test('lost responses are uncertain and no request redirects or retries automatically',async()=>{
 let calls=0;const t={scope:{app:'sample-one'},d:{state:s(),fetch:async(url,options)=>{calls++;assert.equal(url,'/api/apps/sample-one/organic-video/prepare');assert.equal(options.redirect,'error');assert.equal(options.credentials,'same-origin');assert.equal(options.headers['X-CSRF-Token'],'fixture');throw new Error('lost');}}};
 await assert.rejects(()=>ui.request(t,'prepare',{request_id:'one'}),e=>e.uncertain===true);assert.equal(calls,1);await assert.rejects(()=>ui.request(t,'policy-create',{}));assert.equal(calls,1);
});
test('explicit validation denial stays certain and server errors stay uncertain',async()=>{
 for(const code of [400,403,500]){const t={scope:{app:'one'},d:{state:s(),fetch:async()=>({ok:false,status:code,json:async()=>({error:'Safe failure'})})}};await assert.rejects(()=>ui.request(t,'task-list',{}),e=>e.message==='Safe failure'&&e.uncertain===(code>=500));}
});
test('production entry points load the module and route actual actions, forms, invalidation and close',()=>{
 const app=fs.readFileSync(path.join(folder,'app.js'),'utf8'),index=fs.readFileSync(path.join(folder,'index.html'),'utf8');
 for(const text of ['WMMOrganicResearch.panel()','WMMOrganicResearch.invalidate(state)','WMMOrganicResearch.clear()','WMMOrganicResearch.action(node,growthReviewServices())','WMMOrganicResearch.submit(form,growthReviewServices())'])assert.ok(app.includes(text),text);
 assert.ok(index.includes('src="/organic-research.js"'));assert.ok(ui.panel().includes('100,000 views AND 10×'));
});

test('YouTube Shorts metadata task scope is explicit and links reject other YouTube surfaces',()=>{const b=ui.taskBody(fd({...values,platform:['youtube']}),[grant()],s(),()=>'short-task');assert.deepEqual(b.policy.hosts,['www.youtube.com','youtube.com']);assert.equal(ui.safeURL('https://www.youtube.com/shorts/QAshort0000'),'https://www.youtube.com/shorts/QAshort0000');for(const u of ['https://www.youtube.com/watch?v=QAshort0000','https://youtu.be/QAshort0000','https://www.youtube.com/shorts/QAshort0000?x=1'])assert.equal(ui.safeURL(u),null);});
