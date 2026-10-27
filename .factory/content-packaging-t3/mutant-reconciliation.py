import unittest
import inspect
from mission_control import packaging_access as m
s=inspect.getsource(m.reconcile)
old="matches=item['kind']==kind and item['data']['manifest_version']==manifest and item['data']['definition']==definition"
assert old in s
ns=dict(m.__dict__)
exec(compile(s.replace(old,'matches=True'),'<reconciliation-mutant>','exec'),ns)
m.reconcile=ns['reconcile']
raise SystemExit(not unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromName('tests.test_packaging_clients.PackagingClientTests.test_reconcile_observes_without_retry_or_caller_commit_claim')).wasSuccessful())
