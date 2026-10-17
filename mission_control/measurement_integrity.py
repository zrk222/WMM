"""Read-only financial correspondence; no inferred attribution or cash allocation."""
import json
import sqlite3
from .common import Invalid, digest
from .db import connection

TABLES = ("growth_cohorts", "growth_events", "payment_sources", "payment_receipts",
          "payment_attempts", "payment_effects")
KINDS = {"PURCHASE": "charge", "REFUND": "refund", "REFUND_REVERSED": "refund_reversal"}
LIMIT = 10000


def validated(row, table):
    """Verify stored bytes against their original table-specific hash envelope."""
    result = dict(row)
    value = json.loads(result["data"])
    if not isinstance(value, dict):
        raise Invalid("Measurement evidence must contain a structured record")
    envelope = {"cohort_id": result["cohort_id"], "event": value} if table == "growth_events" else value
    if digest(envelope) != result["hash"]:
        raise Invalid("Measurement integrity: stored evidence hash differs; inspect the source history")
    result["data"] = value
    return result


def snapshot(store, app) -> object:
    """Read one app-scoped consistent SQLite snapshot without secrets or network access."""
    store.app(app)
    result = {"app_id": app}
    with connection(store.path) as db:
        db.execute("BEGIN")
        for table in TABLES:
            rows = db.execute(f"SELECT * FROM {table} WHERE app_id=? ORDER BY rowid LIMIT ?", (app, LIMIT + 1)).fetchall()
            if len(rows) > LIMIT:
                raise Invalid("Measurement comparison exceeds 10000 rows in a collection; inspect a bounded export")
            result[table] = [validated(row, table) for row in rows]
    return result


def lineage(receipt, attempt, sources):
    """An old positive attempt cannot survive revocation, rotation or a latest failure."""
    if receipt["imported"] or not attempt:
        return None
    data = attempt["data"]
    source = sources.get(data.get("source_id"))
    if not source or source["imported"] or source["status"] != "ACTIVE":
        return None
    if receipt["status"] not in ("RECONCILED", "DUPLICATE_EFFECT") or data.get("status") not in ("RECONCILED", "DUPLICATE_EFFECT"):
        return None
    if data.get("receipt_hash") != receipt["hash"] or data.get("source_version") != source["version"]:
        return None
    return source


def authorized_effect(effect, source, receipt):
    """Match immutable provider identity and account/mode with the signed receipt."""
    config, signed = source["data"], receipt["data"]
    return (effect.get("account_id") == config.get("account_id")
            and type(effect.get("livemode")) is bool
            and effect["livemode"] is config.get("livemode")
            and effect["livemode"] is signed.get("livemode")
            and effect.get("object_id") == signed.get("object_id")
            and effect.get("charge_id") == signed.get("charge_id"))


def current_effects(data):
    """Deduplicate exact current lineage and exclude unsupported or stale attempts."""
    sources = {row["id"]: row for row in data["payment_sources"]}
    latest = {}
    for row in data["payment_attempts"]:
        old = latest.get(row["event_id"])
        if not old or row["version"] > old["version"]:
            latest[row["event_id"]] = row
    stored = {row["object_id"]: row["data"] for row in data["payment_effects"]}
    accepted = {}
    for receipt in data["payment_receipts"]:
        attempt = latest.get(receipt["event_id"])
        source = lineage(receipt, attempt, sources)
        if source:
            admit_effects(accepted, stored, attempt["data"].get("effects", []), source, receipt)
    return {key: effect for key, effect in accepted.items() if effect is not None}


def admit_effects(accepted, stored, effects, source, receipt):
    """Quarantine conflicts regardless of iteration order; identical lineage deduplicates."""
    if not isinstance(effects, list):
        raise Invalid("Payment attempt effects must be a collection")
    for effect in effects:
        if not isinstance(effect, dict):
            raise Invalid("Payment effect must contain a structured record")
        balance = effect.get("balance_id")
        if authorized_effect(effect, source, receipt):
            key = ("stripe_live" if effect["livemode"] else "stripe_test", balance)
            exact = stored.get(balance) == effect
            accepted[key] = effect if exact and accepted.get(key, effect) == effect else None


def relationship(event, effect, available):
    """Check refund/reversal ownership without inferring subject or cohort attribution."""
    if event["type"] == "PURCHASE":
        return True
    parent = available.get((event["provider"], event["related_event_id"]))
    if not parent or parent["charge_id"] != effect["charge_id"]:
        return False
    if event["type"] == "REFUND":
        return parent["kind"] == "charge"
    return parent["kind"] == "refund" and parent["object_id"] == effect["object_id"]


def correspondence(event, effect, available):
    """Separate exact signed net-cash correspondence from test and unknown evidence."""
    if event["provider"] not in ("stripe_live", "stripe_test"):
        return "UNSUPPORTED_PROVIDER"
    if not effect:
        return "UNVERIFIED"
    expected = KINDS[event["type"]]
    matched = (effect["kind"] == expected and effect["currency"] == event["currency"]
               and amount_corresponds(event, effect)
               and relationship(event, effect, available))
    if not matched:
        return "CONFLICT"
    return "CASH_MATCHED" if effect["livemode"] else "TEST_ONLY"


def amount_corresponds(event, effect):
    """Compare exact integer net minor units after checking signed direction and type."""
    net, amount = effect["net_minor"], event["amount_minor"]
    if type(net) is not int or type(amount) is not int or amount < 0:
        return False
    direction = net <= 0 if event["type"] == "REFUND" else net >= 0
    return direction and abs(net) == amount


def row_result(row, available):
    """Return financial IDs and hashes, never subject IDs or arbitrary source prose."""
    event = row["data"]
    effect = available.get((event["provider"], event["event_id"]))
    return {"cohort_id": row["cohort_id"], "event_id": event["event_id"], "provider": event["provider"],
            "type": event["type"], "currency": event["currency"], "amount_minor": event["amount_minor"],
            "state": correspondence(event, effect, available), "ledger_sha256": row["hash"],
            "settlement_sha256": digest(effect) if effect else None}


def report_state(rows, unallocated, withheld=False):
    """Never label incomplete, unsupported, test-only or empty evidence as live success."""
    states = {row["state"] for row in rows}
    if "CONFLICT" in states:
        return "CONFLICT"
    if withheld or unallocated or states.intersection(("UNVERIFIED", "UNSUPPORTED_PROVIDER")):
        return "INCOMPLETE"
    if "CASH_MATCHED" in states:
        return "FINANCIAL_CORRESPONDENCE_ONLY"
    return "TEST_ONLY" if rows else "NO_DATA"


def compare(data) -> object:
    """Compare the exact snapshot without changing ledger economics or provider state."""
    available = current_effects(data)
    financial = [row for row in data["growth_events"] if row["data"]["type"] in KINDS]
    rows = [row_result(row, available) for row in financial]
    used = {(row["provider"], row["event_id"]) for row in rows}
    unallocated = [{"provider": provider, "balance_id": balance, "currency": effect["currency"],
                    "kind": effect["kind"], "settlement_sha256": digest(effect), "state": "UNALLOCATED"}
                   for (provider, balance), effect in sorted(available.items()) if (provider, balance) not in used]
    counts = {state: sum(row["state"] == state for row in rows)
              for state in ("CASH_MATCHED", "TEST_ONLY", "UNVERIFIED", "CONFLICT", "UNSUPPORTED_PROVIDER")}
    withheld = len(data["payment_effects"]) - len(available)
    pending = sum(row["status"] not in ("RECONCILED", "DUPLICATE_EFFECT", "NO_EFFECT") for row in data["payment_receipts"])
    result = {"app_id": data["app_id"], "state": report_state(rows, unallocated, withheld or pending), "counts": counts,
              "withheld_settlements": withheld, "pending_receipts": pending,
              "rows": rows, "unallocated": unallocated, "input_sha256": digest(data),
              "scope": "DELIVERED_RECORDS_ONLY; imported ledger; financial correspondence does not verify consent, subject ownership, cohort attribution, account completeness or earned revenue",
              "repair": "Use stripe_live or stripe_test with the exact balance transaction ID. Compare net settlement minor units, currency and related purchase/refund balance IDs. Connect and reconcile current payment evidence in Connections."}
    return dict(result, sha256=digest(result))


def view(store, app) -> object:
    """Keep failed comparison visible without substituting emptiness or blocking other panels."""
    try:
        return compare(snapshot(store, app))
    except (Invalid, ValueError, KeyError, TypeError, sqlite3.DatabaseError):
        return {"app_id": app, "state": "UNAVAILABLE", "counts": None, "rows": [], "unallocated": [],
                "scope": "Comparison unavailable; no previous success is reused.",
                "repair": "Refresh and inspect payment and imported ledger source history. Evidence may be missing, corrupt or over capacity."}
