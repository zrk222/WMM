"""Native owner gateway to separately authenticated, app-scoped human review.

The host owns this object for the lifetime of its runtime and calls logout on
lock. Reviewer credentials live only in Identities RAM, never in responses.
"""
import secrets
import threading

from .common import Invalid
from .ios_bridge import decode_document, encode_response
from .operator_identity import Identities


class _BoundIdentities:
    """Recheck both sessions at each protected SQLite entry and commit."""
    def __init__(self, native, owners, owner_session, human_owner, reviewers, reviewer_session, reviewer):
        self.native = native
        self.owners = owners
        self.owner_session = owner_session
        self.human_owner = human_owner
        self.reviewers = reviewers
        self.reviewer_session = reviewer_session
        self.reviewer = reviewer

    def local(self, session, principal, generation=None):
        owner = self.native.local(session, principal, generation)
        if self.human_owner is not None:
            self.owners.local(self.owner_session, self.human_owner['principal'],
                              self.human_owner['session_generation'])
        if self.reviewer is not None:
            self.reviewers.local(self.reviewer_session, self.reviewer['principal'],
                                 self.reviewer['session_generation'])
        return owner


class NativeHumanReview:
    def __init__(self, service, native_identities):
        self.service = service
        self.native = native_identities
        self.owners = Identities()
        self.reviewers = Identities()
        self.lock = threading.RLock()
        self.binding = None
        self.reviewer_session = secrets.token_hex(32)
        self.owner_session = secrets.token_hex(32)

    def logout(self):
        """Immediately discard the reviewer credential when the native host locks."""
        with self.lock:
            self.reviewers.logout(self.reviewer_session)
            self.owners.logout(self.owner_session)
            self.binding = None
            self.reviewer_session = secrets.token_hex(32)
            self.owner_session = secrets.token_hex(32)
        return {'status': 'SIGNED_OUT'}

    def call(self, session, app_id, action, payload):
        from .agent_review_http import human
        from .db import connection
        from .operation_authority import bound_owner, protected
        from .review_access import Access
        from .store import audit
        from .verified_reviews import Reviews

        fields = {
            'owner_identity_login': {'token'}, 'owner_identity_status': set(), 'owner_identity_logout': set(),
            'reviewer_login': {'token'}, 'reviewer_status': set(), 'reviewer_logout': set(),
            'members_list': set(), 'member_save': {'role', 'status', 'version'},
            'member_revoke': {'principal', 'version'},
            'review_sources': set(), 'review_list': set(), 'review_prepare': {'record_id'}, 'review_approve': {'id', 'hash'},
            'agent_list': None, 'agent_inspect': {'id'},
            'agent_approve': {'id', 'revision', 'packet_hash'}, 'agent_cancel': {'id', 'revision'},
            'agent_reconcile': {'id', 'revision', 'outcome', 'evidence_hash'},
        }
        body = decode_document(payload)
        if action not in fields or not isinstance(body, dict):
            raise Invalid('Choose a fixed native human review action')
        if fields[action] is None:
            if set(body) - {'offset'}: raise Invalid('Use only the queue offset')
        elif set(body) != fields[action]:
            raise Invalid('Use the exact fields for this human review action')

        with self.lock:
            try:
                owner = self.native.fresh(session)
            except Exception:
                self.logout()
                raise
            binding = (session, owner['principal'], owner['session_generation'])
            if self.binding is not None and self.binding != binding:
                self.logout()
            self.binding = binding
            reviewer = None
            human_owner = None
            reviewer_actions = ('reviewer_login', 'member_save', 'review_approve', 'agent_list',
                                'agent_inspect', 'agent_approve', 'agent_cancel', 'agent_reconcile')
            if action in reviewer_actions:
                try:
                    human_owner = self.owners.fresh(self.owner_session)
                    human_owner = self.owners.local(self.owner_session, human_owner['principal'])
                except Exception:
                    self.reviewers.logout(self.reviewer_session)
                    raise
            if action in ('member_save', 'review_approve', 'agent_list', 'agent_inspect', 'agent_approve', 'agent_cancel', 'agent_reconcile'):
                reviewer = self.reviewers.fresh(self.reviewer_session)
                reviewer = self.reviewers.local(self.reviewer_session, reviewer['principal'])
                if reviewer['principal'] == human_owner['principal']:
                    self.reviewers.logout(self.reviewer_session)
                    raise PermissionError('The reviewer must use a different verified GitHub account from the owner')
            identities = _BoundIdentities(self.native, self.owners, self.owner_session, human_owner,
                                         self.reviewers, self.reviewer_session, reviewer)
            # Never retain the token in the operation authority context.
            envelope = dict(app_id=app_id, operation='native.human-review.' + action,
                            input={} if action in ('reviewer_login', 'owner_identity_login') else body)
            try:
                with bound_owner(self.service.store, envelope, identities, session, owner):
                    with protected(self.service.store, envelope):
                        if human_owner is not None:
                            with connection(self.service.store.path) as db:
                                saved = db.execute('SELECT * FROM native_owner_review_identity WHERE app_id=?', (app_id,)).fetchone()
                                if not saved or saved['native_owner'] != owner['principal'] or saved['github_principal'] != human_owner['principal']:
                                    raise PermissionError('Verify the bound owner GitHub identity for this app')
                        if action == 'owner_identity_login':
                            self.reviewers.logout(self.reviewer_session)
                            self.owners.logout(self.owner_session)
                            result = self.owners.login(self.owner_session, body)
                            verified = self.owners.local(self.owner_session, result['principal'])
                            with connection(self.service.store.path) as db:
                                db.execute('BEGIN IMMEDIATE')
                                saved = db.execute('SELECT * FROM native_owner_review_identity WHERE app_id=?', (app_id,)).fetchone()
                                if saved and (saved['native_owner'] != owner['principal'] or saved['github_principal'] != verified['principal']):
                                    raise PermissionError('This app already has a different verified owner identity')
                                if not saved:
                                    db.execute('INSERT INTO native_owner_review_identity VALUES(?,?,?,?)',
                                               (app_id, owner['principal'], verified['principal'], verified['login']))
                                    audit(db, app_id, 'access.native_owner_identity_bound',
                                          {'principal': verified['principal'], 'native_owner': owner['principal']})
                                self.owners.local(self.owner_session, verified['principal'], verified['session_generation'])
                        elif action == 'owner_identity_status':
                            result = self.owners.public(self.owner_session)
                            if result['status'] == 'AUTHENTICATED':
                                with connection(self.service.store.path) as db:
                                    saved = db.execute('SELECT * FROM native_owner_review_identity WHERE app_id=?', (app_id,)).fetchone()
                                    if not saved or saved['native_owner'] != owner['principal'] or saved['github_principal'] != result['principal']:
                                        result = {'status': 'SIGNED_OUT'}
                        elif action == 'owner_identity_logout':
                            self.reviewers.logout(self.reviewer_session)
                            result = self.owners.logout(self.owner_session)
                        elif action == 'reviewer_login':
                            self.reviewers.logout(self.reviewer_session)
                            result = self.reviewers.login(self.reviewer_session, body)
                            if result['principal'] == human_owner['principal']:
                                self.reviewers.logout(self.reviewer_session)
                                raise PermissionError('The reviewer must use a different verified GitHub account from the owner')
                        elif action == 'reviewer_status':
                            result = self.reviewers.public(self.reviewer_session)
                        elif action == 'reviewer_logout':
                            result = self.reviewers.logout(self.reviewer_session)
                        elif action == 'members_list':
                            result = Access(self.service.store).list(app_id)
                        elif action == 'member_save':
                            result = Access(self.service.store).save(app_id, owner, reviewer,
                                dict(body, login=reviewer['login']))
                        elif action == 'member_revoke':
                            # Resolve only previously verified app membership; a supplied
                            # principal never becomes an authenticated reviewer identity.
                            rows = Access(self.service.store).list(app_id)['members']
                            target = next((row for row in rows if row['principal'] == body['principal']), None)
                            if target is None or target['role'] not in ('MAKER', 'CHECKER'):
                                raise Invalid('Choose a saved app member to revoke')
                            result = Access(self.service.store).save(app_id, owner, target,
                                dict(login=target['login'], role=target['role'], status='REVOKED', version=body['version']))
                        elif action == 'review_sources':
                            result = {'items': [dict(id=row['id'], title=row['title'], kind=row['kind'])
                                                for row in self.service.store.records(app_id)
                                                if row['kind'] in ('distribution', 'store', 'experiment')]}
                        elif action == 'review_list':
                            result = {'items': Reviews(self.service.store).list(app_id)}
                        elif action == 'review_prepare':
                            result = Reviews(self.service.store).prepare(app_id, owner, body)
                        elif action == 'review_approve':
                            result = Reviews(self.service.store).approve(app_id, body['id'], reviewer,
                                                                        {'hash': body['hash']})
                        else:
                            result = human(self.service.store, app_id, [action.removeprefix('agent_')], reviewer, body)
                        identities.local(session, owner['principal'], owner['session_generation'])
                        return encode_response(result)
            except Exception:
                if action == 'owner_identity_login':
                    self.owners.logout(self.owner_session)
                # A replaced/locked native owner must never leave a usable reviewer session.
                try:
                    self.native.local(session, owner['principal'], owner['session_generation'])
                except Exception:
                    self.logout()
                raise
