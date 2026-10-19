import test from "node:test";
import assert from "node:assert/strict";
import {webcrypto} from "node:crypto";
import {createTracker,validateConfig} from "../mission_control/sdk/experiment-client.mjs";

const CONFIG={schema:"growth.browser-instrumentation.v1",app_id:"sample-one",release:"build-1",locale:"en-US",
  experiment_id:"c7952e67-b1d5-4934-a220-cf32c8c48cf5",experiment_hash:"a".repeat(64),
  flag_key:"wmm-c7952e67-b1d5-4934-a220-cf32c8c48cf5",starts_at:"2026-10-01T00:00:00Z",ends_at:"2026-11-01T00:00:00Z",origin:"https://example.com"};

class State {
  rows=new Map();serial=Promise.resolve();
  change(key,fn) {
    const next=this.serial.then(()=>{const row=fn(structuredClone(this.rows.get(key)));this.rows.set(key,structuredClone(row));return row;});
    this.serial=next.catch(()=>{});return next;
  }
}

function fixture() {
  const events=[],callbacks=new Set(),state=new State();
  const context={app_id:"sample-one",release:"build-1",locale:"en-US",id:"synthetic-opaque-user",identified:true};
  const controls={consent:true,optedOut:false,variant:"control",enabled:true,accepted:true,errors:false};
  let reloads=0,properties=null,options=null;
  const client={config:{person_profiles:"always"},get_distinct_id:()=>context.id,has_opted_out_capturing:()=>controls.optedOut,
    setPersonPropertiesForFlags:p=>{properties=p;},
    onFeatureFlags:fn=>{callbacks.add(fn);fn([],{},{});return()=>callbacks.delete(fn);},
    reloadFeatureFlags:()=>{reloads++;queueMicrotask(()=>{for(const fn of [...callbacks])fn([],{}, {errorsLoading:controls.errors});});},
    getFeatureFlagResult:(_key,opts)=>{options=opts;return {enabled:controls.enabled,variant:controls.variant};},
    capture:(event,props,opts)=>{events.push({event,props,opts});return controls.accepted?{}:undefined;}};
  const env={consent:()=>controls.consent,context:()=>context,now:()=>Date.parse("2026-10-18T00:00:00Z"),
    crypto:webcrypto,origin:"https://example.com",document:{visibilityState:"visible"},width:()=>390,height:()=>844,state};
  const element={isConnected:true,checkVisibility:()=>true,getBoundingClientRect:()=>({width:100,height:50,top:10,bottom:60,left:10,right:110})};
  return {client,env,element,events,controls,context,state,callbacks,counts:()=>({reloads,properties,options}),tracker:()=>createTracker(CONFIG,client,env)};
}

const rejects=(promise,code)=>assert.rejects(promise,error=>error.code===code);

test("validateConfig rejects extra inputs, wrong flag and invalid window",()=>{
  assert.equal(validateConfig(CONFIG).app_id,"sample-one");
  for(const change of [{secret:"no"},{flag_key:"other"},{ends_at:CONFIG.starts_at},{origin:"https://example.com/path"}])
    assert.throws(()=>validateConfig({...CONFIG,...change}),error=>error.code==="CONFIG_INVALID");
});

test("requires SDK prerequisites and consent before evaluating or capturing",async()=>{
  const f=fixture();f.client.config.bootstrap={featureFlags:{}};
  assert.throws(f.tracker,error=>error.code==="SDK_PREREQUISITES_REQUIRED");
  f.client.config.bootstrap={};const tracker=f.tracker();f.controls.consent=false;
  await rejects(tracker.assign(),"CONSENT_REQUIRED");assert.equal(f.counts().reloads,0);assert.equal(f.events.length,0);
});

test("fresh remote assignment and visible exposure retain exact scope and distinct event UUIDs",async()=>{
  const f=fixture(),tracker=f.tracker();assert.equal((await tracker.assign()).status,"QUEUED_NOT_DELIVERED");
  assert.equal((await tracker.expose(f.element,"control")).status,"QUEUED_NOT_DELIVERED");
  assert.deepEqual(f.counts().options,{send_event:false,fresh:true});assert.equal(f.events.length,2);
  assert.equal(f.events[1].props.wmm_experiment_hash,CONFIG.experiment_hash);
  assert.equal(f.events[1].props.wmm_locale,"en-US");assert.notEqual(f.events[0].opts.uuid,f.events[1].opts.uuid);
  assert.equal(f.callbacks.size,0);
  assert(!JSON.stringify(f.events.map(e=>e.props)).includes(f.context.id));
  assert(!JSON.stringify([...f.state.rows]).includes(f.context.id));
});

test("repeat and reopened trackers preserve assignment and do not requeue accepted events",async()=>{
  const f=fixture();await f.tracker().assign();await f.tracker().expose(f.element,"control");
  assert.equal((await f.tracker().assign()).status,"ALREADY_QUEUED_NOT_DELIVERED");
  assert.equal((await f.tracker().expose(f.element,"control")).status,"ALREADY_QUEUED_NOT_DELIVERED");assert.equal(f.events.length,2);
});

test("same-origin concurrent clients retain one event UUID per kind",async()=>{
  const f=fixture();await Promise.all([f.tracker().assign(),f.tracker().assign()]);
  assert.equal(new Set(f.events.map(e=>e.opts.uuid)).size,1);
  assert.equal(f.state.rows.size,1);
});

test("capture rejection retries the same persisted UUID without claiming delivery",async()=>{
  const f=fixture(),tracker=f.tracker();f.controls.accepted=false;
  await rejects(tracker.assign(),"CAPTURE_UNCONFIRMED");f.controls.accepted=true;
  assert.equal((await tracker.assign()).status,"QUEUED_NOT_DELIVERED");assert.equal(f.events[0].opts.uuid,f.events[1].opts.uuid);
});

test("disabled fresh flags and changed variants never reuse the cached assignment",async()=>{
  const f=fixture(),tracker=f.tracker();await tracker.assign();f.controls.enabled=false;
  await rejects(tracker.assign(),"FLAG_UNAVAILABLE");f.controls.enabled=true;f.controls.variant="treatment";
  await rejects(tracker.assign(),"ASSIGNMENT_CHANGED");assert.equal(f.events.length,1);
});

test("exposure requires prior accepted assignment and the actual rendered variant",async()=>{
  const f=fixture(),tracker=f.tracker();await rejects(tracker.expose(f.element,"control"),"ASSIGNMENT_REQUIRED");
  await tracker.assign();await rejects(tracker.expose(f.element,"treatment"),"RENDERED_VARIANT_CHANGED");
  f.element.isConnected=false;await rejects(tracker.expose(f.element,"control"),"VISIBLE_ELEMENT_REQUIRED");assert.equal(f.events.length,1);
});

test("hidden documents, hidden elements and offscreen elements do not emit exposure",async()=>{
  const f=fixture(),tracker=f.tracker();await tracker.assign();f.env.document.visibilityState="hidden";
  await rejects(tracker.expose(f.element,"control"),"ELEMENT_NOT_VISIBLE");f.env.document.visibilityState="visible";
  f.element.checkVisibility=()=>false;await rejects(tracker.expose(f.element,"control"),"ELEMENT_NOT_VISIBLE");
  f.element.checkVisibility=()=>true;f.element.getBoundingClientRect=()=>({width:10,height:10,top:900,bottom:910,left:0,right:10});
  await rejects(tracker.expose(f.element,"control"),"ELEMENT_NOT_VISIBLE");assert.equal(f.events.length,1);
});

test("identity, app, origin and window changes block queued events",async()=>{
  const f=fixture(),tracker=f.tracker();await tracker.assign();f.client.get_distinct_id=()=>"another";
  await rejects(tracker.assign(),"IDENTITY_CHANGED");f.client.get_distinct_id=()=>f.context.id;f.context.release="other";
  await rejects(tracker.assign(),"APP_SCOPE_CHANGED");f.context.release="build-1";f.env.origin="https://other.example";
  await rejects(f.tracker().assign(),"ORIGIN_CHANGED");f.env.origin="https://example.com";f.env.now=()=>Date.parse(CONFIG.ends_at);
  await rejects(f.tracker().assign(),"WINDOW_CLOSED");assert.equal(f.events.length,1);
});

test("async consent withdrawal and stop prevent capture after remote flags finish",async()=>{
  const f=fixture(),tracker=f.tracker();f.client.reloadFeatureFlags=()=>{f.controls.consent=false;for(const cb of [...f.callbacks])cb([],{},{});};
  await rejects(tracker.assign(),"CONSENT_REQUIRED");assert.equal(f.events.length,0);
  f.controls.consent=true;tracker.stop();await rejects(tracker.assign(),"STOPPED");assert.equal(f.events.length,0);
});

test("provider loading error and corrupt local receipts expose typed recovery",async()=>{
  const f=fixture(),tracker=f.tracker();f.controls.errors=true;
  await rejects(tracker.assign(),"FLAG_READ_FAILED");f.controls.errors=false;await tracker.assign();
  const key=[...f.state.rows.keys()][0];f.state.rows.get(key).assignment_uuid="invalid";
  await rejects(tracker.assign(),"STORAGE_INTEGRITY_REQUIRED");assert.equal(f.events.length,1);
});

test("changed SDK prerequisites and fractional acquisition boundaries fail closed",async()=>{
  const f=fixture(),tracker=f.tracker();f.client.config.person_profiles="never";
  await rejects(tracker.assign(),"SDK_PREREQUISITES_REQUIRED");assert.equal(f.counts().reloads,0);
  f.client.config.person_profiles="always";f.env.now=()=>Date.parse("2026-10-18T00:00:00.000Z");
  const fractional=createTracker({...CONFIG,starts_at:"2026-10-18T00:00:00.000001Z"},f.client,f.env);
  await rejects(fractional.assign(),"WINDOW_CLOSED");assert.equal(f.events.length,0);
  f.env.now=()=>NaN;await rejects(f.tracker().assign(),"WINDOW_CLOSED");
  assert.throws(()=>validateConfig({...CONFIG,origin:"invalid"}),error=>error.code==="CONFIG_INVALID");
});
