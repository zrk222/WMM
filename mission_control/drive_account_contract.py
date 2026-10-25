"""Verified Drive account identity, exact review packets and protected connection binding."""
import json
import re
import time
from .common import Invalid, digest
from .drive_auth import SCOPE, selected_files
from .social_contract import display


def identity(payload):
    """Google's requesting-user permission identity is required; email may be absent."""
    if not isinstance(payload, dict) or set(payload) != {'user'} or not isinstance(payload['user'], dict):
        raise Invalid('Drive did not return the requesting account; reconnect')
    user = payload['user']; subject = user.get('permissionId')
    if user.get('me') is not True or user.get('kind') != 'drive#user':
        raise Invalid('Drive did not verify the requesting account; reconnect')
    if not isinstance(subject, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', subject):
        raise Invalid('Drive account identity is unavailable; reconnect')
    result = dict(permission_id=subject)
    for field, output in (('displayName', 'display_name'), ('emailAddress', 'email')):
        if field in user:result[output] = display(user[field], 'Drive account label', 254)
    return result


def connection_row(row):
    """Private rows require an exact connected scope and selected-file inventory."""
    if row is None:return None
    value = dict(row)
    try:value['data'] = json.loads(value['data'])
    except (ValueError, TypeError, RecursionError):
        raise Invalid('Drive connection metadata is invalid; reconnect') from None
    data = value['data']
    if not isinstance(data, dict) or data.get('scope') != SCOPE:
        raise Invalid('Drive connection permission metadata differs; reconnect')
    selected = data.get('selected_files')
    if not isinstance(selected, list) or any(not isinstance(item, str) for item in selected):
        raise Invalid('Drive selected-file inventory is invalid; reconnect')
    selected_files(','.join(selected))
    return value


def connection_binding(row):
    """A protected token belongs to exactly one app, account, selection and revision."""
    return digest({key: row[key] for key in ('app_id', 'id', 'version', 'data', 'expires')})


def packet(row):
    """Only a live reviewed candidate can produce an owner-confirmable packet."""
    if row['status'] != 'AWAITING_ACCOUNT':raise Invalid('Drive account is not awaiting confirmation')
    data = row['data']
    if data['access_expires'] <= time.time():raise Invalid('Drive candidate access expired; reconnect')
    value = {key: row[key] for key in ('app_id', 'id', 'manifest_version', 'connection_id', 'connection_version', 'expires')}
    value.update(account=data['account'], selected_files=data['selected_files'], access_expires=data['access_expires'],
                 scope=SCOPE, next_action='CONFIRM_ACCOUNT_AND_SELECTED_FILES', reuse_permission='NOT_GRANTED')
    return dict(value, packet_hash=digest(value))


def confirmation(body):
    """No owner identity, version override or alternate selection enters confirmation."""
    if not isinstance(body, dict) or set(body) != {'packet_hash', 'confirm_account'} or body['confirm_account'] is not True:
        raise Invalid('Confirm the displayed Drive account and selected files')
    value = body['packet_hash']
    if not isinstance(value, str) or not re.fullmatch(r'[a-f0-9]{64}', value):
        raise Invalid('Reload the current Drive account confirmation packet')
    return value
