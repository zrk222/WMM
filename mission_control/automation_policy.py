"""Typed app-owned automation preferences; no execution authority is stored here."""
from .common import Invalid

MODES = {"AUTO", "SUGGEST", "OFF"}
METRICS = {"activation_rate": "Useful activation", "paid_conversion": "Paid conversion",
           "retention_rate": "Retained value"}


def bounded_text(value, name, maximum):
    """Keep operator preferences bounded and reject ambiguous structured values."""
    if not isinstance(value, str) or len(value) > maximum:
        raise Invalid(f"{name}: use text up to {maximum} characters")
    return value.strip()


def channels(data):
    """An explicit empty list clears suggestions; absent preferences use app hypotheses."""
    if "growth_channels" in data:
        raw = bounded_text(data["growth_channels"], "Pilot channels", 2400).splitlines()
    else:
        raw = data.get("channel_hypotheses", [])
    if not isinstance(raw, list) or len(raw) > 12:
        raise Invalid("Supply at most 12 pilot channels")
    result = []
    for value in raw:
        value = bounded_text(value, "Pilot channel", 180)
        if value and value not in result:
            result.append(value)
    return result


def preferences(data):
    """Validate the same policy at save and read; malformed legacy fields fail visibly."""
    mode = data.get("growth_mode", "AUTO")
    metric = data.get("growth_metric", "activation_rate")
    if not isinstance(mode, str) or mode not in MODES:
        raise Invalid("Automation mode must be AUTO, SUGGEST or OFF")
    if not isinstance(metric, str) or metric not in METRICS:
        raise Invalid("Choose a useful activation, paid conversion or retained-value metric")
    candidates = channels(data)
    preferred = bounded_text(data.get("growth_channel", ""), "Preferred pilot channel", 180)
    if preferred and preferred not in candidates:
        raise Invalid("Preferred pilot channel must be in this app's declared channel list")
    cadence = bounded_text(data.get("growth_cadence", data.get("retention") or ""), "Value cadence", 2000)
    return {"mode": mode, "metric": metric, "channels": candidates, "preferred_channel": preferred, "cadence": cadence}


def validate_manifest(data):
    """Validate without injecting preference fields into old saved manifests."""
    preferences(data)


def check_manifest_version(db, app_id, version):
    """Optional UI binding is checked inside the same transaction as its local write."""
    if version is None:
        return
    row = db.execute("SELECT version FROM apps WHERE id=?", (app_id,)).fetchone()
    if type(version) is not int or not row or version != row["version"]:
        raise Invalid("App setup changed. Close this form, refresh and reopen it; your input is preserved.")
