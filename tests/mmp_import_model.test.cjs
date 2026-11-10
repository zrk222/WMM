const assert = require("node:assert/strict");
const test = require("node:test");
const model = require("../mission_control/static/mmp-import-model.js");

test("CSV headers handle BOM, quotes and common MMP names", () => {
  const headers = model.parseHeaders('\uFEFFcustomer_user_id,attribution_status,install_time,extra\n"a",attributed,2026-11-01,1\n', "csv");
  assert.deepEqual(headers, ["customer_user_id", "attribution_status", "install_time", "extra"]);
  const value = model.suggest(headers);
  assert.deepEqual(value.mapping, {install_id: "customer_user_id", state: "attribution_status", occurred_at: "install_time"});
  assert.deepEqual(value.unmapped, ["extra"]);
  assert.equal(value.confidence, "ALL_THREE");
});

test("JSON objects and wrapped rows are accepted", () => {
  assert.deepEqual(model.parseHeaders(JSON.stringify([{app_user_id: "x", status: "ATTRIBUTED", occurred_at: "t"}]), "json"),
    ["app_user_id", "status", "occurred_at"]);
  assert.deepEqual(model.parseHeaders(JSON.stringify({rows: [{user_id: "x", state: "ATTRIBUTED"}]}), "json"),
    ["user_id", "state"]);
});

test("unknown or empty headers stay explicit", () => {
  const value = model.suggest(["device", "campaign"]);
  assert.deepEqual(value.mapping, {});
  assert.equal(value.confidence, "NONE");
  assert.throws(() => model.parseHeaders("", "csv"));
  assert.throws(() => model.parseHeaders("not json", "json"));
});

test("template uses the exact accepted columns and no customer identifiers", () => {
  const text = model.templateCsv();
  assert.match(text, /^install_id,state,occurred_at/m);
  assert.doesNotMatch(text, /email|phone|idfa|device/i);
});
