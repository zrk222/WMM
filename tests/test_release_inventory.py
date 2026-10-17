"""Explicit synthetic release facts; never provider approval or image authenticity."""
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from mission_control.common import Invalid
from mission_control.release_inventory import read_inventory, Inventory, resource_id, dict_query, screenshot
from mission_control.provider_reports import read_report, report_options
from mission_control.providers import report_destination
from mission_control.store import Store
from mission_control.service import Service
from mission_control.worker import run_once

BINDING = {'provider': 'app_store', 'store_app_id': '123', 'account_id': '0', 'env_ref': 'GROWTH_SAMPLE_ONE_SYNTHETIC'}


def row(kind, identity, attrs, relation=None, owner=None):
    result = {'type': kind, 'id': identity, 'attributes': attrs}
    if relation:
        result['relationships'] = {relation: {'data': {'id': owner}}}
    return result


def fixtures():
    version = row('appStoreVersions', 'version-1', {'versionString': '1.0', 'platform': 'IOS', 'appStoreState': 'WAITING_FOR_REVIEW'}, 'app', '123')
    version['relationships']['build'] = {'data': {'id': 'build-1'}}
    build = row('builds', 'build-1', {'version': '42', 'processingState': 'VALID'})
    locale = row('appStoreVersionLocalizations', 'locale-1', {'locale': 'en-US', 'description': 'Synthetic description', 'keywords': '', 'supportUrl': 'https://example.com'}, 'appStoreVersion', 'version-1')
    display = row('appScreenshotSets', 'set-1', {'screenshotDisplayType': 'APP_IPHONE_67'}, 'appStoreVersionLocalization', 'locale-1')
    image = row('appScreenshots', 'image-1', {'fileName': '<img src=x onerror=alert(1)>.png', 'sourceFileChecksum': 'abc', 'assetDeliveryState': {'state': 'COMPLETE'}, 'imageAsset': {'width': 1290, 'height': 2796, 'templateUrl': 'PRIVATE-ASSET-URL'}, 'uploadOperations': ['PRIVATE-UPLOAD']}, 'appScreenshotSet', 'set-1')
    return [{'data': version, 'included': [build]}, {'data': [locale], 'links': {}}, {'data': [display], 'links': {}}, {'data': [image], 'links': {}}]


class FakeReader:
    def __init__(self, pages):
        self.pages, self.calls = iter(pages), []

    def read(self, url):
        self.calls.append(url)
        return next(self.pages)


class ReleaseInventory(unittest.TestCase):
    def test_owned_release_projection_and_order(self):
        pages = fixtures()
        second = copy.deepcopy(pages[-1]['data'][0]); second['id'] = 'image-2'; second['attributes']['fileName'] = 'second.png'
        pages[-1]['data'].append(second)
        reader = FakeReader(pages)
        result = read_inventory(reader, '123', 'version-1')
        self.assertEqual(result['coverage'], 'COMPLETE')
        self.assertEqual(result['build']['number'], '42')
        self.assertEqual(result['locales'][0]['missing_fields'], ['keywords'])
        images = result['locales'][0]['screenshot_sets'][0]['screenshots']
        self.assertEqual([x['id'] for x in images], ['image-1', 'image-2'])
        self.assertEqual(result['requests'], 4)
        self.assertNotIn('PRIVATE-', json.dumps(result))
        self.assertIn('include=app%2Cbuild', reader.calls[0])

    def test_empty_resources_are_not_fabricated(self):
        pages = fixtures()[:2]; pages[0]['data']['relationships']['build']['data'] = None; pages[1]['data'] = []
        result = read_inventory(FakeReader(pages), '123', 'version-1')
        self.assertEqual(result['locales'], [])
        self.assertIsNone(result['build'])
        self.assertIn('separate verification', result['interpretation'])

    def test_rejects_ids_before_credential_and_foreign_parent_before_children(self):
        for identity in ('../other', 'x?secret=y', '', 'é', 'a'*81, True, 123):
            with self.subTest(identity=identity), patch('mission_control.provider_reports.credential') as secret, self.assertRaises(Invalid):
                read_report(BINDING, 'sample-one', {'operation': 'release_inventory', 'version_id': identity})
            secret.assert_not_called()
        for kind in ('app', 'identity', 'type'):
            pages = fixtures()
            if kind == 'app': pages[0]['data']['relationships']['app']['data']['id'] = '999'
            if kind == 'identity': pages[0]['data']['id'] = 'other'
            if kind == 'type': pages[0]['data']['type'] = 'builds'
            reader = FakeReader(pages)
            with self.assertRaises(Invalid): read_inventory(reader, '123', 'version-1')
            self.assertEqual(len(reader.calls), 1)

    def test_pagination_duplicates_and_hostile_links(self):
        path = '/v1/appStoreVersions/version-1/appStoreVersionLocalizations'
        for link in ('https://evil.example/x', 'https://api.appstoreconnect.apple.com'+path+'?limit=100', 'https://api.appstoreconnect.apple.com/v1/other?cursor=x', 17):
            pages = fixtures(); pages[1]['links']['next'] = link
            with self.subTest(link=link), self.assertRaises(Invalid): read_inventory(FakeReader(pages), '123', 'version-1')
        pages = fixtures(); duplicate = copy.deepcopy(pages[1]['data'][0]); duplicate['attributes']['locale'] = 'fr-FR'; pages[1]['data'].append(duplicate)
        with self.assertRaises(Invalid): read_inventory(FakeReader(pages), '123', 'version-1')
        for wrong in ({'data': [], 'links': None}, {'data': [fixtures()[1]['data'][0]]*101, 'links': {}}):
            with self.assertRaises(Invalid): read_inventory(FakeReader([fixtures()[0], wrong]), '123', 'version-1')

    def test_request_cap_and_exact_cursor_query(self):
        path = '/v1/appStoreVersions/version-1/appStoreVersionLocalizations'
        pages = [{'data': [], 'links': {'next': 'https://api.appstoreconnect.apple.com'+path+'?cursor='+str(i)}} for i in range(30)]
        inventory = Inventory(FakeReader(pages)); rows, complete = inventory.collection(path, 'appStoreVersionLocalizations', 'appStoreVersion', 'version-1')
        self.assertFalse(complete); self.assertEqual(inventory.requests, 24); self.assertEqual(inventory.uninspected, [path])
        self.assertEqual(dict_query('cursor=a%2Bb&x=1&x=2'), [('cursor', 'a+b'), ('x', '1'), ('x', '2')])
        for cursor in ('broken', 'x='+'a'*4001):
            with self.assertRaises(Invalid): dict_query(cursor)

    def test_malformed_children_and_fixed_transport(self):
        for index, relation in ((1, 'appStoreVersion'), (2, 'appStoreVersionLocalization'), (3, 'appScreenshotSet')):
            pages = fixtures(); pages[index]['data'][0]['relationships'][relation]['data']['id'] = 'foreign'
            with self.assertRaises(Invalid): read_inventory(FakeReader(pages), '123', 'version-1')
        image = fixtures()[-1]['data'][0]; image['attributes']['imageAsset']['width'] = True
        with self.assertRaises(Invalid): screenshot(image)
        for url in ('https://api.appstoreconnect.apple.com/v1/appStoreVersions/version-1', 'https://api.appstoreconnect.apple.com/v1/appScreenshotSets/set-1/appScreenshots'):
            report_destination(url, None)
            with self.assertRaises(Invalid): report_destination(url, {})
        with self.assertRaises(Invalid): report_options('apple_ads', {'operation': 'release_inventory', 'version_id': 'version-1'})
        with self.assertRaises(Invalid): report_options('app_store', {'operation': 'release_inventory', 'version_id': 'version-1', 'extra': True})

    def test_partial_inventory_and_missing_build_or_malformed_metadata(self):
        pages = fixtures()
        locales = [row('appStoreVersionLocalizations', 'locale-'+str(i), {'locale':'synthetic-'+str(i)}, 'appStoreVersion', 'version-1') for i in range(30)]
        result = read_inventory(FakeReader([pages[0], {'data':locales,'links':{}}]+[{'data':[],'links':{}}]*30), '123', 'version-1')
        self.assertEqual(result['coverage'], 'PARTIAL')
        self.assertEqual(result['requests'], 24)
        self.assertEqual(len(result['locales']), 30)
        self.assertEqual(len(result['uninspected']), 8)
        self.assertTrue(any(x['coverage']=='PARTIAL' for x in result['locales']))
        for failure in ('build_missing', 'build_duplicate', 'metadata_type', 'delivery_type', 'relationship_type'):
            pages = fixtures()
            if failure=='build_missing': pages[0]['included']=[]
            if failure=='build_duplicate': pages[0]['included']*=2
            if failure=='metadata_type': pages[1]['data'][0]['attributes']['description']={'bad':True}
            if failure=='delivery_type': pages[3]['data'][0]['attributes']['assetDeliveryState']=['bad']
            if failure=='relationship_type': pages[1]['data'][0]['relationships']=[]
            with self.subTest(failure=failure), self.assertRaises(Invalid): read_inventory(FakeReader(pages),'123','version-1')

    def test_durable_failure_preserves_binding_then_explicit_read_succeeds(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'GROWTH_SAMPLE_ONE_SYNTHETIC': 'synthetic-key'}):
            store = Store(Path(folder)/'test.sqlite'); service = Service(store)
            binding = store.save_record('sample-one', {'kind':'connection','title':'Synthetic','source':'Synthetic fixture','data':BINDING})
            body = {'action':'sync','data':{'connection_id':binding['id'],'connection_version':binding['version'],'options':{'operation':'release_inventory','version_id':'version-1'}},'request_key':'fixture-fail'}
            first = service.queue('sample-one', body)
            with patch('mission_control.provider_reports.report_request', side_effect=Invalid('Synthetic read timeout')): run_once(store)
            self.assertEqual(service.workspace('sample-one')['jobs'][0]['status'], 'BLOCKED')
            self.assertEqual(store.records('sample-one')[0]['hash'], binding['hash'])
            service.queue('sample-one', {**body, 'request_key':'fixture-retry'})
            with patch('mission_control.provider_reports.report_request', side_effect=fixtures()): run_once(store)
            latest = service.workspace('sample-one')['jobs'][0]
            self.assertEqual(latest['status'], 'SUCCEEDED')
            self.assertFalse(latest['result']['external_writes'])
            self.assertEqual(len(latest['result']['page_source_hashes']), 4)
            self.assertNotIn('synthetic-key', json.dumps(latest['result']))


if __name__ == '__main__':
    unittest.main()
