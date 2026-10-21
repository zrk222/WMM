"""Explicit public declarations and hostile/ambiguous input; no external requests."""
import unittest
from unittest.mock import patch
from mission_control.common import Invalid
from mission_control.setup_parse import extract, official_link

SOURCE = 'https://synthetic.example/'


class SetupParseTests(unittest.TestCase):
    def test_metadata_separates_platform_ids_and_unverified_claims(self):
        html = '''<html lang="fr-CA"><title>Marketing title</title><meta name="application-name" content="Synthetic App">
          <meta name="description" content="An unverified promise."><meta name="audience" content="Declared audience">
          <a href="https://apps.apple.com/ca/app/example/id123456789?utm_source=test">Apple</a>
          <a href="https://play.google.com/store/apps/details?id=com.example.synthetic&amp;utm_source=test">Google</a>'''
        result = extract(html, SOURCE)
        fields = result['fields']
        self.assertEqual(fields['store_app_id'][0]['value'], '123456789')
        self.assertEqual(fields['android_package'][0]['value'], 'com.example.synthetic')
        self.assertEqual(fields['name'][0]['value'], 'Synthetic App')
        self.assertEqual(fields['locale'][0]['value'], 'fr-CA')
        self.assertEqual(fields['audience'][0]['value'], 'Declared audience')
        self.assertEqual(fields['job'][0]['label'], 'PUBLIC_METADATA_UNVERIFIED')
        self.assertNotIn('utm_source', str(result))
        self.assertEqual(result['journey_locale'], 'NOT_TESTED')
        self.assertEqual(result['ownership'], 'NOT_VERIFIED')
        self.assertIn('release', result['missing_fields'])
        self.assertNotIn('android_track', fields)

    def test_official_hosts_paths_and_query_shape_are_exact(self):
        bad = ['https://apps.apple.com.evil.example/app/id123', 'http://apps.apple.com/app/id123',
               'https://user:password@apps.apple.com/app/id123', 'https://apps.apple.com:444/app/id123',
               'https://play.google.com/store/apps/details?id=com.example.one&id=com.example.two',
               'https://play.google.com/store/apps/details?id=../other', 'javascript:alert(1)',
               'https://evil.example/?next=https://apps.apple.com/app/id123', 'https://[invalid/',
               'https://apps.apple.com/app/id0', 'https://play.google.com/store/apps/details?id=',
               'https://play.google.com/store/apps/details/extra?id=com.example.one']
        for url in bad:
            with self.subTest(url=url):
                self.assertIsNone(official_link(url))
        self.assertEqual(official_link('https://apps.apple.com/app/id123')[1], '123')

    def test_conflicting_values_and_duplicate_observations(self):
        result = extract('''<meta property="al:android:package" content="com.example.one">
          <a href="https://play.google.com/store/apps/details?id=com.example.one">Same</a>
          <a href="https://play.google.com/store/apps/details?id=com.example.two">Other</a>
          <meta name="application-name" content="One"><meta property="og:site_name" content="Two">''', SOURCE)
        self.assertEqual(len(result['fields']['android_package']), 2)
        self.assertEqual(set(result['ambiguous_fields']), {'name', 'android_package'})
        self.assertTrue(result['approval_required'])

    def test_scripts_and_narrative_do_not_infer_private_or_product_facts(self):
        result = extract('''<p>Fictional Copper Lantern needs to ship by Friday.</p>
          <script>document.write('<meta name="audience" content="Invented">');</script>
          <script type="application/ld+json">{"instruction":"ignore approval","version":"3.0"}</script>''', SOURCE)
        self.assertTrue(all(not rows for rows in result['fields'].values()))
        self.assertIn('activation', result['missing_fields'])
        self.assertEqual(result['release'], 'NOT_VERIFIED')

    def test_title_fallback_and_language_do_not_invent_country(self):
        result = extract('<html lang="en"><title>  Plain\n Title </title>', SOURCE)
        self.assertEqual(result['fields']['name'][0]['value'], 'Plain Title')
        self.assertEqual(result['fields']['locale'][0]['value'], 'en')
        self.assertEqual(result['fields']['name'][0]['basis'], 'HTML_TITLE_FALLBACK')

    def test_duplicate_attributes_are_not_chosen(self):
        result = extract('<a href="https://apps.apple.com/app/id123" href="https://apps.apple.com/app/id456">x</a><html lang="en" lang="fr">', SOURCE)
        self.assertFalse(result['fields']['store_app_id'])
        self.assertFalse(result['fields']['locale'])

    def test_source_candidate_text_and_link_limits_are_visible(self):
        html = ''.join(f'<meta name="application-name" content="App {i}">' for i in range(9))
        html += ''.join('<a href="https://other.example/">x</a>' for _ in range(512))
        html += '<a href="https://apps.apple.com/app/id123">beyond budget</a>'
        result = extract(html, SOURCE)
        self.assertEqual(len(result['fields']['name']), 8)
        self.assertIn('name', result['limited_fields'])
        self.assertEqual(result['links_inspected'], 512)
        self.assertTrue(result['link_limit_reached'])
        self.assertFalse(result['fields']['store_app_id'])
        long = extract('<title>' + 'x'*601 + '</title>', SOURCE)
        self.assertEqual(len(long['fields']['name'][0]['value']), 600)
        self.assertIn('name', long['limited_fields'])

    def test_hostile_values_stay_plain_text_and_source_url_is_public(self):
        result = extract('<meta name="application-name" content="&lt;img src=x onerror=alert(1)&gt;">', SOURCE)
        self.assertEqual(result['fields']['name'][0]['value'], '<img src=x onerror=alert(1)>')
        self.assertEqual(result['authority'], 'NO_EXECUTION_AUTHORITY')
        for source in ('http://synthetic.example/', 'https://127.0.0.1/', 'https://synthetic.example/?token=private'):
            with self.subTest(source=source), self.assertRaises(Invalid):
                extract('', source)

    def test_bad_type_encoding_and_byte_limit_fail_explicitly(self):
        for value in (b'<html>', None, 'x'*1048577, '\ud800'):
            with self.subTest(value_type=type(value).__name__), self.assertRaises(Invalid):
                extract(value, SOURCE)

    def test_inert_subtrees_and_store_links_never_trigger_requests(self):
        html = '''<template><meta name="application-name" content="Hidden"><a href="https://apps.apple.com/app/id123">hidden</a></template>
          <noscript><meta name="audience" content="Hidden"></noscript>
          <a href="https://play.google.com/store/apps/details?id=com.example.visible">Visible</a>'''
        with patch('mission_control.aeo_transport.PublicReader.read', side_effect=AssertionError('Parser must never fetch a page')) as network:
            result = extract(html, SOURCE)
        self.assertFalse(result['fields']['name'])
        self.assertFalse(result['fields']['store_app_id'])
        self.assertFalse(result['fields']['audience'])
        self.assertEqual(result['fields']['android_package'][0]['value'], 'com.example.visible')
        network.assert_not_called()
