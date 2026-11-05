"""Destination failure is pre-dispatch, bounded, receipt-backed and replay-safe."""
import unittest
from unittest.mock import Mock, patch
from mission_control.aeo_transport import ReadError
from mission_control.campaign_destination import check_destination
from mission_control.common import Invalid, digest
from mission_control.db import connection
from tests import test_campaign_execution as campaign_fixture


class DestinationTests(unittest.TestCase):
    def test_public_read_receipt_does_not_store_body_or_claim_product_behavior(self):
        reader = Mock(requests=1, redirects=0)
        reader.read.return_value = dict(status=200, bytes=7, sha256='a'*64,
                                       url='https://app.example/', body=b'private')
        with patch('mission_control.campaign_destination.PublicReader', return_value=reader):
            result = check_destination('https://app.example/')
        reader.read.assert_called_once_with('https://app.example/', 1048576)
        self.assertNotIn('private', str(result))
        self.assertEqual(result['approved_link_sha256'], digest('https://app.example/'))
        self.assertIn('unverified', result['scope'])
        self.assertIsNone(check_destination(None))

    def test_malformed_private_credentials_and_query_urls_reject_before_reader(self):
        for value in ('http://app.example/', 'https://127.0.0.1/',
                      'https://u:p@app.example/', 'https://app.example/?token=secret',
                      'https://app.example/#fragment', 'https://app.example:444/'):
            with self.subTest(value=value), patch('mission_control.campaign_destination.PublicReader') as factory:
                with self.assertRaisesRegex(Invalid, 'no post was dispatched'):
                    check_destination(value)
                factory.assert_not_called()

    def test_network_blocked_redirect_deadline_and_bad_status_are_clear_failures(self):
        for code in ('ADDRESS_BLOCKED', 'REDIRECT_ORIGIN', 'DEADLINE', 'TLS_FAILED'):
            with patch('mission_control.campaign_destination.PublicReader') as factory:
                factory.return_value.read.side_effect = ReadError(code)
                with self.assertRaisesRegex(Invalid, code):
                    check_destination('https://app.example/')
        for status, size in ((404, 20), (500, 20), (200, 0), (204, 0)):
            with patch('mission_control.campaign_destination.PublicReader') as factory:
                factory.return_value.read.return_value = dict(status=status, bytes=size)
                with self.assertRaisesRegex(Invalid, 'no post was dispatched'):
                    check_destination('https://app.example/')


class DispatchTests(unittest.TestCase):
    setUp = campaign_fixture.CampaignTests.setUp

    def link_scope(self):
        post = dict(self.post, link='https://app.example/')
        post['content_hash'] = digest(dict(message=post['message'], link=post['link']))
        draft = self.service.prepare_scope('sample', 'owner',
            dict(self.body, approved_content_hashes=[post['content_hash']]))
        scope = self.service.activate_scope('sample', 'owner', draft['scope_id'], draft['approval_hash'])
        return post, scope

    def test_failed_destination_creates_no_intent_or_remote_post_and_same_request_recovers(self):
        post, scope = self.link_scope()
        with patch('mission_control.campaign_execution.check_destination', side_effect=Invalid('Destination failed')):
            with self.assertRaisesRegex(Invalid, 'Destination failed'):
                self.service.run_post('sample', 'owner', scope['scope_id'], post)
        self.assertEqual(self.transport.posts, 0)
        with connection(self.store.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM campaign_intents').fetchone()[0], 0)
        receipt = dict(status='REACHABLE', approved_link_sha256=digest(post['link']))
        with patch('mission_control.campaign_execution.check_destination', return_value=receipt):
            result = self.service.run_post('sample', 'owner', scope['scope_id'], post)
        self.assertEqual(result['status'], 'VERIFIED')
        self.assertEqual(result['result']['destination_check'], receipt)
        with patch('mission_control.campaign_execution.check_destination', side_effect=AssertionError('No replay read')):
            self.assertEqual(self.service.run_post('sample', 'owner', scope['scope_id'], post)['id'], result['id'])
            reconciled = self.service.reconcile('sample', 'owner', scope['scope_id'], result['id'])
        self.assertEqual(reconciled['result']['destination_check'], receipt)
        self.assertEqual(self.transport.posts, 1)

    def test_authority_or_unapproved_content_fails_before_destination_and_expiry_after_read_blocks(self):
        post, scope = self.link_scope()
        with patch('mission_control.campaign_execution.check_destination', side_effect=AssertionError('No unapproved fetch')):
            with self.assertRaises(PermissionError):
                self.service.run_post('sample', 'owner', scope['scope_id'], dict(post, rights_hash='c'*64))
        def revoke(_):
            self.service.revoke_scope('sample', 'owner', scope['scope_id'])
            return dict(status='REACHABLE')
        with patch('mission_control.campaign_execution.check_destination', side_effect=revoke):
            with self.assertRaises(PermissionError):
                self.service.run_post('sample', 'owner', scope['scope_id'], post)
        self.assertEqual(self.transport.posts, 0)
        with connection(self.store.path) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM campaign_intents').fetchone()[0], 0)
