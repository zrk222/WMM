/** Source-bound browser adapter. SDK acceptance is never a delivery receipt. */
export class TrackingError extends Error {
  constructor(code) {super(code);this.name="TrackingError";this.code=code;}
}
const fail=code=>{throw new TrackingError(code);};
const ARMS=["control","treatment"];

/** Reject incomplete, ambiguous or unsafe integration configuration. */
export function validateConfig(config) {
  const fields=["schema","app_id","release","locale","experiment_id","experiment_hash","flag_key","starts_at","ends_at","origin"];
  if(!config||Object.keys(config).sort().join()!==fields.sort().join())fail("CONFIG_INVALID");
  if(config.schema!=="growth.browser-instrumentation.v1")fail("CONFIG_INVALID");
  validateScope(config);validateExperiment(config);
  const start=instant(config.starts_at),end=instant(config.ends_at);
  if(start>=end)fail("CONFIG_INVALID");
  validateOrigin(config.origin);
  return Object.freeze({...config});
}

function validateScope(config) {
  for(const name of ["app_id","release","locale"])
    if(typeof config[name]!=="string"||!config[name]||config[name].length>200)fail("CONFIG_INVALID");
}

function validateExperiment(config) {
  if(!/^[a-f0-9-]{36}$/.test(config.experiment_id)||!/^[a-f0-9]{64}$/.test(config.experiment_hash))fail("CONFIG_INVALID");
  if(config.flag_key!=="wmm-"+config.experiment_id)fail("CONFIG_INVALID");
}

function validateOrigin(value) {
  try {const url=new URL(value);if(url.origin===value&&url.protocol==="https:")return;}catch {}
  fail("CONFIG_INVALID");
}

/** Require absolute instants; do not admit locale-dependent dates or early fractional starts. */
function instant(value,roundStart=false) {
  if(typeof value!=="string"||!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{1,6})?(Z|[+-]\d{2}:\d{2})$/.test(value))fail("CONFIG_INVALID");
  const result=Date.parse(value);if(!Number.isFinite(result))fail("CONFIG_INVALID");
  const fraction=value.match(/\.(\d+)/)?.[1]||"";
  return result+(roundStart&&/[1-9]/.test(fraction.slice(3))?1:0);
}

/** Use one IndexedDB write transaction so separate tabs cannot choose different arms. */
export class IndexedState {
  constructor(indexedDB=globalThis.indexedDB) {this.indexedDB=indexedDB;}
  open() {
    if(!this.indexedDB)fail("STORAGE_REQUIRED");
    return new Promise((resolve,reject)=>{
      let blocked=false;
      const request=this.indexedDB.open("wmm-experiment-state-v1",1);
      request.onupgradeneeded=()=>request.result.createObjectStore("assignments");
      request.onerror=()=>reject(new TrackingError("STORAGE_REQUIRED"));
      request.onblocked=()=>{blocked=true;reject(new TrackingError("STORAGE_REQUIRED"));};
      request.onsuccess=()=>{if(blocked)request.result.close();else resolve(request.result);};
    });
  }
  async change(key,update) {
    const db=await this.open();
    return new Promise((resolve,reject)=>{
      const tx=db.transaction("assignments","readwrite"),store=tx.objectStore("assignments");let value,error;
      const request=store.get(key);
      request.onsuccess=()=>{try {value=update(request.result??null);store.put(value,key);}catch(cause){error=cause;tx.abort();}};
      tx.oncomplete=()=>{db.close();resolve(value);};
      tx.onabort=tx.onerror=()=>{db.close();reject(error||new TrackingError("STORAGE_REQUIRED"));};
    });
  }
}

/** Check documented prerequisites; never initialize identity, consent or provider keys. */
function prerequisites(client) {
  for(const name of ["getFeatureFlagResult","onFeatureFlags","reloadFeatureFlags","setPersonPropertiesForFlags","get_distinct_id","has_opted_out_capturing","capture"])
    if(typeof client?.[name]!=="function")fail("SDK_PREREQUISITES_REQUIRED");
  const config=client.config;
  if(config?.person_profiles!=="always"||config.advanced_disable_feature_flags||Object.keys(config.bootstrap||{}).length)
    fail("SDK_PREREQUISITES_REQUIRED");
}

/** Wait for remote flags after installing exact scope properties; stale disk flags are excluded. */
function freshFlag(client,config) {
  return new Promise((resolve,reject)=>{
    let armed=false,unsubscribe;const timer=setTimeout(()=>finish(new TrackingError("FLAG_READ_TIMEOUT")),10000);
    function finish(error,value) {clearTimeout(timer);if(unsubscribe)unsubscribe();error?reject(error):resolve(value);}
    try {
      unsubscribe=client.onFeatureFlags((_flags,_variants,details)=>{
        if(!armed)return;
        try {
          if(details?.errorsLoading)return finish(new TrackingError("FLAG_READ_FAILED"));
          const result=client.getFeatureFlagResult(config.flag_key,{send_event:false,fresh:true});
          if(!result?.enabled||!ARMS.includes(result.variant))return finish(new TrackingError("FLAG_UNAVAILABLE"));
          finish(null,result.variant);
        } catch {finish(new TrackingError("FLAG_READ_FAILED"));}
      });
      if(typeof unsubscribe!=="function")return finish(new TrackingError("SDK_PREREQUISITES_REQUIRED"));
      client.setPersonPropertiesForFlags({wmm_app_id:config.app_id,wmm_release:config.release,wmm_locale:config.locale},false);
      armed=true;client.reloadFeatureFlags();
    } catch {finish(new TrackingError("FLAG_READ_FAILED"));}
  });
}

/** Read only the current consented app identity and declared acquisition window. */
function context(config,client,env) {
  if(env.consent()!==true||client.has_opted_out_capturing())fail("CONSENT_REQUIRED");
  const value=env.context(),now=env.now();
  if(env.origin!==config.origin)fail("ORIGIN_CHANGED");
  if(!Number.isFinite(now)||now<instant(config.starts_at,true)||now>=instant(config.ends_at))fail("WINDOW_CLOSED");
  if(!value||value.identified!==true||typeof value.id!=="string"||!value.id||value.id.length>200)fail("IDENTITY_REQUIRED");
  if(client.get_distinct_id()!==value.id)fail("IDENTITY_CHANGED");
  for(const name of ["app_id","release","locale"])if(value[name]!==config[name])fail("APP_SCOPE_CHANGED");
  return value.id;
}

/** Hash the identity namespace locally; custom event properties never include it. */
async function namespace(config,identity,crypto) {
  const data=new TextEncoder().encode(JSON.stringify([config.app_id,config.experiment_hash,identity]));
  const bytes=new Uint8Array(await crypto.subtle.digest("SHA-256",data));
  return Array.from(bytes,b=>b.toString(16).padStart(2,"0")).join("");
}

/** A saved participant never silently changes arms when remote configuration changes. */
function assignment(row,arm,crypto) {
  if(row)validateSaved(row);
  if(row&&row.arm!==arm)fail("ASSIGNMENT_CHANGED");
  return row||{arm,assignment_uuid:crypto.randomUUID(),exposure_uuid:crypto.randomUUID(),assignment_queued:false,exposure_queued:false};
}

/** A damaged local receipt must not produce a fresh implicit identity or event UUID. */
function validateSaved(row) {
  const keys=["arm","assignment_uuid","exposure_uuid","assignment_queued","exposure_queued"];
  if(Object.keys(row).sort().join()!==keys.sort().join())fail("STORAGE_INTEGRITY_REQUIRED");
  const uuid=/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/;
  for(const kind of ["assignment","exposure"])
    if(!uuid.test(row[kind+"_uuid"])||typeof row[kind+"_queued"]!=="boolean")fail("STORAGE_INTEGRITY_REQUIRED");
}

/** DOM visibility is an app-side signal, not proof that a human saw the content. */
function visible(element,env) {
  if(!element?.isConnected||typeof element.checkVisibility!=="function")fail("VISIBLE_ELEMENT_REQUIRED");
  const rect=element.getBoundingClientRect();
  if(env.document.visibilityState!=="visible"||!element.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}))fail("ELEMENT_NOT_VISIBLE");
  if(rect.width<=0||rect.height<=0||rect.bottom<=0||rect.right<=0||rect.top>=env.height()||rect.left>=env.width())fail("ELEMENT_NOT_VISIBLE");
}

/** Emit only the exact event contract with the persisted UUID on every safe retry. */
function capture(config,client,row,kind) {
  const event="wmm_experiment_"+kind;
  const value=client.capture(event,{wmm_app_id:config.app_id,wmm_release:config.release,wmm_locale:config.locale,
    wmm_experiment_hash:config.experiment_hash,wmm_variant:row.arm},{uuid:row[kind+"_uuid"]});
  if(!value)fail("CAPTURE_UNCONFIRMED");
}

/** Guard async boundaries and let the host app explicitly report the rendered variant. */
export function createTracker(input,client,environment={}) {
  const config=validateConfig(input);prerequisites(client);
  const env={now:()=>Date.now(),origin:globalThis.location?.origin,crypto:globalThis.crypto,
    document:globalThis.document,width:()=>globalThis.innerWidth,height:()=>globalThis.innerHeight,...environment};
  if(typeof env.consent!=="function"||typeof env.context!=="function"||!env.crypto?.subtle||!env.crypto?.randomUUID)
    fail("SDK_PREREQUISITES_REQUIRED");
  const state=env.state||new IndexedState();let stopped=false,serial=Promise.resolve();
  function guard(identity) {if(stopped)fail("STOPPED");prerequisites(client);const current=context(config,client,env);if(identity&&identity!==current)fail("IDENTITY_CHANGED");return current;}
  async function perform(kind,element,renderedArm) {
    const identity=guard();const arm=await freshFlag(client,config);guard(identity);
    if(kind==="exposure") {visible(element,env);if(renderedArm!==arm)fail("RENDERED_VARIANT_CHANGED");}
    const key=await namespace(config,identity,env.crypto);guard(identity);
    const row=await state.change(key,old=>{
      guard(identity);
      if(kind==="exposure"&&!old?.assignment_queued)fail("ASSIGNMENT_REQUIRED");
      return assignment(old,arm,env.crypto);
    });
    guard(identity);if(kind==="exposure")visible(element,env);
    if(row[kind+"_queued"])return {status:"ALREADY_QUEUED_NOT_DELIVERED",variant:arm};
    capture(config,client,row,kind);guard(identity);
    await state.change(key,current=>{guard(identity);const saved=assignment(current,arm,env.crypto);return {...saved,[kind+"_queued"]:true};});
    return {status:"QUEUED_NOT_DELIVERED",variant:arm};
  }
  function run(kind,element,arm) {const next=serial.then(()=>perform(kind,element,arm));serial=next.catch(()=>{});return next;}
  return Object.freeze({assign:()=>run("assignment"),expose:(element,arm)=>run("exposure",element,arm),stop:()=>{stopped=true;}});
}
