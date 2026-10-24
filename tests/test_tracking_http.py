"""Protected real HTTP and worker dispatch for tracking reads; no live provider access."""
import json,threading,unittest
from unittest.mock import patch
from mission_control.common import canonical
from mission_control.server import Server
from mission_control.worker import run_once
from mission_control.experiment_tracking import Tracking
from mission_control.agent_feedback import feedback
from mission_control.tracking_contract import shape
from tests import test_experiment_tracking as fixtures,test_aeo_http as http
from tests.test_tracking_contract import payload


class TrackingHTTPTests(unittest.TestCase):
    request=http.HTTPTests.request
    protected=http.HTTPTests.protected
    body=fixtures.ExperimentTrackingTests.body
    secret=fixtures.ExperimentTrackingTests.secret

    def setUp(self):
        fixtures.ExperimentTrackingTests.setUp(self)
        self.server=Server(('127.0.0.1',0),self.store)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.close_server)
        self.base='/api/apps/sample-one/experiment-tracking'

    def close_server(self):
        self.server.shutdown();self.server.server_close();self.thread.join()

    def test_post_tracking_prepare_approve_worker_result_and_reload(self):
        headers=self.protected();identifiers=dict(experiment_id=self.experiment['id'],source_id=self.source['id'])
        code,_,raw=self.request(self.base+'/prepare',canonical(identifiers).encode(),headers)
        self.assertEqual(code,200);self.assertIn('expected_flag',json.loads(raw))
        code,_,raw=self.request(self.base+'/approve',canonical(self.body()).encode(),headers)
        self.assertEqual(code,201);run=json.loads(raw)
        with patch('mission_control.experiment_tracking.Vault.get',return_value=self.secret()), \
             patch('mission_control.experiment_tracking.tracking_posthog.read',return_value=shape(payload())) as provider:
            self.assertTrue(run_once(self.store))
        provider.assert_called_once()
        code,_,raw=self.request('/api/apps/sample-one');self.assertEqual(code,200)
        row=json.loads(raw)['experiment_tracking'][0]
        self.assertEqual(row['id'],run['id']);self.assertEqual(row['status'],'OBSERVED')
        self.assertNotIn('SYNTHETIC_PRIVATE_KEY',raw.decode())
        self.assertEqual(self.request('/experiment-tracking.js')[0],200)

    def test_tracking_csrf_origin_query_validation_and_generic_queue_denials(self):
        headers=self.protected();body=canonical(self.body()).encode()
        self.assertEqual(self.request(self.base+'/approve',b'',{'Content-Length':str(len(body))})[0],403)
        self.assertEqual(self.request(self.base+'/approve',b'',{**headers,'Content-Length':str(len(body)),'Origin':'https://other.example'})[0],403)
        self.assertEqual(self.request(self.base+'/approve?extra=1',body,headers)[0],400)
        for changes in ({'command':'publish'},{'confirm_read':False},{'proposal_hash':'stale'}):
            self.assertEqual(self.request(self.base+'/approve',canonical({**self.body(),**changes}).encode(),headers)[0],400)
        job=canonical(dict(action='experiment_tracking',data={},request_key='bypass')).encode()
        self.assertEqual(self.request('/api/apps/sample-one/jobs',job,headers)[0],400)
        self.assertEqual(Tracking(self.store).list('sample-one'),[])

    def test_tracking_cancellation_is_exact_and_foreign_app_cannot_read_or_stop(self):
        headers=self.protected();_,_,raw=self.request(self.base+'/approve',canonical(self.body()).encode(),headers)
        run=json.loads(raw);cancel=self.base+'/'+run['id']+'/cancel'
        self.assertEqual(self.request(cancel,b'{"cancel_run":1}',headers)[0],400)
        foreign=cancel.replace('sample-one','sample-two')
        self.assertEqual(self.request(foreign,b'{"cancel_run":true}',headers)[0],400)
        self.assertEqual(self.request(cancel,b'{"cancel_run":true}',headers)[0],200)
        _,_,raw=self.request('/api/apps/sample-two');self.assertEqual(json.loads(raw)['experiment_tracking'],[])
        with patch('mission_control.experiment_tracking.tracking_posthog.read') as provider:
            self.assertFalse(run_once(self.store));provider.assert_not_called()

    def test_feedback_contains_only_typed_own_app_tracking_state(self):
        app=self.store.app('sample-one');other=self.store.app('sample-two')
        before=feedback(self.store,app);other_before=feedback(self.store,other)
        run=Tracking(self.store).approve('sample-one',self.body())
        after=feedback(self.store,app)
        self.assertNotEqual(before['source_sha256'],after['source_sha256'])
        self.assertEqual(after['experiment_tracking']['run_id'],run['id'])
        self.assertEqual(after['experiment_tracking']['proof'],'TRACKING_ONLY_NOT_CAUSAL')
        self.assertNotIn('expected_flag',canonical(after));self.assertNotIn('project_id',canonical(after))
        self.assertEqual(other_before,feedback(self.store,other))


if __name__=='__main__':unittest.main()
