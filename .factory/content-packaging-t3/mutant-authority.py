import unittest
from contextlib import nullcontext
from mission_control import packaging_http as m
m.protected=lambda *a,**k:nullcontext()
raise SystemExit(not unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromName('tests.test_packaging_clients.PackagingClientTests.test_owner_revocation_before_business_transaction_prevents_commit')).wasSuccessful())
