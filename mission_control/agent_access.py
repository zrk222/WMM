"""Protected operational access profiles, separated from marketing evidence exports."""

import json
import sqlite3
import time
from collections.abc import Callable, Mapping
from typing import Protocol, cast

from . import (
    agent_native,
    agent_registry,
    credential_vault,
)
from . import (
    draft_recipes as draft_recipes_module,
)
from .agent_contract import exact, profile
from .agent_registry import KEYED, NATIVE, TASKS
from .common import Invalid, canonical, identifier, now, uid
from .credential_vault import Vault
from .db import connection
from .store import Store


class VaultLike(Protocol):
    def put(self, key: str, value: Mapping[str, object]) -> None: ...

    def get(self, key: str) -> Mapping[str, object] | None: ...

    def delete(self, key: str) -> None: ...


REGISTRY = cast(
    Mapping[str, Mapping[str, object]],
    vars(agent_registry)["REGISTRY"],
)


def catalog() -> list[Mapping[str, object]]:
    return cast(
        Callable[[], list[Mapping[str, object]]],
        vars(agent_registry)["catalog"],
    )()


def draft_recipes() -> list[Mapping[str, object]]:
    return cast(
        Callable[[], list[Mapping[str, object]]],
        vars(draft_recipes_module)["catalog"],
    )()


def locate(provider: str) -> Mapping[str, object]:
    return cast(
        Callable[[str], Mapping[str, object]],
        vars(agent_native)["locate"],
    )(provider)


def namespace(database: object) -> str:
    return cast(
        Callable[[object], str],
        vars(credential_vault)["namespace"],
    )(database)


def target(store: Store, app_id: str, reference: str) -> str:
    """A profile can address only its own local credential namespace."""
    identifier(app_id)
    identifier(reference)
    return "AgentGrowth/" + namespace(store.path) + "/" + app_id + "/" + reference


def decoded(row: sqlite3.Row | None) -> dict[str, object]:
    """Operational rows contain public configuration and opaque references only."""
    if row is None:
        raise Invalid("Agent connection does not belong to this app")
    value = dict(row)
    value["data"] = json.loads(cast(str, value["data"]))
    return value


def queue_retirement(
    db: sqlite3.Connection,
    app_id: str,
    reference: str | None,
    delay: float = 0,
) -> None:
    """Persist an opaque cleanup reference, never the protected key itself."""
    if reference:
        db.execute(
            "INSERT OR REPLACE INTO agent_retirements VALUES(?,?,?)",
            (app_id, reference, time.time() + delay),
        )


class AgentAccess:
    def __init__(
        self,
        store: Store,
        vault_factory: Callable[[], VaultLike] | None = None,
    ) -> None:
        self.store = store
        self.vault_factory = vault_factory

    def _vault(self) -> VaultLike:
        factory = self.vault_factory or cast(
            Callable[[], VaultLike],
            Vault,
        )
        return factory()

    def get(self, app_id: str, identity: str) -> dict[str, object]:
        """Never find a connection by ID without its selected app scope."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            return decoded(
                db.execute("SELECT * FROM agent_connections WHERE app_id=? AND id=?", (app_id, identity)).fetchone()
            )

    def view(self, app_id: str) -> dict[str, object]:
        """Refresh without invoking native tools, networking or reading secret values."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            profiles = [
                decoded(r)
                for r in db.execute(
                    "SELECT * FROM agent_connections WHERE app_id=? ORDER BY created",
                    (app_id,),
                )
            ]
            route = db.execute("SELECT * FROM agent_routes WHERE app_id=?", (app_id,)).fetchone()
            cleanup = cast(
                int,
                db.execute(
                    "SELECT COUNT(*) FROM agent_retirements WHERE app_id=?",
                    (app_id,),
                ).fetchone()[0],
            )
        for row in profiles:
            data = cast(dict[str, object], row["data"])
            tool = data.pop("tool", None)
            if tool:
                tool_data = cast(Mapping[str, object], tool)
                data["tool_identity"] = dict(
                    fingerprint=tool_data["fingerprint"],
                    version=tool_data.get("package_version"),
                )
            data["protected_key"] = bool(data.pop("credential_ref", None))
        return dict(
            providers=catalog(),
            tasks=TASKS,
            profiles=profiles,
            draft_recipes=draft_recipes(),
            routing=decoded(route) if route else dict(version=0, data={"mode": "subscription", "routes": {}}),
            app_billing=False,
            automatic_fallback=False,
            cleanup_pending=cleanup,
        )

    def save(self, app_id: str, body: Mapping[str, object]) -> dict[str, object]:
        """Stage a protected key before optimistic commit; failed saves retire only the stage."""
        self.store.app(app_id)
        data = profile(body)
        previous = self.previous(app_id, body)
        identity = cast(str, previous["id"]) if previous else uid()
        provider = cast(str, data["provider"])
        if provider in NATIVE:
            data["tool"] = locate(provider)
        reference = self.stage(app_id, cast(str, body["api_key"])) if provider in KEYED and body["api_key"] else None
        if reference:
            data["credential_ref"] = reference
        try:
            self.commit(app_id, identity, data, previous)
        except Exception:
            if reference:
                self.retire(app_id, {"data": {"credential_ref": reference}})
            raise
        cleanup = self.retire(app_id, previous)
        return dict(
            connection=self.get(app_id, identity)["id"],
            status="CONFIGURED_UNTESTED",
            cleanup=cleanup,
        )

    def stage(self, app_id: str, key: object) -> str:
        """Register crash recovery before touching protected storage."""
        reference = uid()
        with connection(self.store.path) as db:
            queue_retirement(db, app_id, reference, 300)
        try:
            self._vault().put(
                target(self.store, app_id, reference),
                {"api_key": key},
            )
        except Exception:
            self.retire(app_id, {"data": {"credential_ref": reference}})
            raise
        return reference

    def previous(self, app_id: str, body: Mapping[str, object]) -> Mapping[str, object] | None:
        """Resolve only the selected app version before staging a replacement key."""
        identity = cast(str | None, body["id"])
        previous = self.get(app_id, identity) if identity else None
        if previous and previous["version"] != body["version"]:
            raise Invalid("Connection changed; reload before editing")
        if not previous and body["version"] is not None:
            raise Invalid("New connection must not supply a version")
        return previous

    def commit(
        self,
        app_id: str,
        identity: str,
        data: Mapping[str, object],
        previous: Mapping[str, object] | None,
    ) -> None:
        """Compare the same app-owned version inside the SQLite writer transaction."""
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute(
                "SELECT version FROM agent_connections WHERE app_id=? AND id=?", (app_id, identity)
            ).fetchone()
            if previous and (current is None or current["version"] != previous["version"]):
                raise Invalid("Connection changed during save")
            if not previous and current:
                raise Invalid("Connection identity already exists")
            self.activate_stage(db, app_id, data)
            if previous:
                previous_data = cast(Mapping[str, object], previous["data"])
                queue_retirement(db, app_id, cast(str | None, previous_data.get("credential_ref")))
            version = cast(int, previous["version"]) + 1 if previous else 1
            db.execute(
                "INSERT OR REPLACE INTO agent_connections VALUES(?,?,?,?,?,?,?,?)",
                (
                    app_id,
                    identity,
                    version,
                    canonical(data),
                    "CONFIGURED_UNTESTED",
                    None,
                    previous["created"] if previous else now(),
                    now(),
                ),
            )

    def activate_stage(self, db: sqlite3.Connection, app_id: str, data: Mapping[str, object]) -> None:
        """Serialize active-key attachment against cleanup of an expired stage."""
        reference = cast(str | None, data.get("credential_ref"))
        if not reference:
            return
        staged = db.execute(
            "SELECT 1 FROM agent_retirements WHERE app_id=? AND reference=?",
            (app_id, reference),
        ).fetchone()
        if not staged or not self._vault().get(target(self.store, app_id, reference)):
            raise Invalid("Protected key stage expired; save this connection again")
        db.execute("DELETE FROM agent_retirements WHERE app_id=? AND reference=?", (app_id, reference))

    def retire(self, app_id: str, previous: Mapping[str, object] | None) -> str:
        """Local removal does not imply revocation of a provider account or other tool."""
        reference = (
            cast(str | None, cast(Mapping[str, object], previous["data"]).get("credential_ref")) if previous else None
        )
        if not reference:
            return "NO_PRIOR_KEY"
        with connection(self.store.path) as db:
            queue_retirement(db, app_id, reference)
        try:
            self.clean_one(app_id, reference)
            return "PRIOR_LOCAL_KEY_REMOVED"
        except Invalid:
            return "LOCAL_KEY_CLEANUP_REQUIRED"

    def clean_one(self, app_id: str, reference: str) -> None:
        """Delete only queued retired keys; never remove an active app connection."""
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            pending = db.execute(
                "SELECT eligible FROM agent_retirements WHERE app_id=? AND reference=?", (app_id, reference)
            ).fetchone()
            if pending is None or pending["eligible"] > time.time():
                return
            active = db.execute(
                "SELECT 1 FROM agent_connections WHERE app_id=? AND status!='DISCONNECTED' AND json_extract(data,'$.credential_ref')=?",
                (app_id, reference),
            ).fetchone()
            if active:
                raise Invalid("Cleanup cannot remove an active provider key")
            self._vault().delete(target(self.store, app_id, reference))
            db.execute("DELETE FROM agent_retirements WHERE app_id=? AND reference=?", (app_id, reference))

    def cleanup(self, app_id: str) -> dict[str, object]:
        """Retry app-owned stale-key cleanup after storage recovery or process restart."""
        self.store.app(app_id)
        with connection(self.store.path) as db:
            pending = [
                r["reference"]
                for r in db.execute(
                    "SELECT reference FROM agent_retirements WHERE app_id=? AND eligible<=? LIMIT 20",
                    (app_id, time.time()),
                )
            ]
        for reference in pending:
            self.clean_one(app_id, reference)
        return dict(remaining=self.view(app_id)["cleanup_pending"], provider_revocation="NOT_PERFORMED")

    def disconnect(self, app_id: str, identity: str, body: Mapping[str, object]) -> dict[str, object]:
        """Disable execution first, keeping unrelated provider sessions signed in."""
        exact(body, ("version",))
        row = self.get(app_id, identity)
        if row["version"] != body["version"]:
            raise Invalid("Connection changed; reload before disconnecting")
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            changed = db.execute(
                "UPDATE agent_connections SET status='DISCONNECTED',version=version+1,updated=? WHERE app_id=? AND id=? AND version=?",
                (now(), app_id, identity, body["version"]),
            ).rowcount
            if not changed:
                raise Invalid("Connection changed during disconnect")
            row_data = cast(Mapping[str, object], row["data"])
            queue_retirement(db, app_id, cast(str | None, row_data.get("credential_ref")))
        return dict(status="DISCONNECTED", cleanup=self.retire(app_id, row), provider_revocation="NOT_PERFORMED")

    def routes(self, app_id: str, body: Mapping[str, object]) -> object:
        """Pin app-owned routes; no implicit API fallback, purchase or provider swap."""
        exact(body, ("version", "mode", "routes"))
        if (
            body["mode"] not in ("subscription", "byok", "local", "mixed")
            or not isinstance(body["routes"], dict)
            or set(cast(dict[object, object], body["routes"])) - set(TASKS)
        ):
            raise Invalid("Choose subscription, BYOK or mixed task routing")
        self.validate_routes(app_id, body)
        self.store.app(app_id)
        with connection(self.store.path) as db:
            db.execute("BEGIN IMMEDIATE")
            current = db.execute("SELECT version FROM agent_routes WHERE app_id=?", (app_id,)).fetchone()
            version = current["version"] if current else 0
            if type(body["version"]) is not int or body["version"] != version:
                raise Invalid("Routes changed; reload before saving")
            routes = cast(Mapping[str, object], body["routes"])
            db.execute(
                "INSERT OR REPLACE INTO agent_routes VALUES(?,?,?,?)",
                (
                    app_id,
                    version + 1,
                    canonical({"mode": body["mode"], "routes": routes}),
                    now(),
                ),
            )
        return self.view(app_id)["routing"]

    def validate_routes(self, app_id: str, body: Mapping[str, object]) -> None:
        """Validate each chosen app-owned provider without introducing a fallback."""
        routes = cast(Mapping[str, str], body["routes"])
        for identity in routes.values():
            if not identity:
                continue
            row = self.get(app_id, identity)
            if row["status"] == "DISCONNECTED":
                raise Invalid("Reconnect this route before selecting it")
            row_data = cast(Mapping[str, object], row["data"])
            provider = cast(str, row_data["provider"])
            if body["mode"] != "mixed" and REGISTRY[provider]["mode"] != body["mode"]:
                raise Invalid("Selected connection is outside the chosen access mode")

    def secret(self, app_id: str, row: Mapping[str, object]) -> object | None:
        """Resolve only the selected connection's protected key just before use."""
        data = cast(Mapping[str, object], row["data"])
        reference = cast(str | None, data.get("credential_ref"))
        if not reference:
            return None
        value = self._vault().get(target(self.store, app_id, reference))
        if not value or set(value) != {"api_key"}:
            raise Invalid("Protected provider key is unavailable; reconnect this app profile")
        return value["api_key"]


def detect(provider: object) -> dict[str, object]:
    """Explicit official status inspection returns no credential or executable paths."""
    if not isinstance(provider, str) or provider not in NATIVE:
        raise Invalid("Choose a supported native adapter")
    found = cast(
        Callable[[str], Mapping[str, object]],
        vars(agent_native)["identity"],
    )(provider)
    return {
        key: found[key]
        for key in (
            "version",
            "fingerprint",
            "login_state",
            "quota",
            "account_identity",
        )
    }
