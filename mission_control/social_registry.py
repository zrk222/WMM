"""Official read-first social protocols; authentication never grants campaign authority."""
from copy import deepcopy
from .common import Invalid

META_VERSION='v26.0'
PROVIDERS={
 'facebook':dict(name='Facebook',destination='Page',scopes=['public_profile','pages_show_list','pages_read_engagement'],
   authorize='https://www.facebook.com/'+META_VERSION+'/dialog/oauth',
   token_url='https://graph.facebook.com/'+META_VERSION+'/oauth/access_token',
   identity='https://graph.facebook.com/'+META_VERSION+'/me',
   docs='https://developers.facebook.com/documentation/facebook-login/guides/advanced/manual-flow',
   setup='https://developers.facebook.com/apps/',renewal='OFFICIAL_REAUTHORIZATION',separator=','),
 'instagram':dict(name='Instagram',destination='Professional account',scopes=['instagram_business_basic'],
   authorize='https://www.instagram.com/oauth/authorize',token_url='https://api.instagram.com/oauth/access_token',
   identity='https://graph.instagram.com/'+META_VERSION+'/me',
   docs='https://developers.facebook.com/documentation/instagram-platform/instagram-api-with-instagram-login/business-login',
   setup='https://developers.facebook.com/apps/',renewal='LONG_LIVED_TOKEN_REFRESH',separator=','),
 'tiktok':dict(name='TikTok',destination='TikTok account',scopes=['user.info.basic'],
   authorize='https://www.tiktok.com/v2/auth/authorize/',token_url='https://open.tiktokapis.com/v2/oauth/token/',
   identity='https://open.tiktokapis.com/v2/user/info/',
   docs='https://developers.tiktok.com/docs/en/login-kit-desktop',
   setup='https://developers.tiktok.com/apps/',renewal='REFRESH_TOKEN',separator=','),
 'youtube':dict(name='YouTube',destination='Channel',scopes=['https://www.googleapis.com/auth/youtube.readonly'],
   authorize='https://accounts.google.com/o/oauth2/v2/auth',token_url='https://oauth2.googleapis.com/token',
   identity='https://www.googleapis.com/youtube/v3/channels',
   docs='https://developers.google.com/youtube/v3/guides/auth/server-side-web-apps',
   setup='https://console.cloud.google.com/apis/credentials',renewal='REFRESH_TOKEN',separator=' '),
 'linkedin':dict(name='LinkedIn',destination='Member profile',scopes=['openid','profile'],
   authorize='https://www.linkedin.com/oauth/v2/authorization',token_url='https://www.linkedin.com/oauth/v2/accessToken',
   identity='https://api.linkedin.com/v2/userinfo',
   docs='https://learn.microsoft.com/en-us/linkedin/shared/authentication/authorization-code-flow',
   setup='https://www.linkedin.com/developers/apps',renewal='REFRESH_IF_ISSUED_OTHERWISE_REAUTHORIZE',separator=' ')}
NATIVE_LINKEDIN='https://www.linkedin.com/oauth/native-pkce/authorization'
SECRET_FIELDS=('client_secret','access_token','refresh_token','page_token','verifier')


def resolve_scopes(provider,mode='read'):
    if (provider not in PROVIDERS or mode not in ('read','publish','ads','instagram_publish')
            or (mode in ('ads','instagram_publish') and provider!='facebook')):
        raise Invalid('Social permission configuration changed; prepare setup again')
    scopes=list(PROVIDERS[provider]['scopes'])
    if mode=='instagram_publish':scopes.extend(['instagram_basic','instagram_content_publish'])
    if mode in ('publish','ads'):
        scopes.extend({'facebook':['pages_manage_posts'], 'instagram':['instagram_business_content_publish'],
                       'tiktok':['video.publish','video.list'], 'linkedin':['w_member_social'],
                       'youtube':['https://www.googleapis.com/auth/youtube.upload']}[provider])
    if mode=='ads':scopes.extend(['ads_management','ads_read'])
    return scopes


def catalog():
    """Expose protocols and honest entitlement states, never configured secrets."""
    channel_kinds={'facebook':(), 'instagram':('instagram_reel',), 'tiktok':('tiktok_video',),
                   'youtube':('youtube_short',), 'linkedin':('linkedin_video','linkedin_text')}
    connection_provider={'instagram':'facebook'}
    return {key:dict(deepcopy(value),publication_kinds=list(channel_kinds[key]),
                     publication_connection_provider=connection_provider.get(key,key),
                     publishing_implemented=key=='facebook' or bool(channel_kinds[key]),automatic_ad_spend=False,
                     paid_campaign_execution_implemented=key=='facebook',
                     execution_authority='SEPARATE_OWNER_SCOPE_AND_CURRENT_PERMISSIONS_REQUIRED',
                     setup_required=True) for key,value in PROVIDERS.items()}
