const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const root=path.join(__dirname,'..'),directory=path.join(root,'mission_control/static');
const loaded={exports:{}};new Function('module',fs.readFileSync(path.join(directory,'ui-stories.js'),'utf8'))(loaded);
const stories=loaded.exports;

test('agent research dialogs explain the stage and exact effect without generic repeated prose',()=>{
 for(const title of ['Your agent research','Give your agent a focused search','Review the search assignment','Review agent research','Turn this source into an app experiment','Review this research approval']){
  const html=stories.dialog(title,'<form id="oresearch-adopt-form"></form>');assert.ok(html.startsWith('<header'));assert.ok(!html.includes('Inspect '+title));assert.ok(!html.includes('guaranteed'));
 }
 assert.ok(stories.dialog('Review this research approval','').includes('publication need their own authority'));
});
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
 assert.match(stories.FORMS['publication-draft-form'][1],/TikTok options/);
 assert.match(stories.FORMS['publication-approval-form'][2],/not a provider success receipt/);
});
test('read-only and unknown dialogs escape hostile titles without inventing an effect',()=>{
 const title='<img src=x onerror=alert(1)>';
 for(const source of ['', '<form id="future-form"><input value="PRIVATE_SENTINEL"></form>']){
  const html=stories.dialog(title,source);assert.ok(!html.includes('<img'));assert.ok(html.includes('&lt;img'));
  assert.ok(!html.includes('PRIVATE_SENTINEL'));assert.ok(!html.includes('will publish'));
 }
});
test('shared modal and page hooks add narrative alongside existing control and report paths',()=>{
 const app=fs.readFileSync(path.join(directory,'app.js'),'utf8')+fs.readFileSync(path.join(directory,'app-ui.js'),'utf8')+fs.readFileSync(path.join(directory,'app-events.js'),'utf8');
 const flatApp=app.replace(/\s+/g,'');assert.ok(flatApp.includes('WMMStories.dialog(title,html)'));assert.ok(flatApp.includes('WMMAgentControl.submit'));
 const reports=fs.readFileSync(path.join(directory,'page-reporting.js'),'utf8');
 assert.ok(reports.includes('WMMStories.page(state.view)'));assert.ok(reports.includes('Report / Save PDF'));
});

test('Drive dialog guidance covers access and import independently of hidden form order',()=>{
 const setup='<details><form id="drive-setup-form"></form></details>';
 const importing='<form id="drive-import-form"></form>';
 const first=stories.dialog('Your selected Drive clips',setup+importing);
 assert.equal(first,stories.dialog('Your selected Drive clips',importing+setup));
 assert.ok(!first.includes(stories.FORMS['drive-setup-form'][1]));
 assert.ok(first.includes('original picture and sound'));
 assert.ok(first.includes('approve reuse before editing'));
});

test('goal packet guidance explains its useful next step without repeating generic instructions',()=>{
 for(const goal of ['Find a useful marketing angle','Produce or revise a video','Run an approved campaign','Understand app results']){
  const html=stories.dialog(goal+' — evidence packet','<p>PRIVATE_SENTINEL</p>');
  assert.ok(html.includes('saved evidence for your goal'));
  assert.ok(html.includes('download this snapshot'));
  assert.ok(!html.includes('PRIVATE_SENTINEL'));
  assert.ok(!html.includes('Inspect '+goal));
 }
});

test('readiness guidance distinguishes personal-agent access from managed-work requirements',()=>{
 const choice=stories.dialog('Choose your agent setup','');
 assert.match(choice,/personal agent uses scoped access/);
 assert.match(choice,/WMM-managed work needs a tested connection/);
 const form=stories.dialog('WMM-managed automation setup','<form id="goal-readiness-form"></form>');
 assert.match(form,/This check starts no work/);
 assert.equal((form.match(/<p>/g)||[]).length,1);
 assert.match(stories.FORMS['goal-readiness-form'][2],/Personal agents can use ordinary scoped grants/);
 const result=stories.dialog('WMM-managed readiness checklist','');
 assert.match(result,/setup observations for WMM-managed work/);
});
