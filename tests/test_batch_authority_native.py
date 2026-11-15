"""Native retained authority needs a fresh host-backed owner at completion."""

from datetime import datetime, timedelta, timezone
import unittest
from mission_control.agent_grants import Grants, capture_batch_authority, check_batch_authority
from mission_control.common import digest, canonical
from mission_control.db import connection
from mission_control.operation_authority import bound_agent, bound_owner, protected
from tests import test_ios_agent_access as fixture
from tests import test_ios_host as host


class NativeBatchAuthorityTests(unittest.TestCase):
    setUp = host.NativeRuntimeTests.setUp
    verify = host.NativeRuntimeTests.verify
    creation = host.NativeRuntimeTests.creation
    manage = fixture.NativeAgentAccessTests.manage
    issue = fixture.NativeAgentAccessTests.issue

    def test_fresh_native_owner_rechecks_original_grant(self):
        issued = self.issue(operations=["creative.batch.create"])
        store = self.runtime.service.store
        expires = (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat()
        plan = {"expires": expires, "synthetic": "fixed"}
        plan_hash = digest(plan)
        envelope = dict(
            app_id="new-app",
            operation="creative.batch.create",
            input=dict(plan=canonical(plan), plan_hash=plan_hash, request_key="key"),
        )
        admitted = Grants(store).admit(issued["token"], envelope)
        user = self.runtime.identities.fresh(self.session)

        def host_check():
            self.runtime.identities.local(self.session, user["principal"], user["session_generation"])

        with bound_agent(store, envelope, admitted, host_check=host_check), protected(store, envelope):
            with connection(store.path) as db:
                reference = capture_batch_authority(db, store, "new-app", "creative.batch.create", plan_hash, expires)
        self.assertTrue(reference["native_host_required"])
        with connection(store.path) as db:
            with self.assertRaises(PermissionError):
                check_batch_authority(db, store, "new-app", reference, plan_hash)
        finish = dict(app_id="new-app", operation="native.batch.finish", input={})
        with bound_owner(store, finish, self.runtime.identities, self.session, user), protected(store, finish):
            with connection(store.path) as db:
                check_batch_authority(db, store, "new-app", reference, plan_hash)
            self.available = False
            with self.assertRaises(PermissionError):
                with connection(store.path) as db:
                    check_batch_authority(db, store, "new-app", reference, plan_hash)


if __name__ == "__main__":
    unittest.main()
