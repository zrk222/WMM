const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');

const source=fs.readFileSync(path.join(__dirname,'../mission_control/static/app.js'),'utf8');
const preview=source.slice(source.indexOf('function automationRulesResult('),source.indexOf('function resultsView('));
const identity=source.slice(source.indexOf('function experimentScheduleIdentity('),source.indexOf('function experimentScheduleForm('));

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
