"""Boundary and literal-injection tests for editable local Hypit authoring."""
import copy
import hashlib
import json
import unittest
from mission_control.common import Invalid
from mission_control.hypit_authoring import project, scene_contract, xml_character


def scene():
    return dict(title='Synthetic authoring fixture', shape='PORTRAIT', scenes=[dict(text='A small problem.', seconds=2), dict(text='An editable explanation.', seconds=3)])


class AuthoringTests(unittest.TestCase):
    def test_fixed_project_profile_and_deterministic_source_receipts(self):
        value = scene()
        saved = copy.deepcopy(value)
        result = project(value)
        self.assertEqual(value, saved)
        self.assertEqual(project(value), result)
        self.assertEqual(set(result['files']), {'package.json', 'film.svml', 'style.svs', 'build.svrun', 'runtime.json'})
        self.assertTrue(json.loads(result['files']['package.json'])['hypit']['project'])
        runtime = json.loads(result['files']['runtime.json'])
        self.assertEqual({e['use'] for e in runtime['endpoints'].values()}, {'@hypit/media-local', '@hypit/provider-html-local'})
        self.assertEqual(result['receipt']['duration_seconds'], 5)
        for name, text in result['files'].items():
            self.assertEqual(result['receipt']['source_hashes'][name], hashlib.sha256(text.encode()).hexdigest())
        value['scenes'][0]['text'] = 'Changed opening.'
        self.assertNotEqual(project(value)['receipt']['scene_hash'], result['receipt']['scene_hash'])
        self.assertEqual(project(value)['files']['style.svs'], result['files']['style.svs'])

    def test_markup_looking_text_remains_literal_and_cannot_add_imports(self):
        value = scene()
        value['scenes'][0]['text'] = '</typo:Flow><import from="evil"/> & {not-a-reference}'
        text = project(value)['files']['film.svml']
        self.assertIn('&lt;/typo:Flow&gt;&lt;import from="evil"/&gt; &amp; {not-a-reference}', text)
        self.assertNotIn('<import from="evil"', text)
        self.assertEqual(text.count('<import '), 7)
        self.assertNotIn('https://', text)

    def test_bounded_counts_timing_and_both_shapes(self):
        value = scene()
        value['scenes'] = [dict(text='x' * 240, seconds=5) for _ in range(12)]
        self.assertEqual(project(value)['receipt']['duration_seconds'], 60)
        self.assertIn('frame-rate="24"', project(value)['files']['film.svml'])
        value['shape'] = 'LANDSCAPE'
        self.assertIn('width="1280" height="720"', project(value)['files']['film.svml'])
        for scenes in ([], [dict(text='x', seconds=1)] * 13, [dict(text='x', seconds=15)] * 5):
            with self.subTest(scenes=len(scenes)), self.assertRaises(Invalid):
                project(dict(scene(), scenes=scenes))

    def test_closed_schema_and_malformed_fields_reject_before_emission(self):
        invalid = [None, [], {}, dict(scene(), endpoint='https://example.com'), dict(scene(), code='process.exit()'),
                   dict(scene(), package='arbitrary'), dict(scene(), shape=[]), dict(scene(), shape='SQUARE'),
                   dict(scene(), title=''), dict(scene(), title='x' * 241), dict(scene(), scenes={})]
        invalid += [dict(scene(), scenes=[item]) for item in (None, {}, dict(text='x', seconds=2, code='arbitrary'),
                    dict(text='x', seconds=True), dict(text='x', seconds=0), dict(text='x', seconds=16),
                    dict(text='x', seconds=1.5), dict(text=[], seconds=2), dict(text='x' * 241, seconds=2))]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(Invalid):
                project(value)

    def test_xml_controls_surrogates_and_noncharacters_reject_without_losing_unicode(self):
        for code in (0, 1, 8, 11, 0xD800, 0xFFFF, 0x1FFFE):
            self.assertFalse(xml_character(code))
            with self.subTest(code=code), self.assertRaises(Invalid):
                project(dict(scene(), title='x' + chr(code)))
        value = dict(scene(), title='日本語 & café 🌱')
        self.assertEqual(scene_contract(value)['title'], value['title'])
        self.assertIn('日本語 &amp; café 🌱', project(value)['files']['film.svml'])
        self.assertIn('from="2s" for="3s"', project(value)['files']['film.svml'])
