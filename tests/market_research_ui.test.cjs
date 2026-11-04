const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),holder={exports:{}};
new Function('module',fs.readFileSync('mission_control/static/growth-review.js','utf8'))(holder);
const growth=holder.exports;
function state(){return {app:'one',workspace:{app:{id:'one',version:1,data:{name:'Test <app>',release:'r1',locale:'en-US'}},subscription_growth:{app_id:'one',context:{manifest_version:1},history:{history:[]},issues:[],journeys:[],experiments:[],ads_sources:[],evidence_states:{},observed_at:'2026-11-04',source_hash:'h'}}};}
function form(){const error={textContent:''},button={disabled:false},preview={innerHTML:''};return {dataset:{app:'one',version:'1',id:'fixed-request',mode:'research'},isConnected:true,querySelector:s=>s.includes('submit')?button:s.includes('preview')?preview:error,button,error,preview};}
const data={release:'r1',snapshot:{platform:'iOS',locale:'en-US',territory:'US',observed_at:'2026-11-04',sources:[],phrases:[],competitors:[]}};
test('file form is labeled, bounded and discloses source assertion boundary',()=>{const html=growth.researchFields(state());for(const value of ['for="market-research-file"','required','1 MiB','not provider verified','wmm_catalog','MARKET_RESEARCH','Test &lt;app&gt;'])assert.ok(html.includes(value));});
test('imported stale app scope is reported independently from assertion provenance',()=>{
 const row={id:'note',hash:'h',kind:'EDITORIAL_NOTE',created:'now',data:{decision:'DEFER',rationale:'Scope changed',target_id:'source',target_hash:'hash'},readout:{availability:'IMPORTED_ASSERTION',scope_status:'STALE_APP_SCOPE',import_provenance:'IMPORTED_ASSERTION',analysis:{status:'EDITORIAL_NOTE_ONLY'}}};
 const text=growth.entryNotes(row).join('\n');assert.ok(text.includes('stale app scope'));assert.ok(text.includes('imported assertion'));
});
test('raw JSON and immutable request ID preserve server duplicate validation',()=>{const f=form(),raw='{"release":"r1","release":"r1","snapshot":{}}';const packet=growth.researchBody(f,raw,state());assert.ok(packet.body.includes(raw));assert.equal(JSON.parse(packet.body).id,'fixed-request');assert.throws(()=>growth.researchBody(f,'[]',state()));assert.throws(()=>growth.researchBody(f,'{',state()));assert.throws(()=>growth.researchBody(f,JSON.stringify({padding:'x'.repeat(1048576)}),state()));assert.throws(()=>growth.researchBody(f,JSON.stringify(data),{...state(),app:'two'}));});
test('review precedes save and uncertain response retains identical request for explicit retry',async()=>{
 const f=form(),s=state(),raw=JSON.stringify(data),requests=[];let fail=true,closed=0;
 class Fields{get(){return {size:raw.length,text:async()=>raw};}}
 const deps={state:s,FormData:Fields,api:async(path,body,options)=>{requests.push({path,body:options.body});if(fail)throw Error('Response unavailable');},refresh:async()=>{},close:()=>closed++,toast:()=>{}};
 await growth.submit(f,deps);assert.equal(requests.length,0);assert.ok(f.preview.innerHTML.includes('Review before saving'));
 await growth.submit(f,deps);assert.equal(closed,0);assert.ok(f.error.textContent.includes('Inputs are preserved'));
 fail=false;await growth.submit(f,deps);assert.equal(requests.length,2);assert.deepEqual(requests[0],requests[1]);assert.equal(closed,1);assert.equal(f.dataset.id,'fixed-request');
});
test('file changes require a fresh preview and escaped candidate reports preserve unknown metrics',async()=>{
 const f=form();let raw=JSON.stringify(data),calls=0;
 class Fields{get(){return {size:raw.length,text:async()=>raw};}}
 const deps={state:state(),FormData:Fields,api:async()=>calls++,refresh:async()=>{},close:()=>{},toast:()=>{}};
 await growth.submit(f,deps);raw=JSON.stringify({...data,release:'changed'});await growth.submit(f,deps);assert.equal(calls,0);assert.ok(f.preview.innerHTML.includes('changed'));
 const row={id:'r',kind:'MARKET_RESEARCH',hash:'h',created:'now',data:{snapshot:{...data.snapshot,own_listing:{excerpt:'<script>own</script>',source_id:'source'},sources:[{id:'source',url:'https://example.com',sha256:'hash',retrieved_at:'today',coverage:'PARTIAL',excerpt:'proof'}],phrases:[{phrase:'keyword',source_ids:['source'],observed:{demand_signal:null,competitor_position:null},inferred:{intent:'app search',relevance:.8},metrics:{rank:null,search_volume:null,difficulty:null}}]}},readout:{availability:'CURRENT_LOCAL_EVIDENCE',analysis:{status:'PARTIAL',next_action:'Complete evidence',scope:'No ranking inference',coverage:{sourced_phrases:1,phrases:1},candidates:[{phrase:'keyword',reason:'Source overlap',own_listing_overlap:false,competitor_ids:[],suggested_test:'Test copy'}]}}};
 const notes=growth.entryNotes(row).join('\n');assert.ok(notes.includes('rank: Unknown'));assert.ok(notes.includes('source https')===false);assert.ok(notes.includes('https://example.com'));assert.ok(notes.includes('not search demand'));let rendered='';const s=state();s.workspace.subscription_growth.history.history=[row];growth.detail('r',{state:s,modal:(_title,html)=>rendered=html});assert.ok(rendered.includes('&lt;script&gt;own&lt;/script&gt;'));assert.ok(!rendered.includes('<script>'));
});
