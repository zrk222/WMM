const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
test('Cloudflare setup offers an explicit paid choice and bounded, labelled free defaults',()=>{
 const context={esc:x=>String(x),document:{querySelector:()=>({addEventListener(){}})}};
 vm.createContext(context);vm.runInContext(fs.readFileSync('mission_control/static/agent-access.js','utf8'),context);
 const html=context.agentCloudflareFields();
 assert.match(html,/<label class="field">Cloudflare account ID<input name="account_id"/);
 assert.match(html,/<option value="free" selected>Free allowance only<\/option>/);
 assert.match(html,/<option value="paid" >Allow paid inference<\/option>/);
 assert.match(html,/<input type="checkbox" name="charges"> I explicitly allow paid inference/);
 assert.match(html,/name="max_output_tokens" type="number" min="64" max="2048"/);
 assert.match(html,/name="daily_request_limit" type="number" min="1" max="1000"/);
 assert.match(html,/not account-wide or a dollar cap/);
});
test('setup submits explicit paid policy and keeps generic adapter payload unchanged',async()=>{
 const calls=[];
 const state={app:'app',workspace:{agent_access:{}}};
 const context={state,FormData:class {constructor(form){return Object.entries(form.values)}},
   document:{querySelector:()=>({addEventListener(){}})},$:()=>({close(){}}),
   api:async (...args)=>{calls.push(args);return {cleanup:'NO_PRIOR_KEY'}},refresh:async()=>{},toast:()=>{}};
 vm.createContext(context);vm.runInContext(fs.readFileSync('mission_control/static/agent-access.js','utf8'),context);
 const form=(provider,values)=>({id:'agent-setup-form',dataset:{app:'app',provider,profile:'',version:''},values,
   isConnected:true,reset(){},querySelector:()=>({disabled:false,textContent:''})});
 await context.agentSubmit(form('cloudflare_api',{label:'CF',model:'@cf/example',api_key:'synthetic',billing_mode:'paid',charges:'on',account_id:'a'.repeat(32),daily_request_limit:'7',max_output_tokens:'64'}));
 assert.deepEqual(JSON.parse(JSON.stringify(calls[0][1])),{provider:'cloudflare_api',label:'CF',model:'@cf/example',endpoint:'',api_key:'synthetic',allow_api_charges:true,id:null,version:null,account_id:'a'.repeat(32),billing_mode:'paid',daily_request_limit:7,max_output_tokens:64});
 await context.agentSubmit(form('cloudflare_api',{label:'Free',model:'@cf/meta/llama-3.2-3b-instruct',api_key:'synthetic',billing_mode:'free',account_id:'a'.repeat(32),daily_request_limit:'10',max_output_tokens:'1024'}));
 assert.equal(calls[1][1].allow_api_charges,false);assert.equal(calls[1][1].billing_mode,'free');
 await context.agentSubmit(form('compatible_api',{label:'Generic',model:'model',endpoint:'https://example.com/v1',api_key:'synthetic',charges:'on'}));
 assert.deepEqual(JSON.parse(JSON.stringify(calls[2][1])),{provider:'compatible_api',label:'Generic',model:'model',endpoint:'https://example.com/v1',api_key:'synthetic',allow_api_charges:true,id:null,version:null});
});
