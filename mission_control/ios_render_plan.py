"""Compile the authoritative editor timeline into a data-only native render plan."""
from copy import deepcopy
from .common import digest
from .video_edit_contract import definition, output_frames, PROFILES, FPS


def compile_plan(project):
    """Retain all editing controls and original source identities, never file paths.

    This is a compilation result, not permission or evidence of a decoded output.
    Native dispatch must resolve each source through current app-owned media and
    recheck source hashes, rights and operation authority before output commit.
    """
    value = definition(project)
    width, height = PROFILES[value['output']]
    cursor = 0
    clips = []
    for row in value['clips']:
        count = output_frames(row)
        clips.append(dict(
            id=row['id'], source=deepcopy(row['source']), role=row['role'],
            source_in_frame=row['in_frame'], source_out_frame=row['out_frame'],
            speed_percent=row['speed_percent'], output_start_frame=cursor,
            output_frame_count=count, transform=deepcopy(row['transform']),
            effects=deepcopy(row['effects']), audio=row.get('audio', 'MUTE')))
        cursor += count
    plan = dict(schema='growth.ios-render-plan.v1', project_sha256=digest(value),
                fps=FPS, width=width, height=height, output_frame_count=cursor,
                clips=clips, execution_authority=False,
                source_resolution='CURRENT_APP_OWNED_HASH_AND_RIGHTS_REQUIRED',
                completion='DECODED_OUTPUT_AND_CURRENT_AUTHORITY_REQUIRED')
    return dict(plan, plan_sha256=digest(plan))
