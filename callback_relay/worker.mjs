// Stateless code handoff only. Mission Control itself must remain private.
const providers = new Set(['facebook','instagram','tiktok','youtube','linkedin']);
const printable = (value,min,max) => typeof value==='string' && value.length>=min && value.length<=max && /^[!-~]+$/.test(value);
const googleMetadata = new Set(['scope','authuser','prompt','hd']);
function validGoogleMetadata(key,value) {
  if(value.length>4096||!/^[\x20-\x7e]*$/.test(value))return false;
  if(key==='authuser')return /^\d{1,12}$/.test(value);
  if(key==='prompt')return /^(?:none|consent|select_account)(?: (?:consent|select_account))*$/.test(value);
  if(key==='hd')return /^[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$/.test(value);
  return key==='scope'&&value.length>0;
}
const headers = {'Cache-Control':'no-store','Referrer-Policy':'no-referrer','Content-Security-Policy':"default-src 'none'; frame-ancestors 'none'; base-uri 'none'",'X-Content-Type-Options':'nosniff'};

export function handoff(request) {
  const url=new URL(request.url),parts=url.pathname.split('/');
  if(request.method!=='GET'||url.protocol!=='https:'||url.hash||url.username||url.password||url.port||parts.length!==3||parts[1]!=='cb'||!providers.has(parts[2]))return new Response('Invalid callback',{status:400,headers});
  const entries=[...url.searchParams];
  if(entries.length>8||new Set(entries.map(([key])=>key)).size!==entries.length)return new Response('Invalid callback',{status:400,headers});
  const allowed=new Set(['state','code','error','error_description','error_reason','error_code']);
  if(entries.some(([key,value])=>{
    if(allowed.has(key))return value.length>4096;
    return parts[2]!=='youtube'||!googleMetadata.has(key)||!validGoogleMetadata(key,value);
  }))return new Response('Invalid callback',{status:400,headers});
  const state=url.searchParams.get('state'),code=url.searchParams.get('code'),error=url.searchParams.get('error');
  if(!printable(state,43,128)||Boolean(code)===Boolean(error)||code&&!printable(code,1,4096)||error&&!printable(error,1,100))return new Response('Invalid callback',{status:400,headers});
  const target=new URL('http://127.0.0.1:8765/social/callback/'+parts[2]);
  target.hash=new URLSearchParams({state,code:code||'',error:error||''}).toString();
  return new Response(null,{status:303,headers:{...headers,Location:target.href}});
}

export default {fetch:handoff};
