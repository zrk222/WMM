"""Native compilation preserves the existing shared editor contract exactly."""
import unittest
from mission_control.common import Invalid, digest
from mission_control.ios_render_plan import compile_plan
from mission_control.video_edit_contract import definition, edit


def clip(identity='first-clip', start=0, end=48, speed=100):
    return dict(id=identity, source=dict(kind='MANAGED', id='11111111-1111-1111-1111-111111111111', sha256='a'*64),
                role='DEMO', in_frame=start, out_frame=end, speed_percent=speed,
                transform=dict(crop=dict(x=1000,y=500,width=8000,height=9000),
                               rotation=90,flip_x=True,flip_y=False,fit='COVER',background='#123456'),
                effects=dict(brightness=-10,contrast=120,saturation=90), audio='RETAIN')


def project():
    return dict(title='Synthetic edit', purpose='Demonstrate the app', locale='en-US',
                output='PORTRAIT', clips=[clip(),clip('second-clip',24,72,200)])


class IOSRenderPlanTests(unittest.TestCase):
    def test_every_control_and_exact_timing_is_retained(self):
        source=project();plan=compile_plan(source)
        self.assertEqual((plan['width'],plan['height'],plan['fps']),(720,1280,24))
        self.assertEqual(plan['output_frame_count'],72)
        self.assertEqual(plan['project_sha256'],digest(definition(source)))
        for original, compiled in zip(source['clips'],plan['clips']):
            for key in ('id','source','role','speed_percent','transform','effects','audio'):
                self.assertEqual(original[key],compiled[key])
        self.assertEqual(plan['clips'][1]['output_start_frame'],48)
        self.assertEqual(plan['clips'][1]['output_frame_count'],24)
        self.assertFalse(plan['execution_authority'])
        self.assertNotIn('path',str(plan))

    def test_shared_split_and_order_commands_flow_into_native_plan(self):
        source=project()
        split=edit(source,dict(operation='split',clip_id='first-clip',at_frame=24,new_id='split-clip'))
        plan=compile_plan(split)
        self.assertEqual([c['id'] for c in plan['clips']],['first-clip','split-clip','second-clip'])
        self.assertEqual([c['output_start_frame'] for c in plan['clips']],[0,24,48])
        self.assertEqual(plan['output_frame_count'],72)

    def test_invalid_frame_speed_and_hidden_fields_rejected_by_shared_rules(self):
        source=project();source['clips'][0]['out_frame']=49;source['clips'][0]['speed_percent']=200
        with self.assertRaises(Invalid):compile_plan(source)
        source=project();source['clips'][0]['source']['path']='/private/file'
        with self.assertRaises(Invalid):compile_plan(source)

    def test_compiled_controls_are_detached_and_old_audio_defaults_to_mute(self):
        source=project();del source['clips'][0]['audio']
        plan=compile_plan(source)
        self.assertEqual(plan['clips'][0]['audio'],'MUTE')
        plan['clips'][0]['transform']['crop']['x']=9999
        self.assertEqual(source['clips'][0]['transform']['crop']['x'],1000)
