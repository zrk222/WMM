"""Synthetic payment provider fixtures; actual signature bytes, SQLite and native vault."""
import copy
import secrets
import hashlib
import hmac
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from mission_control.common import Invalid, digest
from mission_control.db import connection
from mission_control.store import Store
from mission_control.review_access import Access
from mission_control.credential_vault import Vault
from mission_control.payment_signature import verify, strict_json
from mission_control.payment_sources import Sources, credential_name
from mission_control.signed_payments import Payments
from mission_control.payment_transport import read, NoRedirect
from tests.test_verified_review import OWNER,CHECKER,STRANGER

APP="payment-test"
# Ephemeral synthetic signing material; never a provider credential.
SECRET="whsec_"+secrets.token_hex(24)
CONFIG={"account_id":"acct_Synthetic123","livemode":False,"api_version":"2025-09-30.clover",
        "api_key":"rk_test_SyntheticReadOnlyKey123456","endpoint_secret":SECRET,"confirm_read":True}


class MemoryVault:
    def __init__(self):self.items={};self.fail_delete=False
    def put(self,name,value):self.items[name]=copy.deepcopy(value)
    def get(self,name):return copy.deepcopy(self.items.get(name))
    def delete(self,name):
        if self.fail_delete:raise Invalid("Synthetic native deletion unavailable")
        self.items.pop(name,None)


def snapshot(eid="evt_one",kind="charge.succeeded",oid=None):
    refund=kind.startswith("refund.");oid=oid or ("re_one" if refund else "ch_one")
    obj={"object":"refund" if refund else "charge","id":oid,"metadata":{"growth_app_id":APP},
         "customer":"cus_private","description":"private narrative","receipt_email":"private@example.test"}
    if refund:obj["charge"]="ch_one"
    return {"object":"event","id":eid,"type":kind,"created":int(time.time())-30,"livemode":False,
            "api_version":CONFIG["api_version"],"data":{"object":obj}}


def signed(body,secret=SECRET,stamp=None):
    raw=body if isinstance(body,bytes) else json.dumps(body,separators=(",",":")).encode()
    stamp=int(time.time()) if stamp is None else stamp
    mac=hmac.new(secret.encode(),str(stamp).encode()+b"."+raw,hashlib.sha256).hexdigest()
    return raw,"t="+str(stamp)+",v1="+mac


def objects():
    created=int(time.time())-20
    return {"/account":{"object":"account","id":CONFIG["account_id"]},
        "/charges/ch_one":{"object":"charge","id":"ch_one","livemode":False,"paid":True,"captured":True,
            "status":"succeeded","amount_captured":2000,"currency":"usd","metadata":{"growth_app_id":APP},
            "balance_transaction":"txn_charge"},
        "/refunds/re_one":{"object":"refund","id":"re_one","charge":"ch_one","status":"succeeded",
            "amount":2000,"currency":"usd","balance_transaction":"txn_refund"},
        "/balance_transactions/txn_charge":{"object":"balance_transaction","id":"txn_charge","source":"ch_one",
            "amount":2000,"fee":88,"net":1912,"currency":"usd","status":"available","created":created},
        "/balance_transactions/txn_refund":{"object":"balance_transaction","id":"txn_refund","source":"re_one",
            "amount":-2000,"fee":0,"net":-2000,"currency":"usd","status":"available","created":created},
        "/balance_transactions/txn_credit":{"object":"balance_transaction","id":"txn_credit","source":"re_one",
            "amount":2000,"fee":0,"net":2000,"currency":"usd","status":"available","created":created}}


class PaymentFixture:
    def __init__(self,store):
        self.store=store;self.vault=MemoryVault();self.data=objects();self.sources=Sources(store);self.payments=Payments(store)
        store.save_app(APP,{"name":"Synthetic payments","release":"1","locale":"en-US"})
        Access(store).bootstrap(APP,OWNER,{"confirm_owner":True})
        with self.context():self.source=self.sources.create(APP,OWNER,CONFIG)

    def provider(self,config,path):return copy.deepcopy(self.data[path])

    def context(self):
        from contextlib import ExitStack
        stack=ExitStack()
        stack.enter_context(patch("mission_control.payment_sources.Vault",return_value=self.vault))
        stack.enter_context(patch("mission_control.payment_sources.read",side_effect=self.provider))
        stack.enter_context(patch("mission_control.signed_payments.read",side_effect=self.provider))
        return stack

    def ingest(self,body=None):
        raw,header=signed(snapshot() if body is None else body)
        return self.payments.intake(APP,self.source["id"],raw,header)

    def reconcile(self,eid="evt_one",user=OWNER):
        receipt=next(r for r in self.payments.list(APP)["receipts"] if r["event_id"]==eid)
        return self.payments.reconcile(APP,eid,user,{"receipt_hash":receipt["hash"],"source_id":self.source["id"],"confirm_read":True})


class SignedPaymentTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/"state.sqlite",seed=False)
        self.f=PaymentFixture(self.store);self.context=self.f.context();self.context.__enter__()

    def tearDown(self):
        self.context.__exit__(None,None,None);self.tmp.cleanup()

    def test_raw_signature_freshness_multiple_candidates_and_strict_json(self):
        raw,header=signed(snapshot());verify(raw,header,SECRET)
        verify(raw,header+",v1="+"0"*64,SECRET)
        for body,sig in ((raw+b" ",header),(raw,header.replace("v1=","v0=")),(raw,header+",t=1"),
                         (raw,"t=x,v1="+"f"*64),(raw,header+",v1=nothex"),(raw,"x"*4097)):
            with self.assertRaises(PermissionError):verify(body,sig,SECRET)
        for delta in (-301,301):
            r,h=signed(snapshot(),stamp=int(time.time())+delta)
            with self.assertRaises(PermissionError):verify(r,h,SECRET)
        for raw in (b'{"a":1,"a":2}',b'{"a":NaN}',b"[]",b"\xff",b"x"*262145,b""):
            with self.assertRaises(Invalid):strict_json(raw)
        with self.assertRaises(Invalid):strict_json(('{"a":'*22+'0'+'}'*22).encode())

    def test_signed_receipt_redaction_duplicate_and_conflict(self):
        body=snapshot();self.assertFalse(self.f.ingest(body)["duplicate"])
        raw=json.dumps(body,indent=2).encode();r,h=signed(raw)
        self.assertTrue(self.f.payments.intake(APP,self.f.source["id"],r,h)["duplicate"])
        body["data"]["object"]["description"]="changed"
        with self.assertRaisesRegex(Invalid,"conflicts"):self.f.ingest(body)
        history=json.dumps(self.f.payments.list(APP))
        for forbidden in ("private@example.test","private narrative","cus_private",SECRET,CONFIG["api_key"]):
            self.assertNotIn(forbidden,history)
        self.assertEqual(len(self.f.payments.list(APP)["receipts"]),1)

    def test_wrong_scope_mode_version_shape_and_unsupported(self):
        base=snapshot()
        for changes in ({"account":"acct_another"},{"livemode":True},{"livemode":0},{"api_version":"different"},{"created":True},{"created":int(time.time())+400},{"data":[]},{"object":"v2.core.event"}):
            body=copy.deepcopy(base);body.update(changes)
            with self.assertRaises(Invalid):self.f.ingest(body)
        body=copy.deepcopy(base);body["data"]["object"]["metadata"]["growth_app_id"]="another"
        with self.assertRaises(Invalid):self.f.ingest(body)
        body=snapshot(kind="invoice.created");self.assertEqual(self.f.ingest(body)["status"],"UNSUPPORTED")
        with self.assertRaises(Invalid):self.f.reconcile()
        self.assertEqual(self.f.payments.list(APP)["cash"]["status"],"INCOMPLETE")

    def test_actual_net_cash_full_refund_negative_fees_and_object_deduplication(self):
        self.f.ingest();result=self.f.reconcile()
        self.assertEqual(result["status"],"RECONCILED")
        cash=self.f.payments.list(APP)["cash"];self.assertEqual(cash["complete_totals"][0]["net_cash_minor"],1912)
        self.f.ingest(snapshot("evt_duplicate"));self.assertEqual(self.f.reconcile("evt_duplicate")["status"],"DUPLICATE_EFFECT")
        self.f.ingest(snapshot("evt_refund","refund.created"));self.f.reconcile("evt_refund")
        cash=self.f.payments.list(APP)["cash"];self.assertEqual(cash["complete_totals"][0]["net_cash_minor"],-88)
        self.assertEqual(cash["complete_totals"][0]["refund_outflow_minor"],2000)
        self.assertEqual(len(self.f.payments.list(APP)["effects"]),2)
        self.assertEqual(self.f.reconcile()["status"],"DUPLICATE_EFFECT")

    def test_out_of_order_refund_and_actual_failed_refund_compensation(self):
        self.f.ingest(snapshot("evt_refund","refund.created"));self.f.reconcile("evt_refund")
        self.assertEqual(self.f.payments.list(APP)["cash"]["complete_totals"][0]["net_cash_minor"],-2000)
        obj=self.f.data["/refunds/re_one"];obj.update(status="failed",failure_balance_transaction="txn_credit")
        self.f.ingest(snapshot("evt_failed","refund.failed"))
        self.assertEqual(len(self.f.reconcile("evt_failed")["effects"]),2)
        self.assertEqual(self.f.payments.list(APP)["cash"]["complete_totals"][0]["net_cash_minor"],0)
        self.assertEqual(self.f.reconcile("evt_failed")["status"],"DUPLICATE_EFFECT")
        self.assertEqual(len(self.f.payments.list(APP)["effects"]),2)

    def test_failed_refund_first_reconciles_actual_debit_credit_pair_atomically(self):
        self.f.data["/refunds/re_one"].update(status="failed",failure_balance_transaction="txn_credit")
        self.f.ingest(snapshot("evt_failed","refund.failed"));self.f.reconcile("evt_failed")
        self.assertEqual(len(self.f.payments.list(APP)["effects"]),2)
        self.assertEqual(self.f.payments.list(APP)["cash"]["complete_totals"][0]["net_cash_minor"],0)

    def test_pending_fx_failed_read_and_explicit_recovery_never_guess_net(self):
        self.f.ingest()
        self.f.data["/balance_transactions/txn_charge"]["status"]="pending"
        self.assertEqual(self.f.reconcile()["status"],"PENDING")
        self.assertIsNone(self.f.payments.list(APP)["cash"]["complete_totals"])
        self.f.data["/balance_transactions/txn_charge"]["status"]="available"
        self.f.data["/balance_transactions/txn_charge"]["currency"]="eur"
        self.assertEqual(self.f.reconcile()["status"],"FX_RECONCILIATION_REQUIRED")
        self.f.data["/balance_transactions/txn_charge"]["currency"]="usd"
        with patch("mission_control.signed_payments.read",side_effect=Invalid("synthetic private failure")):
            self.assertEqual(self.f.reconcile()["status"],"FAILED")
        self.assertNotIn("synthetic private",json.dumps(self.f.payments.list(APP)))
        self.assertEqual(self.f.reconcile()["status"],"RECONCILED")
        self.assertEqual(len(self.f.payments.list(APP)["attempts"]),4)

    def test_settlement_identity_math_scope_and_immutable_conflicts(self):
        self.f.ingest()
        for path,key,value in (("/charges/ch_one","livemode",True),("/charges/ch_one","id","ch_other"),
            ("/charges/ch_one","metadata",{}),("/charges/ch_one","paid",False),
            ("/balance_transactions/txn_charge","source","ch_other"),
            ("/balance_transactions/txn_charge","net",True),("/balance_transactions/txn_charge","fee",0)):
            prior=copy.deepcopy(self.f.data[path]);self.f.data[path][key]=value
            self.assertEqual(self.f.reconcile()["status"],"FAILED")
            self.assertFalse(self.f.payments.list(APP)["effects"]);self.f.data[path]=prior
        self.f.reconcile()
        self.f.data["/balance_transactions/txn_charge"].update(fee=90,net=1910)
        self.assertEqual(self.f.reconcile()["status"],"FAILED")
        self.assertIsNone(self.f.payments.list(APP)["cash"]["complete_totals"])

    def test_owner_setup_validation_isolation_and_role_race(self):
        with self.assertRaises(PermissionError):self.f.sources.create(APP,STRANGER,CONFIG)
        for change in ({"confirm_read":False},{"api_key":"rk_live_123456789123456789"},{"api_key":"sk_test_"+"UnrestrictedKey123456789"},{"account_id":"bad"},{"livemode":0},{"endpoint_secret":"bad"}):
            with self.assertRaises(Invalid):self.f.sources.create(APP,OWNER,dict(CONFIG,**change))
        self.store.save_app("other-app",{"name":"Other app"})
        Access(self.store).bootstrap("other-app",OWNER,{"confirm_owner":True})
        with self.assertRaisesRegex(Invalid,"separate endpoint"):self.f.sources.create("other-app",OWNER,CONFIG)
        self.f.ingest()
        with self.assertRaises(PermissionError):self.f.reconcile(user=CHECKER)
        def changed(config,path):
            with connection(self.store.path) as db:db.execute("UPDATE operator_roles SET version=version+1 WHERE app_id=?",(APP,))
            return self.f.provider(config,path)
        with patch("mission_control.signed_payments.read",side_effect=changed):
            with self.assertRaisesRegex(Invalid,"changed during"):self.f.reconcile()
        self.assertFalse(self.f.payments.list(APP)["effects"])

    def test_disconnect_disables_before_failed_native_cleanup_and_can_retry(self):
        self.f.vault.fail_delete=True
        r=self.f.sources.disconnect(APP,self.f.source["id"],OWNER,{"version":1,"confirm_disconnect":True})
        self.assertEqual(r["status"],"CLEANUP_REQUIRED")
        with self.assertRaises(Invalid):self.f.ingest()
        self.f.vault.fail_delete=False
        self.f.sources.disconnect(APP,self.f.source["id"],OWNER,{"version":2,"confirm_disconnect":True})
        self.assertFalse(self.f.vault.items)
        self.assertEqual(self.f.sources.list(APP)[0]["status"],"DISCONNECTED")

    def test_fixed_read_transport_and_redirects_do_not_forward_secrets(self):
        config=dict(CONFIG)
        with patch("mission_control.payment_transport.build_opener") as opener:
            opener.return_value.open.return_value.__enter__.return_value.read.return_value=b'{"object":"account"}'
            read(config,"/account")
            request=opener.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url,"https://api.stripe.com/v1/account");self.assertEqual(request.get_method(),"GET")
            self.assertEqual(opener.return_value.open.call_args.kwargs["timeout"],15)
            for path in ("https://evil.test","/account?key=x","/charges/../account","/customers/cus_one"):
                with self.assertRaises(Invalid):read(config,path)
            for exc in (HTTPError("x",403,"secret",{},None),URLError("secret"),TimeoutError("secret")):
                opener.return_value.open.side_effect=exc
                with self.assertRaises(Invalid) as error:read(config,"/account")
                self.assertNotIn("secret",str(error.exception))
        with self.assertRaises(Invalid):NoRedirect().redirect_request(None,None,302,"",{},"https://evil.test")

    def test_unique_actual_windows_vault_roundtrip_cleanup(self):
        import uuid
        name=credential_name(self.store,APP,str(uuid.uuid4()));native=Vault()
        try:
            native.put(name,{"synthetic":"disposable payment fixture"})
            self.assertEqual(native.get(name),{"synthetic":"disposable payment fixture"})
        finally:native.delete(name)
        self.assertIsNone(native.get(name))

    def test_signature_normalize_and_numeric_boundaries_reject_ambiguous_inputs(self):
        from mission_control.payment_signature import object_id,unique_pairs,bounded_tree,signature_parts,event_scope,normalize
        from mission_control.signed_payments import integer,identity,charge_scope,settlement_currency,settlement_time,cash_amounts,cash_result,cash_report
        for value in ("person@example.test","https://evil.test","ch_","ch_"+("a"*111)):
            with self.assertRaises(Invalid):object_id(value,"ch")
        with self.assertRaises(Invalid):unique_pairs([("id",1),("id",2)])
        with self.assertRaises(Invalid):bounded_tree(float("inf"))
        with self.assertRaises(PermissionError):signature_parts("t=1,"+",".join(["v1="+"f"*64]*9))
        with self.assertRaises(Invalid):event_scope(dict(snapshot(),created=True),CONFIG)
        with self.assertRaises(Invalid):normalize(json.dumps(dict(snapshot(),data={})).encode(),CONFIG,APP)
        for value in (True,0.5,-1,10**12+1):
            with self.assertRaises(Invalid):integer(value,"cash")
        with self.assertRaises(Invalid):identity({},"charge","ch_one",False)
        with self.assertRaises(Invalid):charge_scope(dict(self.f.data["/charges/ch_one"],metadata={}),CONFIG,APP,"ch_one")
        with self.assertRaises(Invalid):settlement_currency({"currency":"USD"})
        with self.assertRaises(Invalid):settlement_time(int(time.time())+400)
        with self.assertRaises(Invalid):cash_amounts(self.f.data["/charges/ch_one"],dict(self.f.data["/balance_transactions/txn_charge"],net=7),"charge")
        with self.assertRaises(Invalid):cash_result(CONFIG,snapshot(),self.f.data["/charges/ch_one"],{},"charge")
        self.assertEqual(cash_report([],[])["status"],"NO_DATA")

    def test_source_hash_binding_declaration_and_capacity_fail_closed(self):
        from mission_control.payment_sources import decoded,protected,declaration,capacity,source
        with self.assertRaises(Invalid):credential_name(self.store,APP,"../secret")
        with self.assertRaises(Invalid):declaration(dict(CONFIG,api_version="unknown"))
        with connection(self.store.path) as db:
            row=source(db,APP,self.f.source["id"])
            altered=dict(row,data='{}')
            with self.assertRaises(Invalid):decoded(altered)
            with self.assertRaises(Invalid):capacity(db,APP,"f"*64)
        key=next(iter(self.f.vault.items));self.f.vault.items[key]["binding"]["app_id"]="another"
        with self.assertRaises(Invalid):protected(self.store,APP,row)
        self.f.vault.items.clear()
        with self.assertRaisesRegex(Invalid,"missing"):protected(self.store,APP,row)

    def test_pending_candidates_attempt_capacity_and_current_role_guards(self):
        from mission_control.signed_payments import candidate,settled_candidate,failed_refund,append_attempt,effect_once,prepare_read,current_read
        config=dict(CONFIG);obj=copy.deepcopy(self.f.data["/refunds/re_one"])
        obj.update(status="failed",balance_transaction=None)
        self.assertEqual(failed_refund(config,{"charge_id":"ch_one"},obj)["status"],"NO_EFFECT")
        obj.update(balance_transaction="txn_refund")
        self.assertEqual(failed_refund(config,{"charge_id":"ch_one"},obj)["status"],"PENDING")
        obj.update(status="pending")
        self.assertEqual(settled_candidate(config,{"charge_id":"ch_one"},obj,"refund")["status"],"PENDING")
        self.f.ingest()
        with connection(self.store.path) as db:
            receipt=db.execute("SELECT * FROM payment_receipts WHERE app_id=?",(APP,)).fetchone()
            data=json.loads(receipt["data"]);role,row,_,src=prepare_read(db,APP,"evt_one",OWNER,{"receipt_hash":receipt["hash"],"source_id":self.f.source["id"]})
            current_read(db,APP,OWNER,src,role)
            with self.assertRaises(Invalid):prepare_read(db,APP,"evt_one",OWNER,{"receipt_hash":"bad","source_id":src["id"]})
            self.assertEqual(candidate(config,data,APP)["status"],"RECONCILED")
            effects=candidate(config,data,APP)["effects"]
            self.assertEqual(effect_once(db,APP,effects)["status"],"RECONCILED")
            self.assertEqual(effect_once(db,APP,effects)["status"],"DUPLICATE_EFFECT")
            for number in range(100):append_attempt(db,APP,"evt_one",{"status":"PENDING"})
            with self.assertRaises(Invalid):append_attempt(db,APP,"evt_one",{"status":"PENDING"})

    def test_one_hundred_receipt_reporting_is_bounded_local_fixture(self):
        for number in range(100):self.f.ingest(snapshot("evt_"+str(number)))
        started=time.perf_counter();rows=self.f.payments.list(APP)
        self.assertEqual(len(rows["receipts"]),100);self.assertLess(time.perf_counter()-started,10)
