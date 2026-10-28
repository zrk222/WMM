"""Synthetic receipt-integrity fixtures are not native acceptance evidence."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import copy

path=Path(__file__).resolve().parents[1]/'tools/check_platform_receipts.py'
spec=importlib.util.spec_from_file_location('platform_receipts',path)
checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)


class NativeCIContractTests(unittest.TestCase):
    def setUp(self):
        folder=tempfile.TemporaryDirectory();self.addCleanup(folder.cleanup)
        self.root=Path(folder.name)
        self.workflow=self.root/'.github/workflows/platform-checks.yml'
        self.workflow.parent.mkdir(parents=True)
        self.value=json.loads((checker.ROOT/'.github/workflows/platform-checks.yml').read_text())
        (self.root/'ios/Build').mkdir(parents=True)
        for script in ('build_runtime.py','generate_project.py','run_simulators.py'):
            (self.root/'ios/Build'/script).write_text('# synthetic stage')

    def check(self,value):
        self.workflow.write_text(json.dumps(value))
        return checker.check_ci_contract(self.root)

    def test_declared_contract_is_not_runtime_acceptance(self):
        result=self.check(self.value)
        self.assertEqual(result['state'],'CI_CONTRACT_VALID')
        self.assertFalse(result['certifies_runtime'])
        self.assertEqual(result['native_execution'],'NOT_ESTABLISHED')
        self.assertEqual(result['physical_acceptance'],'NOT_ESTABLISHED')

    def test_deleted_stage_fails_and_missing_script_fails(self):
        for stage in (2,3,4,5):
            changed=copy.deepcopy(self.value)
            del changed['jobs']['native-simulators']['steps'][stage]
            with self.subTest(stage=stage):self.assertEqual(self.check(changed)['state'],'INCOMPLETE')
        (self.root/'ios/Build/run_simulators.py').unlink()
        self.assertEqual(self.check(self.value)['state'],'INCOMPLETE')

    def test_wrong_host_unpinned_action_and_ignored_failure_fail(self):
        for change in ('host','pin','ignore','dispatch','dependency'):
            value=copy.deepcopy(self.value);job=value['jobs']['native-simulators']
            if change=='host':job['runs-on']='ubuntu-24.04'
            elif change=='pin':job['steps'][0]['uses']='actions/checkout@main'
            elif change=='ignore':job['steps'][5]['continue-on-error']=True
            elif change=='dependency':job.pop('needs')
            else:value['on'].pop('workflow_dispatch')
            with self.subTest(change=change):self.assertEqual(self.check(value)['state'],'INCOMPLETE')

    def test_evidence_must_survive_failures_with_source_identity(self):
        for change in ('upload','missing','app','source'):
            value=copy.deepcopy(self.value);steps=value['jobs']['native-simulators']['steps']
            if change=='upload':steps[-1]['if']='success()'
            elif change=='missing':steps[-1]['with']['if-no-files-found']='ignore'
            elif change=='app':steps[-1]['with']['path']='ios/build-evidence/**'
            else:steps[2]['run']=steps[2]['run'].replace('git rev-parse HEAD','echo fixture')
            with self.subTest(change=change):self.assertEqual(self.check(value)['state'],'INCOMPLETE')


class NativeReceiptTests(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name);self.evidence=self.root/'evidence';self.evidence.mkdir()
        for directory in ('ios','mission_control','specs','plans','package','tools','tests'):(self.root/directory).mkdir()
        (self.root/'.github/workflows').mkdir(parents=True)
        (self.root/'.github/workflows/platform-checks.yml').write_text('{}')
        (self.root/'ios/App.swift').write_text('synthetic native source')
        (self.root/'mission_control/core.py').write_text('synthetic shared source')
        for p in ('codemagic.yaml','plans/ios-client.md','package/acquisition_analysis.py','tools/check_platform_receipts.py','tests/ios_acceptance.md'):(self.root/p).write_text('synthetic')
        self.requirements=['ios_'+str(i) for i in range(16)]
        (self.root/'specs/ios-client.md').write_text('\n'.join('identified by `'+r+'`' for r in self.requirements))

    def receipt(self):
        candidate=checker.check(self.root,self.evidence)['candidate_sha256']
        value=dict(schema='wmm.ios-acceptance.v1',candidate_sha256=candidate,artifacts=[],profiles=[])
        for family in ('iphone','ipad'):
            ids=[]
            for kind in checker.KINDS:
                identity=family+'-'+kind;ids.append(identity)
                file=self.evidence/identity;file.write_text('Synthetic artifact, not device proof')
                value['artifacts'].append(dict(id=identity,path=identity,sha256=checker.sha(file),family=family,kind=kind))
            profile=dict(family=family,physical=True,companion_offline=True,
                **{key:'synthetic' for key in ('device_model','os_version','xcode_version','sdk_version','python_version','bundle_id','signing_identity','observed_at')},
                observations=[dict(requirement=r,status='PASS',artifacts=ids) for r in self.requirements])
            value['profiles'].append(profile)
        return value

    def check(self,value):
        (self.evidence/'receipt.json').write_text(json.dumps(value))
        return checker.check(self.root,self.evidence)

    def test_missing_receipt_cannot_establish_ios_support(self):
        result=checker.check(self.root,self.evidence)
        self.assertEqual(result['state'],'INCOMPLETE');self.assertFalse(result['certifies_runtime'])

    def test_intact_fixture_only_establishes_integrity_and_requires_review(self):
        result=self.check(self.receipt())
        self.assertEqual(result['state'],'EVIDENCE_CURRENT_REVIEW_REQUIRED')
        self.assertFalse(result['certifies_runtime'])

    def test_changed_source_and_modified_artifact_fail(self):
        value=self.receipt()
        (self.root/'ios/App.swift').write_text('changed')
        self.assertIn('Source candidate is stale or unbound',self.check(value)['errors'])
        (self.evidence/value['artifacts'][0]['path']).write_text('changed bytes')
        self.assertTrue(any('changed artifact' in e for e in self.check(value)['errors']))

    def test_simulator_missing_requirements_and_failed_checks_fail(self):
        for mutation in ('simulator','missing','failed','foreign','duplicate'):
            with self.subTest(mutation=mutation):
                value=self.receipt();profile=value['profiles'][0]
                if mutation=='simulator':profile['physical']=False
                if mutation=='missing':profile['observations'].pop()
                if mutation=='failed':profile['observations'][0]['status']='NOT_RUN'
                if mutation=='foreign':profile['observations'][0]['artifacts']=['ipad-domain']
                if mutation=='duplicate':profile['observations'].append(profile['observations'][0])
                self.assertEqual(self.check(value)['state'],'INCOMPLETE')

    def test_escaping_artifact_and_missing_device_family_fail(self):
        value=self.receipt();value['artifacts'][0]['path']='../outside'
        self.assertIn('Artifact path escapes evidence directory',self.check(value)['errors'])
        value=self.receipt();value['profiles'].pop()
        self.assertIn('Both physical iPhone and iPad receipts are required',self.check(value)['errors'])

    def test_build_outputs_do_not_change_source_candidate(self):
        before=checker.source_inventory(self.root)
        output=self.root/'ios/DerivedData';output.mkdir();(output/'generated.swift').write_text('build output')
        self.assertEqual(before,checker.source_inventory(self.root))
