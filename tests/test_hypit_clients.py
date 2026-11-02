"""Shipped CLI and HTTP preflight/reuse use the actual source-bound store."""
import json
import subprocess
import sys
import threading
import unittest
from mission_control.server import Server
from mission_control.operator_client import OperatorClient
from mission_control.worker import jobs
from tests import test_hypit_preflight as fixture


class HypitClientTests(unittest.TestCase):
    setUp=fixture.HypitPreflightTests.setUp
    retain=fixture.HypitPreflightTests.retain

    def test_cli_plan_and_http_reuse_never_start_a_second_build(self):
        identity=self.retain();before=jobs(self.store,fixture.APP)
        server=Server(('127.0.0.1',0),self.store)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            origin='http://127.0.0.1:'+str(server.server_port)
            envelope=dict(app_id=fixture.APP,operation='hypit.plan',input={'data':self.request})
            result=subprocess.run([sys.executable,'-m','mission_control.agent_cli','call','--origin',origin],
                                  input=json.dumps(envelope).encode(),capture_output=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr)
            plan=json.loads(result.stdout)
            self.assertEqual(plan['reuse_candidates']['items'][0]['render_id'],identity)
            client=OperatorClient(origin)
            reused=client.call(dict(app_id=fixture.APP,operation='hypit.reuse',input={
                'data':self.request,'render_id':identity,'source_hash':plan['source_hash']}))
            self.assertTrue(reused['reused']);self.assertFalse(reused['job_created']);self.assertFalse(reused['build_started'])
            self.assertEqual(jobs(self.store,fixture.APP),before)
        finally:
            server.shutdown();server.server_close();thread.join()


if __name__=='__main__':unittest.main()
