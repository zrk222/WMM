"""LinkedIn video render intent preserves its independently prepared text copy."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mission_control.common import Invalid
from mission_control.creative_briefs import Briefs
from mission_control.creative_rendering import current_request, render_request
from mission_control.db import connection
from mission_control.hypit_jobs import HypitRenders, brief_scene, resolve_inputs
from mission_control.store import Store
from tests.test_creative_rendering import APP, prepared_render


class LinkedInRenderContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "state.sqlite")
        original, _ = prepared_render(self.store)
        self.definition = original["data"]["definition"]

    def save_brief(self, channel):
        brief = Briefs(self.store).save(APP, {"data": dict(self.definition, channel=channel)})
        return brief, dict(brief_id=brief["id"], brief_hash=brief["hash"], shape="PORTRAIT")

    def test_explicit_linkedin_video_render_keeps_beats_and_text_copy(self):
        brief, body = self.save_brief("LINKEDIN")
        copy = brief["data"]["content"]["copy"]
        with connection(self.store.path) as db:
            frozen = render_request(db, self.store, APP, body)
            current_request(db, self.store, APP, frozen)
            hypit, sources = resolve_inputs(db, self.store, APP, body)
        self.assertEqual(hypit["request"], frozen)
        self.assertEqual(sources, {})
        self.assertEqual(frozen["captions"], [beat["script"] for beat in brief["data"]["content"]["beats"]])
        scene = brief_scene(frozen)
        self.assertEqual(
            scene,
            {
                "title": brief["data"]["app"]["name"],
                "shape": "PORTRAIT",
                "scenes": [
                    {"text": beat["script"], "seconds": seconds}
                    for beat, seconds in zip(brief["data"]["content"]["beats"], (8, 8, 7, 7), strict=True)
                ],
            },
        )
        self.assertEqual(Briefs(self.store).list(APP)[0]["current"]["data"]["content"]["copy"], copy)
        self.assertEqual(frozen["brief"], brief)
        with patch(
            "mission_control.hypit_jobs.identity", return_value={"launcher": "fixture", "launcher_sha256": "0" * 64}
        ):
            queued = HypitRenders(self.store).queue(APP, {"data": body, "request_key": "linkedin-video"})
        self.assertEqual(queued["data"]["request"], frozen)

    def test_linkedin_keeps_source_integrity_and_readability_guards(self):
        brief, body = self.save_brief("LINKEDIN")
        with connection(self.store.path) as db:
            frozen = render_request(db, self.store, APP, body)
            with self.assertRaisesRegex(Invalid, "changed"):
                current_request(db, self.store, APP, dict(frozen, captions=["forged"]))
        app = self.store.app(APP)
        self.store.save_app(APP, dict(app["data"], name="Changed app"), app["version"])
        with connection(self.store.path) as db, self.assertRaisesRegex(Invalid, "brief proof"):
            render_request(db, self.store, APP, body)

    def test_x_stays_text_only_and_linkedin_stale_hash_is_rejected(self):
        _, text = self.save_brief("X")
        with connection(self.store.path) as db, self.assertRaisesRegex(Invalid, "brief"):
            render_request(db, self.store, APP, text)
        _, video = self.save_brief("LINKEDIN")
        with connection(self.store.path) as db, self.assertRaisesRegex(Invalid, "changed"):
            render_request(db, self.store, APP, dict(video, brief_hash="0" * 64))


if __name__ == "__main__":
    unittest.main()
