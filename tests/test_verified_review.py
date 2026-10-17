"""Isolated authenticated review tests; provider identities are explicit synthetic responses."""
from io import BytesIO
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError,URLError
from mission_control.common import Invalid,digest
from mission_control.db import connection
from mission_control.store import Store
from mission_control.operator_identity import Identities,github_read,identity
from mission_control.review_access import Access,member
from mission_control.verified_reviews import Reviews

OWNER=identity({"id":101,"login":"fixture-owner","type":"User"})
CHECKER=identity({"id":202,"login":"fixture-checker","type":"User"})
STRANGER=identity({"id":303,"login":"fixture-stranger","type":"User"})
OWNER_TOKEN="synthetic_owner_identity_token"
CHECKER_TOKEN="synthetic_checker_identity_token"


def synthetic_identity(path,token):
    """Documented synthetic network boundary; never used by the production server."""
    if token not in (OWNER_TOKEN,CHECKER_TOKEN):raise Invalid("Synthetic token rejected by fixture provider")
    if path=="/users/fixture-checker":return dict(CHECKER)
    if path=="/user":return dict(OWNER if token==OWNER_TOKEN else CHECKER)
    raise Invalid("Synthetic identity not configured")


def fixture(store,app="review-test"):
    store.save_app(app,{"name":"Synthetic review app","release":"1","locale":"en-US"})
    record=store.save_record(app,{"kind":"store","title":"Synthetic exact store copy","source":"Synthetic test proof","data":{"description":"Actual approved fixture description"}})
    access=Access(store);access.bootstrap(app,OWNER,{"confirm_owner":True})
    access.save(app,OWNER,CHECKER,{"login":CHECKER["login"],"role":"CHECKER","status":"ACTIVE","version":None})
    return record


class VerifiedReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/"state.sqlite",seed=False)
        self.record=fixture(self.store);self.access=Access(self.store);self.reviews=Reviews(self.store)

    def tearDown(self):self.tmp.cleanup()

    def prepare(self):return self.reviews.prepare("review-test",OWNER,{"record_id":self.record["id"]})

    def test_transport_fixed_identity_scope_and_error_redaction(self):
        raw=json.dumps({"id":101,"login":"fixture-owner","type":"User","email":"ignored@example.test"}).encode()
        with patch("mission_control.operator_identity.build_opener") as opener:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value=raw
            user=github_read("/user",OWNER_TOKEN);self.assertEqual(user["principal"],OWNER["principal"])
            request=opener.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url,"https://api.github.com/user");self.assertEqual(request.get_method(),"GET")
            self.assertEqual(opener.return_value.open.call_args.kwargs["timeout"],15)
            self.assertEqual(request.headers["Authorization"],"Bearer "+OWNER_TOKEN)
            self.assertEqual(set(user),{"principal","login","provider","verified_at"})
            for path in ("https://evil.test/user","/user?token=x","/users/a/b","/repos/owner/private","/users/../user"):
                before=opener.return_value.open.call_count
                with self.assertRaises(Invalid):github_read(path,OWNER_TOKEN)
                self.assertEqual(opener.return_value.open.call_count,before)
            for body in (b"x"*65537,b"not-json",b"[]",b'{"id":true,"login":"x","type":"User"}',b'{"id":1,"login":"bot","type":"Bot"}'):
                opener.return_value.open.return_value.__enter__.return_value.read.return_value=body
                with self.assertRaises(Invalid):github_read("/user",OWNER_TOKEN)
            for failure in (HTTPError("https://api.github.com/user",401,OWNER_TOKEN,{},None),URLError(OWNER_TOKEN),TimeoutError(OWNER_TOKEN)):
                opener.return_value.open.side_effect=failure
                with self.assertRaises(Invalid) as caught:github_read("/user",OWNER_TOKEN)
                self.assertNotIn(OWNER_TOKEN,str(caught.exception))
        renamed=identity({"id":101,"login":"renamed-owner","type":"User"})
        self.assertEqual(renamed["principal"],OWNER["principal"])

    def test_ephemeral_sessions_expiry_logout_revocation_and_changed_identity(self):
        identities=Identities()
        with patch("mission_control.operator_identity.github_read",side_effect=synthetic_identity):
            identities.login("a",{"token":OWNER_TOKEN});identities.login("b",{"token":CHECKER_TOKEN})
            self.assertEqual(identities.fresh("a")["principal"],OWNER["principal"])
            self.assertNotIn(OWNER_TOKEN,json.dumps(identities.public("a")))
            identities.logout("a")
            with self.assertRaises(PermissionError):identities.fresh("a")
            self.assertEqual(identities.public("b")["principal"],CHECKER["principal"])
            identities.sessions["b"]["expires"]=0
            self.assertEqual(identities.public("b"),{"status":"SIGNED_OUT"});self.assertEqual(identities.sessions,{})
            identities.login("a",{"token":OWNER_TOKEN})
        with patch("mission_control.operator_identity.github_read",side_effect=Invalid("Provider unavailable")):
            with self.assertRaises(Invalid):identities.fresh("a")
            self.assertEqual(identities.public("a")["status"],"SIGNED_OUT")
        with patch("mission_control.operator_identity.github_read",return_value=OWNER):identities.login("a",{"token":OWNER_TOKEN})
        with patch("mission_control.operator_identity.github_read",return_value=CHECKER):
            with self.assertRaises(PermissionError):identities.fresh("a")
            self.assertEqual(identities.sessions,{})
        for body in ({"token":"short"},{"token":OWNER_TOKEN,"principal":OWNER["principal"]},{"token":"x\n"*20},{"token":"x"*257}):
            with self.assertRaises(Invalid):identities.login("a",body)
        with self.assertRaises(PermissionError):identities.lookup("a","fixture-checker")
        with self.assertRaises(Invalid):identities.lookup("a","../user")

    def test_owner_bootstrap_role_scope_versions_and_race(self):
        with self.assertRaises(Invalid):self.access.bootstrap("review-test",STRANGER,{"confirm_owner":True})
        self.store.save_app("other",{"name":"Other app"})
        with connection(self.store.path) as db:
            with self.assertRaises(PermissionError):member(db,"other",OWNER["principal"],"OWNER")
        body={"login":STRANGER["login"],"role":"MAKER","status":"ACTIVE","version":None}
        with self.assertRaises(PermissionError):self.access.save("review-test",CHECKER,STRANGER,body)
        self.access.save("review-test",OWNER,STRANGER,body)
        with self.assertRaises(Invalid):self.access.save("review-test",OWNER,STRANGER,body)
        with self.assertRaises(Invalid):self.access.save("review-test",OWNER,STRANGER,dict(body,version=True))
        self.access.save("review-test",OWNER,STRANGER,dict(body,status="REVOKED",version=1))
        with self.assertRaises(PermissionError):self.reviews.prepare("review-test",STRANGER,{"record_id":self.record["id"]})
        with self.assertRaises(Invalid):self.access.save("review-test",OWNER,OWNER,dict(body,version=1))
        failures=[]
        def establish(user):
            try:self.access.bootstrap("other",user,{"confirm_owner":True})
            except Invalid:failures.append(user["principal"])
        threads=[threading.Thread(target=establish,args=(u,)) for u in (OWNER,CHECKER)]
        for thread in threads:thread.start()
        for thread in threads:thread.join()
        self.assertEqual(len(failures),1);self.assertEqual(len(self.access.list("other")["members"]),1)

    def test_exact_independent_approval_hash_replay_and_foreign_scope(self):
        row=self.prepare();self.assertEqual(row["hash"],digest(row["packet"]))
        self.assertEqual(row["packet"]["record"],self.record);self.assertEqual(row["packet"]["authorized_spend_minor"],0)
        with self.assertRaises(Invalid):self.reviews.approve("review-test",row["id"],OWNER,{"hash":row["hash"]})
        with self.assertRaises(PermissionError):self.reviews.approve("review-test",row["id"],STRANGER,{"hash":row["hash"]})
        with self.assertRaises(Invalid):self.reviews.approve("review-test",row["id"],CHECKER,{"hash":"wrong"})
        with self.assertRaises(Invalid):self.reviews.approve("review-test",row["id"],CHECKER,{"hash":row["hash"],"checker":OWNER["principal"]})
        approved=self.reviews.approve("review-test",row["id"],CHECKER,{"hash":row["hash"]})
        self.assertEqual(approved["status"],"VERIFIED_REVIEW_RECORDED");self.assertEqual(approved["availability"],"CURRENT")
        self.assertEqual(approved["preparer"],OWNER["principal"]);self.assertEqual(approved["checker"],CHECKER["principal"])
        with self.assertRaises(Invalid):self.reviews.approve("review-test",row["id"],CHECKER,{"hash":row["hash"]})
        self.store.save_app("other",{"name":"Other app"})
        with self.assertRaises(Invalid):self.reviews.approve("other",row["id"],CHECKER,{"hash":row["hash"]})
        self.assertEqual(self.reviews.list("other"),[])

    def test_source_manifest_expiry_hash_tamper_and_role_reactivation(self):
        for change in ("source","manifest","expiry","hash","maker_role","checker_role"):
            with self.subTest(change=change),tempfile.TemporaryDirectory() as folder:
                store=Store(Path(folder)/"case.sqlite",seed=False);record=fixture(store);reviews=Reviews(store)
                row=reviews.prepare("review-test",OWNER,{"record_id":record["id"]})
                if change=="checker_role":row=reviews.approve("review-test",row["id"],CHECKER,{"hash":row["hash"]})
                with connection(store.path) as db:
                    if change=="source":db.execute("UPDATE records SET title='Changed title' WHERE id=?",(record["id"],))
                    if change=="manifest":db.execute("UPDATE apps SET version=version+1 WHERE id='review-test'")
                    if change=="expiry":db.execute("UPDATE verified_reviews SET expires='2000-01-01T00:00:00+00:00'")
                    if change=="hash":db.execute("UPDATE verified_reviews SET hash='forged'")
                    if change in ("maker_role","checker_role"):
                        principal=OWNER["principal"] if change=="maker_role" else CHECKER["principal"]
                        db.execute("UPDATE operator_roles SET version=version+1 WHERE principal=?",(principal,))
                self.assertEqual(reviews.list("review-test")[0]["availability"],"UNAVAILABLE")
                with self.assertRaises((Invalid,PermissionError)):reviews.approve("review-test",row["id"],CHECKER,{"hash":row["hash"]})
        row=self.prepare();self.reviews.approve("review-test",row["id"],CHECKER,{"hash":row["hash"]})
        for version,status in ((1,"REVOKED"),(2,"ACTIVE")):
            self.access.save("review-test",OWNER,CHECKER,{"login":CHECKER["login"],"role":"CHECKER","status":status,"version":version})
            self.assertEqual(self.reviews.list("review-test")[0]["availability"],"UNAVAILABLE")

    def test_snapshot_does_not_transfer_approval_or_role_authority(self):
        row=self.prepare();self.reviews.approve("review-test",row["id"],CHECKER,{"hash":row["hash"]})
        snapshot=self.store.export("review-test");encoded=json.dumps(snapshot)
        self.assertNotIn(OWNER_TOKEN,encoded);self.assertNotIn("VERIFIED_REVIEW_RECORDED",encoded)
        with tempfile.TemporaryDirectory() as folder:
            restored=Store(Path(folder)/"restore.sqlite",seed=False);restored.restore(snapshot)
            self.assertFalse(Access(restored).list("review-test")["configured"])
            self.assertEqual(Reviews(restored).list("review-test"),[])
        reloaded=Store(self.store.path,seed=False)
        self.assertEqual(Reviews(reloaded).list("review-test")[0]["checker"],CHECKER["principal"])


if __name__=="__main__":unittest.main()
