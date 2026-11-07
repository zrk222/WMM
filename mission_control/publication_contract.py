"""Pure closed contracts for reviewed organic channel publications."""
from copy import deepcopy
import re
from urllib.parse import parse_qsl, urlsplit

from .aeo_transport import hostname
from .common import Invalid, digest, safe_data, identifier
from .social_contract import account_id, reference


SCHEMA = 'wmm.organic-publication.v1'
PUBLICATION_PROVIDERS = ('instagram', 'tiktok', 'youtube', 'linkedin')
KINDS = {
    'instagram': ('instagram_reel',),
    'tiktok': ('tiktok_video',),
    'youtube': ('youtube_short',),
    'linkedin': ('linkedin_video', 'linkedin_text'),
}
SETTINGS_FIELDS = {
    'instagram': ('share_to_feed',),
    'tiktok': ('privacy_level', 'disable_duet', 'disable_comment', 'disable_stitch',
               'brand_content_toggle', 'brand_organic_toggle', 'is_aigc'),
    'youtube': ('privacy_status', 'self_declared_made_for_kids', 'contains_synthetic_media'),
    'linkedin': ('visibility',),
}
PRIVACY_LEVELS = ('PUBLIC_TO_EVERYONE', 'MUTUAL_FOLLOW_FRIENDS', 'FOLLOWER_OF_CREATOR', 'SELF_ONLY')
YOUTUBE_PRIVACY = ('public', 'unlisted', 'private')
LINKEDIN_VISIBILITY = ('PUBLIC', 'CONNECTIONS')
BASE_FIELDS = ('schema', 'request_id', 'app_id', 'manifest_version', 'provider', 'connection_id',
               'connection_version', 'destination_id', 'kind', 'title', 'caption', 'link',
               'artifact', 'rights_hashes', 'source_hashes', 'settings')
HASH_PATTERN = r'^[0-9a-f]{64}$'
UUID_PATTERN = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'


def _string(value, label, limit, *, nonempty=False):
    if not isinstance(value, str) or len(value) > limit or (nonempty and not value.strip()):
        raise Invalid(f'Invalid publication {label}')
    if re.search(r'[\x00-\x08\x0b-\x1f\x7f-\x9f\ud800-\udfff]', value):
        raise Invalid(f'Invalid publication {label}')
    return value


def _hashes(value, label, *, nonempty):
    if (not isinstance(value, list) or (nonempty and not value) or len(value) > 100
            or any(not isinstance(item, str) or not re.fullmatch(HASH_PATTERN[1:-1], item) for item in value)
            or value != sorted(set(value))):
        raise Invalid(f'Invalid publication {label}')
    return list(value)


def _link(value):
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > 2048 or re.search(r'[\x00-\x20\x7f\\]', value):
        raise Invalid('Invalid publication link')
    try:
        parts = urlsplit(value)
        port = parts.port
        query = parse_qsl(parts.query, keep_blank_values=True, max_num_fields=64)
    except ValueError:
        raise Invalid('Invalid publication link') from None
    if (parts.scheme != 'https' or not parts.hostname or parts.username is not None
            or parts.password is not None or port not in (None, 443)):
        raise Invalid('Publication link must be public HTTPS without credentials')
    credential_names = {'access_token', 'api_key', 'authorization', 'client_secret', 'credential',
                        'password', 'refresh_token', 'secret', 'signature', 'state', 'token'}
    if any(key.casefold() in credential_names or key.casefold().endswith('_token') for key, _ in query):
        raise Invalid('Publication link cannot contain credential parameters')
    try:
        hostname(parts.hostname)
    except Invalid:
        raise Invalid('Publication link must use a public DNS hostname') from None
    return value


def _settings(provider, value):
    if not isinstance(value, dict) or set(value) != set(SETTINGS_FIELDS[provider]):
        raise Invalid('Use the exact channel publication settings')
    if provider == 'instagram':
        if type(value['share_to_feed']) is not bool:
            raise Invalid('Instagram share_to_feed must be an explicit boolean')
    elif provider == 'tiktok':
        if value['privacy_level'] not in PRIVACY_LEVELS:
            raise Invalid('Choose an allowed TikTok privacy level')
        for key in SETTINGS_FIELDS[provider][1:]:
            if type(value[key]) is not bool:
                raise Invalid('TikTok disclosure and interaction settings must be explicit booleans')
    elif provider == 'youtube':
        if value['privacy_status'] not in YOUTUBE_PRIVACY:
            raise Invalid('Choose an allowed YouTube privacy status')
        for key in SETTINGS_FIELDS[provider][1:]:
            if type(value[key]) is not bool:
                raise Invalid('YouTube audience and synthetic-media settings must be explicit booleans')
    elif value['visibility'] not in LINKEDIN_VISIBILITY:
        raise Invalid('Choose an allowed LinkedIn visibility')
    return dict(value)


def _draft_identity(body):
    """Validate the closed envelope and normalize app, connection and channel identity."""
    if not isinstance(body, dict) or set(body) != set(BASE_FIELDS):
        raise Invalid('Use the exact organic publication draft fields')
    safe_data(body)
    if body['schema'] != SCHEMA:
        raise Invalid('Unsupported organic publication schema')
    reference(body['request_id'])
    value = dict(body)
    value['app_id'] = identifier(body['app_id'])
    if type(body['manifest_version']) is not int or body['manifest_version'] < 1:
        raise Invalid('Use the current positive app revision')
    provider = body['provider']
    if provider not in PUBLICATION_PROVIDERS:
        raise Invalid('Choose a supported organic publication channel')
    reference(body['connection_id'])
    if type(body['connection_version']) is not int or body['connection_version'] < 1:
        raise Invalid('Use the current positive connection revision')
    if not isinstance(body['destination_id'], str):
        raise Invalid('Use an exact provider destination identity')
    value['destination_id'] = account_id(body['destination_id'])
    kind = body['kind']
    if kind not in KINDS[provider]:
        raise Invalid('Publication kind does not match its channel')
    return value,provider,kind


def _draft_content(body,value,provider,kind):
    """Validate user-visible copy, link safety and the exact media reference."""
    value['title'] = _string(body['title'], 'title', 100, nonempty=kind == 'youtube_short')
    caption_limit = 2200 if provider == 'instagram' else 5000
    value['caption'] = _string(body['caption'], 'caption', caption_limit, nonempty=True)
    value['link'] = _link(body['link'])
    artifact = body['artifact']
    if kind == 'linkedin_text':
        if artifact is not None:
            raise Invalid('LinkedIn text publication cannot include a media artifact')
    else:
        if not isinstance(artifact, dict) or set(artifact) != {'id', 'sha256'}:
            raise Invalid('Video publication requires an exact retained artifact')
        reference(artifact['id'])
        if not isinstance(artifact['sha256'], str) or not re.fullmatch(HASH_PATTERN[1:-1], artifact['sha256']):
            raise Invalid('Invalid publication artifact hash')
        value['artifact'] = dict(artifact)


def _draft_provenance(body,value,provider):
    """Require canonical rights and source hashes plus channel-specific settings."""
    value['rights_hashes'] = _hashes(body['rights_hashes'], 'rights hashes', nonempty=True)
    value['source_hashes'] = _hashes(body['source_hashes'], 'source hashes', nonempty=False)
    value['settings'] = _settings(provider, body['settings'])


def validate_draft(body):
    """Validate and return a normalized immutable-review input; perform no effects."""
    value,provider,kind=_draft_identity(body)
    _draft_content(body,value,provider,kind)
    _draft_provenance(body,value,provider)
    return value


def channel_descriptor(draft):
    """Return the channel/account identity bound by a validated draft."""
    value = validate_draft(draft)
    return {key: value[key] for key in ('provider', 'kind', 'destination_id', 'connection_id')}


def preview_summary(draft):
    """Build a secret-free review projection and hash; this grants no authority."""
    value = validate_draft(draft)
    preview = {key: value[key] for key in ('title', 'caption', 'link', 'artifact', 'rights_hashes', 'source_hashes')}
    return dict(schema=SCHEMA, request_id=value['request_id'], app_id=value['app_id'],
                manifest_version=value['manifest_version'], channel=channel_descriptor(value),
                preview=preview, review_hash=digest(value), privacy=value['settings'],
                ad_spend_minor=0, authority='NOT_GRANTED')


def channel_catalog():
    """Expose only channel kinds with a wired organic executor; ads stay separate."""
    names={'instagram':'Instagram','tiktok':'TikTok','youtube':'YouTube','linkedin':'LinkedIn'}
    return deepcopy({provider: dict(name=names[provider],kinds=list(KINDS[provider]),
                                    settings=list(SETTINGS_FIELDS[provider]),contract_only=False,
                                    execution_implemented=True,advertising=False)
                     for provider in PUBLICATION_PROVIDERS})


def _schema_for(provider, kind):
    settings = {name: {'type': 'boolean'} for name in SETTINGS_FIELDS[provider]}
    if provider == 'tiktok':
        settings['privacy_level'] = {'type': 'string', 'enum': list(PRIVACY_LEVELS)}
    elif provider == 'youtube':
        settings['privacy_status'] = {'type': 'string', 'enum': list(YOUTUBE_PRIVACY)}
    elif provider == 'linkedin':
        settings['visibility'] = {'type': 'string', 'enum': list(LINKEDIN_VISIBILITY)}
    title = {'type': 'string', 'maxLength': 100}
    if kind == 'youtube_short':
        title.update(minLength=1, pattern=r'\S')
    artifact = {'type': 'null'} if kind == 'linkedin_text' else {
        'type': 'object', 'required': ['id', 'sha256'], 'additionalProperties': False,
        'properties': {'id': {'type': 'string', 'pattern': UUID_PATTERN},
                       'sha256': {'type': 'string', 'pattern': HASH_PATTERN}},
    }
    return {'type': 'object', 'required': list(BASE_FIELDS), 'additionalProperties': False,
            'properties': {
                'schema': {'const': SCHEMA},
                'request_id': {'type': 'string', 'pattern': UUID_PATTERN},
                'app_id': {'type': 'string', 'pattern': r'^[a-z0-9]+(?:-[a-z0-9]+)*$'},
                'manifest_version': {'type': 'integer', 'minimum': 1},
                'provider': {'const': provider},
                'connection_id': {'type': 'string', 'pattern': UUID_PATTERN},
                'connection_version': {'type': 'integer', 'minimum': 1},
                'destination_id': {'type': 'string', 'pattern': r'^[A-Za-z0-9_.:@-]{1,160}$'},
                'kind': {'const': kind}, 'title': title,
                'caption': {'type': 'string', 'minLength': 1, 'maxLength': 2200 if provider == 'instagram' else 5000,
                            'pattern': r'\S'},
                'link': {'type': ['string', 'null'], 'maxLength': 2048,
                         'pattern': r'^https://[^/@?#]+(?:/[^\s?#]*)?(?:\?[^\s#]*)?(?:#[^\s]*)?$'},
                'artifact': artifact,
                'rights_hashes': {'type': 'array', 'minItems': 1, 'maxItems': 100,
                                  'uniqueItems': True, 'items': {'type': 'string', 'pattern': HASH_PATTERN}},
                'source_hashes': {'type': 'array', 'maxItems': 100, 'uniqueItems': True,
                                  'items': {'type': 'string', 'pattern': HASH_PATTERN}},
                'settings': {'type': 'object', 'required': list(SETTINGS_FIELDS[provider]),
                             'additionalProperties': False, 'properties': settings},
            }}


DRAFT_SCHEMA = {'oneOf': [_schema_for(provider, kind)
                          for provider in PUBLICATION_PROVIDERS for kind in KINDS[provider]]}
