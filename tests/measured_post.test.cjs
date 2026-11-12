const assert = require("node:assert/strict");
const test = require("node:test");
const vm = require("node:vm");
const fs = require('./helpers/module-source.cjs');
const source = fs.readFileSync(require.resolve("../mission_control/static/app-campaign.mjs"), "utf8");
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

test("study view and private PDF share descriptive guidance and never turn incomplete data into a rate",()=>{
  const script=fs.readFileSync(require.resolve("../mission_control/static/observational-campaign.mjs"),"utf8");
  const renders=[];
  const view=vm.runInNewContext(script+"\nWMMObservationalCampaign",{
    esc:String,state:{},window:{},WMMPageReports:{model:()=>({}),openReport:model=>renders.push(model)},
  });
  const report={checkpoint:{state:"DESCRIPTIVE_READY",collector_source_id:"collector-a",
    coverage_issues:{},ratio_counts:{linked_registrations:1,eligible_landings:2}},
    landing_subjects:2,linked_registration_subjects:1,coverage:{},exclusions:{UNMATCHED_REGISTRATION:1},
    starts_at:"2030-01-01T00:00:00Z",ends_at:"2030-01-02T00:00:00Z",
    study_hash:"study-digest",source_hash:"source-digest",limits:[]};
  const html=view.checkpointMarkup(report);
  view.pdf(report);
  const printed=renders[0];
  assert.match(html,/1 of 2 eligible landings \(50%\)/);
  assert.match(printed.notes.join(" "),/1 of 2 eligible landings \(50%\)/);
  assert.ok(html.includes(printed.next_step));
  assert.match(html,/Source hash: source-digest/);
  assert.ok(printed.notes.includes("Source hash: source-digest"));
  report.checkpoint={...report.checkpoint,state:"COVERAGE_INCOMPLETE",coverage_issues:{LANDING:"BEFORE_CLOSE"}};
  assert.match(view.checkpointMarkup(report),/Receipt predates the end of the window/);
  assert.doesNotMatch(view.checkpointMarkup(report),/Linked registration rate/);
  view.pdf(report);
  assert.doesNotMatch(renders[1].notes.join(" "),/Linked registration rate/);
});
