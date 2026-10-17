"""Official read-first social protocols; authentication never grants campaign authority."""
from copy import deepcopy

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
 'linkedin':dict(name='LinkedIn',destination='Member profile',scopes=['openid','profile'],
   authorize='https://www.linkedin.com/oauth/v2/authorization',token_url='https://www.linkedin.com/oauth/v2/accessToken',
   identity='https://api.linkedin.com/v2/userinfo',
   docs='https://learn.microsoft.com/en-us/linkedin/shared/authentication/authorization-code-flow',
   setup='https://www.linkedin.com/developers/apps',renewal='REFRESH_IF_ISSUED_OTHERWISE_REAUTHORIZE',separator=' ')}
NATIVE_LINKEDIN='https://www.linkedin.com/oauth/native-pkce/authorization'
SECRET_FIELDS=('client_secret','access_token','refresh_token','page_token','verifier')


def catalog():
    """Expose protocols and honest entitlement states, never configured secrets."""
    return {key:dict(deepcopy(value),publishing_implemented=False,automatic_ad_spend=False,
                     setup_required=True) for key,value in PROVIDERS.items()}
