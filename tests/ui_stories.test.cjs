const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const root=path.join(__dirname,'..'),directory=path.join(root,'mission_control/static');
const loaded={exports:{}};new Function('module',fs.readFileSync(path.join(directory,'ui-stories.js'),'utf8'))(loaded);
const stories=loaded.exports;
test('every actual navigation page has a distinct mission input output and next step',()=>{
 const index=fs.readFileSync(path.join(directory,'index.html'),'utf8');
 const views=[...index.matchAll(/data-view="([a-z]+)"/g)].map(m=>m[1]);
 assert.deepEqual(Object.keys(stories.PAGES).sort(),views.sort());
 const missions=new Set();for(const view of views){
  const row=stories.PAGES[view];assert.equal(row.length,5);assert.ok(row.every(text=>text.length>20));missions.add(row[0]);
  const html=stories.page(view);for(const label of ['What goes in:','What you get:','Your next step:'])assert.ok(html.includes(label));
  assert.ok(!/guaranteed|go viral|unlimited|99%|96\+/.test(html));
 }assert.equal(missions.size,10);assert.throws(()=>stories.page('unknown'));
});
test('every static task form has an explicit narrative and renders without controls or form values',()=>{
 const ids=new Set();for(const file of fs.readdirSync(directory).filter(p=>p.endsWith('.js')&&p!=='ui-stories.js')){
  const source=fs.readFileSync(path.join(directory,file),'utf8');
  for(const match of source.matchAll(/<form\b[^>]*\sid=["']([^"']+)["']/g))ids.add(match[1]);
 }
 assert.ok(ids.size>40);
 for(const id of ids){
  assert.ok(stories.FORMS[id],`Missing narrative for ${id}`);
  const html=stories.dialog('A specific task',`<form id="${id}"><input value="PRIVATE_SENTINEL"></form>`);
  assert.ok(html.includes(stories.FORMS[id][0].replaceAll('’','’'))||html.includes('&#39;'));
  assert.ok(!html.includes('PRIVATE_SENTINEL'));assert.ok(!/<input|<form|<button/.test(html));
 }
});
test('read-only and unknown dialogs escape hostile titles without inventing an effect',()=>{
 const title='<img src=x onerror=alert(1)>';
 for(const source of ['', '<form id="future-form"><input value="PRIVATE_SENTINEL"></form>']){
  const html=stories.dialog(title,source);assert.ok(!html.includes('<img'));assert.ok(html.includes('&lt;img'));
  assert.ok(!html.includes('PRIVATE_SENTINEL'));assert.ok(!html.includes('will publish'));
 }
});
test('shared modal and page hooks add narrative alongside existing control and report paths',()=>{
 const app=fs.readFileSync(path.join(directory,'app.js'),'utf8');
 assert.ok(app.includes('WMMStories.dialog(title,html)'));assert.ok(app.includes('WMMAgentControl.submit'));
 const reports=fs.readFileSync(path.join(directory,'page-reporting.js'),'utf8');
 assert.ok(reports.includes('WMMStories.page(state.view)'));assert.ok(reports.includes('Report / Save PDF'));
});
