const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const context={Error,module:{exports:{}}};
vm.runInNewContext(fs.readFileSync('mission_control/static/operation-feedback.js','utf8'),context);
const feedback=context.module.exports;

test('approval, changed evidence, limits, accounts and setup have distinct next steps',()=>{
  for(const [raw,code,next] of [
    ['Protected batch admission is required','AGENT_APPROVAL_NEEDED',/owner/],
    ['Agent grant is revoked or expired','ACCESS_ENDED',/cannot renew/],
    ['Post content changed since review','REVIEW_CHANGED',/current version/],
    ['Agent grant call ceiling is exhausted','APPROVED_LIMIT_REACHED',/new allowance/],
    ['Facebook connection expired','ACCOUNT_RECONNECT_NEEDED',/Connections/],
    ['Campaign approval is OFF or expired','APPROVAL_ENDED',/does not renew/],
    ['Paid lifecycle verification is incomplete','PAID_VERIFICATION_NEEDED',/verification checks/],
    ['GitHub browser sign-in is not configured on this WMM installation.','SIGN_IN_SETUP_NEEDED',/local packet/]
  ]){
    const error=feedback.error(new Error(raw));
    assert.equal(error.feedback.code,code);assert.match(error.feedback.next,next);
    assert.equal(error.technicalMessage,raw);assert.ok(!error.message.includes('admission'));
    assert.match(feedback.view(error),/<details><summary>Technical details/);
  }
});
test('uncertain metadata overrides known rejection text and cannot be downgraded on display',()=>{
  for(const context of [{outcome:'UNKNOWN'},{reconciliation_required:true},{status:500,method:'POST'},{interrupted:true,method:'POST'}]){
    const error=feedback.error(new Error('Agent grant is revoked or expired'),context);
    assert.equal(error.feedback.code,'RESULT_NOT_CONFIRMED');
    assert.match(error.message,/do not create a duplicate/);
    assert.equal(feedback.error(error).feedback.code,'RESULT_NOT_CONFIRMED');
    assert.ok(!error.message.includes('new approval'));
  }
});
test('read interruption permits reloading the view; validation errors keep their exact field guidance',()=>{
  assert.equal(feedback.error(new Error('Failed to fetch'),{interrupted:true,method:'GET'}).feedback.code,'LATEST_VIEW_UNAVAILABLE');
  const original=new Error('Choose one to twenty target countries');
  assert.equal(feedback.error(original),original);assert.equal(original.feedback,undefined);
});
test('an unreadable HTTP rejection is distinct from a lost success or server failure',()=>{
  for(const status of [400,401,403,409])assert.equal(feedback.error(new Error('parse'),{unreadable:true,method:'POST',status}).feedback.code,'REQUEST_REJECTED');
  for(const status of [200,201,500,503])assert.equal(feedback.error(new Error('parse'),{unreadable:true,method:'POST',status}).feedback.code,'RESULT_NOT_CONFIRMED');
});
test('raw unconfirmed provider responses and markup never enter the richer diagnostic panel',()=>{
  const secret='<img src=x onerror=alert(1)> private-provider-token';
  const error=feedback.error(new Error(secret),{outcome:'UNKNOWN',status:409});
  const html=feedback.view(error);assert.ok(!html.includes(secret));assert.match(html,/HTTP 409/);
  assert.equal(error.technicalMessage,secret); // available on the local Error, never logged here
  assert.equal(feedback.view(new Error('<script>bad</script>')),'<p>&lt;script&gt;bad&lt;/script&gt;</p>');
});
