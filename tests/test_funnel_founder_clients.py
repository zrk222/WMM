"""Current owner and scoped CLI/official MCP share private founder evidence."""
from datetime import datetime,timezone
import threading
import unittest
from unittest.mock import patch
from mission_control.common import Invalid
from mission_control.db import connection
from mission_control.funnel_store import Funnels
from mission_control.operator_client import ClientError,OperatorClient
from mission_control import funnel_founder_review as founder
from tests import test_funnel_clients as fixture
from tests import test_agent_mcp as sdk

APP='sample-one'


class FunnelFounderClientsTests(unittest.IsolatedAsyncioTestCase):
    setUp=fixture.FunnelClientsTests.setUp
    tearDown=fixture.FunnelClientsTests.tearDown
    body=fixture.FunnelClientsTests.body
    envelope=fixture.FunnelClientsTests.envelope
    grant=fixture.FunnelClientsTests.grant
    cli=fixture.FunnelClientsTests.cli
    session=fixture.FunnelClientsTests.session
    payload=fixture.FunnelClientsTests.payload

    @unittest.skipUnless(sdk.HAS_MCP,'Official MCP SDK required for founder conformance')
    async def test_actual_owner_cli_and_official_mcp_report_same_exact_private_sources(self):
        saved=Funnels(self.store).save(APP,self.payload());self.grant(['funnel.review'])
        stamp=datetime.now(timezone.utc)
        with patch.object(founder,'utc',return_value=stamp):
            expected=self.owner.request('GET','/api/apps/'+APP+'/funnels/_review?offset=0')
            self.assertEqual(self.cli(self.envelope('funnel.review',dict(offset=0))),expected)
            async with self.session()as client:
                result=await client.call_tool('wmm_funnel_review',dict(app_id=APP,input=dict(offset=0)))
                self.assertFalse(result.isError,result.content)
                self.assertEqual(result.structuredContent['data'],expected)
        self.assertEqual(expected['funnels'][0]['definition_hash'],saved['hash'])
        workspace=self.owner.request('GET','/api/apps/'+APP)
        self.assertNotIn(saved['id'],str(workspace))
        self.assertNotIn('app-sales-founder-review',str(workspace))

    def test_unsigned_ungranted_foreign_and_revoked_reads_deny_private_review(self):
        saved=Funnels(self.store).save(APP,self.payload());anonymous=OperatorClient(self.origin);anonymous.bootstrap()
        with self.assertRaises(ClientError):anonymous.request('GET','/api/apps/'+APP+'/funnels/_review')
        limited=self.grant(['growth.read'])
        with self.assertRaises(ClientError):limited.call(self.envelope('funnel.review'))
        agent=self.grant(['funnel.review'])
        with self.assertRaises(ClientError):agent.call(self.envelope('funnel.review',app_id='sample-two'))
        with self.assertRaises((ClientError,ValueError)):agent.call(self.envelope('funnel.review',dict(approved=True)))
        with connection(self.store.path)as db:db.execute("UPDATE agent_grants SET status='REVOKED',version=version+1")
        with self.assertRaises(ClientError):agent.call(self.envelope('funnel.review'))
        self.assertEqual(Funnels(self.store).read(APP,saved['id'])['hash'],saved['hash'])

    def test_raw_query_variants_reserved_id_and_post_cannot_alias_founder_read(self):
        path='/api/apps/'+APP+'/funnels/_review'
        for suffix in ('/','?extra=1','?offset=01','?offset=-1','?offset=10001','?offset=0&offset=1','/report','%2f'):
            with self.subTest(suffix=suffix),self.assertRaises(ClientError):self.owner.request('GET',path+suffix)
        with self.assertRaises(ClientError):self.owner.request('POST',path,{})
        with self.assertRaises(Invalid):Funnels(self.store).save(APP,dict(self.payload(),id='_review'))

    def test_owner_revocation_during_review_denies_final_private_readback(self):
        Funnels(self.store).save(APP,self.payload());original=founder.entry
        def revoke(*args):
            row=original(*args)
            def change():
                with connection(self.store.path)as db:db.execute("UPDATE operator_roles SET status='REVOKED',version=version+1 WHERE app_id=?",(APP,))
            thread=threading.Thread(target=change);thread.start();thread.join(timeout=5);self.assertFalse(thread.is_alive());return row
        with patch.object(founder,'entry',side_effect=revoke),self.assertRaises(ClientError):self.owner.request('GET','/api/apps/'+APP+'/funnels/_review')
