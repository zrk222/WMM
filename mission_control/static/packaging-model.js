/* Pure packaging authoring and preview models. No provider or rendering calls. */
(function(root,factory){const value=factory();if(typeof module==='object'&&module.exports)module.exports=value;else root.WMMPackagingModel=value;})(globalThis,function(){
'use strict';
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const copy=v=>JSON.parse(JSON.stringify(v));
function stable(v){if(Array.isArray(v))return '['+v.map(stable).join(',')+']';if(v&&typeof v==='object')return '{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+stable(v[k])).join(',')+'}';return JSON.stringify(v);}
const equal=(a,b)=>stable(a)===stable(b);
function text(v,name,max=2000,optional=false){if(typeof v!=='string'||v.length>max||(!optional&&!v.trim()))throw new Error(name+': enter '+(optional?'at most ':'1 through ')+max+' characters.');return v.trim();}
function id(v){if(typeof v!=='string'||v.length>60||! /^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(v))throw new Error('Use a lowercase identifier with single hyphens.');return v;}
function number(v,name,min=0,max=2000){if(!/^(0|[1-9][0-9]*)$/.test(String(v)))throw new Error(name+': enter a whole number.');const n=Number(v);if(!Number.isSafeInteger(n)||n<min||n>max)throw new Error(name+': outside the supported range.');return n;}
function milliseconds(v){if(!/^(0|[1-9][0-9]*)(\.[0-9]{1,3})?$/.test(String(v)))throw new Error('Source time: use seconds with up to three decimal places.');const n=Math.round(Number(v)*1000);if(n>86400000)throw new Error('Source time exceeds 24 hours.');return n;}
function hash(v){if(typeof v!=='string'||! /^[a-f0-9]{64}$/.test(v))throw new Error('Evidence digest is unavailable. Reload the app.');return v;}
function ref(kind,row){return {kind,id:id(row.id),version:number(row.version,'Evidence revision',1,2147483647),sha256:hash(row.hash)};}
const key=r=>r.kind+':'+r.id;
function entry(kind,row,label,raw=row){return {key:kind+':'+row.id,label,ref:ref(kind,row),raw};}
function libraries(state,collections=[],media=[]){
 const w=state.workspace,app=w.app.data,records=(w.records||[]).filter(r=>r.data.release===app.release&&r.data.locale===app.locale);
 const sources=(w.references||[]).map(r=>entry('SOURCE',{...r.current,id:r.id},r.current.data.title,r.current.data));
 const products=records.filter(r=>['claim','asset'].includes(r.kind)).map(r=>entry(r.kind.toUpperCase(),r,r.title+(r.data.claim?' / '+r.data.claim:''),r.data));
 const briefs=(w.briefs||[]).map(r=>entry('BRIEF',{...r.current,id:r.id},r.id+' / revision '+r.current.version));
 const research=collections.map(r=>entry('COLLECTION',r,r.id+' / revision '+r.version));
 const clips=media.filter(r=>r.reuse_available===true).map(r=>entry('MEDIA',{id:r.id,version:r.review_version,hash:r.source_sha256},r.filename+' / current reuse review',r));
 const latest=new Map();for(const row of [...sources,...products,...briefs,...research,...clips]){if(!latest.has(row.key)||latest.get(row.key).ref.version<row.ref.version)latest.set(row.key,row);}return [...latest.values()];
}
function find(value,lib,kinds){const row=lib.find(r=>r.key===value&&kinds.includes(r.ref.kind));if(!row)throw new Error('Selected evidence changed or is unavailable. Reload this app and review the selection.');return row;}
function selected(values,lib,kinds){if(values.length>100||new Set(values).size!==values.length)throw new Error('Select at most 100 distinct evidence items.');return values.map(v=>copy(find(v,lib,kinds).ref));}
function imageURL(app,file){id(app);if(typeof file!=='string'||! /^[a-zA-Z0-9][a-zA-Z0-9._-]{0,199}$/.test(file))return null;return '/api/apps/'+encodeURIComponent(app)+'/files/'+encodeURIComponent(file);}
function thumbnail(definition,lib,app){const asset=(definition.app_proofs||[]).find(r=>r.kind==='ASSET'),row=asset&&lib.find(r=>r.key===key(asset)&&equal(r.ref,asset));return row?imageURL(app,row.raw.file_id):null;}
function variantData(fd,lib){
 const data={};for(const name of ['audience','app_outcome','title','thumbnail','opening_frame','hook','cta'])data[name]=text(fd.get(name),name.replaceAll('_',' '),name==='title'?300:2000);
 data.sources=selected(fd.getAll('sources'),lib,['SOURCE','COLLECTION']);
 data.creative=fd.get('creative')?copy(find(fd.get('creative'),lib,['BRIEF']).ref):null;
 const thumb=fd.get('thumbnail_asset'),proof=selected(fd.getAll('app_proofs'),lib,['CLAIM','ASSET']);
 data.app_proofs=thumb?[copy(find(thumb,lib,['ASSET']).ref),...proof.filter(r=>key(r)!==thumb)]:proof;
 return data;
}
function newShots(variant,uuid){const segment='segment-'+uuid();return {variant:ref('VARIANT',variant),script:[{id:segment,text:variant.data.definition.hook}],shots:[{id:'shot-'+uuid(),segment_id:segment,kind:'A_ROLL',description:'',source:'',start:'',end:'',assets:[],claims:[],claim_text:''}]};}
function editableShots(definition){return {variant:copy(definition.variant),script:copy(definition.script),shots:definition.shots.map(s=>({...s,source:s.source?key(s.source):'',start:s.start_ms===null?'':String(s.start_ms/1000),end:s.end_ms===null?'':String(s.end_ms/1000),assets:s.assets.map(key),claims:s.claims.map(key)}))};}
function collectShots(fd,draft){
 const script=draft.script.map((s,i)=>({id:fd.get('segment_'+i+'_id'),text:fd.get('segment_'+i+'_text')}));
 const shots=draft.shots.map((s,i)=>{const p='shot_'+i+'_',row={};for(const name of ['id','segment_id','kind','description','source','start','end','claim_text'])row[name]=fd.get(p+name);row.assets=fd.getAll(p+'assets');row.claims=fd.getAll(p+'claims');return row;});
 return {variant:copy(draft.variant),script,shots};
}
async function sha(value,cryptoImpl=globalThis.crypto){if(!cryptoImpl?.subtle)throw new Error('This browser cannot calculate the required script digest. Use a browser with Web Crypto support; entered fields are preserved.');const bytes=new TextEncoder().encode(stable(value));return Array.from(new Uint8Array(await cryptoImpl.subtle.digest('SHA-256',bytes)),n=>n.toString(16).padStart(2,'0')).join('');}
function shotTiming(row,source){if(!source){if(row.start!==''||row.end!=='')throw new Error('Choose a source before setting source timestamps.');return {start_ms:null,end_ms:null};}const start=milliseconds(row.start),end=milliseconds(row.end);if(start>=end)throw new Error('Source end time must follow its start time.');return {start_ms:start,end_ms:end};}
async function shotData(draft,lib,cryptoImpl){
 if(!draft.script.length||draft.script.length>100||draft.shots.length>100)throw new Error('Use 1 through 100 script segments and at most 100 shots.');
 const script=draft.script.map(s=>({id:id(s.id),text:text(s.text,'Script text',4000)}));
 if(new Set(script.map(s=>s.id)).size!==script.length)throw new Error('Each script segment needs a different identifier.');
 const hashes=new Map(await Promise.all(script.map(async s=>[s.id,await sha(s,cryptoImpl)])));
 const shots=draft.shots.map(s=>shotRow(s,hashes,lib));
 if(new Set(shots.map(s=>s.id)).size!==shots.length)throw new Error('Each shot needs a different identifier.');
 return {variant:copy(draft.variant),script,shots};
}
function shotRow(row,hashes,lib){
 if(!hashes.has(row.segment_id))throw new Error('Choose a current script segment for every shot.');
 if(!['A_ROLL','B_ROLL','SCREEN_RECORDING','GRAPHICS','AUDIO'].includes(row.kind))throw new Error('Choose a supported shot kind.');
 const source=row.source?copy(find(row.source,lib,['SOURCE']).ref):null;
 return {id:id(row.id),segment_id:row.segment_id,segment_sha256:hashes.get(row.segment_id),kind:row.kind,description:text(row.description,'Shot description'),source,...shotTiming(row,source),assets:selected(row.assets,lib,['ASSET','MEDIA']),claims:selected(row.claims,lib,['CLAIM']),claim_text:text(row.claim_text,'Claim copy',2000,true)};
}
function move(rows,index,delta){number(index,'Row',0,rows.length-1);if(![-1,1].includes(delta)||index+delta<0||index+delta>=rows.length)throw new Error('This row cannot move farther.');const result=copy(rows);[result[index],result[index+delta]]=[result[index+delta],result[index]];return result;}
function input(name,label,value='',max=2000,type='textarea'){const ident='packaging-'+name,attrs=`id="${esc(ident)}" name="${esc(name)}"`;return `<label class="field" for="${esc(ident)}">${esc(label)}${type==='textarea'?`<textarea ${attrs} maxlength="${max}" rows="3">${esc(value)}</textarea>`:`<input ${attrs} type="${esc(type)}" value="${esc(value)}">`}</label>`;}
function select(name,label,rows,values=[],multiple=false){return `<label class="field" for="packaging-${esc(name)}">${esc(label)}<select id="packaging-${esc(name)}" name="${esc(name)}" ${multiple?'multiple size="4"':''}>${multiple?'':'<option value="">Choose an option</option>'}${rows.map(r=>`<option value="${esc(r[0])}"${values.includes(r[0])?' selected':''}>${esc(r[1])}</option>`).join('')}</select></label>`;}
const choices=(lib,kinds)=>lib.filter(r=>kinds.includes(r.ref.kind)).map(r=>[r.key,r.label]);
function variantFields(data,lib){const names={audience:'Who is this video for?',app_outcome:'What app outcome will it show?',title:'Video title',thumbnail:'Thumbnail layout or image description',opening_frame:'What appears in the first frame?',hook:'What are the opening words?',cta:'What should the viewer do next?'};const primary=Object.entries(names).map(([k,label])=>input(k,label,data[k]||'',k==='title'?300:2000)).join('');return `<div class="form-grid">${primary}${select('thumbnail_asset','Uploaded thumbnail image (optional)',choices(lib,['ASSET']),[(data.app_proofs||[]).find(r=>r.kind==='ASSET')].filter(Boolean).map(key))}</div><details><summary>Connect source ideas and authentic app proof</summary><p>Selections bind their current saved revision. The first selected uploaded image supplies the thumbnail preview. Review these choices before saving.</p>${select('sources','Saved sources or research collections',choices(lib,['SOURCE','COLLECTION']),(data.sources||[]).map(key),true)}${select('creative','Original production brief (optional)',choices(lib,['BRIEF']),data.creative?[key(data.creative)]:[])}${select('app_proofs','App claims and assets',choices(lib,['CLAIM','ASSET']),(data.app_proofs||[]).map(key),true)}</details>`;}
function shuffle(rows,seed){let n=2166136261;for(const c of seed)n=Math.imul(n^c.charCodeAt(0),16777619);const out=copy(rows);for(let i=out.length-1;i>0;i--){n=(Math.imul(n,1664525)+1013904223)>>>0;const j=n%(i+1);[out[i],out[j]]=[out[j],out[i]];}return out;}
function previewInput(saved,selection){
 if(saved.kind!=='VARIANT'||saved.source_status!=='CURRENT')throw new Error('Open a current saved variant before comparing packaging.');
 if(!Array.isArray(selection.references)||selection.references.length<2||selection.references.length>3)throw new Error('Choose two or three saved reference sources.');
 if(new Set(selection.references.map(r=>r.source)).size!==selection.references.length)throw new Error('Choose different reference sources.');
 if(!['desktop','mobile'].includes(selection.device))throw new Error('Choose desktop or mobile.');
}
function referenceCard(item,lib,app){const source=find(item.source,lib,['SOURCE']),asset=item.asset?find(item.asset,lib,['ASSET']):null;return {id:source.ref.id,title:source.raw.title,image:asset?imageURL(app,asset.raw.file_id):null,image_reference:asset?copy(asset.ref):null,identity:source.raw.creator_id||'Saved reference',hash:source.ref.sha256,version:source.ref.version,draft:false,observed_views:source.raw.metric_kind==='VIEWS'?source.raw.metric_value:null,observed_at:source.raw.metric_at||null};}
function preview(saved,lib,selection,app){
 previewInput(saved,selection);
 const seed=text(selection.seed,'Preview seed',120),definition=saved.data.definition;
 const cards=[{id:saved.id,title:definition.title,image:thumbnail(definition,lib,app),image_reference:copy(definition.app_proofs.find(r=>r.kind==='ASSET')||null),identity:'Your saved draft',hash:saved.hash,version:saved.version,draft:true}];
 for(const item of selection.references)cards.push(referenceCard(item,lib,app));
 return {schema:'wmm.packaging-preview.v1',variant:ref('VARIANT',saved),device:selection.device,width:selection.device==='desktop'?1440:390,seed,hide_identity:selection.hide_identity===true,cards:shuffle(cards,seed),observations:text(selection.observations||'','Preview observations',2000,true),observations_kind:'HUMAN_SUPPLIED_SIMULATION_NOTE',measured_ctr:null,measured_installs:null,measured_app_sales:null,execution_authority:false};
}
function feedHTML(value,origin=''){return `<div class="packaging-feed-stage" tabindex="0" aria-label="${value.width} pixel ${esc(value.device)} comparison; scroll within this frame if needed"><div class="packaging-feed ${value.device==='mobile'?'is-mobile':''}">${value.cards.map(c=>`<article class="packaging-feed-card">${c.image?`<img src="${esc(origin+c.image)}" alt="Selected local thumbnail for ${esc(c.title)}">`:'<div class="packaging-thumbnail-empty">No thumbnail selected</div>'}<h3 class="packaging-feed-title">${esc(c.title)}</h3><p>${value.hide_identity?'Comparison item':esc(c.identity)}</p>${value.hide_identity?'':`<p>${c.draft?'Draft / not published':c.observed_views===null?'Observed views unavailable':esc(c.observed_views)+' observed views / '+esc(c.observed_at)}</p>`}</article>`).join('')}</div></div>`;}
function exported(saved,previewValue=null){return {schema:'wmm.packaging-report.v1',document:copy(saved),preview:previewValue?copy(previewValue):null,render:'NOT_RUN',publication:'NOT_RUN',measured_app_sales:null};}
function report(saved,state,previewValue=null){const def=saved.data.definition,shots=saved.kind==='SHOTS'?def.shots:[];return {title:'Your saved creative plan',app_id:state.app,app_name:state.workspace.app.data.name,scope:'SELECTED_APP',manifest_version:saved.data.manifest_version,generated_at:new Date().toISOString(),loaded_at:state.workspaceObservedAt||'Workspace load time unavailable',purpose:'Review this title, opening and shootable plan before production.',next_step:'Resolve missing evidence, then use the original production brief and video editor.',filters:{document:saved.id,revision:saved.version,kind:saved.kind,source_status:saved.source_status,preview_device:previewValue?.device||'Not compared',preview_seed:previewValue?.seed||''},cohorts:shots.map(s=>({id:s.id,status:s.kind,horizon:'PREPRODUCTION',currency:'NOT_APPLICABLE',segment:s.segment_id,description:s.description,assets:s.assets.length,claims:s.claims.length})),metrics:[{label:'Saved revision',value:saved.version,unit:'revision',source:saved.hash},{label:'Missing evidence items',value:saved.missing_evidence.length,unit:'count',source:'Server readback'},{label:'Planned shots',value:shots.length,unit:'count',source:'Saved plan'},{label:'Measured CTR',value:null,unit:'rate',source:'No measured CTR supplied'},{label:'Measured app sales',value:null,unit:'count',source:'No attributed sales supplied'}],notes:['Saved document hash: '+saved.hash,'Source status: '+saved.source_status,'A saved draft or simulation grants no rendering, reuse, publication or spending authority.',previewValue?'Simulation note (owner supplied): '+previewValue.observations:'No feed comparison included.',previewValue?'Reference snapshots: '+previewValue.cards.map(c=>c.id+' revision '+c.version+' / '+c.hash).join('; '):'Source bindings are retained in the JSON plan.']};}
function csv(saved,previewValue=null){const cell=v=>'"'+String(v??'').replace(/^[\s]*[=+@-]/,"'$&").replaceAll('"','""')+'"';const rows=[['Document','Revision','Kind','Source status','Shot','Description','Measured CTR','Measured app sales']];const shots=saved.kind==='SHOTS'?saved.data.definition.shots:[{id:'',description:saved.data.definition.title}];for(const s of shots)rows.push([saved.id,saved.version,saved.kind,saved.source_status,s.id,s.description,'UNAVAILABLE','UNAVAILABLE']);if(previewValue)rows.push([saved.id,saved.version,'SIMULATION',saved.source_status,'',previewValue.observations,'UNAVAILABLE','UNAVAILABLE']);return rows.map(r=>r.map(cell).join(',')).join('\r\n')+'\r\n';}
return {esc,copy,stable,equal,text,id,hash,number,milliseconds,ref,key,entry,libraries,find,selected,imageURL,thumbnail,variantData,newShots,editableShots,collectShots,sha,shotTiming,shotData,shotRow,move,input,select,choices,variantFields,shuffle,preview,feedHTML,exported,report,csv};
});
