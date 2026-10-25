"""Real synthetic FFmpeg/AAC decode and profile separation; no provider calls."""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from mission_control.common import Invalid
from mission_control.hypit_media import validate_video, metadata, duration, probe
from mission_control.media_native import video_metadata


def decoded(audio=True):
    video = dict(codec_type='video', codec_name='h264', pix_fmt='yuv420p', width=720, height=1280, avg_frame_rate='24/1', duration='1')
    voice = dict(codec_type='audio', codec_name='aac', sample_rate='48000', channels=2, duration='1')
    return dict(streams=[video, voice] if audio else [video], format=dict(duration='1'))


class HypitMediaTests(unittest.TestCase):
    def test_actual_audio_and_silent_videos_decode_without_weakening_native_profile(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            for audio in (False, True):
                path = folder / ('audio.mp4' if audio else 'silent.mp4')
                args = ['ffmpeg', '-v', 'error', '-nostdin', '-f', 'lavfi', '-i', 'color=c=blue:s=720x1280:r=24']
                if audio:
                    args += ['-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo', '-c:a', 'aac']
                args += ['-t', '1', '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', '-y', str(path)]
                subprocess.run(args, capture_output=True, timeout=30, check=True)
                receipt = validate_video(path, 'PORTRAIT', 1)
                self.assertEqual(receipt['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
                self.assertEqual(receipt['bytes'], path.stat().st_size)
                self.assertEqual(receipt['metadata']['audio'], audio)
                if audio:
                    with self.assertRaises(Invalid):
                        video_metadata(path)
                else:
                    self.assertFalse(video_metadata(path)['audio'])

    def test_wrong_codec_shape_frame_rate_and_timing_are_rejected(self):
        for key, bad in (('codec_name', 'vp9'), ('pix_fmt', 'yuv444p'), ('width', 1280), ('height', True), ('avg_frame_rate', '30/1'), ('duration', '1.16')):
            value = decoded()
            value['streams'][0][key] = bad
            with self.subTest(key=key), self.assertRaises(Invalid):
                metadata(value, 'PORTRAIT', 1)
        value = decoded()
        value['format']['duration'] = '2'
        with self.assertRaises(Invalid):
            metadata(value, 'PORTRAIT', 1)

    def test_unsupported_extra_and_malformed_audio_streams_reject(self):
        for key, bad in (('codec_name', 'mp3'), ('sample_rate', '44100'), ('channels', True), ('channels', 3), ('duration', '2')):
            value = decoded()
            value['streams'][1][key] = bad
            with self.subTest(key=key), self.assertRaises(Invalid):
                metadata(value, 'PORTRAIT', 1)
        for streams in ([], [None], decoded()['streams'] * 2, [decoded()['streams'][0], dict(codec_type='subtitle')], [decoded()['streams'][1]]):
            with self.subTest(streams=streams), self.assertRaises(Invalid):
                metadata(dict(streams=streams, format=dict(duration='1')), 'PORTRAIT', 1)

    def test_malformed_timing_and_decoder_payload_are_closed_errors(self):
        for value in (None, True, 'nan', 'inf', '-1', '0', [], {}):
            with self.subTest(value=value), self.assertRaises(Invalid):
                duration(value)
        for value in (None, {}, [], dict(streams=None), dict(streams=[{}], format=None)):
            with self.subTest(value=value), self.assertRaises(Invalid):
                metadata(value, 'PORTRAIT', 1)

    def test_probe_deadline_argv_and_raw_diagnostics_do_not_escape(self):
        with patch('mission_control.hypit_media.shutil.which', return_value='ffprobe'), patch('mission_control.hypit_media.capture') as run:
            run.side_effect = Invalid('PRIVATE_RAW_DIAGNOSTICS')
            with self.assertRaises(Invalid) as caught:
                probe(Path('video.mp4'))
            self.assertNotIn('PRIVATE_RAW', str(caught.exception))
            self.assertEqual(run.call_args.kwargs['timeout'], 15)
            self.assertEqual(run.call_args.args[0][3:5], ['-protocol_whitelist', 'file,pipe'])
            self.assertEqual(set(run.call_args.kwargs), {'timeout'})
            run.side_effect = None
            run.return_value = dict(code=1, stdout='', stderr='PRIVATE_RAW_DIAGNOSTICS')
            with self.assertRaisesRegex(Invalid, 'could not be decoded'):
                probe(Path('video.mp4'))
            run.return_value = dict(code=0, stdout='invalid json', stderr='')
            with self.assertRaisesRegex(Invalid, 'malformed metadata'):
                probe(Path('video.mp4'))
        with patch('mission_control.hypit_media.shutil.which', return_value=None), self.assertRaises(Invalid):
            probe(Path('video.mp4'))

    def test_missing_empty_changed_and_invalid_request_artifacts_reject(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'video.mp4'
            for raw in (None, b''):
                if raw is not None:
                    path.write_bytes(raw)
                with self.assertRaises(Invalid):
                    validate_video(path, 'PORTRAIT', 1)
            path.write_bytes(b'synthetic bytes')
            for shape, seconds in (([], 1), ('SQUARE', 1), ('PORTRAIT', True), ('PORTRAIT', 0), ('PORTRAIT', 61)):
                with self.subTest(shape=shape, seconds=seconds), self.assertRaises(Invalid):
                    validate_video(path, shape, seconds)
            def changed(_):
                path.write_bytes(b'changed bytes')
                return decoded()
            with patch('mission_control.hypit_media.probe', side_effect=changed), self.assertRaisesRegex(Invalid, 'changed'):
                validate_video(path, 'PORTRAIT', 1)
            with patch('mission_control.hypit_media.Path.read_bytes', side_effect=OSError('PRIVATE_PATH')), self.assertRaises(Invalid) as caught:
                validate_video(path, 'PORTRAIT', 1)
            self.assertNotIn('PRIVATE_PATH', str(caught.exception))
