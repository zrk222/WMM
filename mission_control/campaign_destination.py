"""Credential-free, bounded destination reachability before link-post dispatch."""

import time
from .aeo_transport import PublicReader, ReadError, public_url
from .common import Invalid, digest, now


def check_destination(link):
    """Observe the approved URL, with no cookies, auth, unsafe hosts or silent rewrite.

    The shared reader pins public DNS, verifies TLS and permits at most two
    same-origin redirects. Public UTM parameters must survive each request and
    redirect exactly as approved.
    """
    if link is None:
        return None
    try:
        target = public_url(link, allow_tracking=True)
        reader = PublicReader(allow_tracking=True)
        reader.deadline = time.monotonic() + 10
        result = reader.read(target, 1048576)
    except ReadError as exc:
        raise Invalid(
            "Destination check failed (" + exc.code + "). Repair or choose a reachable public HTTPS landing page, "
            "then review the exact link again; no post was dispatched."
        ) from None
    if result["status"] != 200 or result["bytes"] < 1:
        raise Invalid(
            "Destination returned HTTP "
            + str(result["status"])
            + " or an empty response. Repair the landing page and retry "
            "the approved post; no post was dispatched."
        )
    return dict(
        schema="wmm.campaign-destination-check.v1",
        status="REACHABLE",
        observed_at=now(),
        approved_link_sha256=digest(link),
        final_url=result["url"],
        http_status=result["status"],
        response_sha256=result["sha256"],
        response_bytes=result["bytes"],
        requests=reader.requests,
        redirects=reader.redirects,
        scope="Public HTTPS response only; rendered app behavior, conversion and ongoing availability are unverified.",
    )
