"""Explain research decisions over permitted captures; never infer app conversions."""
from fractions import Fraction
from .common import iso_time
from .viral_policy import qualify, PLATFORMS


def boundaries():
    """Research states confer no downstream authority, even on qualified sources."""
    return dict(reuse_approval='NOT_GRANTED', production_execution='NOT_RUN',
                publication='NOT_RUN', measured_app_sales=None, authority='RECHECK_EXACT_DOWNSTREAM_AUTHORITY')


def candidate(data):
    """Use observed views, not supplier outlier labels or likes, for viral eligibility."""
    if data['platform'] not in PLATFORMS or not data['creator_id'] or data['metric_kind'] != 'VIEWS':return None
    if any(data[key] is None for key in ('metric_value','metric_at','published_at')):return None
    return dict(platform=data['platform'],post_id=data['post_id'],creator_id=data['creator_id'],format=data['format'],
                url=data['url'],views=data['metric_value'],published_at=data['published_at'],observed_at=data['metric_at'])


def qualification(data, review, stamp):
    """A supplied high-view or third-party outlier example stays a candidate without baseline proof."""
    value=candidate(data)
    if value is None:return dict(qualification='CANDIDATE',baseline_count=0,median=None,reasons=['VIEWS_CREATOR_OR_SUPPORTED_PLATFORM_MISSING'])
    return qualify(value,review['baseline'] if review else [],stamp)


def observed_ratio(numerator, denominator, basis, window):
    """Expose exact denominators and window rather than manufacture a comparable score."""
    if numerator is None or denominator is None or denominator <= 0:return None
    ratio=Fraction(numerator,denominator)
    return dict(numerator=numerator,denominator=denominator,value=float(ratio),basis=basis,window=window)


def velocity(data, previous):
    """Velocity needs two same-post view observations; lifetime views are not growth velocity."""
    if not previous or previous['metric_kind']!='VIEWS' or data['metric_kind']!='VIEWS':return None
    if any(x is None for x in (data['metric_value'],previous['metric_value'],data['metric_at'],previous['metric_at'])):return None
    if (data['platform'],data['post_id']) != (previous['platform'],previous['post_id']):return None
    start,end=iso_time(previous['metric_at']),iso_time(data['metric_at'])
    micros=int((end-start).total_seconds()*1000000);delta=data['metric_value']-previous['metric_value']
    if micros<=0 or delta<0:return None
    return observed_ratio(delta*1000000,micros,'OBSERVED_VIEWS_PER_SECOND',dict(start=start.isoformat(),end=end.isoformat(),views_delta=delta))


def rankings(data, review, policy, previous):
    """Attention measures stay separate from installs, attributed sales and causal lift."""
    views=data['metric_value'] if data['metric_kind']=='VIEWS' else None
    window=dict(published_at=data['published_at'],observed_at=data['metric_at'])
    result=dict(REACH=observed_ratio(views,1,'OBSERVED_VIEWS',window),ENGAGEMENT=None,
                VELOCITY=velocity(data,previous),CREATOR_OUTLIER=None)
    metrics=review['metrics'] if review else None
    if metrics and metrics['likes'] is not None and metrics['comments'] is not None:
        result['ENGAGEMENT']=observed_ratio(metrics['likes']+metrics['comments'],metrics['views'],'SAME_OBSERVATION_LIKES_PLUS_COMMENTS_PER_VIEW',window)
    median=policy['median']
    if median and views is not None:
        result['CREATOR_OUTLIER']=observed_ratio(views*median['denominator'],median['numerator'],'VIEWS_PER_COMPARABLE_CREATOR_MEDIAN',window)
    return result


def filter_reasons(data, review, filters, stamp):
    """Every absent or failed filter is visible; no missing fact silently passes."""
    reasons=[]
    for field,group in [('industry','industries'),('narrative','narratives'),('treatment','treatments')]:
        if filters[group] and (not review or review['taxonomy'][field] not in filters[group]):reasons.append(field.upper()+'_MISMATCH_OR_UNKNOWN')
    reasons.extend(observation_reasons(data,filters,stamp))
    return reasons


def observation_reasons(data, filters, stamp):
    """Check timing and view filters independently of taxonomy classifications."""
    reasons=[];published=data['published_at']
    if published is None or not iso_time(filters['published_after'])<=iso_time(published)<=iso_time(filters['published_before']):reasons.append('PUBLICATION_OUTSIDE_WINDOW_OR_UNKNOWN')
    observed=data['metric_at'] if data['metric_kind']=='VIEWS' else data['captured_at']
    age=(iso_time(stamp)-iso_time(observed or data['captured_at'])).total_seconds()
    if not 0<=age<=filters['freshness_seconds']:reasons.append('OBSERVATION_STALE_OR_FUTURE')
    if data['metric_kind']!='VIEWS' or data['metric_value'] is None:reasons.append('OBSERVED_VIEWS_MISSING')
    elif data['metric_value']<filters['minimum_views']:reasons.append('BELOW_REQUESTED_MINIMUM_VIEWS')
    return reasons


def evaluate(capture, review, filters, stamp, previous=None):
    """Explain one source, preserving independent qualification and rights missingness."""
    data=capture['data'];policy=qualification(data,review,stamp);reasons=filter_reasons(data,review,filters,stamp)
    baseline_missing=policy['median'] is None
    if filters['baseline_required'] and baseline_missing:reasons.append('DOCUMENTED_BASELINE_MISSING')
    qualified=policy['qualification']=='QUALIFIED_BY_REPORTED_COUNTS'
    if filters['viral_only'] and not qualified:reasons.extend(['VIRAL_QUALIFICATION_REQUIRED',*policy['reasons']])
    rights_missing=not review or review['card']['rights_status']!='ALLOWED_BY_ATTESTATION'
    return dict(reference_id=capture['reference_id'],source_hash=capture['hash'],source_version=capture['version'],
                observed_at=data['captured_at'],included=not reasons,reasons=reasons or ['MATCHED_REQUESTED_RESEARCH_FILTERS'],
                review_status='APP_CONTEXT_REVIEWED' if review else 'REVIEW_MISSING',qualified=qualified,
                baseline_missing=baseline_missing,rights_missing=rights_missing,policy=policy,
                rankings=rankings(data,review,policy,previous),boundaries=boundaries())


def ordered(results, ranking):
    """Sort exact fractions deterministically; unknown metrics stay last without becoming zero."""
    def key(row):
        value=row['rankings'][ranking]
        return (value is None,-Fraction(value['numerator'],value['denominator']) if value else Fraction(0),row['reference_id'])
    return sorted(results,key=key)


def coverage(results, attempted, failed):
    """Observed, qualified, baseline missing and rights missing are independent counts."""
    return dict(observed_candidates=len(results),included_candidates=sum(r['included'] for r in results),
                qualified_candidates=sum(r['qualified'] for r in results),baseline_missing=sum(r['baseline_missing'] for r in results),
                rights_missing=sum(r['rights_missing'] for r in results),attempted_sources=attempted,failed_sources=failed,
                source_universe='APP_SAVED_PERMITTED_REFERENCES_ONLY',platform_coverage='NOT_EXHAUSTIVE')
