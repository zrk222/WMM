"""Actual local download routes preserve exact source binding and server boundaries."""
from io import BytesIO
import json,unittest,zipfile
from unittest.mock import patch
from mission_control.db import connection
from tests import test_tracking_http as fixtures


class InstrumentationHTTPTests(unittest.TestCase):
    def setUp(self):
        fixtures.TrackingHTTPTests.setUp(self)
        app=self.store.app('sample-one')
        self.store.save_app('sample-one',{**app['data'],'website':'https://example.com'},app['version'])
    close_server=fixtures.TrackingHTTPTests.close_server
    request=fixtures.TrackingHTTPTests.request
    protected=fixtures.TrackingHTTPTests.protected

    def address(self):
        value=self.tracking.prepare('sample-one',dict(experiment_id=self.experiment['id'],source_id=self.source['id']))
        return self.base+'/'+self.experiment['id']+'/instrumentation/'+self.source['id']+'/'+value['proposal_hash']

    def test_exact_download_contains_current_hashed_files_without_provider_access(self):
        path=self.address()
        with patch('mission_control.tracking_posthog.request') as remote:
            code,headers,raw=self.request(path);remote.assert_not_called()
        self.assertEqual(code,200,raw);self.assertEqual(headers['Content-Type'],'application/zip')
        self.assertIn('attachment;',headers['Content-Disposition']);self.assertEqual(headers['Cache-Control'],'no-store')
        with zipfile.ZipFile(BytesIO(raw)) as zipped:
            config=json.loads(zipped.read('config.json'));manifest=json.loads(zipped.read('manifest.json'))
            self.assertEqual(config['experiment_id'],self.experiment['id'])
            self.assertEqual(manifest['status'],'PREPARED_NOT_INSTALLED')
            self.assertNotIn(b'SYNTHETIC_PRIVATE_KEY',raw)
        self.assertEqual(self.tracking.list('sample-one'),[])
        with connection(self.store.path) as db:self.assertEqual(db.execute('SELECT count(*) FROM jobs').fetchone()[0],0)

    def test_stale_foreign_query_and_malformed_package_addresses_are_rejected(self):
        path=self.address()
        for target in (path+'?extra=1',path+'/extra',path.replace('sample-one','sample-two'),path[:-64]+'0'*64):
            self.assertEqual(self.request(target)[0],400,target)
        with connection(self.store.path) as db:db.execute("UPDATE insight_sources SET version=2 WHERE app_id='sample-one'")
        self.assertEqual(self.request(path)[0],400)

    def test_host_and_post_boundaries_remain_enforced_for_package_route(self):
        path=self.address()
        self.assertEqual(self.request(path,headers={'Host':'evil.example'})[0],403)
        self.assertEqual(self.request(path,b'{}')[0],403)
        good=self.protected()
        self.assertEqual(self.request(path,b'{}',{**good,'Origin':'https://evil.example'})[0],403)


if __name__=='__main__':unittest.main()
