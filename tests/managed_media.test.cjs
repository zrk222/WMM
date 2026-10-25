const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),crypto=require('node:crypto');
const holder={exports:{}};new Function('module',fs.readFileSync('mission_control/static/managed-media.js','utf8'))(holder);const media=holder.exports;
const digest=v=>crypto.createHash('sha256').update(v).digest('hex');let serial=0;
function fixture(){
 media.clear();const app='media-case-'+(++serial),calls=[],reports=[],nodes={},writes=[{dataset:{locked:'false'},disabled:false}];let html='',counter=0,items=[];
 const root={open:true,querySelector:s=>nodes[s]||(nodes[s]={textContent:'',setAttribute(){},focus(){}}),querySelectorAll:s=>s==='video'?[]:s==='[data-media-write]'?writes:[]};
 const d={state:{app,boot:{csrf:'CSRF_SENTINEL'},workspace:{app:{version:1,data:{name:'Synthetic app'}},identity:{principal:'owner'},access:{members:[{principal:'owner',role:'OWNER',status:'ACTIVE'}]}}},document:{querySelector:()=>root},modal:(title,value)=>{media.clear();html=value;Object.keys(nodes).forEach(k=>delete nodes[k]);writes[0].dataset.locked=html.includes('data-locked="true"')?'true':'false';},uuid:()=>`request-${++counter}`,FormData:class{constructor(f){this.values=f.values;}get(k){return this.values[k];}},browser:{crypto:crypto.webcrypto},pageReports:{openReport:r=>reports.push(r)}};
 const row=(name='PRIVATE_FILENAME.mp4',extra={})=>({id:'clip-'+(++counter),app_id:app,filename:name,source_sha256:digest('source'),manifest_version:1,bytes:6,metadata:{width:320,height:180,codec:'h264',duration_seconds:2,frame_rate:'24/1',audio:true,audio_metadata:{codec:'aac'}},decoded:{video_frames:48,audio_frames:96},provenance:{kind:'LOCAL_UPLOAD'},rights_status:'UNKNOWN',reuse_available:false,review_version:0,review_history:[],...extra});
 const respond=value=>({ok:true,status:200,json:async()=>value});
 d.fetch=async(url,options)=>{calls.push({url,options});
  if(options.method==='POST'&&url.endsWith('/uploads')){const file=options.body,value=row(decodeURIComponent(options.headers['X-Filename']),{source_sha256:digest(Buffer.from(await file.arrayBuffer())),upload_request_key_sha256:digest(options.headers['X-WMM-Request-Key'])});items.push(value);return respond(value);}
  if(options.method==='POST'){const body=JSON.parse(options.body),old=items.find(r=>url.endsWith('/'+r.id+'/reviews')),value={...old,review_version:old.review_version+1,rights_status:body.status==='ALLOWED'?'ALLOWED_BY_ATTESTATION':'REVOKED',reuse_available:body.status==='ALLOWED',review_history:[body]};items=items.map(r=>r.id===value.id?value:r);return respond(value);}
  return respond(url.endsWith('/media')?{items}:items.find(r=>url.endsWith('/'+r.id)));
 };
 return {d,root,nodes,writes,calls,reports,row,respond,html:()=>html,items:()=>items,setItems:v=>items=v};
}
const action=(name,id)=>({dataset:{action:'media-'+name,id}});
const file=(name,body='source')=>({name,size:Buffer.byteLength(body),arrayBuffer:async()=>Uint8Array.from(Buffer.from(body)).buffer});
const upload=files=>({id:'media-upload-form',querySelector:()=>({files})});
const review=(values={})=>({id:'media-review-form',values:{status:'ALLOWED',basis:'OWNED',evidence:'PRIVATE_REVIEW_EVIDENCE',...values}});
test('bounds reject empty unsupported and oversized clips before sending any selected file',async()=>{
 for(const value of [{name:'bad.exe',size:2},{name:'empty.mp4',size:0},{name:'big.mov',size:media.MAX_BYTES+1}])assert.throws(()=>media.validateFile(value));
 assert.doesNotThrow(()=>media.validateFile({name:'clip.webm',size:media.MAX_BYTES}));
 const f=fixture();await media.open(f.d);await media.submit(upload([file('valid.mp4'),file('bad.exe')]),f.d);assert.equal(f.calls.length,1);
});
test('multiple clips upload sequentially with exact source/request receipts and fresh keys',async()=>{
 const f=fixture();await media.open(f.d);await media.submit(upload([file('red.mp4','red'),file('blue.mov','blue')]),f.d);
 const sent=f.calls.filter(c=>c.options.method==='POST');assert.equal(sent.length,2);
 assert.notEqual(sent[0].options.headers['X-WMM-Request-Key'],sent[1].options.headers['X-WMM-Request-Key']);
 assert.equal(sent[0].options.headers['X-CSRF-Token'],'CSRF_SENTINEL');assert.equal(sent[0].options.headers['Content-Type'],'application/octet-stream');assert.equal(sent[0].options.headers['X-WMM-Manifest-Version'],'1');assert.equal(sent[0].options.redirect,'error');
 assert.match(f.html(),/2 saved original clips observed/);assert.match(f.nodes['#media-progress'].textContent,/2 original clip\(s\) saved/);
});
test('unknown upload never resends and only exact request/source/name/manifest receipt unlocks',async()=>{
 const f=fixture();await media.open(f.d);const original=f.d.fetch;let sends=0;
 f.d.fetch=async(url,opts)=>{if(url.endsWith('/uploads')){sends++;await original(url,opts);throw new Error('lost reply');}return original(url,opts);};
 await media.submit(upload([file('original.mp4')]),f.d);assert.equal(sends,1);assert.match(f.nodes['#media-error'].textContent,/Outcome unknown/);assert.equal(f.writes[0].disabled,true);
 const exact={...f.items()[0]};f.setItems([{...exact,upload_request_key_sha256:'older-key'}]);await media.open(f.d);await media.submit(upload([file('original.mp4')]),f.d);assert.equal(sends,1);
 for(const altered of [{source_sha256:'wrong'},{filename:'other.mp4'},{manifest_version:2}]){f.setItems([{...exact,...altered}]);await media.open(f.d);await media.submit(upload([file('original.mp4')]),f.d);assert.equal(sends,1);}
 f.d.fetch=original;f.setItems([exact]);await media.open(f.d);assert.ok(!f.html().includes('outcome(s) pending or unknown'));
});
test('pending duplicate upload sends once and identity change discards late response',async()=>{
 const f=fixture();await media.open(f.d);let release;const original=f.d.fetch;
 f.d.fetch=async(url,opts)=>{if(url.endsWith('/uploads'))return new Promise(r=>release=async()=>r(await original(url,opts)));return original(url,opts);};
 const first=media.submit(upload([file('one.mp4')]),f.d);while(!release)await new Promise(r=>setImmediate(r));await media.submit(upload([file('one.mp4')]),f.d);
 f.d.state.workspace.identity.principal='other';media.invalidate(f.d.state);const before=f.html();await release();await first;assert.equal(f.html(),before);assert.equal(f.calls.filter(c=>c.options.method==='POST').length,1);
});
test('malformed success receipts remain uncertain rather than permitting resend',async()=>{
 const f=fixture();await media.open(f.d);let sends=0;const original=f.d.fetch;
 f.d.fetch=async(url,opts)=>{if(opts.method==='POST'){sends++;return f.respond(null);}return original(url,opts);};
 await media.submit(upload([file('one.mp4')]),f.d);await media.submit(upload([file('one.mp4')]),f.d);assert.equal(sends,1);assert.equal(f.writes[0].disabled,true);
 const g=fixture(),row=g.row();g.setItems([row]);await media.open(g.d);await media.action(action('inspect',row.id),g.d);let reviews=0;const read=g.d.fetch;
 g.d.fetch=async(url,opts)=>{if(opts.method==='POST'){reviews++;return g.respond({...row,review_version:99});}return read(url,opts);};
 await media.submit(review(),g.d);await media.submit(review(),g.d);assert.equal(reviews,1);assert.equal(g.writes[0].disabled,true);
});
test('inspection escapes metadata, plays original and separates owner reuse attestation from decoding',async()=>{
 const f=fixture(),r=f.row('<img src=x>.mp4');f.setItems([r]);await media.open(f.d);await media.action(action('inspect',r.id),f.d);
 assert.ok(!f.html().includes('<img src=x>'));assert.match(f.html(),/Reuse not approved/);assert.match(f.html(),/controls preload="metadata"/);assert.ok(f.html().includes('/preview'));assert.ok(f.html().includes('/download'));assert.ok(f.html().includes('not independent legal verification'));
 await media.submit(review(),f.d);const sent=JSON.parse(f.calls.at(-1).options.body);
 assert.deepEqual(sent,{expected_version:0,manifest_version:1,source_sha256:r.source_sha256,status:'ALLOWED',basis:'OWNED',evidence:'PRIVATE_REVIEW_EVIDENCE'});
 assert.match(f.html(),/Reuse allowed by owner attestation/);await media.submit(review({status:'REVOKED'}),f.d);assert.match(f.html(),/Reuse revoked/);
});
test('uncertain review pauses changes across reopen without an automatic retry',async()=>{
 const f=fixture(),r=f.row();f.setItems([r]);await media.open(f.d);await media.action(action('inspect',r.id),f.d);const original=f.d.fetch;let sends=0;
 f.d.fetch=async(url,opts)=>{if(opts.method==='POST'){sends++;throw new Error('lost reply');}return original(url,opts);};
 await media.submit(review(),f.d);await media.submit(review(),f.d);assert.equal(sends,1);assert.equal(f.writes[0].disabled,true);
 await media.open(f.d);await media.action(action('inspect',r.id),f.d);await media.submit(review(),f.d);assert.equal(sends,1);
});
test('review evidence stays within exact server bound before sending',async()=>{
 const f=fixture(),r=f.row();f.setItems([r]);await media.open(f.d);await media.action(action('inspect',r.id),f.d);
 assert.ok(f.html().includes('maxlength="1000"'));
 for(const evidence of ['', ' ', 'x'.repeat(1001)])await media.submit(review({evidence}),f.d);
 assert.equal(f.calls.filter(c=>c.options.method==='POST').length,0);
 await media.submit(review({evidence:'x'.repeat(1000)}),f.d);assert.equal(f.calls.filter(c=>c.options.method==='POST').length,1);
});
test('reports contain observed counts and receipt time without filenames evidence credentials or private paths',async()=>{
 const f=fixture(),r=f.row();r.review_history=[{evidence:'PRIVATE_REVIEW_EVIDENCE'}];f.setItems([r]);await media.open(f.d);await media.action(action('report'),f.d);
 const report=f.reports[0],text=JSON.stringify(report);assert.equal(report.metrics[0].value,1);assert.equal(report.metrics[1].value,0);assert.equal(report.metrics[2].value,1);assert.ok(report.loaded_at);
 for(const privateText of ['PRIVATE_FILENAME','PRIVATE_REVIEW_EVIDENCE','CSRF_SENTINEL'])assert.ok(!text.includes(privateText));
});
test('closed dialog or new app drops late library reads; owner is required for writes',async()=>{
 const f=fixture();let release;f.d.fetch=()=>new Promise(r=>release=r);const call=media.open(f.d);const before=f.html();f.root.open=false;release(f.respond({items:[]}));await call;assert.equal(f.html(),before);
 const g=fixture();await media.open(g.d);g.d.state.workspace.access.members[0].role='CHECKER';await media.submit(upload([file('one.mp4')]),g.d);assert.equal(g.calls.length,1);
});
test('Research and modal hooks load one exact module and preserve scoped cleanup',()=>{
 const app=fs.readFileSync('mission_control/static/app.js','utf8'),index=fs.readFileSync('mission_control/static/index.html','utf8');
 for(const hook of ['WMMMedia.panel()','WMMMedia.invalidate(state)','WMMMedia.clear()','WMMMedia.submit(form,growthReviewServices())','WMMMedia.action(node,growthReviewServices())'])assert.ok(app.includes(hook),hook);
 assert.equal((index.match(/src="\/managed-media.js"/g)||[]).length,1);assert.match(media.panel(),/Optional Drive selection/);
});

test('saved revocation and permission basis remain selected when an original is reopened',async()=>{
 const f=fixture(),r=f.row('clip.mp4',{rights_status:'REVOKED',review_version:2,latest_review:{status:'REVOKED',basis:'LICENSED'}});
 f.setItems([r]);await media.open(f.d);await media.action(action('inspect',r.id),f.d);
 assert.match(f.html(),/<option value="REVOKED" selected>/);
 assert.match(f.html(),/<option value="LICENSED" selected>/);
 assert.doesNotMatch(f.html(),/<option value="ALLOWED" selected>/);
 assert.doesNotMatch(f.html(),/<option value="OWNED" selected>/);
 await media.open(f.d);await media.action(action('inspect',r.id),f.d);
 assert.match(f.html(),/<option value="REVOKED" selected>/);
});
