"""Bounded public campaign context; no network, credential or uploaded-file reads."""

from collections.abc import Callable, Mapping
from sqlite3 import Connection, Row
from typing import cast

from . import (
    agent_economics,
    agent_feedback,
    agent_registry,
    pipeline,
)
from . import creative_taste as creative_taste_module
from . import release_readiness as release_readiness_module
from . import store as store_module
from . import subscription_readiness as subscription_readiness_module
from .common import Invalid, canonical, digest
from .db import connection
from .store import Store


def decode(row: Row) -> dict[str, object]:
    return cast(
        Callable[[Row], dict[str, object]],
        vars(store_module).get("decode"),
    )(row)


def evaluate(
    app: object,
    records: object,
    ledger_reports: object = (),
    catalog: object = None,
    release: object = None,
) -> list[Mapping[str, object]]:
    return cast(
        Callable[..., list[Mapping[str, object]]],
        vars(pipeline).get("evaluate"),
    )(app, records, ledger_reports, catalog, release)


def release_readiness(app: object, records: object, jobs: object, statuses: object) -> Mapping[str, object]:
    return cast(
        Callable[..., Mapping[str, object]],
        vars(release_readiness_module).get("readiness"),
    )(app, records, jobs, statuses)


def subscription_readiness(app: object, records: object, jobs: object, statuses: object) -> Mapping[str, object]:
    return cast(
        Callable[..., Mapping[str, object]],
        vars(subscription_readiness_module).get("readiness"),
    )(app, records, jobs, statuses)


def derive(store: Store, app: object) -> tuple[list[Mapping[str, object]], Mapping[str, object]]:
    return cast(
        Callable[..., tuple[list[Mapping[str, object]], Mapping[str, object]]],
        vars(agent_economics).get("derive"),
    )(store, app)


def feedback(store: Store, app: object) -> Mapping[str, object]:
    return cast(
        Callable[..., Mapping[str, object]],
        vars(agent_feedback).get("feedback"),
    )(store, app)


def creative_taste() -> Mapping[str, object]:
    return cast(
        Callable[[], Mapping[str, object]],
        vars(creative_taste_module).get("guidance"),
    )()


FACTS = cast(tuple[str, ...], vars(agent_registry).get("FACTS"))

LIMIT = 100
MAX_CHARS = 32768
SCHEMA = "growth.agent-context.v1"


def indexed(db: Connection, sql: str, app_id: str) -> list[dict[str, object]]:
    """Reject overflow instead of silently omitting a newer failed observation."""
    rows = db.execute(sql, (app_id, LIMIT + 1)).fetchall()
    if len(rows) > LIMIT:
        raise Invalid("Agent source index exceeds100 entries; narrow or archive evidence, then review again")
    return [decode(row) for row in rows]


def saved_sources(store: Store, app_id: str) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Load this app only; review content is replaced with a critical-count signal."""
    with connection(store.path) as db:
        records = indexed(
            db, "SELECT * FROM records WHERE app_id=? AND kind!='review' ORDER BY updated DESC,id LIMIT ?", app_id
        )
        reviews = cast(
            int,
            db.execute(
                "SELECT COUNT(*) FROM records WHERE app_id=? AND kind='review' AND json_extract(data,'$.confirmed')=1 AND json_extract(data,'$.severity')='P0'",
                (app_id,),
            ).fetchone()[0],
        )
        jobs = indexed(
            db,
            "SELECT * FROM jobs WHERE app_id=? AND action='sync' AND json_extract(data,'$.options.operation') IN ('release_inventory','subscription_catalog') ORDER BY created DESC,id LIMIT ?",
            app_id,
        )
    if reviews:
        records.append(
            dict(
                id="critical-summary",
                app_id=app_id,
                kind="review",
                title="Confirmed critical feature failure",
                data=dict(confirmed=True, severity="P0"),
                hash=digest(reviews),
                version=1,
                updated="",
            )
        )
    return records, jobs


def source(identity: str, classification: str, data: Mapping[str, object]) -> dict[str, object]:
    """Bind citations to exactly the sanitized values approved for transmission."""
    return dict(
        id=identity,
        classification=classification,
        data=data,
        sha256=digest(data),
    )


def provider_source(identity: str, view: Mapping[str, object]) -> dict[str, object]:
    """Expose validator state and public identity, never raw reports or diagnostics."""
    report = cast(Mapping[str, object], view.get("report") or {})
    values: dict[str, object] = dict(
        state=view["state"],
        access="NOT_CHECKED",
        scope="Saved provider observation only; no live access or product journey verified",
    )
    for key in ("store_app_id", "job_id"):
        if key in view:
            values[key] = view[key]
    for key in ("observed_at", "review_state", "coverage", "version", "platform"):
        if key in report:
            values[key] = report[key]
    if view["state"] not in ("NOT_APPLICABLE", "INVENTORY_CHECKED", "CATALOG_APPROVED"):
        values["resolution"] = (
            "Inspect this app saved provider read; reconnect or refresh it, then review a new proposal"
        )
    return source(identity, "SAVED_PROVIDER_OBSERVATION", values)


def stage_source(stage: Mapping[str, object]) -> dict[str, object]:
    """Use catalog instructions and counts, excluding operator-written diagnostics."""
    data: dict[str, object] = {
        key: stage[key]
        for key in (
            "id",
            "title",
            "status",
            "inputs",
            "dependencies",
            "operations",
        )
    }
    data.update(
        missing_count=len(cast(list[object], stage["missing"])),
        evidence_scope="OPERATOR_ASSERTIONS_AND_SAVED_PROVIDER_CHECKS",
        economics="Current imported-ledger derivation; amounts excluded and provider signatures not independently verified",
    )
    return source("stage_" + str(stage["id"]), "WORKFLOW_DERIVATION", data)


def snapshot(store: Store, app_id: str) -> dict[str, object]:
    """Assemble the selected public manifest and twelve current stage summaries."""
    app = store.app(app_id)
    records, jobs = saved_sources(store, app_id)
    release = release_readiness(app, records, jobs, {})
    subscriptions = subscription_readiness(app, records, jobs, {})
    ledger, economics = derive(store, app)
    fields = FACTS + (
        "brand_source",
        "brand_visual",
        "store_app_id",
        "authorized_spend_minor",
    )
    app_data = cast(Mapping[str, object], app["data"])
    facts: dict[str, object] = {key: app_data.get(key) for key in fields}
    facts["authorized_spend_minor"] = 0
    sources: list[dict[str, object]] = [source("app_manifest", "OWNER_SUPPLIED_PUBLIC_FACTS", facts)]
    sources += [
        stage_source(stage)
        for stage in evaluate(app, records, ledger_reports=ledger, catalog=subscriptions, release=release)
    ]
    sources += [
        provider_source("release_observation", release),
        provider_source("subscription_observation", subscriptions),
    ]
    sources += [source("ledger_state", "LOCAL_IMPORTED_LEDGER_DERIVATION", economics)]
    sources += [source("action_feedback", "TYPED_LOCAL_ACTION_OUTCOMES", feedback(store, app))]
    sources += [source("creative_taste", "PRODUCT_ADVISORY_GUIDANCE", creative_taste())]
    value: dict[str, object] = dict(
        schema=SCHEMA,
        app_id=app_id,
        sources=sources,
        excluded=[
            "credentials",
            "personal histories",
            "uploaded files",
            "customer review text",
            "raw provider reports",
        ],
        external_execution="NOT_RUN",
    )
    # Bind all selected evidence versions without transmitting their contents.
    value["evidence_fingerprint"] = digest(
        dict(
            records=[(r["id"], r.get("version"), r.get("hash")) for r in records],
            jobs=[(j["id"], j["status"], digest(j.get("result"))) for j in jobs],
        )
    )
    if len(canonical(value)) > MAX_CHARS:
        raise Invalid("Agent context exceeds32768 characters; shorten public app facts and review again")
    return value
