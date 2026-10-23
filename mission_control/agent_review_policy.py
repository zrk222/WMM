"""Immutable owner-selected local write review policy, separate from bearer secrets."""
import json
from .common import Invalid,canonical
from .operation_catalog import OPERATIONS


def validate(body):
    """Select only a unique subset of this grant's fixed local writes."""
    selected=body.get('review_operations',[])
    if not isinstance(selected,list) or any(not isinstance(name,str) or name not in body['operations'] for name in selected):
        raise Invalid('Review operations must be a subset of granted operations')
    if len(selected)!=len(set(selected)) or any(OPERATIONS[name]['method']!='POST' for name in selected):
        raise Invalid('Review policy accepts unique local write operations only')
    return sorted(selected)


def save(db,grant_id,body):
    """Persist once in the same transaction as credential issuance."""
    db.execute('INSERT INTO agent_grant_review_policy VALUES(?,?)',(grant_id,canonical(validate(body))))


def operations(db,grant_id):
    """Legacy grants have no required review operations; imports cannot create policy."""
    row=db.execute('SELECT operations FROM agent_grant_review_policy WHERE grant_id=?',(grant_id,)).fetchone()
    return json.loads(row['operations']) if row else []


def ordinary_dispatch(db,grant_id,operation):
    """An ordinary bearer call may never bypass the owner's required checkpoint."""
    if operation in operations(db,grant_id):
        raise PermissionError('Independent human review required; prepare and resume an exact agent review request')
