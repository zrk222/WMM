"""Real server callback routing retains self-only assets and never exchanges on GET."""
import unittest
from unittest.mock import patch
from tests import test_managed_media_http as media


class DriveCallbackHTTPTests(unittest.TestCase):
    setUp = media.MediaHTTPTests.setUp
    tearDown = media.MediaHTTPTests.tearDown
    send = media.MediaHTTPTests.send

    def test_drive_and_play_callbacks_remain_distinct_without_get_exchange(self):
        with patch('mission_control.drive_auth.exchange') as exchange:
            code, raw, headers = self.send('GET', '/?state=drive_'+'a'*43+'&code=synthetic-code')
            self.assertEqual(code, 200); self.assertIn(b'/drive-callback.js', raw)
            self.assertNotIn(b'/play-callback.js', raw); self.assertIn("script-src 'self'", headers['Content-Security-Policy'])
            code, raw, _ = self.send('GET', '/?state=play_synthetic&code=synthetic-code')
            self.assertEqual(code, 200); self.assertIn(b'/play-callback.js', raw)
            exchange.assert_not_called()

    def test_only_exact_callback_assets_are_served(self):
        for asset, expected in [('/drive-callback.js','javascript'),('/drive-callback.css','css')]:
            code, raw, headers = self.send('GET', asset)
            self.assertEqual(code, 200); self.assertIn(expected, headers['Content-Type']); self.assertGreater(len(raw), 100)
        self.assertNotEqual(self.send('GET', '/drive-callback.html')[0], 200)
