"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const loaded = {exports:{}};
new Function("module", fs.readFileSync(process.env.WMM_REPORT_TEST_SOURCE || path.join(__dirname,"../mission_control/static/page-reporting.js"),"utf8"))(loaded);
const reports = loaded.exports;
const timestamp = "2026-10-23T12:00:00Z";
function fixture() {
  return {app:"sample-one", view:"overview", workspaceObservedAt:timestamp,
    workspace:{app:{id:"sample-one", version:3, data:{name:"Synthetic café"}},
      stages:[{status:"READY"},{status:"NEEDS_INPUT"}], records:[{kind:"asset",title:"Current capture"},{kind:"cohort",title:"Pilot cohort"}],
      jobs:[{action:"sync",status:"FAILED"},{action:"agent_run",status:"COMPLETED"}],
      connections:{source:{status:"DISCONNECTED"}}, agent_access:{profiles:[{status:"DISCONNECTED"},{status:"CONFIGURED_UNTESTED"}]},
      verified_reviews:[], experiments:[], ledger:[], metrics:{cohorts:[]}},
    research:{ledger:{other_notebooks:[]}}};
}
test("page_explainers covers exactly every top-level navigation view", () => {
  const index = fs.readFileSync(path.join(__dirname,"../mission_control/static/index.html"),"utf8");
  const views = [...index.matchAll(/data-view="([a-z]+)"/g)].map(m=>m[1]).sort();
  assert.deepEqual(Object.keys(reports.PAGES).sort(), views);
  for (const view of views) {
    const state = {...fixture(), view};
    const model = reports.model(state, timestamp);
    assert.ok(model.purpose.length > 20 && model.next_step.length > 20);
    assert.ok(reports.panel(model).includes("Report / Save PDF"));
    assert.ok(model.metrics.length >= 2 && model.metrics.every(m=>m.source && m.unit));
  }
});
test("overview_story names purpose, inputs, operations and delivered artifacts directly", () => {
  const html = reports.overviewStory();
  for (const phrase of ["preparing and measuring app marketing","Tell WMM about your app","Bring in the evidence","usage, purchase and refund events","account connections","Prepare and check the work","six creative briefs","conversion, acquisition cost and contribution","Take the deliverables","twelve stage packets","experiment plans","PDF reports","Start here"]) assert.ok(html.includes(phrase));
  assert.equal((html.match(/<li>/g)||[]).length,4);
  assert.ok(!/\b(?:may|might|could|helps|can)\b/i.test(html));
  assert.ok(!html.includes("guaranteed growth"));
  assert.ok(!html.includes("OAuth") && !html.includes("schema") && !html.includes("cohort"));
});
test("page_analytics distinguishes unavailable sources from loaded zero", () => {
  const state = fixture();
  state.workspace.records = undefined;
  assert.equal(reports.model(state).metrics[2].value,null);
  state.workspace.records = [];
  assert.equal(reports.model(state).metrics[2].value,0);
  state.view = "connections";
  assert.deepEqual(reports.pageMetrics(state.view,state).map(m=>m.value),[1,1,1]);
});
test("evidenceMetrics applies the same title/kind search and records filter scope", () => {
  const state = {...fixture(),view:"evidence",filter:"ASSET",referencePlatform:"youtube"};
  const model = reports.model(state,timestamp);
  assert.equal(model.metrics[0].value,1);
  assert.equal(model.metrics[1].value,1);
  assert.equal(model.metrics[2].value,2);
  assert.equal(model.filters.evidence_search,"ASSET");
  assert.equal(model.filters.reference_platform,"youtube");
});
test("weeklyMetrics uses displayed portfolio coverage and retains source failures", () => {
  const state = {...fixture(),view:"weekly",weeklyReview:{observed_at:timestamp,coverage:{evaluated:2,offset:5},exceptions:[{},{}],apps:[{exceptions:[]},{exceptions:[{state:"UNAVAILABLE"}]}]}};
  const model = reports.model(state,timestamp);
  assert.deepEqual(model.metrics.map(m=>m.value),[2,2,1]);
  assert.equal(model.scope,"PORTFOLIO_DISPLAYED_PAGE");
  assert.equal(model.app_id,null);
  assert.equal(model.filters.offset,5);
  for (const change of [{weeklyError:"Read failed"},{weeklyLoading:true}]) assert.ok(reports.model({...state,...change}).metrics.every(m=>m.value===null));
});
test("cohortRows preserves currencies, eligible denominator and unavailable rates", () => {
  const state = {...fixture(),view:"results"};
  state.workspace.metrics.cohorts = [
    {status:"MEASURED",cohort_id:"usd-cohort",currency:"USD",horizon:"D7",counts:{installs:100},activation_rate:0.5,paid_conversion:0.1,paid_cac_minor:500,contribution_after_acquisition_minor:-50},
    {status:"MEASURED",cohort_id:"eur-zero",currency:"EUR",horizon:"D30",counts:{installs:0},activation_rate:null,paid_conversion:null},
    {status:"INCONCLUSIVE",activation_rate:0.9}];
  const report = reports.model(state,timestamp);
  assert.equal(report.cohorts[0].installs,100);
  assert.equal(report.cohorts[0].contribution_minor,-50);
  assert.equal(report.cohorts[1].currency,"EUR");
  assert.equal(report.cohorts[1].paid_conversion,null);
  assert.equal(report.cohorts[2].activation_rate,null);
  assert.match(report.notes.join(" "),/eligible installs as denominator/);
});
test("report_privacy rejects unknown views and mismatched selected app", () => {
  assert.throws(()=>reports.model({...fixture(),view:"__proto__"}),/Load/);
  assert.throws(()=>reports.model({...fixture(),view:"unknown"}),/Load/);
  assert.throws(()=>reports.model({...fixture(),app:"sample-two"}),/Load/);
  assert.throws(()=>reports.model({...fixture(),workspace:null}),/Load/);
});
test("report_scope excludes raw profiles, tokens, record data and draft inputs", () => {
  const state = fixture();
  state.workspace.app.data.api_key = "SECRET_SENTINEL";
  state.workspace.records[0].data = {draft:"SECRET_SENTINEL"};
  state.workspace.agent_access.profiles[0].data = {api_key:"SECRET_SENTINEL",credential_ref:"SECRET_SENTINEL"};
  for (const view of Object.keys(reports.PAGES)) {
    const report = reports.model({...state,view},timestamp);
    assert.ok(!JSON.stringify(report).includes("SECRET_SENTINEL"));
    assert.ok(!reports.reportHTML(report,"http://127.0.0.1:8080").includes("SECRET_SENTINEL"));
  }
});
test("panel metricTable and reportHTML escape hostile text while preserving Unicode", () => {
  const state = fixture();
  state.workspace.app.data.name = '<img src=x onerror=alert(1)> Café 東京';
  const model = reports.model(state,timestamp);
  const html = reports.reportHTML(model,"http://127.0.0.1:8080");
  assert.ok(!html.includes("<img"));
  assert.ok(html.includes("&lt;img"));
  assert.ok(html.includes("Café 東京"));
  assert.match(reports.metricTable(model),/scope="col"/);
  assert.match(reports.panel(model),/aria-labelledby/);
});
test("pdf_export accurately describes browser Save as PDF and includes report dates", () => {
  const report = reports.model(fixture(),timestamp);
  const html = reports.reportHTML(report,"http://127.0.0.1:8080");
  assert.ok(html.includes("No file has been saved until you complete that step"));
  assert.ok(html.includes(timestamp));
  assert.ok(html.includes("All loaded saved history; no date filter"));
  assert.ok(html.includes("app setup version") || html.includes("App setup version"));
});
test("openReport reports blocked popup without implying successful export", () => {
  assert.throws(()=>reports.openReport(reports.model(fixture()),{open:()=>null}),/Allow a report window/);
});
test("openReport binds print and close actions without inline scripts or opener access", () => {
  const listeners = {};
  let printed = false, closed = false, html = "";
  const popup = {document:{open(){},write(value){html=value;},close(){},getElementById(id){return {addEventListener(event,fn){listeners[id]=fn;}};}},print(){printed=true;},close(){closed=true;},focus(){},opener:{}};
  reports.openReport(reports.model(fixture(),timestamp),{open:()=>popup,location:{origin:"http://127.0.0.1:8080"}});
  assert.equal(popup.opener,null);
  assert.ok(!html.includes("<script") && !html.includes("onclick="));
  listeners["print-page-report"]();
  listeners["close-page-report"]();
  assert.ok(printed && closed);
});
test("long cohort reports disclose truncation and text bounds", () => {
  const state = {...fixture(),view:"results"};
  state.workspace.metrics.cohorts = Array.from({length:101},()=>({status:"MEASURED",cohort_id:"x".repeat(1200)}));
  const report = reports.model(state,timestamp);
  assert.equal(report.cohorts.length,100);
  assert.equal(report.cohorts[0].id.length,1000);
  assert.ok(report.notes.some(note=>note.includes("first 100")));
});
