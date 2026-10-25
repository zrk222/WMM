"""Current source discovery is shared by owner HTTP, grant CLI and official MCP."""
import json
import unittest
from unittest.mock import patch
from mission_control.managed_media_store import Media
from mission_control.operator_client import ClientError
from tests.test_managed_media_store import RAW, synthetic_inspection
from tests import test_agent_grants as grants
from tests import test_video_edit_clients as editing
from tests import test_agent_mcp as sdk
from tests import test_verified_review as identities

APP='sample-one'


class MediaSourceClientsTests(unittest.IsolatedAsyncioTestCase):
    setUp=grants.GrantTests.setUp
    tearDown=grants.GrantTests.tearDown
    body=grants.GrantTests.body
    envelope=grants.GrantTests.envelope
    grant=editing.VideoClientsTests.grant
    cli=editing.VideoClientsTests.cli
    session=editing.VideoClientsTests.session

    def uploaded(self,app=APP):
        with patch('mission_control.managed_media_store.inspect',side_effect=synthetic_inspection):
            return Media(self.store).upload(app,'PRIVATE_FILE_NAME.mp4',RAW,dict(manifest_version=1,request_key='source-fixture'))

    def review(self,row,status,version):
        return Media(self.store).review(APP,row['id'],dict(expected_version=version,manifest_version=1,source_sha256=row['source_sha256'],status=status,basis='OWNED',evidence='PRIVATE_PERMISSION_EVIDENCE'),identities.OWNER)

    @unittest.skipUnless(sdk.HAS_MCP,'Official MCP SDK required for source discovery acceptance')
    async def test_sources_owner_cli_mcp_match_and_follow_revocation_without_private_evidence(self):
        row=self.uploaded();self.uploaded('sample-two');self.review(row,'ALLOWED',0)
        self.grant(['media.sources'])
        owner=self.owner.request('GET','/api/apps/'+APP+'/media/sources')
        cli=self.cli(self.envelope('media.sources'))
        self.assertEqual(owner,cli)
        self.assertEqual(len(cli['items']),1)
        self.assertEqual(cli['items'][0]['id'],row['id'])
        self.assertTrue(cli['items'][0]['reuse_available'])
        for private in ('PRIVATE_PERMISSION_EVIDENCE','PRIVATE_FILE_NAME',str(self.store.path.parent),'latest_review','review_history','storage_name'):
            self.assertNotIn(private,json.dumps(cli))
        async with self.session() as client:
            value=await client.call_tool('wmm_media_sources',dict(app_id=APP,input={}))
            self.assertFalse(value.isError,value.content)
            self.assertEqual(value.structuredContent['data'],owner)
            self.review(row,'REVOKED',1)
            value=await client.call_tool('wmm_media_sources',dict(app_id=APP,input={}))
            self.assertFalse(value.isError,value.content)
            self.assertFalse(value.structuredContent['data']['items'][0]['reuse_available'])
            self.assertEqual(value.structuredContent['data']['items'][0]['rights_status'],'REVOKED')

    def test_sources_missing_grant_and_foreign_app_are_denied(self):
        self.uploaded()
        agent=self.grant(['jobs.read'])
        with self.assertRaises(ClientError):agent.call(self.envelope('media.sources'))
        agent=self.grant(['media.sources'])
        with self.assertRaises(ClientError):agent.call(self.envelope('media.sources',app_id='sample-two'))
        with self.assertRaises((ClientError,ValueError)):agent.call(self.envelope('media.sources',dict(path='PRIVATE_PATH')))
        self.assertEqual(Media(self.store).sources('sample-two')['items'],[])

    def test_sources_operation_is_explicitly_mapped_without_enabling_complete_editor_autonomy(self):
        from mission_control.automation_requirements import workflow_catalog
        catalog=workflow_catalog();workflows=catalog['workflows']
        self.assertIn('media.sources',workflows['video_authoring_editing']['operations'])
        self.assertIn('COMPLETE_AGENT_AND_HUMAN_EDITOR_REQUIRED',workflows['video_authoring_editing']['blockers'])
        self.assertNotIn('media.sources',workflows['paid_effects']['operations'])
        self.assertEqual({name for row in workflows.values()for name in row['operations']},set(catalog['operations']))
