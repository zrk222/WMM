"""Boundary and literal-injection tests for editable local Hypit authoring."""

import copy
import hashlib
import json
import re
import unittest
from mission_control.common import Invalid
from mission_control.hypit_authoring import project, scene_contract, xml_character


def scene():
    return dict(
        title="Synthetic authoring fixture",
        shape="PORTRAIT",
        scenes=[dict(text="A small problem.", seconds=2), dict(text="An editable explanation.", seconds=3)],
    )


class AuthoringTests(unittest.TestCase):
    def test_captured_screen_and_caption_have_separate_reading_regions(self):
        value = dict(scene(), schema="growth.hypit-footage-scene.v1")
        value["scenes"][0]["media"] = {
            "id": "11111111-1111-1111-1111-111111111111",
            "sha256": "a" * 64,
            "in_frame": 24,
            "audio": "MUTE",
        }
        for shape in ("PORTRAIT", "LANDSCAPE"):
            with self.subTest(shape=shape):
                value["shape"] = shape
                original = copy.deepcopy(value)
                film = project(value)["files"]["film.svml"]
                regions = {}
                for name, left, top, right, bottom in re.findall(
                    r'<space:Frame id="(picture|caption)" within=\{canvas.bounds\} '
                    r'left="(\d+)%" top="(\d+)%" right="(\d+)%" bottom="(\d+)%"/>',
                    film,
                ):
                    regions[name] = tuple(map(int, (left, top, right, bottom)))
                self.assertEqual(set(regions), {"picture", "caption"})
                self.assertLess(regions["picture"][3], regions["caption"][1])
                for left, top, right, bottom in regions.values():
                    self.assertTrue(0 <= left < right <= 100 and 0 <= top < bottom <= 100)
                self.assertRegex(film, r'<visual:Clip id="clip0"[^>]+frame=\{picture\}[^>]+fit="contain"')
                self.assertRegex(film, r'<typo:Flow id="scene0"[^>]+within=\{caption\}')
                self.assertRegex(film, r'<typo:Flow id="scene1"[^>]+within=\{body\}')
                self.assertIn('from="0s" for="2s"', film)
                self.assertIn('from="2s" for="3s"', film)
                self.assertEqual(value, original)
        plain = project(scene())["files"]["film.svml"]
        self.assertNotIn('id="picture"', plain)
        self.assertNotIn('id="caption"', plain)

    def test_versioned_managed_footage_uses_fixed_media_source_and_mute(self):
        value = dict(scene(), schema="growth.hypit-footage-scene.v1")
        value["scenes"][0]["media"] = {
            "id": "11111111-1111-1111-1111-111111111111",
            "sha256": "a" * 64,
            "in_frame": 24,
            "audio": "MUTE",
        }
        result = project(value)
        self.assertEqual(scene_contract(value), value)
        film = result["files"]["film.svml"]
        self.assertIn('<media:Video id="original0" src="./assets/scene0.mp4"/>', film)
        self.assertIn('source={original0} video="primary-moving" audio="none"', film)
        self.assertIn("media={normalized0.media} during={clock.scene0}", film)
        self.assertLess(
            film.index("<film:Track source={footage0.visual}/>"), film.index("<film:Track source={title.visual}/>")
        )
        self.assertNotIn(value["scenes"][0]["media"]["id"], film)
        self.assertNotIn(value["scenes"][0]["media"]["sha256"], film)

    def test_footage_rejects_untrusted_path_audio_and_frame_ranges(self):
        value = dict(scene(), schema="growth.hypit-footage-scene.v1")
        valid = {"id": "11111111-1111-1111-1111-111111111111", "sha256": "a" * 64, "in_frame": 24, "audio": "MUTE"}
        for change in (
            {"path": "/private/video.mp4"},
            {"audio": "RETAIN"},
            {"in_frame": True},
            {"in_frame": 4319},
            {"sha256": "bad"},
            {"id": "../outside"},
        ):
            altered = copy.deepcopy(value)
            altered["scenes"][0]["media"] = {**valid, **change}
            with self.subTest(change=change), self.assertRaises(Invalid):
                project(altered)
        with self.assertRaises(Invalid):
            project(value)

    def test_fixed_project_profile_and_deterministic_source_receipts(self):
        value = scene()
        saved = copy.deepcopy(value)
        result = project(value)
        self.assertEqual(value, saved)
        self.assertEqual(project(value), result)
        self.assertEqual(
            set(result["files"]), {"package.json", "film.svml", "style.svs", "build.svrun", "runtime.json"}
        )
        self.assertTrue(json.loads(result["files"]["package.json"])["hypit"]["project"])
        runtime = json.loads(result["files"]["runtime.json"])
        self.assertEqual(
            {e["use"] for e in runtime["endpoints"].values()}, {"@hypit/media-local", "@hypit/provider-html-local"}
        )
        self.assertEqual(result["receipt"]["duration_seconds"], 5)
        for name, text in result["files"].items():
            self.assertEqual(result["receipt"]["source_hashes"][name], hashlib.sha256(text.encode()).hexdigest())
        value["scenes"][0]["text"] = "Changed opening."
        self.assertNotEqual(project(value)["receipt"]["scene_hash"], result["receipt"]["scene_hash"])
        self.assertEqual(project(value)["files"]["style.svs"], result["files"]["style.svs"])

    def test_markup_looking_text_remains_literal_and_cannot_add_imports(self):
        value = scene()
        value["scenes"][0]["text"] = '</typo:Flow><import from="evil"/> & {not-a-reference}'
        text = project(value)["files"]["film.svml"]
        self.assertIn('&lt;/typo:Flow&gt;&lt;import from="evil"/&gt; &amp; {not-a-reference}', text)
        self.assertNotIn('<import from="evil"', text)
        self.assertEqual(text.count("<import "), 7)
        self.assertNotIn("https://", text)

    def test_bounded_counts_timing_and_both_shapes(self):
        value = scene()
        value["scenes"] = [dict(text="x" * 240, seconds=5) for _ in range(12)]
        self.assertEqual(project(value)["receipt"]["duration_seconds"], 60)
        self.assertIn('frame-rate="24"', project(value)["files"]["film.svml"])
        value["shape"] = "LANDSCAPE"
        self.assertIn('width="1280" height="720"', project(value)["files"]["film.svml"])
        for scenes in ([], [dict(text="x", seconds=1)] * 13, [dict(text="x", seconds=15)] * 5):
            with self.subTest(scenes=len(scenes)), self.assertRaises(Invalid):
                project(dict(scene(), scenes=scenes))

    def test_closed_schema_and_malformed_fields_reject_before_emission(self):
        invalid = [
            None,
            [],
            {},
            dict(scene(), endpoint="https://example.com"),
            dict(scene(), code="process.exit()"),
            dict(scene(), package="arbitrary"),
            dict(scene(), shape=[]),
            dict(scene(), shape="SQUARE"),
            dict(scene(), title=""),
            dict(scene(), title="x" * 241),
            dict(scene(), scenes={}),
        ]
        invalid += [
            dict(scene(), scenes=[item])
            for item in (
                None,
                {},
                dict(text="x", seconds=2, code="arbitrary"),
                dict(text="x", seconds=True),
                dict(text="x", seconds=0),
                dict(text="x", seconds=16),
                dict(text="x", seconds=1.5),
                dict(text=[], seconds=2),
                dict(text="x" * 241, seconds=2),
            )
        ]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(Invalid):
                project(value)

    def test_xml_controls_surrogates_and_noncharacters_reject_without_losing_unicode(self):
        for code in (0, 1, 8, 11, 0xD800, 0xFFFF, 0x1FFFE):
            self.assertFalse(xml_character(code))
            with self.subTest(code=code), self.assertRaises(Invalid):
                project(dict(scene(), title="x" + chr(code)))
        value = dict(scene(), title="日本語 & café 🌱")
        self.assertEqual(scene_contract(value)["title"], value["title"])
        self.assertIn("日本語 &amp; café 🌱", project(value)["files"]["film.svml"])
        self.assertIn('from="2s" for="3s"', project(value)["files"]["film.svml"])
