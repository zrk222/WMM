const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

const source=fs.readFileSync(path.join(__dirname,'../mission_control/static/app-campaign.js'),'utf8');
const resultsSource=fs.readFileSync(path.join(__dirname,'../mission_control/static/app.js'),'utf8');
const preview=source.slice(source.indexOf('function automationRulesResult('),source.indexOf('function resultsView('));
const identity=resultsSource.slice(resultsSource.indexOf('function experimentScheduleIdentity('),resultsSource.indexOf('function experimentScheduleForm('));

function fixture(){
  const state={app:'first-app',workspace:{app:{version:1},
    identity:{principal:'owner',status:'AUTHENTICATED',expires_at_epoch:100},
    access:{members:[{principal:'owner',role:'OWNER',status:'ACTIVE',version:1}]}},
    boot:{csrf:'synthetic'}};
  const status={isConnected:true,innerHTML:'',textContent:''};
  const node={isConnected:true,disabled:false,closest:()=>({
    querySelector:selector=>selector==='#automation-rules-result'?status:{value:'{}'},
  })};
  let respond;
  const context={
    state,
    esc:String,
    api:url=>{
      assert.equal(url,'/api/apps/first-app/automation/evaluate');
      return new Promise(resolve=>{respond=resolve;});
    },
  };
  const run=vm.runInNewContext(identity+preview+'\nrunAutomationRulePreview',context);
  return {state,status,node,run:()=>run(node),deliver:()=>respond({proposals:[],results:[]})};
}

test('the automation preview renders only for the originating app and session',async t=>{
  for(const [scenario,change,show] of [
    ['current',()=>{},true],
    ['app switched',f=>{f.state.app='second-app';},false],
    ['session changed',f=>{f.state.workspace.identity.expires_at_epoch=200;},false],
    ['panel removed',f=>{f.status.isConnected=false;},false],
  ]){
    await t.test(scenario,async ()=>{
      const f=fixture(),pending=f.run();
      assert.equal(f.node.disabled,true);
      change(f); f.deliver(); await pending;
      assert.equal(f.node.disabled,false);
      if(show) assert.match(f.status.innerHTML,/Preview complete/);
      else assert.equal(f.status.innerHTML,'');
    });
  }
});

test('saved automation rules remain in the originating app, session and unchanged draft',async t=>{
  for(const [scenario,change,expected] of [
    ['current',()=>{},'loaded'],
    ['app switched',f=>{f.state.app='second-app';},'unchanged'],
    ['session changed',f=>{f.state.workspace.identity.expires_at_epoch=200;},'unchanged'],
    ['editor replaced',f=>{f.input.isConnected=false;},'unchanged'],
    ['draft changed while loading',f=>{f.input.value='new draft';},'draft'],
    ['different app in response',f=>{f.response.app_id='second-app';},'unchanged'],
  ]){
    await t.test(scenario,async ()=>{
      const f=ruleStoreFixture();
      const pending=f.run('automation-rules-load');
      await f.run('automation-rules-save');
      assert.equal(f.requests.length,1);
      assert.equal(f.buttons.every(b=>b.disabled),true);
      change(f); f.deliver(); await pending;
      assert.equal(f.buttons.every(b=>!b.disabled),true);
      if(expected==='loaded'){
        assert.deepEqual(JSON.parse(f.input.value),{saved:true});
        assert.match(f.status.textContent,/Loaded version 1/);
      }else if(expected==='draft'){
        assert.equal(f.input.value,'new draft');
        assert.match(f.status.textContent,/Your draft changed/);
      }else{
        assert.equal(f.input.value,'{}');
        assert.equal(f.status.textContent,'');
      }
    });
  }
});

test('save stays bound to the submitted app and never renders stale feedback',async ()=>{
  const f=ruleStoreFixture();
  const pending=f.run('automation-rules-save');
  assert.deepEqual(JSON.parse(JSON.stringify(f.requests)),[
    ['/api/apps/first-app/automation/rules',{document:{}}],
  ]);
  f.state.app='second-app'; f.deliver(); await pending;
  assert.equal(f.status.textContent,'');
  assert.equal(f.input.value,'{}');
});

function ruleStoreFixture(){
  const state=fixture().state;
  const input={isConnected:true,value:'{}',focused:false,focus(){this.focused=true;}};
  const status={isConnected:true,textContent:''};
  const buttons=Array.from({length:2},()=>({isConnected:true,disabled:false}));
  const node={closest:()=>({
    querySelector:s=>s==='#automation-rules-json'?input:status,
    querySelectorAll:()=>buttons,
  })};
  const requests=[];
  let respond,fail;
  const run=vm.runInNewContext(identity+preview+'\nmanageAutomationRules',{
    state,api:(...args)=>{requests.push(args);return new Promise((r,j)=>{respond=r;fail=j;});},
  });
  const response={app_id:'first-app',version:1,hash:'1'.repeat(64),document:{saved:true}};
  return {state,input,status,buttons,requests,response,run:a=>run(node,a),deliver:()=>respond(response),fail:()=>fail(new Error('Request failed'))};
}


test('invalid JSON focuses the editor and a failed request can be retried',async ()=>{
  const f=ruleStoreFixture();
  f.input.value='{';
  await f.run('automation-rules-save');
  assert.equal(f.input.focused,true);
  assert.match(f.status.textContent,/Check the rule JSON/);
  assert.equal(f.requests.length,0);
  f.input.value='{}';
  let pending=f.run('automation-rules-save');
  f.fail(); await pending;
  assert.match(f.status.textContent,/Could not save rules/);
  assert.equal(f.buttons.every(b=>!b.disabled),true);
  pending=f.run('automation-rules-save');
  f.deliver(); await pending;
  assert.match(f.status.textContent,/Saved version 1/);
});
