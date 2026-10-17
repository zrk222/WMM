// Stateless code handoff only. Mission Control itself must remain private.
const providers = new Set(['facebook','instagram','tiktok','linkedin']);
const printable = (value,min,max) => typeof value==='string' && value.length>=min && value.length<=max && /^[!-~]+$/.test(value);
const headers = {'Cache-Control':'no-store','Referrer-Policy':'no-referrer','Content-Security-Policy':"default-src 'none'; frame-ancestors 'none'; base-uri 'none'",'X-Content-Type-Options':'nosniff'};

export function handoff(request) {
  const url=new URL(request.url),parts=url.pathname.split('/');
  if(request.method!=='GET'||url.protocol!=='https:'||url.hash||url.username||url.password||url.port||parts.length!==3||parts[1]!=='cb'||!providers.has(parts[2]))return new Response('Invalid callback',{status:400,headers});
  const entries=[...url.searchParams];
  if(entries.length>6||new Set(entries.map(([key])=>key)).size!==entries.length)return new Response('Invalid callback',{status:400,headers});
  const allowed=new Set(['state','code','error','error_description','error_reason','error_code']);
  if(entries.some(([key,value])=>!allowed.has(key)||value.length>4096))return new Response('Invalid callback',{status:400,headers});
  const state=url.searchParams.get('state'),code=url.searchParams.get('code'),error=url.searchParams.get('error');
  if(!printable(state,43,128)||Boolean(code)===Boolean(error)||code&&!printable(code,1,4096)||error&&!printable(error,1,100))return new Response('Invalid callback',{status:400,headers});
  const target=new URL('http://127.0.0.1:8765/social/callback/'+parts[2]);
  target.hash=new URLSearchParams({state,code:code||'',error:error||''}).toString();
  return new Response(null,{status:303,headers:{...headers,Location:target.href}});
}

export default {fetch:handoff};
