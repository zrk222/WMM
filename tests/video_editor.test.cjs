const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),loaded={exports:{}};
new Function('module',fs.readFileSync(path.join(__dirname,'../mission_control/static/video-editor.js'),'utf8'))(loaded);
const ui=loaded.exports;
const source={id:'a'.repeat(36),data:{artifact:{sha256:'b'.repeat(64),metadata:{duration_seconds:15}},request:{brief:{data:{app:{name:'Synthetic source'}}}}}};
const data=()=>ui.newData({title:'Synthetic edit',purpose:'Show a useful step'},source,'en-US','clip-one');
function project(){return {id:'project-one',revision:1,hash:'c'.repeat(64),source_status:'CURRENT',data:{definition:data()},timing:{total_frames:120},can_undo:false,can_redo:false,history:[{revision:1,action:'SAVE'}]};}
function fields(p){const d=p.data.definition,c=d.clips[0],v={title:d.title,purpose:d.purpose,output:d.output};for(const k of ['in_frame','out_frame','speed_percent','role'])v['c0.'+k]=String(c[k]);for(const k of ['rotation','flip_x','flip_y','fit','background'])v['c0.'+k]=String(c.transform[k]);for(const k of ['x','y','width','height'])v['c0.crop.'+k]=String(c.transform.crop[k]/100);for(const k of ['brightness','contrast','saturation'])v['c0.'+k]=String(c.effects[k]);return v;}
function fixture(){
 const node={open:true,querySelector:()=>error},error={textContent:''},state={app:'sample-one',workspace:{app:{version:2,data:{name:'Synthetic app',locale:'en-US'}}}},p=project();let html='',count=0;
 const deps={state,uuid:()=>`uuid-${++count}`,document:{querySelector:()=>node},modal:(title,value)=>{ui.clear();node.open=true;html=value;},api:async path=>path.endsWith('/native-renders')?{items:[{...source,status:'CURRENT'}]}:path.endsWith('/video-edit-renders')?{items:[]}:path.endsWith('/jobs')?[]:path.endsWith('/video-projects')?{items:[p]}:p,
  FormData:class{constructor(form){return Object.entries(form.values);}},toast:()=>{},pageReports:{model:()=>({})}};
 return {deps,node,error,p,html:()=>html};
}
test('human settings preserve exact source identities and typed crop/timing values',()=>{
 const p=project(),v=fields(p);v['c0.in_frame']='24';v['c0.out_frame']='96';v['c0.rotation']='90';v['c0.crop.width']='50.25';v['c0.flip_x']='true';v['c0.brightness']='25';
 const result=ui.edited(p,v);assert.equal(result.clips[0].in_frame,24);assert.equal(result.clips[0].transform.rotation,90);assert.equal(result.clips[0].transform.crop.width,5025);assert.equal(result.clips[0].transform.flip_x,true);assert.equal(result.clips[0].effects.brightness,25);assert.deepEqual(result.clips[0].source,p.data.definition.clips[0].source);assert.equal(p.data.definition.clips[0].in_frame,0);
 assert.throws(()=>ui.edited(p,{...v,'c0.in_frame':''}));assert.throws(()=>ui.edited(p,{...v,'c0.in_frame':'Infinity'}));
});
test('clip controls escape source identifiers and expose commands and current profile honestly',()=>{
 const c=data().clips[0];c.id='<img src=x onerror=alert(1)>';
 const html=ui.clipMarkup(c,0,1);assert.ok(!html.includes('<img'));for(const name of ['Move earlier','Move later','Duplicate clip','Delete clip','Split clip','Framing, crop and color','Source start frame'])assert.ok(html.includes(name));assert.ok(html.includes('disabled'));
 const panel=ui.panel();assert.ok(panel.includes('Uploaded clips can retain or mute'));assert.ok(panel.includes('whole source frame'));assert.ok(!panel.includes('fully complete'));
});
test('reports project observed metrics without unrelated secrets or raw operation payloads',()=>{
 const p=project();p.data.secret_profile={api_key:'PRIVATE_KEY_SENTINEL'};
 const report=ui.report({project:p,renders:[]},{view:'research'},{model:()=>({})});const text=JSON.stringify(report);
 assert.ok(!text.includes('PRIVATE_KEY_SENTINEL'));assert.equal(report.metrics[0].value,1);assert.equal(report.metrics[1].value,5);assert.ok(text.includes('machine cost is not measured'));assert.ok(text.includes('publication and business outcomes are not established'));
});
test('pending duplicate submits write once and closed dialogs discard late readbacks',async()=>{
 const f=fixture();await ui.open(f.deps);await ui.action({dataset:{action:'veditor-create'}},f.deps);
 let resolve,calls=0;const firstApi=f.deps.api;
 f.deps.api=(path,body)=>{if(body){calls++;return new Promise(r=>resolve=r);}return firstApi(path);};
 const submit={disabled:false},form={values:{title:'Private title',purpose:'Useful narrow purpose',source_id:source.id},querySelector:()=>submit};
 const pending=ui.submit(form,f.deps),duplicate=ui.submit(form,f.deps);assert.equal(calls,1);assert.equal(submit.disabled,true);
 const before=f.html();ui.clear();f.node.open=false;resolve({id:'project-one'});await Promise.all([pending,duplicate]);assert.equal(f.html(),before);assert.equal(submit.disabled,false);
});
test('failed save retains fields and a changed app discards an in-flight library response',async()=>{
 const f=fixture();await ui.open(f.deps);await ui.action({dataset:{action:'veditor-create'}},f.deps);f.deps.api=async()=>{throw new Error('Source changed');};
 const form={values:{title:'Retain this title',purpose:'Retain this purpose',source_id:source.id},querySelector:()=>({disabled:false})};
 const html=f.html();await ui.submit(form,f.deps);assert.equal(f.html(),html);assert.ok(f.error.textContent.includes('fields are retained'));
 const g=fixture(),releases=[];g.deps.api=()=>new Promise(r=>releases.push(r));const pending=ui.open(g.deps);g.deps.state.app='sample-two';ui.invalidate(g.deps.state);const before=g.html();
 releases.forEach((release,i)=>release(i===3?[]:{items:[]}));await pending;assert.equal(g.html(),before);ui.clear();
});
test('unsaved fields block rendering and results navigation before any server call',async()=>{
 const f=fixture();await ui.open(f.deps);await ui.action({dataset:{action:'veditor-project',id:f.p.id}},f.deps);
 const v=fields(f.p);v.title='Unsaved title';const form={values:v};
 f.node.querySelector=selector=>selector==='#video-project-edit-form'?form:f.error;
 let calls=0;f.deps.api=async()=>{calls++;return {};};
 await ui.action({dataset:{action:'veditor-render'}},f.deps);assert.equal(calls,0);assert.ok(f.error.textContent.includes('Save your current field edits first'));
 await ui.action({dataset:{action:'veditor-outputs'}},f.deps);assert.equal(calls,0);assert.equal(v.title,'Unsaved title');ui.clear();
});

test('managed source selection retains kind, digest and explicit sound controls',()=>{
 const managed={id:source.id,kind:'MANAGED',data:{artifact:{sha256:'d'.repeat(64),metadata:{duration_seconds:2}}}};
 const d=ui.newData({title:'UGC edit',purpose:'One useful demonstration'},managed,'en-US','ugc-one');
 assert.deepEqual(d.clips[0].source,{kind:'MANAGED',id:source.id,sha256:'d'.repeat(64)});
 assert.equal(d.clips[0].audio,'RETAIN');
 const p={data:{definition:d}},v=fields(p);v['c0.audio']='MUTE';
 assert.equal(ui.edited(p,v).clips[0].audio,'MUTE');
 assert.match(ui.clipMarkup(d.clips[0],0,1),/Retain source sound/);
 assert.match(ui.clipMarkup(d.clips[0],0,1),/normalized to 24/);
});
