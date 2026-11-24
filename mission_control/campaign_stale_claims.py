"""Index approved public wording and flag changed sources, never rewrite it."""

import time
from html import unescape
from html.parser import HTMLParser
from sqlite3 import Connection
from typing import Any

from .aeo_transport import PublicReader, ReadError, public_url
from .common import Invalid, digest, iso_time, required
from .marketing_review_store import rows, save


def source_snapshot(db: Connection, app: str, claim_ids: list[str]) -> dict:
    """Freeze source identities rather than guessing claims from public prose."""
    row = db.execute("SELECT data FROM apps WHERE id=?", (app,)).fetchone()
    if row is None:
        raise Invalid("Product source is unavailable")
    import json

    result: dict[str, Any] = dict(app_sha256=digest(json.loads(row["data"])), claims={})
    product_claims = []
    for claim in db.execute(
        "SELECT id,data,hash,source FROM records WHERE app_id=? AND kind='claim' ORDER BY id", (app,)
    ):
        if digest(dict(kind="claim", data=json.loads(claim["data"]), source=claim["source"])) != claim["hash"]:
            raise Invalid("Product claim integrity changed")
        product_claims.append((claim["id"], claim["hash"]))
    result["product_claims_sha256"] = digest(product_claims)
    if (
        not isinstance(claim_ids, list)
        or len(claim_ids) > 100
        or any(not isinstance(item, str) for item in claim_ids)
        or len(set(claim_ids)) != len(claim_ids)
    ):
        raise Invalid("Select distinct product claim IDs")
    for identity in claim_ids:
        row = db.execute(
            "SELECT data,hash,source FROM records WHERE app_id=? AND id=? AND kind='claim'", (app, identity)
        ).fetchone()
        if row is None or digest(dict(kind="claim", data=json.loads(row["data"]), source=row["source"])) != row["hash"]:
            raise Invalid("Product claim source is unavailable or changed")
        result["claims"][identity] = row["hash"]
    return result


def retain_post(
    db: Connection, app: str, owner: str, scope: str, identity: str, snapshot: dict, url: str, published_at: str
) -> dict:
    """Index a provider-verified post from the original exact approved request."""
    public_url(url, allow_tracking=True)
    iso_time(published_at)
    return save(
        db,
        app,
        owner,
        "ARTIFACT",
        identity,
        scope,
        dict(
            url=url,
            approved_claim_text=snapshot["approved_claim_text"],
            source=snapshot["source"],
            source_sha256=digest(snapshot["source"]),
            published_at=published_at,
            provenance="VERIFIED_CAMPAIGN_RECEIPT",
        ),
    )


def retain_verified_receipt(
    db: Connection, app: str, row: Any, status: str, result: dict | None, previous: dict
) -> None:
    """Index only verified public receipts inside the caller's existing transaction."""
    if status != "VERIFIED" or not result or not result.get("permalink_url") or not previous.get("claim_snapshot"):
        return
    scope = db.execute("SELECT owner FROM campaign_scopes WHERE app_id=? AND id=?", (app, row["scope_id"])).fetchone()
    retain_post(
        db,
        app,
        scope["owner"],
        row["scope_id"],
        row["id"],
        previous["claim_snapshot"],
        result["permalink_url"],
        row["created"],
    )


def review(db: Connection, app: str, owner: str, scope: str) -> dict:
    """A report reads saved local evidence only, without public-page requests."""
    artifacts = []
    for row in [*rows(db, app, owner, scope, "ARTIFACT"), *rows(db, app, owner, "", "ARTIFACT")]:
        data = row["data"]
        try:
            current = source_snapshot(db, app, list(data["source"]["claims"]))
            stale = current != data["source"] or digest(data["source"]) != data["source_sha256"]
        except Invalid:
            stale = True
        artifacts.append(
            dict(
                id=row["id"],
                url=data["url"],
                approved_claim_text=data["approved_claim_text"],
                published_at=data["published_at"],
                link_status="RECORDED" if data["url"] else "PUBLIC_URL_UNAVAILABLE",
                source_sha256=data["source_sha256"],
                status="STALE" if stale else "SOURCE_UNCHANGED",
            )
        )
    return dict(
        artifacts=artifacts,
        stale_count=sum(row["status"] == "STALE" for row in artifacts),
        action="OWNER_REVIEW_ONLY",
        public_content="NOT_READ",
        automatic_changes=False,
    )


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in ("script", "style"):
            self.hidden += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style"):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data: str) -> None:
        if not self.hidden:
            self.parts.append(data)


def verify_public(url: str, wording: str) -> dict:
    """Explicit credential-free public check, outside report/storage transactions."""
    target = public_url(url, allow_tracking=True)
    wording = required(wording, "Approved public wording", 20000)
    reader = PublicReader(allow_tracking=True)
    reader.deadline = time.monotonic() + 10
    try:
        result = reader.read(target, 1048576)
    except ReadError as error:
        return dict(status="UNVERIFIABLE", reason=error.code)
    if result["status"] != 200:
        return dict(status="UNVERIFIABLE", http_status=result["status"])
    parser = _Text()
    parser.feed(result["body"].decode("utf-8", errors="replace"))
    text = " ".join(unescape(" ".join(parser.parts)).split())
    return dict(
        status="WORDING_FOUND" if " ".join(wording.split()) in text else "WORDING_NOT_FOUND",
        final_url=result["url"],
        response_sha256=result["sha256"],
        limits="Public response text only; rendered or authenticated pages may be unverifiable.",
    )


def retained_claim_snapshot(db: Connection, app: str, post: dict, destination_check: dict | None, tag: Any) -> dict:
    """Freeze the original source and preserve optional destination and tag evidence."""
    retained: dict[str, Any] = {
        "claim_snapshot": dict(approved_claim_text=post["message"], source=source_snapshot(db, app, []))
    }
    if destination_check:
        retained["destination_check"] = destination_check
    if tag is not None:
        retained["campaign_tag_hash"] = digest(tag)
    return retained
