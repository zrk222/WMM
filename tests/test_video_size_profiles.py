"""Real output dimensions and later slices from bounded original footage."""
from copy import deepcopy
from pathlib import Path
import subprocess
import tempfile
import unittest

from mission_control.common import Invalid
from mission_control.hypit_authoring import FOOTAGE_SCHEMA, scene_contract
from mission_control.managed_media_validation import inspect
from mission_control.media_native import capability
from mission_control.video_edit_contract import definition, PROFILES, source_key, timing
from mission_control.video_edit_rendering import render
from tests.test_video_edit_projects import project_data
from tests.test_video_edit_render import frame


class VideoSizeTests(unittest.TestCase):
    def test_later_source_bounds_do_not_widen_finished_timeline(self):
        value = project_data('a' * 36, 'b' * 64)
        value['clips'][0].update(in_frame=66 * 24, out_frame=67 * 24)
        self.assertEqual(timing(definition(value))['total_frames'], 24)
        value['clips'][0].update(in_frame=179 * 24, out_frame=180 * 24)
        definition(value)
        value['clips'][0]['out_frame'] += 1
        with self.assertRaises(Invalid):
            definition(value)
        value['clips'][0].update(in_frame=0, out_frame=61 * 24)
        with self.assertRaises(Invalid):
            definition(value)
        scene = dict(schema=FOOTAGE_SCHEMA, title='Synthetic late source', shape='PORTRAIT',
                     scenes=[dict(text='Synthetic caption', seconds=1,
                         media=dict(id='a' * 36, sha256='b' * 64, in_frame=179 * 24, audio='MUTE'))])
        scene_contract(scene)
        scene['scenes'][0]['media']['in_frame'] += 1
        with self.assertRaises(Invalid):
            scene_contract(scene)

    def test_actual_encoded_hd_and_feed_profiles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'source.mp4'
            subprocess.run([capability()['tools']['ffmpeg'], '-v', 'error', '-f', 'lavfi', '-i',
                            'color=c=blue:s=64x36:r=24:d=1', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                            str(source)], capture_output=True, check=True, timeout=30)
            for name in ('PORTRAIT_HD', 'LANDSCAPE_HD', 'SQUARE_HD', 'FEED_PORTRAIT'):
                with self.subTest(profile=name):
                    value = project_data('a' * 36, 'b' * 64)
                    value['output'] = name
                    value['clips'][0]['out_frame'] = 24
                    folder = root / name
                    folder.mkdir()
                    _, artifact = render(folder, value,
                        {source_key(value['clips'][0]['source']): source}, lambda: None)
                    metadata = artifact['metadata']
                    self.assertEqual((metadata['width'], metadata['height']), PROFILES[name])
                    self.assertAlmostEqual(metadata['duration_seconds'], 1, delta=1 / 24)
                    self.assertFalse(metadata['audio'])

    def test_late_managed_slice_decodes_actual_late_pixels(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'long-source.mp4'
            subprocess.run([capability()['tools']['ffmpeg'], '-v', 'error', '-f', 'lavfi', '-i',
                'color=c=red:s=32x32:r=1:d=65', '-f', 'lavfi', '-i', 'color=c=lime:s=32x32:r=1:d=5',
                '-filter_complex', '[0:v][1:v]concat=n=2:v=1:a=0[v]', '-map', '[v]',
                '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', str(source)],
                capture_output=True, check=True, timeout=30)
            retained = inspect(source.read_bytes(), '.mp4')
            self.assertAlmostEqual(retained['metadata']['duration_seconds'], 70, delta=.05)
            value = project_data('a' * 36, retained['sha256'])
            value['clips'][0]['source']['kind'] = 'MANAGED'
            value['clips'][0].update(in_frame=66 * 24, out_frame=67 * 24)
            folder = root / 'edited'
            folder.mkdir()
            output, artifact = render(folder, deepcopy(value),
                {source_key(value['clips'][0]['source']): source}, lambda: None)
            pixels = frame(output, .5)
            offset = (24 * 48 + 24) * 3
            red, green, blue = pixels[offset:offset + 3]
            self.assertGreater(green, 230)
            self.assertLess(red, 10)
            self.assertLess(blue, 10)
            self.assertAlmostEqual(artifact['metadata']['duration_seconds'], 1, delta=1 / 24)


if __name__ == '__main__':
    unittest.main()
