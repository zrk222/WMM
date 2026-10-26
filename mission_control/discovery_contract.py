"""Closed discovery evidence shapes; source observations never imply production rights."""
from copy import deepcopy
from .common import Invalid, required, iso_time
from .pmf_contract import exact, count, hashed, one

INDUSTRIES = {'BUSINESS','EDUCATION','FINANCE','HEALTH_FITNESS','GAMING','LIFESTYLE','ENTERTAINMENT','ECOMMERCE','OTHER','UNKNOWN'}
NARRATIVES = {'APP_DEMO','TUTORIAL','PROBLEM_SOLUTION','TESTIMONIAL','STORY','BEFORE_AFTER','MEME_TREND','LISTICLE','EDUCATIONAL','ENTERTAINMENT','OTHER','UNKNOWN'}
TREATMENTS = {'TALKING_HEAD','SCREEN_RECORDING','SLIDESHOW','ANIMATION','TEXT_HEAVY','LIVE_ACTION','MIXED','OTHER','UNKNOWN'}


def items(value, maximum, name):
    """Reject oversized collections and duplicate labels before normalization."""
    if not isinstance(value, list) or len(value) > maximum:raise Invalid(name + ': too many or invalid items')
    return value


def texts(value, maximum, bound, name):
    """Store supplied text as data with finite size and no silent deduplication."""
    result = [required(x, name, bound) for x in items(value, maximum, name)]
    if len(set(result)) != len(result):raise Invalid(name + ': duplicate items')
    return result


def taxonomy(value):
    """Keep supplier labels distinct from explicit analyst or agent classification."""
    exact(value, {'original_labels','industry','narrative','treatment','classified_by','rationale'})
    result = deepcopy(value); result['original_labels'] = texts(value['original_labels'],24,200,'Original labels')
    for field, choices in [('industry',INDUSTRIES),('narrative',NARRATIVES),('treatment',TREATMENTS)]:one(value[field],choices,field)
    one(value['classified_by'],{'HUMAN_SUPPLIED','AGENT_SUPPLIED'},'Classification origin')
    required(value['rationale'],'Classification rationale',2000)
    return result


def segments(value, duration, name):
    """Require ordered non-overlapping millisecond ranges within declared source duration."""
    result=[]; previous=0
    for row in items(value,200,name):
        exact(row,{'start_ms','end_ms','text'});count(row['start_ms'],0,duration);count(row['end_ms'],1,duration)
        if row['start_ms'] < previous or row['end_ms'] <= row['start_ms']:raise Invalid(name + ': overlapping or invalid timing')
        required(row['text'],name+' text',2000);previous=row['end_ms'];result.append(deepcopy(row))
    if sum(len(r['text']) for r in result)>100000:raise Invalid(name+': combined text limit exceeded')
    return result


def transcript(value):
    """Permission, language, collection source and uncertainty are explicit supplied facts."""
    if value is None:return None
    exact(value,{'permission_confirmed','language','source','observed_at','duration_ms','uncertainty','segments'})
    if value['permission_confirmed'] is not True:raise Invalid('Confirm permission to retain transcript text')
    for field,bound in [('language',80),('source',2000),('uncertainty',2000)]:required(value[field],field,bound)
    count(value['duration_ms'],1,3600000);iso_time(value['observed_at'])
    return dict(value,segments=segments(value['segments'],value['duration_ms'],'Transcript'))


def card(value, duration):
    """Observed hook/beats and interpretations remain different fields in the evidence card."""
    exact(value,{'observed_hook','observed_beats','interpreted_mechanism','relevance_rationale','reproduction_requirements','authentic_evidence_ids','rights_status','rights_evidence','next_experiment'})
    for field in ('observed_hook','interpreted_mechanism','relevance_rationale','next_experiment'):required(value[field],field,4000)
    one(value['rights_status'],{'UNKNOWN','REFERENCE_ONLY','ALLOWED_BY_ATTESTATION','REVOKED'},'Rights status')
    if not isinstance(value['rights_evidence'],str) or len(value['rights_evidence'])>2000:raise Invalid('Rights evidence is invalid')
    if value['rights_status']=='ALLOWED_BY_ATTESTATION':required(value['rights_evidence'],'Rights evidence',2000)
    return dict(value,observed_beats=segments(value['observed_beats'],duration,'Observed beats'),
                reproduction_requirements=texts(value['reproduction_requirements'],24,1000,'Reproduction requirements'),
                authentic_evidence_ids=texts(value['authentic_evidence_ids'],24,200,'Authentic evidence identities'))


def metrics(value):
    """Comparable engagement requires explicit same-observation counts and denominator."""
    if value is None:return None
    exact(value,{'views','likes','comments','shares','observed_at','collection_source'})
    for name in ('views','likes','comments','shares'):
        if value[name] is not None:count(value[name],0,1000000000000)
    iso_time(value['observed_at']);required(value['collection_source'],'Metrics collection source',2000)
    return deepcopy(value)


def review(value):
    """Close the review envelope and cap raw baseline observations for policy validation."""
    exact(value,{'taxonomy','duration_ms','transcript','card','baseline','metrics'})
    count(value['duration_ms'],1,3600000)
    result=dict(taxonomy=taxonomy(value['taxonomy']),duration_ms=value['duration_ms'],transcript=transcript(value['transcript']),
                card=card(value['card'],value['duration_ms']),baseline=deepcopy(items(value['baseline'],1000,'Baseline')),metrics=metrics(value['metrics']))
    if result['transcript'] and result['transcript']['duration_ms']!=value['duration_ms']:raise Invalid('Transcript duration differs from reviewed source')
    return result


def query(value):
    """Every research filter is explicit; no free-text prompt grants collection authority."""
    exact(value,{'outcome','audience','industries','narratives','treatments','published_after','published_before','freshness_seconds','minimum_views','baseline_required','viral_only','ranking'})
    for field in ('outcome','audience'):required(value[field],field,2000)
    for field,choices in [('industries',INDUSTRIES),('narratives',NARRATIVES),('treatments',TREATMENTS)]:
        texts(value[field],24,120,field)
        for option in value[field]:one(option,choices,field)
    start,end=iso_time(value['published_after']),iso_time(value['published_before'])
    if start>=end:raise Invalid('Publication window must have an increasing range')
    count(value['freshness_seconds'],1,31536000);count(value['minimum_views'],0,1000000000000)
    for flag in ('baseline_required','viral_only'):
        if type(value[flag]) is not bool:raise Invalid('Choose explicit discovery eligibility flags')
    one(value['ranking'],{'REACH','ENGAGEMENT','VELOCITY','CREATOR_OUTLIER'},'Ranking view')
    return deepcopy(value)


def watch(value):
    """Record explicit collection intent without turning it into an external capability."""
    exact(value,{'kind','subjects','query','source','interval_seconds','confirm_authorized_reads'})
    one(value['kind'],{'CREATOR','COMPETITOR'},'Watch kind');texts(value['subjects'],24,200,'Watch subjects')
    if not value['subjects'] or value['confirm_authorized_reads'] is not True:raise Invalid('Select subjects and confirm authorized reads')
    required(value['source'],'Authorized collector source',2000);count(value['interval_seconds'],3600,31536000)
    return dict(value,query=query(value['query']))
