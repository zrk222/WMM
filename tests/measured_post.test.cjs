const assert = require("node:assert/strict");
const test = require("node:test");
const vm = require("node:vm");
const fs = require("node:fs");
const source = fs.readFileSync(require.resolve("../mission_control/static/app.js"), "utf8");
const evidence = vm.runInNewContext(source.slice(source.indexOf("function measuredPostEvidence("),
  source.indexOf("function measuredPostContext(")) + "\nmeasuredPostEvidence");
const link = {study: {source:"youtube"}, study_id:"study-a", url:"https://example.test/?utm_campaign=study-a"};
const authority = (id, url, destination_id) => ({id, status:"APPROVED", draft:{provider:"youtube", link:url, destination_id}});
const verified = id => ({authority_id:id, status:"PUBLISHED", remote_id:id, receipt_hash:"saved-hash"});
test("a different campaign, untagged post or destination cannot complete the journey", () => {
  const pubs = {authorities:[authority("other","https://example.test/?utm_campaign=study-b","one"),
    authority("untagged","https://example.test/","one"),authority("wrong-page",link.url,"two"),
    authority("right",link.url,"one")],
    intents:[verified("other"),verified("untagged"),verified("wrong-page"),{authority_id:"right",status:"PROCESSING"}]};
  const workspace={install_attribution:{campaigns:[{campaign_token:"study-b",study_status:"LINKED",coverage_status:"COMPLETE"},
    {campaign_token:"study-a",study_status:"MIXED",coverage_status:"COMPLETE"}]}};
  let result=evidence(link,"one",pubs,workspace);
  assert.equal(result.delivery,false);
  assert.equal(result.queued,true);
  assert.equal(result.coverage,null);
  pubs.intents[3]=verified("right");
  workspace.install_attribution.campaigns.push({campaign_token:"study-a",study_status:"LINKED",coverage_status:"PARTIAL"});
  result=evidence(link,"one",pubs,workspace);
  assert.equal(result.delivery,true);
  assert.equal(result.coverage,"PARTIAL");
});
test("Facebook delivery requires matching scheduled request, Page and verified readback", () => {
  const fb={...link,study:{source:"facebook"}};
  const job={action:"campaign_post",status:"QUEUED",data:{scope_id:"scope",request:{link:link.url}}};
  const ws={jobs:[job]};
  assert.equal(evidence(fb,"one",{},ws,[{scope_id:"scope",page_id:"one"}]).queued,true);
  job.status="SUCCEEDED";
  job.result={page_id:"two",status:"VERIFIED",remote_id:"post"};
  assert.equal(evidence(fb,"one",{},ws,[{scope_id:"scope",page_id:"one"}]).delivery,false);
  assert.equal(evidence(fb,"one",{},ws,null).historyAvailable,false);
  job.result.page_id="one";
  assert.equal(evidence(fb,"one",{},ws).delivery,true);
  ws.jobs.push({...job});
  assert.equal(evidence(fb,"one",{},ws).ambiguous,false);
  ws.jobs.push({...job,result:{...job.result,remote_id:"second-post"}});
  assert.equal(evidence(fb,"one",{},ws).ambiguous,true);
});

test("missing delivery history stays distinct from a successful empty read", () => {
  assert.equal(evidence(link,"one",null,{}).historyAvailable,false);
  assert.equal(evidence(link,"one",{authorities:[],intents:[]},{}).historyAvailable,true);
});

test("a canonical Facebook receipt completes only its Page and deduplicates scheduled proof", () => {
  const fb={...link,study:{source:"facebook"}};
  const result={page_id:"one",status:"VERIFIED",remote_id:"post"};
  const ws={jobs:[{action:"campaign_post",status:"SUCCEEDED",data:{request:{link:link.url}},result}]};
  const tracked={complete:true,records:[result]};
  assert.equal(evidence(fb,"one",{},ws,[],tracked).delivery,true);
  assert.equal(evidence(fb,"one",{},ws,[],tracked).ambiguous,false);
  assert.equal(evidence(fb,"two",{},ws,[],tracked).delivery,false);
  assert.equal(evidence(fb,"one",{},ws,[],{...tracked,complete:false}).delivery,false);
  assert.equal(evidence(fb,"one",{}, {jobs:[]},[],tracked).delivery,true);
});

test("a cached identity ceases to bind a study after its expiry", () => {
  const state={app:"app",workspace:{app:{version:1},identity:{principal:"owner",expires_at_epoch:101}}};
  let time=100000;
  const context=vm.runInNewContext(source.slice(source.indexOf("function measuredPostContext("),
    source.indexOf("async function firstMeasuredPost(")) + "\nmeasuredPostContext",{state,Date:{now:()=>time}});
  assert.notEqual(context(),null);
  time=101000;
  assert.equal(context(),null);
});
