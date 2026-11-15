"""Only confirmed private child termination may release a render hold."""

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mission_control.common import Invalid
from mission_control.media_native import invoke, track_children, video_metadata


class FakeChild:
    def __init__(self, uncertain=False):
        self.returncode = None
        self.uncertain = uncertain

    def poll(self):
        return self.returncode

    def terminate(self):
        pass

    def wait(self, timeout):
        if self.uncertain:
            raise OSError("synthetic unconfirmed child")
        self.returncode = -1
        return self.returncode


class RenderCleanupTests(unittest.TestCase):
    def test_cancelled_ffmpeg_requires_confirmed_wait(self):
        for uncertain in (False, True):
            with self.subTest(uncertain=uncertain), tempfile.TemporaryDirectory() as folder:
                child = FakeChild(uncertain)
                with (
                    patch("mission_control.media_native.subprocess.Popen", return_value=child),
                    track_children() as state,
                ):
                    with self.assertRaises((Invalid, OSError)):
                        invoke(
                            ["synthetic-ffmpeg"],
                            Path(folder),
                            lambda: (_ for _ in ()).throw(Invalid("cancel")),
                            float("inf"),
                        )
                    self.assertEqual(state["active"], 0)
                    self.assertEqual(state["uncertain"], uncertain)

    def test_uncertain_ffprobe_cleanup_never_proves_child_exit(self):
        with (
            patch("mission_control.media_native.subprocess.run", side_effect=OSError("synthetic uncertainty")),
            track_children() as state,
        ):
            with self.assertRaises(OSError):
                video_metadata(Path("unused"), {"ffprobe": "synthetic"})
            self.assertEqual(state["active"], 0)
            self.assertTrue(state["uncertain"])
