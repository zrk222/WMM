"""Closed reported-token observations; never infer billing, quota or missing totals."""

MAX_TOKENS = 10000000
FIELDS = {
    'input_tokens': (('input_tokens',), ('prompt_tokens',)),
    'output_tokens': (('output_tokens',), ('completion_tokens',)),
    'total_tokens': (('total_tokens',),),
    'cache_read_tokens': (('cached_input_tokens',), ('cache_read_input_tokens',),
                          ('input_tokens_details', 'cached_tokens'), ('prompt_tokens_details', 'cached_tokens')),
    'cache_write_tokens': (('cache_creation_input_tokens',),),
    'reasoning_tokens': (('output_tokens_details', 'reasoning_tokens'), ('completion_tokens_details', 'reasoning_tokens')),
}
MISSING = object()


def reported_path(value, path):
    """Read only fixed protocol fields, distinguishing absent from malformed details."""
    current = value
    for key in path:
        if not isinstance(current, dict):
            return None
        if key not in current:
            return MISSING
        current = current[key]
    return current


def field_observation(value, name, paths):
    """Reject ambiguous aliases instead of silently preferring or summing them."""
    supplied = [reported_path(value, path) for path in paths]
    supplied = [item for item in supplied if item is not MISSING]
    if not supplied:
        return None, None
    if any(type(item) is not int or not 0 <= item <= MAX_TOKENS for item in supplied):
        return None, 'INVALID_' + name.upper()
    if len(set(supplied)) != 1:
        return None, 'CONFLICT_' + name.upper()
    return supplied[0], None


def observation(value):
    """Return safe canonical counts and explicit completeness without raw telemetry."""
    if value is None:
        return dict(usage={}, usage_status='UNAVAILABLE', usage_issues=[])
    if not isinstance(value, dict):
        return dict(usage={}, usage_status='INVALID', usage_issues=['INVALID_USAGE_OBJECT'])
    counts = {}
    issues = []
    for name, paths in FIELDS.items():
        count, issue = field_observation(value, name, paths)
        if count is not None:
            counts[name] = count
        if issue:
            issues.append(issue)
    return dict(usage=counts, usage_status=completeness(counts, issues), usage_issues=issues)


def completeness(counts, issues):
    """Absence is not zero; a provider's explicit total is never reconstructed."""
    if not counts:
        return 'INVALID' if issues else 'UNAVAILABLE'
    if issues or not {'input_tokens', 'output_tokens', 'total_tokens'} <= counts.keys():
        return 'PARTIAL'
    return 'REPORTED'
