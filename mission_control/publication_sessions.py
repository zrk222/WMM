"""Native protected, hash-bound publication checkpoint bundles."""

import base64, hashlib, json, math, re
from .common import Invalid, canonical, identifier
from .credential_vault import Vault, namespace
from .social_contract import reference

CHUNK = 1400
MAX_BYTES = 65536
MAX_CHUNKS = math.ceil((4 * math.ceil(MAX_BYTES / 3)) / CHUNK)


def _prefix(store, app_id, intent_id, checkpoint):
    identifier(app_id)
    reference(intent_id)
    reference(checkpoint)
    return "/".join(("PublicationSession", namespace(store.path), app_id, intent_id, checkpoint))


def _hash(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise Invalid("Invalid publication checkpoint binding")
    return value


def _bind(app_id, intent_id, checkpoint, intent_hash):
    return {"app_id": app_id, "intent_id": intent_id, "checkpoint": checkpoint, "intent_hash": _hash(intent_hash)}


def _encode_state(state):
    """Serialize only the closed publication checkpoint shape within its byte cap."""
    if not isinstance(state, dict) or set(state) != {"status", "remote_id", "asset_id", "session", "observation"}:
        raise Invalid("Invalid protected publication state")
    try:
        raw = canonical(state).encode("utf-8")
    except (ValueError, TypeError, UnicodeError):
        raise Invalid("Invalid protected publication state") from None
    if len(raw) > MAX_BYTES:
        raise Invalid("Protected publication state exceeds limit")
    return raw


def _write_pieces(vault, prefix, binding, pieces):
    """Write immutable indexed pieces, rejecting conflicting partial bundles."""
    for index, piece in enumerate(pieces):
        name = prefix + "/" + str(index)
        entry = {**binding, "index": index, "data": piece}
        old = vault.get(name)
        if old is not None and old != entry:
            raise Invalid("Protected checkpoint has conflicting partial data")
        if old is None:
            vault.put(name, entry)


def retain(store, app_id, intent_id, intent_hash, checkpoint, state):
    """Persist a secret-bearing phase checkpoint as a bound native-vault bundle."""
    prefix = _prefix(store, app_id, intent_id, checkpoint)
    binding = _bind(app_id, intent_id, checkpoint, intent_hash)
    raw = _encode_state(state)
    data = base64.b64encode(raw).decode("ascii")
    pieces = [data[i : i + CHUNK] for i in range(0, len(data), CHUNK)]
    manifest = {**binding, "sha256": hashlib.sha256(raw).hexdigest(), "count": len(pieces), "bytes": len(raw)}
    vault = Vault()
    existing = vault.get(prefix + "/manifest")
    if existing is not None:
        if existing != manifest or load(store, app_id, intent_id, intent_hash, checkpoint) != state:
            raise Invalid("Protected checkpoint already exists with different state")
        return
    _write_pieces(vault, prefix, binding, pieces)
    vault.put(prefix + "/manifest", manifest)


def _manifest(vault, prefix, app_id, intent_id, checkpoint):
    item = vault.get(prefix + "/manifest")
    if (
        not isinstance(item, dict)
        or set(item) != {"app_id", "intent_id", "checkpoint", "intent_hash", "sha256", "count", "bytes"}
        or item.get("app_id") != app_id
        or item.get("intent_id") != intent_id
        or item.get("checkpoint") != checkpoint
    ):
        raise Invalid("Protected publication checkpoint unavailable")
    _hash(item["intent_hash"])
    _hash(item["sha256"])
    if (
        type(item["count"]) is not int
        or not 1 <= item["count"] <= MAX_CHUNKS
        or type(item["bytes"]) is not int
        or not 1 <= item["bytes"] <= MAX_BYTES
    ):
        raise Invalid("Invalid protected publication checkpoint")
    if item["count"] != math.ceil((4 * math.ceil(item["bytes"] / 3)) / CHUNK):
        raise Invalid("Invalid protected publication checkpoint")
    return item


def _read_pieces(vault, prefix, binding, manifest):
    """Read every chunk under its exact index and complete checkpoint binding."""
    pieces = []
    for index in range(manifest["count"]):
        entry = vault.get(prefix + "/" + str(index))
        if (
            not isinstance(entry, dict)
            or set(entry) != {*binding, "index", "data"}
            or any(entry.get(k) != v for k, v in binding.items())
            or entry.get("index") != index
            or not isinstance(entry.get("data"), str)
            or not 1 <= len(entry["data"]) <= CHUNK
        ):
            raise Invalid("Protected publication checkpoint incomplete")
        pieces.append(entry["data"])
    return pieces


def _decode_state(pieces, manifest):
    """Decode canonical checkpoint JSON and verify its byte count and digest."""
    try:
        raw = base64.b64decode("".join(pieces), validate=True)
        state = json.loads(raw)
    except (ValueError, TypeError, UnicodeError):
        raise Invalid("Invalid protected publication checkpoint") from None
    if (
        len(raw) != manifest["bytes"]
        or hashlib.sha256(raw).hexdigest() != manifest["sha256"]
        or not isinstance(state, dict)
        or set(state) != {"status", "remote_id", "asset_id", "session", "observation"}
        or canonical(state).encode("utf-8") != raw
    ):
        raise Invalid("Protected publication checkpoint integrity failed")
    return state


def load(store, app_id, intent_id, intent_hash, checkpoint):
    """Load a checkpoint only after manifest, chunk, canonical JSON and digest checks."""
    prefix = _prefix(store, app_id, intent_id, checkpoint)
    binding = _bind(app_id, intent_id, checkpoint, intent_hash)
    vault = Vault()
    manifest = _manifest(vault, prefix, app_id, intent_id, checkpoint)
    if manifest["intent_hash"] != intent_hash:
        raise Invalid("Protected publication checkpoint binding changed")
    pieces = _read_pieces(vault, prefix, binding, manifest)
    return _decode_state(pieces, manifest)


def retire(store, app_id, intent_id, checkpoint):
    """Delete only a completely verified checkpoint bundle from the native vault."""
    prefix = _prefix(store, app_id, intent_id, checkpoint)
    vault = Vault()
    manifest = _manifest(vault, prefix, app_id, intent_id, checkpoint)
    # Verify every blob before deletion; a failed native delete leaves the manifest for diagnosis.
    load(store, app_id, intent_id, manifest["intent_hash"], checkpoint)
    for index in range(manifest["count"]):
        vault.delete(prefix + "/" + str(index))
    vault.delete(prefix + "/manifest")
