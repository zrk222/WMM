"""One bounded marketing pack over the existing approved original-copy task."""
from .common import Invalid

CONTENT_PACK_ID='content_repurposing_pack'
CONTENT_PACK_TITLES=('Carousel outline','Email draft','Blog outline',
                     'Social post 1','Social post 2','Social post 3','Ad angle 1','Ad angle 2')
CONTENT_PACK_FOCUS=(
    'Repurpose one app benefit from the approved facts into exactly eight draft items, '
    'in this order, with these exact titles: '+', '.join(CONTENT_PACK_TITLES)+'. '
    'Each detail must contain usable copy or a concise outline and a relevant next action. '
    'Use one app outcome and one clear first-value action. Vary hooks, not product facts. '
    'Cite the approved source IDs supporting each item. Keep product facts, audience, '
    'brand boundaries and offer details consistent. Mark missing facts in unknowns; '
    'do not invent reviews, buyer badges, prices, rights, results or urgency. '
    'These are text drafts, not rendered images, videos, sent email or published posts.')


def recipe(task,focus):
    """Only the exact approved task/focus selects this versioned structure."""
    if task!='original_copy' or focus!=CONTENT_PACK_FOCUS:return None
    return dict(id=CONTENT_PACK_ID,version=1,task='original_copy',focus=CONTENT_PACK_FOCUS,
                item_titles=list(CONTENT_PACK_TITLES),status='TEXT_DRAFTS_ONLY',
                route='EXISTING_OWNER_REVIEWED_DRAFT_WORKFLOW',
                next_step='Review the pack, select one creative angle, then preregister an app-outcome experiment through the existing brief and experiment workflows.',
                factual_verification='OWNER_REVIEW_REQUIRED',publication='NOT_RUN')


def catalog():
    """Discovery adds no task, tool, transmission, grant or execution authority."""
    return [recipe('original_copy',CONTENT_PACK_FOCUS)]


def validate(value,selected):
    """A successful generic draft is not a complete pack unless every slot exists."""
    if selected is None:return None
    if selected!=recipe('original_copy',CONTENT_PACK_FOCUS):
        raise Invalid('Draft recipe changed; review the current recipe')
    items=value['items']
    if [item['title'] for item in items]!=selected['item_titles']:
        raise Invalid('Content pack needs every requested item in its reviewed order')
    if any(not item['detail'].strip() or not item['source_ids'] for item in items):
        raise Invalid('Content pack items need nonblank draft text and approved source references')
    return dict(id=selected['id'],version=selected['version'],status='TEXT_DRAFT_PACK_READY',
                factual_verification='OWNER_REVIEW_REQUIRED',rendering='NOT_RUN',publication='NOT_RUN')
