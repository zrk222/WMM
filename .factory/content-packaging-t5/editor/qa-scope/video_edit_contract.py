def project_shape(value):
    """Keep optional reviewed packaging references within a closed project shape."""
    exact(value, ('title', 'purpose', 'locale', 'output', 'clips', *(['packaging'] if 'packaging' in value else [])))
    if 'packaging' in value:
        from .packaging_editor import provenance
        provenance(value['packaging'])

def definition(value):
    """A project timeline is ordered and bounded, with unique clip identities."""
    project_shape(value)
    for key in ('title', 'purpose', 'locale'):required(value[key], key, 2000 if key == 'purpose' else 200)
    if not isinstance(value['output'], str) or value['output'] not in PROFILES:
        raise Invalid('Choose portrait, landscape or square output')
    rows = value['clips']
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_CLIPS:
        raise Invalid('Keep the project between 1 and 24 clips')
    normalized = [clip(row) for row in rows]
    if len({row['id'] for row in normalized}) != len(rows):raise Invalid('Clip identifiers must be unique')
    if sum(output_frames(row) for row in normalized) > MAX_FRAMES:
        raise Invalid('Keep the edited project within 60 seconds')
    return dict(deepcopy(value), clips=normalized)
