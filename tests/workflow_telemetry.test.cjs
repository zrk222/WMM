const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const context={module:{exports:{}},setTimeout,clearTimeout};vm.createContext(context);
vm.runInContext(fs.readFileSync(require('node:path').join(__dirname,'../mission_control/static/workflow-telemetry.js'),'utf8'),context);
const ui=context.module.exports;
test('monitor displays actual stage and fixed activity without injecting source markup',()=>{
 const html=ui.markup({runs:[{action:'pipeline',status:'RUNNING',attempts:1,processed_stages:2,blocked_stages:1,updated:'now',latest:{stage:3,stage_title:'<script>bad</script>',observed_at:'now'},activity:'Checking evidence',events:[{observed_at:'now',stage:3,message:'<img src=x>'}]}]});
 assert.match(html,/Stage 3/);assert.match(html,/2 stages processed/);assert.match(html,/Checking evidence/);
 assert.ok(!html.includes('<script>'));assert.ok(!html.includes('<img'));assert.ok(!html.includes('%'));
});
test('empty and unobserved attempts do not invent stage completion',()=>{
 assert.match(ui.markup({runs:[]}),/No workflow runs yet/);
 const html=ui.markup({runs:[{action:'pipeline',status:'QUEUED',attempts:0,processed_stages:0,blocked_stages:0,activity:'No worker event',events:[],updated:'now'}]});
 assert.match(html,/No event recorded/);assert.ok(!html.includes('Stage undefined'));assert.equal(ui.POLL_MS,2000);
});
