/* App-sales input and result models. The server owns validation and evidence. */
(function(root,factory){const value=factory();if(typeof module==='object'&&module.exports)module.exports=value;else root.WMMFunnelModel=value;})(globalThis,function(){
 'use strict';
 const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const human=v=>String(v??'Unavailable').replaceAll('_',' ').toLowerCase();
 const copy=v=>JSON.parse(JSON.stringify(v));
 const button=(label,mode,id='',extra='')=>`<button type="button" class="button outline" data-action="funnel-${mode}" data-id="${esc(id)}" ${extra}>${esc(label)}</button>`;
 function input(name,label,value='',type='text',required=true){
  const id='funnel-'+name,attrs=`id="${esc(id)}" name="${esc(name)}" ${required?'required':''}`;
  const control=type==='textarea'?`<textarea ${attrs} rows="3">${esc(value)}</textarea>`:`<input ${attrs} type="${esc(type)}" value="${esc(value)}" ${type==='number'?'min="0" step="1"':''}>`;
  return `<label class="field" for="${esc(id)}">${esc(label)}${control}</label>`;
 }
 function select(name,label,choices,value='',multiple=false){
  return `<label class="field" for="funnel-${esc(name)}">${esc(label)}<select id="funnel-${esc(name)}" name="${esc(name)}" ${multiple?'multiple size="3"':''}>${choices.map(([id,text])=>`<option value="${esc(id)}"${id===value?' selected':''}>${esc(text)}</option>`).join('')}</select></label>`;
 }
 function sources(state,contract){
  const app=state.workspace.app,match=c=>['release','locale','currency'].every(k=>c[k]===app.data[k]);
  return {app:app.id,version:app.version,principal:state.workspace.identity?.principal||null,
   facts:copy({release:app.data.release,locale:app.data.locale,currency:app.data.currency,audience:app.data.audience||'',activation:app.data.activation||''}),
   cohorts:(state.workspace.ledger||[]).map(r=>r.cohort).filter(match).map(copy),
   creatives:(state.workspace.briefs||[]).filter(r=>r.evidence_status==='CURRENT').map(r=>({kind:'CREATIVE_BRIEF',id:r.id,version:r.current.version,sha256:r.current.hash})),
   research:(state.workspace.subscription_growth?.customer_workflows?.history||[]).filter(r=>r.readout?.status==='HYPOTHESIS_READY_FOR_REVIEW').map(r=>({kind:'CUSTOMER_WORKFLOW',id:r.id,version:1,sha256:r.hash})),contract:copy(contract)};
 }
 function integer(value,name,min=0,max=1e12){
  if(!/^\d+$/.test(String(value)))throw new Error(name+' must be a whole number.');
  const result=Number(value);if(!Number.isSafeInteger(result)||result<min||result>max)throw new Error(name+' is outside its declared range.');return result;
 }
 function text(value,name){if(typeof value!=='string'||!value.trim())throw new Error('Enter '+name+'.');return value.trim();}
 function stamp(value){const date=new Date(value);if(!Number.isFinite(date.getTime()))throw new Error('Enter a valid ISO timestamp with timezone.');if(!/(Z|[+-]\d\d:\d\d)$/.test(value))throw new Error('Include a timezone in each timestamp.');return date.toISOString();}
 function chosen(ids,rows,name,minimum=0){
  if(ids.length<minimum||ids.length>20)throw new Error('Select '+minimum+' to20 '+name+'.');
  return ids.map(id=>{const value=rows.find(r=>r.id===id);if(!value)throw new Error('Reopen the form: selected '+name+' changed.');return copy(value);});
 }
 function graph(rows,contract){
  if(!rows.length||rows.length>32)throw new Error('Use one to32 stages.');const seen=new Set();
  return rows.map(row=>{
   if(row.id.length>60||!/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(row.id)||seen.has(row.id))throw new Error('Use distinct lowercase stage IDs with single hyphens.');
   if(!contract.stage_types.includes(row.type)||!contract.stage_units.includes(row.unit))throw new Error('Choose a declared stage type and unit.');
   if(row.parents.some(p=>!seen.has(p))||new Set(row.parents).size!==row.parents.length)throw new Error('Parents must be distinct earlier stage IDs.');
   seen.add(row.id);return {...row,label:text(row.label,'stage label'),denominator_definition:text(row.denominator_definition,'stage population')};
  });
 }
 function defaults(){
  const types=['VIDEO_VIEW','STORE_VISIT','INSTALL','ONBOARDING_COMPLETE','ACTIVATION','TRIAL_START','PURCHASE','RENEWAL'];
  return types.map((type,i)=>({id:type.toLowerCase().replaceAll('_','-'),type,label:human(type),parents:i?[types[i-1].toLowerCase().replaceAll('_','-')]:[],unit:i?'UNIQUE_SUBJECTS':'VIEWS',denominator_definition:i?'Attributed cohort users':'Eligible platform views'}));
 }
 function stageFields(row,index,contract){
  const prefix='stage-'+index+'-',f=(name,label,value,type='text')=>input(prefix+name,label,value,type,name!=='parents');
  return `<details data-funnel-stage><summary>Stage ${index+1}: ${esc(row.label)}</summary><div class="form-grid">${f('id','Stage ID',row.id)}${select(prefix+'type','Stage type',contract.stage_types.map(v=>[v,human(v)]),row.type)}${f('label','Stage label',row.label)}${f('parents','Parent IDs, comma-separated',row.parents.join(', '))}${select(prefix+'unit','Count unit',contract.stage_units.map(v=>[v,human(v)]),row.unit)}${f('denominator_definition','Eligible population definition',row.denominator_definition,'textarea')}</div><div class="button-row">${button('Move stage earlier','stage-up',String(index))}${button('Move stage later','stage-down',String(index))}${button('Remove stage','stage-remove',String(index))}</div></details>`;
 }
 function lines(value){return String(value||'').split(/\r?\n/).map(s=>s.trim()).filter(Boolean);}
 function plan(values,all,stages,snapshot,id){
  const cohort=snapshot.cohorts.find(c=>c.cohort_id===values.cohort_id);if(!cohort)throw new Error('Choose an existing matching cohort.');
  const facts=snapshot.facts,outcome={audience:text(values.audience,'audience'),pain:text(values.pain,'specific pain'),research_refs:chosen(all('research'),snapshot.research,'customer sources'),milestone:text(values.milestone,'first-value milestone'),metric:text(values.metric,'outcome metric'),target:integer(values.target,'Outcome target'),due_at:stamp(values.due_at)};
  const data={release:facts.release,locale:facts.locale,currency:facts.currency,cohort_id:cohort.cohort_id,outcome,creative_refs:chosen(all('creative'),snapshot.creatives,'creative sources',1),hook:text(values.hook,'hook'),cta:text(values.cta,'call to action'),destination:text(values.destination,'app destination'),route:values.route,
   stages:graph(stages,snapshot.contract),attribution:{method:text(values.method,'attribution method'),identity_scope:text(values.identity_scope,'identity scope'),starts_at:cohort.starts_at,ends_at:cohort.ends_at,conversion_window_seconds:integer(values.conversion_window_seconds,'Conversion window',1,31536000)},offer_boundary:{free_deliverables:lines(values.free_deliverables),paid_deliverables:lines(values.paid_deliverables)}};
  return {id,manifest_version:snapshot.version,data};
 }
 function observation(values,saved){
  const plan=saved.data.definition,stage=plan.stages.find(s=>s.id===values.stage_id);if(!stage)throw new Error('Select a saved funnel stage.');
  if(!['OBSERVED','PARTIAL','UNKNOWN'].includes(values.coverage))throw new Error('Choose the actual coverage state.');
  return {event_id:text(values.event_id,'stable source event ID'),stage_id:stage.id,source_ref:text(values.source_ref,'source reference'),source_sha256:text(values.source_sha256,'source SHA256'),cohort_id:plan.cohort_id,starts_at:stamp(values.starts_at),ends_at:stamp(values.ends_at),observed_at:stamp(values.observed_at),coverage:values.coverage,count:values.coverage==='UNKNOWN'?null:integer(values.count,'Observed count'),unit:stage.unit,denominator_definition:stage.denominator_definition,identity_scope:plan.attribution.identity_scope};
 }
 function importBody(saved,version,values,raw){
  const observations=raw===undefined?JSON.stringify([observation(values,saved)]):raw;
  const parsed=JSON.parse(observations);if(!Array.isArray(parsed)||!parsed.length||parsed.length>500)throw new Error('Import one to500 observations.');
  // Preserve raw batch JSON so duplicate keys reach the server's strict decoder.
  const body=`{"funnel_hash":${JSON.stringify(saved.hash)},"manifest_version":${version},"observations":${observations}}`;
  if(new TextEncoder().encode(body).length>1048576)throw new Error('Observation request exceeds1 MiB.');return body;
 }
 function equal(a,b){return canonical(a)===canonical(b);}
 function canonical(v){if(Array.isArray(v))return '['+v.map(canonical).join(',')+']';if(v&&typeof v==='object')return '{'+Object.keys(v).sort().map(k=>JSON.stringify(k)+':'+canonical(v[k])).join(',')+'}';return JSON.stringify(v);}
 function comparableObservation(actual,expected){
  const normalize=v=>({...v,...Object.fromEntries(['starts_at','ends_at','observed_at'].map(k=>[k,stamp(v[k])]))});return equal(normalize(actual),normalize(expected));
 }
 function comparablePlan(actual,expected){const normalize=p=>({...p,outcome:{...p.outcome,due_at:stamp(p.outcome.due_at)},attribution:{...p.attribution,starts_at:stamp(p.attribution.starts_at),ends_at:stamp(p.attribution.ends_at)}});return equal(normalize(actual),normalize(expected));}
 function valuesTable(rows,headings,cells){return `<div class="table-wrap"><table class="result-table"><thead><tr>${headings.map(h=>`<th scope="col">${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(r=>`<tr>${cells(r).map(v=>`<td>${esc(v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;}
 function stageCells(r){return [r.label,r.count??'Unknown',human(r.status),human(r.unit),r.denominator_definition,r.source_refs.join(', ')||'Not observed'];}
 function edgeCells(r){return [r.from_stage+' → '+r.to_stage,r.numerator??'Unknown',r.denominator??'Unknown',r.rate===null?'Withheld':(r.rate*100).toFixed(2)+'%',r.drop_off_count??'Unknown',human(r.status)];}
 function results(saved,report){
  const plan=saved.data.definition;
  return `<p><strong>${esc(plan.outcome.milestone)}</strong> · target ${esc(plan.outcome.target)} ${esc(plan.outcome.metric)}. This is your chosen target.</p><p>Cohort ${esc(report.cohort_id)} · ${esc(report.currency)} · observed ${esc(report.as_of)} · ${esc(human(report.source_status))}.</p><h3>What was observed at each stage</h3>${valuesTable(report.stages,['Stage','Count','Coverage','Unit','Eligible population','Source'],stageCells)}<h3>Where the supplied counts fall</h3><p>Ratios require complete counts with matching units and populations. Views do not identify people, and aggregate ratios do not prove individual transitions or causal growth.</p>${valuesTable(report.edges,['Transition','Numerator','Denominator','Ratio','Drop-off count','Interpretation'],edgeCells)}<h3>Your next evidence work</h3><ul>${report.findings.map(f=>`<li>${esc(f.stage_id||'Funnel')}: ${esc(human(f.code))}. ${esc(f.next_action)}</li>`).join('')||'<li>Every declared stage has a complete supplied observation. Review sources and app outcomes before drawing conclusions.</li>'}</ul><details><summary>Inspect existing subscription ledger and refund-adjusted economics</summary><pre>${esc(JSON.stringify(report.subscription_ledger,null,2))}</pre></details><details><summary>Inspect saved outcome, sources and app capabilities</summary><pre>${esc(JSON.stringify(plan,null,2))}</pre></details>`;
 }
 function exportData(saved,report){return {schema:'growth.app-sales-funnel-export.v1',definition:copy(saved),report:copy(report),scope:'Exact displayed local evidence. Targets are plans; supplied aggregate counts do not establish individual transitions or causal lift.'};}
 function printable(saved,report,pages,state){
  const base=pages.model(state),plan=saved.data.definition;
  return {...base,title:'App-sales funnel: '+saved.id,purpose:'Trace '+plan.outcome.milestone+' from creative through app outcomes.',next_step:report.findings[0]?.next_action||'Review source coverage and choose the next app-sales test.',loaded_at:report.as_of,filters:{funnel_id:saved.id,definition_hash:saved.hash,report_hash:report.source_hash,cohort_id:report.cohort_id,currency:report.currency,window_start:plan.attribution.starts_at,window_end:plan.attribution.ends_at},cohorts:[],metrics:report.stages.map(r=>({label:r.label+' / '+human(r.status),value:r.count,unit:r.unit,source:r.source_refs.join(', ')||'Missing stage observation'})),notes:[...report.stages.map(r=>r.label+': '+r.denominator_definition+'; '+human(r.status)),...report.edges.map(r=>edgeCells(r).join(' / ')),...report.findings.map(f=>(f.stage_id||'Funnel')+': '+f.next_action),'Outcome target: '+plan.outcome.target+' '+plan.outcome.metric+' by '+plan.outcome.due_at,report.scope,'Existing subscription ledger: '+JSON.stringify(report.subscription_ledger)]};
 }
 function csvCell(value){let s=String(value??'');if(/^[=+\-@\t\r]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';}
 function csv(saved,report){
  const headers=['kind','app_id','funnel_id','definition_hash','report_hash','cohort_id','currency','as_of','stage_or_edge','count_or_numerator','denominator','rate','coverage','unit','population','sources'];
  const base=[saved.app_id,saved.id,saved.hash,report.source_hash,report.cohort_id,report.currency,report.as_of];
  const stages=report.stages.map(r=>['stage',...base,r.id,r.count??'', '', '',r.status,r.unit,r.denominator_definition,r.source_refs.join('; ')]);
  const edges=report.edges.map(r=>['edge',...base,r.from_stage+' -> '+r.to_stage,r.numerator??'',r.denominator??'',r.rate??'',r.status,'','','']);
  return [headers,...stages,...edges].map(row=>row.map(csvCell).join(',')).join('\r\n')+'\r\n';
 }
 function findingList(value){return `<p>${value.shown} of ${value.total} findings shown${value.has_more?'; open the exact source report for the remaining findings':''}.</p><ul>${value.items.map(r=>`<li>${esc(r.stage_id||r.area||r.id||'Source')}: ${esc(human(r.code))}. ${esc(r.next_action)}</li>`).join('')}</ul>`;}
 function founderEntry(row){
  const counts=row.stage_coverage,summary=counts?Object.entries(counts).map(([state,total])=>total+' '+human(state)+' stages').join(' / '):'Stage counts unavailable';
  const comparisons=row.comparisons?`${row.comparisons.comparable} comparable aggregate ratios / ${row.comparisons.withheld} withheld`:'Comparisons unavailable';
  return `<section class="panel"><h3>${esc(row.id)}</h3><p>${esc(human(row.state))} · cohort ${esc(row.cohort_id||'Unavailable')} · currency ${esc(row.currency||'Unavailable')}.</p><p>${esc(summary)}. ${esc(comparisons)}.</p>${findingList(row.findings)}${button('Open exact stage report','detail',row.id)}<details><summary>Inspect source receipts and stage populations</summary><pre>${esc(JSON.stringify({definition_hash:row.definition_hash,report_hash:row.report_hash,stages:row.stages},null,2))}</pre></details></section>`;
 }
 function founderHTML(value){
  const c=value.coverage,base=value.subscription_review;
  return `<p>This page: ${esc(human(value.status))} · observed ${esc(value.observed_at)} · app setup ${esc(value.context.manifest_version)}.</p><p>This page covers ${c.evaluated} of ${c.total} saved funnels from offset ${c.offset}.</p><details><summary>Subscription growth: ${esc(human(base.status))} / ${base.findings.total} findings</summary><p>Observed ${esc(base.observed_at)}.</p>${findingList(base.findings)}</details><h3>Your app-sales next actions</h3>${value.findings.map(r=>`<p>${esc(r.next_action)}</p>`).join('')}${founderEntries(value).map(founderEntry).join('')||'<p>No saved app-sales plan is available yet. Create one with a current creative brief and matching cohort.</p>'}<details><summary>Review scope and comparison limits</summary><p>${esc(value.scope)}</p><p>${esc(human(value.change))}.</p></details><div class="button-row">${c.offset?button('Previous review page','review-page',String(Math.max(0,c.offset-5))):''}${c.next_offset===null?'':button('Next review page','review-page',String(c.next_offset))}${button('Reload founder review','review-page',String(c.offset))}${button('Create app-sales plan','new')}${button('Return to subscription review','review-close')}${button('Report / Save PDF','review-pdf')}${button('Download review JSON','review-json')}${button('Download review CSV','review-csv')}</div>`;
 }
 function founderEntries(value){const rank=r=>r.state==='UNAVAILABLE'?0:r.state!=='CURRENT'?1:r.findings.total?2:3;return [...value.funnels].sort((a,b)=>rank(a)-rank(b));}
 function founderNext(value){return value.findings[0]?.next_action||founderEntries(value)[0]?.findings.items[0]?.next_action||value.subscription_review.findings.items[0]?.next_action||'Inspect the exact source reports and choose the next app-sales test.';}
 function founderPrintable(value,pages,state){
  const base=pages.model(state),c=value.coverage;
  const metrics=founderEntries(value).flatMap(r=>r.stages?r.stages.map(s=>({label:r.id+' / '+s.label+' / '+human(s.status),value:s.count,unit:s.unit,source:r.report_hash})): [{label:r.id+' / unavailable stage evidence',value:null,unit:'unknown',source:'Unavailable source'}]);
  const issues=[...value.findings,...value.subscription_review.findings.items,...value.funnels.flatMap(r=>r.findings.items)];
  return {...base,title:'App-sales founder review',purpose:'Choose the next app-sales task from source-bound subscription and funnel evidence.',next_step:founderNext(value),loaded_at:value.observed_at,filters:{review_hash:value.source_hash,app_setup:value.context.manifest_version,offset:c.offset,displayed_funnels:c.evaluated,total_funnels:c.total,subscription_findings_shown:value.subscription_review.findings.shown,subscription_findings_total:value.subscription_review.findings.total},cohorts:[],metrics,notes:[...issues.map(r=>(r.stage_id||r.area||r.id||'Source')+': '+r.next_action),...value.funnels.map(r=>r.id+': cohort '+r.cohort_id+'; currency '+r.currency+'; findings '+r.findings.shown+' of '+r.findings.total),value.scope,'Prior-review comparison: '+value.change]};
 }
 function founderCSV(value){
  const headers=['app_id','review_hash','observed_at','manifest_version','page_offset','total_funnels','kind','funnel_id','cohort_id','currency','stage_or_area','count','status','unit','message','source_hash'];
  const common={app_id:value.app_id,review_hash:value.source_hash,observed_at:value.observed_at,manifest_version:value.context.manifest_version,page_offset:value.coverage.offset,total_funnels:value.coverage.total};
  const rows=founderEntries(value).flatMap(r=>r.stages?r.stages.map(s=>({kind:'stage',funnel_id:r.id,cohort_id:r.cohort_id,currency:r.currency,stage_or_area:s.id,count:s.count??'',status:s.status,unit:s.unit,message:s.denominator_definition,source_hash:r.report_hash})):[{kind:'unavailable',funnel_id:r.id,status:r.state,count:'',source_hash:''}]);
  const issues=[...value.findings,...value.subscription_review.findings.items,...value.funnels.flatMap(r=>r.findings.items.map(f=>({...f,funnel_id:r.id})))];
  rows.push(...issues.map(r=>({kind:'finding',funnel_id:r.funnel_id||'',stage_or_area:r.stage_id||r.area||r.id||'',status:r.code,message:r.next_action,source_hash:value.source_hash})));
  return [headers,...rows.map(r=>headers.map(k=>({...common,...r})[k]??''))].map(row=>row.map(csvCell).join(',')).join('\r\n')+'\r\n';
 }
 return {esc,human,copy,button,input,select,sources,integer,text,stamp,chosen,graph,defaults,stageFields,lines,plan,observation,importBody,canonical,equal,comparableObservation,comparablePlan,valuesTable,stageCells,edgeCells,results,exportData,printable,csvCell,csv,findingList,founderEntry,founderEntries,founderHTML,founderNext,founderPrintable,founderCSV};
});
