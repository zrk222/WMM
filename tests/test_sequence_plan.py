"""Finite recommendations and immutable per-step approval envelopes."""
from copy import deepcopy
import unittest,uuid
from mission_control.sequence_plan import prepare,freeze,useful,choices,selected
from mission_control.common import Invalid,digest
from mission_control.service import Service
from tests import test_source_progress as fixtures


class SequencePlanTests(unittest.TestCase):
    setUp=fixtures.SourceProgressTests.setUp

    def current(self):
        w=Service(self.store).workspace('sample-one')
        return w,prepare(w['app'],w['resolutions'],w['preparation']['collection'])

    def connected(self):
        app=self.store.app('sample-one')
        self.store.save_app('sample-one',{**app['data'],'store_app_id':'123'},app['version'])
        self.store.save_record('sample-one',dict(kind='connection',title='Synthetic',source='Fixture',
            data=dict(provider='app_store',store_app_id='123',account_id='0',env_ref='SYNTHETIC_TOKEN')))

    def body(self,proposal):
        return dict(proposal_hash=proposal['proposal_hash'],selected_steps=[s['id'] for s in proposal['steps']],request_key=str(uuid.uuid4()))

    def test_prepare_and_choices_deduplicate_ready_current_targets_without_io(self):
        self.connected();w,p=self.current()
        self.assertEqual(len(p['steps']),3)
        self.assertEqual(len({s['id'] for s in p['steps']}),3)
        self.assertEqual({s['tool'] for s in p['steps']},{'discover_setup','collect_sources','inspect_site'})
        self.assertFalse(p['external_writes']);self.assertEqual(p['spend_minor'],0)
        self.assertEqual(p['execution_mode'],'LOCAL_SERVICE_REQUIRED')
        self.assertEqual(p['proposal_hash'],digest({k:v for k,v in p.items() if k!='proposal_hash'}))

    def test_freeze_preserves_reviewed_order_and_deterministic_child_identities(self):
        self.connected();w,p=self.current();body=self.body(p);run_id=str(uuid.uuid4())
        plan=freeze(w['app'],w['resolutions'],p,body,run_id,'fixture-owner')
        self.assertEqual([s['id'] for s in plan['steps']],body['selected_steps'])
        keys=[s['data']['original_request']['request_key'] for s in plan['steps']]
        self.assertEqual(keys,[str(uuid.uuid5(uuid.UUID(run_id),str(i))) for i in range(3)])
        self.assertTrue(all(s['data']['envelope_hash']==digest(s['data']['envelope']) for s in plan['steps']))
        self.assertFalse(p['automatically_verified'])

    def test_selected_rejects_empty_unknown_duplicate_and_unreviewed_order(self):
        self.connected();_,p=self.current();body=self.body(p);ids=body['selected_steps']
        for value in ([],None,['unknown'],[ids[0],ids[0]],list(reversed(ids)),[{}]):
            with self.subTest(value=value),self.assertRaises(Invalid):selected(p,{**body,'selected_steps':value})
        self.assertEqual(len(selected(p,{**body,'selected_steps':[ids[0]]})),1)

    def test_useful_skips_completed_collection_and_redundant_website_read(self):
        self.connected();w,p=self.current();collection=w['preparation']['collection']
        option=next(o for o in w['resolutions']['issues'][0]['options'] if o['tool']=='collect_sources')
        done=deepcopy(collection)
        for t in done['tasks']:t['job']={'status':'SUCCEEDED'}
        self.assertFalse(useful(option,done,False))
        site=next(o for o in w['resolutions']['issues'][0]['options'] if o['tool']=='inspect_site')
        self.assertFalse(useful(site,collection,True))
        self.assertEqual(choices(w['resolutions'],collection,[])[0],[])

    def test_missing_access_has_next_action_instead_of_fake_execution(self):
        w,p=self.current();res=deepcopy(w['resolutions'])
        for issue in res['issues']:
            for option in issue['options']:option['ready']=False
        blocked=prepare(w['app'],res,w['preparation']['collection'])
        self.assertEqual(blocked['steps'],[])
        self.assertEqual(blocked['status'],'SOURCE_OR_IMPLEMENTATION_REQUIRED')
        self.assertIn('source access',blocked['next_actions'][0])


if __name__=='__main__':unittest.main()
