const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('./helpers/module-source.cjs');
function fixture(){
 const fields={'[name=task]':{value:'campaign_plan'},'[name=focus]':{value:'',focus(){this.focused=true;}},'#agent-error':{textContent:''}};
 const form={dataset:{app:'sample-one'},querySelector:s=>fields[s]};
 const state={app:'sample-one',workspace:{agent_access:{tasks:{original_copy:{}},draft_recipes:[{id:'pack',task:'original_copy',focus:'Approved recipe'}]}}};
 const notices=[],calls=[];
 const context={state,document:{querySelector:()=>({addEventListener(){}})},$:()=>form,toast:m=>notices.push(m),api:(...x)=>calls.push(x)};
 vm.createContext(context);vm.runInContext(fs.readFileSync('mission_control/static/agent-access.mjs','utf8'),context);
 return {context,fields,form,state,notices,calls};
}
test('recipe selection fills existing form without provider call or submission',()=>{
 const f=fixture();f.context.agentChooseRecipe('pack');
 assert.equal(f.fields['[name=task]'].value,'original_copy');assert.equal(f.fields['[name=focus]'].value,'Approved recipe');assert.equal(f.fields['[name=focus]'].focused,true);
 assert.match(f.fields['#agent-error'].textContent,/Review/);assert.equal(f.calls.length,0);
});
test('stale app, missing recipe and invalid focus cannot change the request',()=>{
 for(const change of [f=>f.state.app='sample-two',f=>f.state.workspace.agent_access.draft_recipes=[],f=>f.state.workspace.agent_access.draft_recipes[0].focus='x'.repeat(1001)]){
  const f=fixture();change(f);f.context.agentChooseRecipe('pack');assert.equal(f.fields['[name=task]'].value,'campaign_plan');assert.equal(f.fields['[name=focus]'].value,'');assert.equal(f.calls.length,0);assert.equal(f.notices.length,1);
 }
});
