"use strict";
const journeyChecks=[
  ["authentication","Login and account access","Test supported login methods, denied access and sign-out."],
  ["core_value","Promised useful outcome","Complete the app's advertised task and inspect the saved result."],
  ["corrections","Corrections and answer quality","Correct an input and verify the answer uses it without cutoff or invented facts."],
  ["restoration","Return and restore context","Reload and reopen the correct account, thread and saved work."],
  ["quota","Quota and paywall","Test exhausted and available quota through each advertised entry."],
  ["billing","Purchase and restore","Use sandbox purchase, entitlement, restore and management paths."],
  ["privacy","Privacy and data controls","Verify advertised export, deletion and permission controls."],
  ["help_access","Help and support access","Open the advertised help/contact path and verify it works."],
  ["devices","Advertised device layouts","Test actual supported devices, scrolling, composer and reachable controls."],
  ["accessibility","Accessible interaction","Test keyboard, labels, focus, contrast and supported assistive interaction."],
  ["voice","Voice and entitlements","Test advertised TTS/STT/V2V, denied permissions and plan restrictions."],
  ["language","Language and regional flows","Test advertised locale, fallback, layout and regional prices."]
];

function journeyFields(data) {
  const rows=journeyChecks.map(([id,title,hint])=>{
    const row=(data.journeys||[]).find(r=>r.id===id)||{};
    const options=["NOT_RUN","PASS","FAIL","N/A"].map(s=>`<option value="${s}" ${s===(row.status||"NOT_RUN")?"selected":""}>${s==="NOT_RUN"?"Not tested":s==="N/A"?"Does not apply":label(s)}</option>`).join("");
    const inputs=["expected","observed","evidence","reason"].map(key=>{
      const name=`journey_${key}_${id}`,title={expected:"Expected behavior",observed:"Actual observation",evidence:"Evidence reference",reason:"Why this does not apply"}[key];
      return field(name,row[key]||"",key==="evidence"?"text":"textarea",key==="reason"?"Required only when this capability does not apply":key==="evidence"?"Test receipt or observation reference; no credentials":"",false).replace(`>${esc(label(name))}<`,`>${title}<`);
    }).join("");
    return `<fieldset class="detail-item" data-journey="${id}"><legend>${esc(title)}</legend><p class="description">${esc(hint)}</p><label class="field" for="journey-status-${id}">Test result<select id="journey-status-${id}" name="journey_status_${id}">${options}</select></label><details><summary>Observations and evidence</summary><div class="form-grid">${inputs}</div></details></fieldset>`;
  }).join("");
  return `<section aria-labelledby="journey-title"><h3 id="journey-title">Check the actual user journeys</h3>${notice("These are your recorded observations, not automatic tests. Untested journeys remain incomplete. A summary alone cannot pass readiness. For capabilities that are absent, choose Does not apply and explain why. Useful outcome, privacy, help and devices always need testing.")}${field("candidate_sha256",data.candidate_sha256||"","text","SHA256 of the tested app artifact or source manifest; this field does not independently verify the build.")}${field("locale",data.locale||state.workspace.app.data.locale||"")}${field("result","NOT_RUN","text","Calculated from all journey observations and P0 count.")}<div class="form-grid">${rows}</div></section>`;
}

function collectJourneys(data) {
  const rows=journeyChecks.map(([id])=>{
    const row={id};
    for(const key of ["status","expected","observed","evidence","reason"]) {
      const name=`journey_${key}_${id}`;row[key]=data[name]||"";delete data[name];
    }
    return row;
  });
  return rows;
}

function journeyResult(rows,p0) {
  if(p0>0||rows.some(r=>r.status==="FAIL"))return "FAIL";
  if(rows.some(r=>r.status==="NOT_RUN"))return "NOT_RUN";
  return "PASS";
}

function wireJourneys(data) {
  const form=$("#evidence-form"),summary=form.querySelector('[name="result"]');
  summary.readOnly=true;
  const update=()=>{
    const values=Object.fromEntries(new FormData(form));
    summary.value=journeyResult(collectJourneys(values),Number(values.p0_count));
  };
  form.addEventListener("change",update);update();
}

function saveJourneyFields(data) {
  data.journeys=collectJourneys(data);data.journey_schema=1;
  data.result=journeyResult(data.journeys,Number(data.p0_count));
}
