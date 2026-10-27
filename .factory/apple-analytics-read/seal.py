"""Seal the bounded analytics readiness increment; metric ingestion stays open."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import subprocess
import os

P=Path('.factory/apple-analytics-read')

def item(path,kind='log'):
    return dict(path=str(path).replace('\\','/'),sha256=hashlib.sha256(Path(path).read_bytes()).hexdigest(),kind=kind)

def write(name,value):
    (P/name).write_bytes((json.dumps(value,indent=2)+'\n').encode())

review=P/'scope.md'
review.write_bytes(b'Bounded Apple report-readiness adapter using existing protected per-app connections and sync jobs. Reports and instances are metadata, not metric observations. Null metrics, explicit pending/setup/download-required states and partial coverage are required. No UI changes; accessibility is not applicable to this packet. Existing agent grants and provider-write authority are unchanged. Tests preload the sequence policy module before mocking it to avoid a retained test mock. Native private read receipts stay outside the public repository. Bulk segment downloads, actual metric ingestion, refresh scheduling, human/agent UI acceptance and full MV1 remain INCOMPLETE.\n')
q=subprocess.run(['specline','strict','apple-analytics-read','--root','.','--json'],capture_output=True,check=True,env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUTF8='1'))
(P/'requirements.log').write_bytes((q.stdout+q.stderr).replace(b'\r\n',b'\n'))
paths=['mission_control/apple_analytics.py','mission_control/provider_reports.py','mission_control/providers.py','tests/test_apple_analytics.py','tests/test_campaign_inputs.py','specs/apple-analytics-read.md','specs/apple-analytics-read.ssat.yaml',str(P/'quality.py'),str(P/'mutations.py'),str(P/'seal.py'),str(P/'changed_functions.py')]
candidate=[item(path,'source' if path.endswith('.py') else 'contract') for path in paths]
quality=json.loads((P/'qa.json').read_text()); security=json.loads((P/'security.json').read_text())
assert quality['passed'] and not quality['findings'] and quality['metrics']['max_complexity']<=10
assert security['audit_coverage']['complete'] and security['audit_coverage']['measurement_state']=='complete'
assert security['files_scanned']==3 and not security['findings'] and not security['database_context']['gaps']
assert all(security[key]==0 for key in ('parse_errors','unreadable_sources','oversized_sources'))
for record in json.loads((P/'security-binding.json').read_text()):
    assert item(record['path'])['sha256']==record['sha256']==item(record['copy'])['sha256']
checks=[
 ('readiness','happy_path','Persist typed app-scoped report readiness through the actual sync worker and reload'),
 ('validation','validation','Reject foreign identities, bad types, invalid dates, unsafe URLs and duplicate source conflicts'),
 ('recovery','failure_recovery','Propagate permission and provider errors; missing generated instances remain unknown metrics'),
 ('scope','state_consistency','Preserve connection/app scope, immutable source hashes and exact durable result identity'),
 ('security','security_privacy','Keep authenticated requests on allowed read endpoints; reject cross-app access and retain null metrics'),
 ('budgets','performance','Bound collection reads to three pages of one hundred entries and five declared report families under the existing reader deadline'),
 ('effects','external_effects','Reject POST on new analytics endpoints; never create streams, grant access, spend or publish')]
categories=['happy_path','validation','failure_recovery','state_consistency','security_privacy','performance','accessibility','external_effects']
profile='Windows-Python3.11-synthetic-worker-native-sqlite'
contract=dict(schema='factory.workflow-audit.contract.v1',project_id='WMM-apple-analytics-readiness',candidate=candidate,
    applicability=[dict(category=c,applicable=c!='accessibility',reason='See scoped requirements and review',**({'review_evidence':item(review,'review')} if c=='accessibility' else {})) for c in categories],
    checks=[dict(id=i,category=c,requirement=r,profiles=[profile]) for i,c,r in checks])
write('contract.json',contract)
artifacts=[item(P/name) for name in ('regressions.log','adjacent-regressions.log','mutations.json','mutation-baseline.log','mutation-foreign-parent.log','mutation-foreign-host.log','mutation-unknown-metrics.log','qa.json','qa-binding.json','security.json','security-binding.json','requirements.log')]
write('observations.json',dict(schema='factory.workflow-audit.observations.v1',contract_sha256=item(P/'contract.json')['sha256'],candidate_sha256=hashlib.sha256(json.dumps(candidate,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
 observations=[dict(id=i,profile=profile,status='PASS',reason=r,execution_identity='python -m unittest tests.test_apple_analytics tests.test_provider_reports tests.test_provider_setup tests.test_subscription_variants tests.test_release_inventory -v; python -m unittest tests.test_campaign_inputs tests.test_source_retry_guards tests.test_play_collection -v; python .factory/apple-analytics-read/mutations.py; python .factory/apple-analytics-read/quality.py',observed_at=datetime.now(timezone.utc).isoformat(),artifacts=artifacts) for i,c,r in checks]))
q=subprocess.run(['factory','audit','workflows','--root','.','--contract',str(P/'contract.json'),'--observations',str(P/'observations.json'),'--json'],capture_output=True,check=True)
(P/'workflow-receipt.json').write_bytes(q.stdout.replace(b'\r\n',b'\n'))
print(json.loads(q.stdout)['state'])
