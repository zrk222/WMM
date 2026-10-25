import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const __dirname=path.dirname(fileURLToPath(import.meta.url));

function fixture() {
  const listeners={},calls=[],error={textContent:''};let markup='';
  const request={brief_id:'brief',brief_hash:'hash',shape:'PORTRAIT',duration_seconds:30,captions:['Exact <approved> text']};
  const native={id:'native',status:'CURRENT',data:{renderer:'NATIVE_FFMPEG',request,artifact:{bytes:100}}};
  const hypit={id:'hypit',status:'CURRENT',data:{renderer:'HYPIT_LOCAL',inputs:{request},artifact:{bytes:200}}};
  const esc=value=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
  const context={state:{app:'sample-one',workspace:{jobs:[],renders:{capability:{status:'READY'},items:[native]},hypit_renders:{capability:{status:'DETECTED'},items:[hypit]},briefs:[{id:'brief',evidence_status:'CURRENT',current:{hash:'hash',data:{definition:{channel:'SHORT_VIDEO',duration_seconds:30,objective:'Synthetic'}}}}]}},
    document:{addEventListener:(name,fn)=>listeners[name]=fn},crypto:{randomUUID:()=> 'retry-key'},
    esc,label:value=>value,status:value=>esc(value),notice:value=>`<p>${esc(value)}</p>`,button:(title,action,extra='')=>`<button data-action="${action}" ${extra}>${esc(title)}</button>`,
    choiceField:(name,options)=>`<label>${name}<select name="${name}">${options.map(o=>`<option value="${o.id}">${esc(o.title)}</option>`).join('')}</select></label>`,
    modal:(title,html)=>{markup=html;},json:JSON.stringify,toast:()=>{},refresh:async()=>{},download:()=>{},
    $:selector=>selector==='#form-error'?error:selector==='#modal video'?{addEventListener:()=>{}}:{close:()=>{}},
    api:async(url,body)=>calls.push({url,body}),FormData:class {constructor(form){return form.values;}}};
  vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(__dirname,'../mission_control/static/creative-rendering.js'),'utf8'),context);
  return {context,listeners,calls,error,request,markup:()=>markup};
}

test('both saved renderer types appear without modifying their stored envelopes',()=>{
  const f=fixture(),before=JSON.stringify(f.context.state.workspace);
  assert.equal(f.context.renderRows().length,2);
  assert.equal(f.context.briefRenderState({id:'brief',current:{hash:'hash'}}),'RENDERED_LOCAL');
  assert.match(f.context.renderingPanel(),/Hypit caption composition/);
  assert.match(f.context.renderingPanel(),/does not include app screens/);
  assert.equal(JSON.stringify(f.context.state.workspace),before);
  assert.throws(()=>f.context.renderEndpoint('../unsafe'),/supported/);
});

test('renderer form and preview choose exact routes with escaped approved captions',()=>{
  const f=fixture();f.context.renderForm();
  assert.match(f.markup(),/name="renderer"/);assert.match(f.markup(),/value="HYPIT_LOCAL"/);
  f.context.openRender('hypit');assert.match(f.markup(),/hypit-renders\/hypit\/preview/);
  assert.match(f.markup(),/Exact &lt;approved&gt; text/);
  f.context.openRender('native');assert.match(f.markup(),/\/renders\/native\/preview/);
});

test('submission preserves brief proof and retry identity and blocks stale app forms',async()=>{
  const f=fixture(),submit={disabled:false};
  const form={id:'render-form',dataset:{app:'sample-one',key:'fixed-retry'},querySelector:()=>submit,values:[['renderer','HYPIT_LOCAL'],['brief_id','brief'],['shape','PORTRAIT']]};
  await f.listeners.submit({target:form,preventDefault(){}});
  assert.equal(f.calls[0].url,'/api/apps/sample-one/production/hypit-renders');
  assert.equal(f.calls[0].body.request_key,'fixed-retry');
  assert.equal(f.calls[0].body.data.brief_hash,'hash');assert.equal(f.calls[0].body.data.renderer,undefined);
  form.dataset.app='sample-two';await f.listeners.submit({target:form,preventDefault(){}});
  assert.equal(f.calls.length,1);assert.match(f.error.textContent,/App changed/);assert.equal(submit.disabled,false);
});
