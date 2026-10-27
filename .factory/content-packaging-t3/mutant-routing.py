import unittest
import inspect
from mission_control import server as m
s=inspect.getsource(m.owner_domain_post)
assert "'packaging':'packaging_http'" in s
ns=dict(m.__dict__)
exec(compile(s.replace("'packaging':'packaging_http'","'packaging':'discovery_http'"),'<route-mutant>','exec'),ns)
m.owner_domain_post=ns['owner_domain_post']
raise SystemExit(not unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromName('tests.test_packaging_clients.PackagingClientTests.test_owner_domain_post_fixed_lazy_handlers')).wasSuccessful())
