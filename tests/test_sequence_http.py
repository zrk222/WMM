"""Real protected loopback routes and typed agent feedback for execution sequences."""
import json,threading,unittest
from mission_control.server import Server,Handler
from mission_control.common import canonical
from mission_control.db import connection
from mission_control.agent_feedback import feedback
from mission_control.sequence_store import Sequences
from tests import test_sequence_plan as fixtures
from tests import test_aeo_http as http


class SequenceHTTPTests(unittest.TestCase):
    request=http.HTTPTests.request
    protected=http.HTTPTests.protected
    body=fixtures.SequencePlanTests.body

    def setUp(self):
        fixtures.SequencePlanTests.setUp(self)
        self.server=Server(('127.0.0.1',0),self.store)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.close_server)
        self.path='/api/apps/sample-one/sequences/approve'

    def close_server(self):
        self.server.shutdown();self.server.server_close();self.thread.join()

    def proposal(self):
        status,_,raw=self.request('/api/apps/sample-one')
        self.assertEqual(status,200)
        return json.loads(raw)['sequences']['proposal']

    def test_approval_cancel_reload_and_static_route(self):
        headers=self.protected();body=self.body(self.proposal())
        code,_,raw=self.request(self.path,canonical(body).encode(),headers)
        self.assertEqual(code,201);run=json.loads(raw)
        self.assertEqual(run['state'],'QUEUED')
        cancel='/api/apps/sample-one/sequences/'+run['id']+'/cancel'
        self.assertEqual(self.request(cancel,b'{"confirm_cancel":true}',headers)[0],200)
        _,_,raw=self.request('/api/apps/sample-one');saved=json.loads(raw)['sequences']['history'][0]
        self.assertEqual(saved['state'],'CANCELLED');self.assertEqual(saved['id'],run['id'])
        self.assertEqual(self.request('/campaign-sequence.js')[0],200)

    def test_csrf_origin_stale_and_arbitrary_commands_are_denied(self):
        headers=self.protected();body=self.body(self.proposal())
        self.assertEqual(self.request(self.path,b'')[0],403)
        self.assertEqual(self.request(self.path,canonical(body).encode(),{**headers,'Origin':'https://other.example'})[0],403)
        for invalid in ({**body,'command':'publish'},{**body,'envelope':{}},{**body,'proposal_hash':'stale'},{**body,'selected_steps':['unknown']}):
            self.assertEqual(self.request(self.path,canonical(invalid).encode(),headers)[0],400)
        self.assertEqual(self.request(self.path+'?extra=1',canonical(body).encode(),headers)[0],400)
        self.assertEqual(Sequences(self.store).history('sample-one'),[])

    def test_cross_app_and_generic_queue_cannot_bypass_approval(self):
        headers=self.protected();body=self.body(self.proposal())
        self.assertEqual(self.request('/api/apps/sample-two/sequences/approve',canonical(body).encode(),headers)[0],400)
        for action in ('sequence','campaign_sequence'):
            data=dict(action=action,data={},request_key='synthetic-bypass')
            self.assertEqual(self.request('/api/apps/sample-one/jobs',canonical(data).encode(),headers)[0],400)

    def test_saved_run_changes_only_own_typed_feedback_without_raw_diagnostics(self):
        app=self.store.app('sample-one');other=self.store.app('sample-two')
        before=feedback(self.store,app);other_before=feedback(self.store,other)
        headers=self.protected();body=self.body(self.proposal())
        code,_,raw=self.request(self.path,canonical(body).encode(),headers);self.assertEqual(code,201)
        run=json.loads(raw)
        with connection(self.store.path) as db:
            db.execute('UPDATE campaign_sequences SET result=? WHERE id=?',
                       (canonical(dict(checkpoint=0,step_outcomes=[],summary='SYNTHETIC_PRIVATE_PROVIDER_ERROR')),run['id']))
        after=feedback(self.store,app)
        self.assertNotEqual(before['source_sha256'],after['source_sha256'])
        self.assertEqual(after['sequence']['state'],'QUEUED')
        self.assertNotIn('SYNTHETIC_PRIVATE',canonical(after))
        self.assertEqual(other_before,feedback(self.store,other))

    def test_post_dispatchers_reject_unregistered_operations_without_creating_work(self):
        from unittest.mock import patch
        cases={'post_sequence':'sequences','post_resolution':'resolutions','post_release_selection':'release-selection',
               'post_inspection':'inspections','post_pmf_research':'pmf-research','post_followup':'followup',
               'post_aeo':'aeo','post_insights':'insights','post_storekit':'storekit','post_attribution':'attribution',
               'post_connection':'connections','post_experiment':'experiments','post_reference':'references',
               'post_production':'production','post_ranking':'rankings','post_acquisition':'acquisition',
               'post_access':'access','post_verified_review':'verified-reviews','post_provider_action':'provider-actions',
               'post_learning':'learning','post_payments':'payments'}
        headers=self.protected()
        identity_gated={'post_storekit','post_attribution','post_access','post_verified_review',
                        'post_provider_action','post_learning','post_payments'}
        for handler,route in cases.items():
            called=[];original=getattr(Handler,handler)
            def traced(current,parts,data):
                called.append(handler);return original(current,parts,data)
            with self.subTest(handler=handler),patch.object(Handler,handler,traced):
                status,_,_=self.request('/api/apps/sample-one/'+route+'/unregistered',b'{}',headers)
                expected=(403,) if handler in identity_gated else (400,404)
                self.assertIn(status,expected);self.assertEqual(called,[handler])
        self.assertEqual(Sequences(self.store).history('sample-one'),[])
        from mission_control.worker import jobs
        self.assertEqual(jobs(self.store,'sample-one'),[])


if __name__=='__main__':unittest.main()
