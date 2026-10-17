"""Fixed-host, bounded read-only Stripe transport; no provider mutation capability."""
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, HTTPRedirectHandler, build_opener
from .common import Invalid
from .payment_signature import strict_json


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        """Reject every redirect before a credential can leave the fixed API host."""
        raise Invalid("Stripe redirect blocked; credential was not forwarded")


def read(config,path):
    """Read only account, charge, refund or balance identities through HTTPS."""
    if not re.fullmatch(r"/(?:account|charges/ch_[A-Za-z0-9_]{1,110}|refunds/re_[A-Za-z0-9_]{1,110}|balance_transactions/txn_[A-Za-z0-9_]{1,110})",path):
        raise Invalid("Unsupported Stripe read path")
    request=Request("https://api.stripe.com/v1"+path,headers={
        "Authorization":"Bearer "+config["api_key"],"Stripe-Version":config["api_version"],"Accept":"application/json"},method="GET")
    try:
        with build_opener(NoRedirect()).open(request,timeout=15) as response:
            raw=response.read(262145)
        return strict_json(raw)
    except HTTPError as exc:
        raise Invalid("Stripe read returned HTTP "+str(exc.code)+"; inspect restricted key access and retry") from exc
    except (URLError,TimeoutError,OSError) as exc:
        raise Invalid("Stripe read was unavailable; receipt is retained for explicit retry") from exc
