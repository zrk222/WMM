"""Real edited-MP4 CLI/MCP parity and exact human preview/download readbacks."""
import json
import os
import subprocess
import sys
import unittest
from urllib.request import Request
from urllib.error import HTTPError
from mission_control.operator_client import ClientError
from mission_control.worker import run_once
from tests import test_video_edit_clients as fixture
from tests import test_agent_mcp as sdk

APP='sample-one'


class EditRenderClientTests(unittest.IsolatedAsyncioTestCase):
    body=fixture.VideoClientsTests.body
    envelope=fixture.VideoClientsTests.envelope
    session=fixture.VideoClientsTests.session
    grant=fixture.VideoClientsTests.grant
    create=fixture.VideoClientsTests.create
    cli=fixture.VideoClientsTests.cli

    def setUp(self):
        fixture.VideoClientsTests.setUp(self)
        self.data['clips'][0]['out_frame']=48
        self.project=self.create()

    def tearDown(self):fixture.VideoClientsTests.tearDown(self)

    def payload(self,key='client-edited-video'):
        return dict(data=dict(project_id=self.project['id'],revision=self.project['revision'],project_hash=self.project['hash']),request_key=key)

    def test_edit_clients_exact_owner_queue_download_seek_scope_and_unknown_field_rejection(self):
        base='/api/apps/'+APP+'/video-edit-renders'
        queued=self.owner.request('POST',base,self.payload())
        self.assertEqual(self.owner.request('POST',base,self.payload())['id'],queued['id'])
        self.assertTrue(run_once(self.store))
        history=self.owner.request('GET',base);row=history['items'][0]
        self.assertEqual(row['job_id'],queued['id'])
        preview=self.origin+base+'/'+row['id']+'/preview'
        with self.owner.opener.open(Request(preview,headers={'Origin':self.origin})) as response:
            raw=response.read();self.assertEqual(response.headers.get_content_type(),'video/mp4')
            self.assertGreater(len(raw),0)
        with self.owner.opener.open(Request(preview,headers={'Origin':self.origin,'Range':'bytes=2-8'})) as response:
            self.assertEqual(response.status,206);self.assertEqual(response.read(),raw[2:9])
        with self.owner.opener.open(Request(preview.replace('/preview','/download'),headers={'Origin':self.origin})) as response:
            self.assertEqual(response.read(),raw);self.assertIn('attachment',response.headers['Content-Disposition'])
        for path in (preview+'?extra=1',preview.replace(APP,'sample-two'),preview.replace('/preview','/unknown')):
            with self.assertRaises(HTTPError):self.owner.opener.open(Request(path,headers={'Origin':self.origin}))
        agent=self.grant(['editor.renders'])
        self.assertEqual(agent.call(self.envelope('editor.renders'))['items'][0]['id'],row['id'])
        with self.assertRaises(ClientError):agent.call(self.envelope('editor.queue',self.payload('ungranted')))
        agent=self.grant(['editor.queue'])
        with self.assertRaises((ClientError,ValueError)):agent.call(self.envelope('editor.queue',dict(self.payload('invalid'),shell='arbitrary')))
        with self.assertRaises(ClientError):agent.call(self.envelope('editor.queue',self.payload('foreign'),app_id='sample-two'))
        with self.assertRaises(ClientError):self.owner.request('POST','/api/apps/'+APP+'/jobs',dict(action='edit_render',data={},request_key='bypass'))

    @unittest.skipUnless(sdk.HAS_MCP,'Official MCP SDK required for edited render acceptance')
    async def test_edit_clients_cli_queue_actual_mcp_replay_and_render_history(self):
        self.grant(['editor.queue','editor.renders','jobs.read'])
        queued=self.cli(self.envelope('editor.queue',self.payload()))
        async with self.session() as client:
            tools={row.name for row in (await client.list_tools()).tools}
            self.assertTrue({'wmm_editor_queue','wmm_editor_renders'} <= tools)
            repeated=await client.call_tool('wmm_editor_queue',dict(app_id=APP,input=self.payload()))
            self.assertFalse(repeated.isError,repeated.content)
            self.assertEqual(repeated.structuredContent['data']['id'],queued['id'])
            self.assertTrue(run_once(self.store))
            result=await client.call_tool('wmm_editor_renders',dict(app_id=APP,input={}))
            self.assertFalse(result.isError,result.content)
            row=result.structuredContent['data']['items'][0]
            self.assertEqual(row['job_id'],queued['id'])
            self.assertEqual(row['data']['artifact']['metadata']['duration_seconds'],2.0)
            self.assertNotIn(self.token,json.dumps(result.structuredContent))
