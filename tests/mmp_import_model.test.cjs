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

test("column detection preserves edits and ignores replaced files", async () => {
  const fs = require('./helpers/module-source.cjs'), vm = require("node:vm");
  const source = fs.readFileSync(require.resolve("../mission_control/static/app-install.mjs"), "utf8");
  const snippet = source.slice(source.indexOf("async function installImportDetect("),
    source.indexOf("async function saveCloudConnection("));
  const state = {app: "demo"};
  const detect = vm.runInNewContext(snippet + "\ninstallImportDetect", {state, WMMMmpImport: model});
  const fields = Object.fromEntries(["col_install_id", "col_state", "col_occurred_at"]
    .map(name => [name, {value: name}]));
  const status = {textContent: ""};
  const picker = {files: []};
  const form = {dataset: {app: "demo"}, isConnected: true, elements: fields,
    closest: () => ({open: true}),
    querySelector: selector => selector === "#install-detect-status" ? status
      : selector.includes("export_file") ? picker : fields[selector.match(/"([^"]+)"/)[1]]};
  const header = "customer_user_id,attribution_status,install_time\na,b,c";
  let deliver;
  const file = () => ({size: 10, name: "export.csv", text: () => new Promise(resolve => { deliver = resolve; })});
  picker.files = [file()];
  const first = detect(form);
  fields.col_install_id.value = "operator_choice";
  deliver(header);
  await first;
  assert.equal(fields.col_install_id.value, "operator_choice");
  assert.equal(fields.col_state.value, "attribution_status");
  picker.files = [file()];
  const second = detect(form);
  picker.files = [file()];
  status.textContent = "new file";
  deliver(header);
  await second;
  assert.equal(status.textContent, "new file");
});
