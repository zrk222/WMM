"""Closed preproduction contracts. Draft copy is never verified app proof."""
from .common import Invalid, digest, identifier, required, safe_data
from .pmf_contract import count, exact, hashed, one


def items(value, maximum=100):
    """Bound ordered input without silently dropping duplicates or excess rows."""
    if not isinstance(value, list) or len(value) > maximum:
        raise Invalid('Packaging list exceeds its declared bound')
    return value


def reference(value, kinds):
    """Require exact app-local version and digest for every supplied reference."""
    exact(value, {'kind', 'id', 'version', 'sha256'})
    return dict(kind=one(value['kind'], kinds, 'Reference kind'), id=identifier(value['id']),
                version=count(value['version'], 1, 2147483647), sha256=hashed(value['sha256']))


def refs(values, kinds):
    """Reject repeated identities rather than implying additional evidence."""
    result=[reference(v, kinds) for v in items(values)]
    keys=[(v['kind'], v['id']) for v in result]
    if len(set(keys)) != len(keys):raise Invalid('Duplicate packaging reference')
    return result


def variant(value):
    """Allow missing proof during ideation while validating all provided evidence."""
    safe_data(value)
    text={'audience', 'app_outcome', 'title', 'thumbnail', 'opening_frame', 'hook', 'cta'}
    exact(value, text | {'sources', 'creative', 'app_proofs'})
    result={k:required(value[k], k, 300 if k=='title' else 2000) for k in text}
    result['sources']=refs(value['sources'], {'SOURCE', 'COLLECTION'})
    result['creative']=None if value['creative'] is None else reference(value['creative'], {'BRIEF'})
    result['app_proofs']=refs(value['app_proofs'], {'CLAIM', 'ASSET'})
    return result


def shot(value, segments):
    """Tie each planned shot to one script segment and explicit evidence gaps."""
    exact(value, {'id', 'segment_id', 'segment_sha256', 'kind', 'description', 'source', 'start_ms', 'end_ms', 'assets', 'claims', 'claim_text'})
    result=dict(value, id=identifier(value['id']), segment_id=identifier(value['segment_id']))
    if result['segment_id'] not in segments:raise Invalid('Shot requires an existing script segment')
    if hashed(value['segment_sha256'])!=segments[result['segment_id']]:raise Invalid('Script segment changed; review this shot again')
    result['kind']=one(value['kind'], {'A_ROLL', 'B_ROLL', 'SCREEN_RECORDING', 'GRAPHICS', 'AUDIO'}, 'Shot kind')
    result['description']=required(value['description'], 'Shot description', 2000)
    if not isinstance(value['claim_text'], str) or len(value['claim_text'])>2000:raise Invalid('Claim text exceeds 2000 characters')
    result['source']=None if value['source'] is None else reference(value['source'], {'SOURCE'})
    timing(value)
    result['assets']=refs(value['assets'], {'ASSET', 'MEDIA'})
    result['claims']=refs(value['claims'], {'CLAIM'})
    return result


def timing(value):
    """Source timestamps are paired and bounded; original shots have none."""
    if value['source'] is None:
        if value['start_ms'] is not None or value['end_ms'] is not None:raise Invalid('Original shots have no source timestamp')
        return
    start=count(value['start_ms'], 0, 86400000);end=count(value['end_ms'], 1, 86400000)
    if start>=end:raise Invalid('Source shot timestamps must increase')


def shotlist(value):
    """Freeze editable script text and its segment-to-shot mapping per revision."""
    safe_data(value);exact(value, {'variant', 'script', 'shots'})
    result=dict(variant=reference(value['variant'], {'VARIANT'}));segments={};script=[]
    for segment in items(value['script']):
        exact(segment, {'id', 'text'});identity=identifier(segment['id'])
        if identity in segments:raise Invalid('Duplicate script segment')
        text=required(segment['text'], 'Script text', 4000)
        segments[identity]=digest(dict(id=identity, text=text));script.append(dict(id=identity, text=text))
    if not script:raise Invalid('A shot list requires a script')
    shots=[shot(v, segments) for v in items(value['shots'])]
    if len({v['id'] for v in shots})!=len(shots):raise Invalid('Duplicate shot identity')
    return dict(result, script=script, shots=shots)


def agent_contract():
    """Describe actual preparation controls without promoting drafts to execution."""
    return dict(schema='growth.packaging-contract.v1',kinds=['VARIANT','SHOTS'],
                operations=['packaging.save','packaging.read','packaging.history','packaging.reconcile'],
                save_fields=['id','version','kind','manifest_version','data'],
                variant_fields=['audience','app_outcome','title','thumbnail','opening_frame','hook','cta','sources','creative','app_proofs'],
                shotlist_fields=['variant','script','shots'],
                script_fields=['id','text'],
                script_segment_sha256='SHA256 of UTF-8 JSON for {id,text}, keys sorted, separators comma and colon without whitespace, Unicode retained.',
                thumbnail_preview='The first ASSET in app_proofs supplies the local thumbnail preview; thumbnail text describes its layout.',
                reference_fields=['kind','id','version','sha256'],
                shot_fields=['id','segment_id','segment_sha256','kind','description','source','start_ms','end_ms','assets','claims','claim_text'],
                shot_kinds=['A_ROLL','B_ROLL','SCREEN_RECORDING','GRAPHICS','AUDIO'],
                limits=dict(history_page=100,revisions=100,app_history=2000,title_characters=300),
                state='DRAFT',execution_authority=False,publication='NOT_RUN',render='NOT_RUN',
                uncertain_write=dict(operation='packaging.reconcile',automatic_retry=False,caller_commit_identity='NOT_PROVEN',
                    statuses=['MATCHING_REVISION_OBSERVED','DIFFERENT_REVISION_OBSERVED','NO_REVISION_OBSERVED']),
                approval='Owner-issued current scoped grants; owner-selected independent checker review is enforced by the existing gateway; discovery grants no authority.')
