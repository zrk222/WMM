"""Version-specific SKAdNetwork verification; conversion observations stay unsigned."""
from . import attribution_contract as contract
from . import attribution_keys as keys
from . import attribution_native as native

BASE = ("ad-network-id", "app-id", "transaction-id", "attribution-signature")
VERSIONS = ("1.0", "2.0", "2.1", "2.2", "3.0", "4.0")


def layout(version):
    """Select a closed field set for exactly one supported wire version."""
    if version == "1.0":
        return BASE + ("campaign-id",), ("version",)
    required = BASE + ("version", "redownload")
    required += ("source-identifier",) if version == "4.0" else ("campaign-id",)
    optional = ("source-app-id", "conversion-value")
    if version in ("2.2", "3.0", "4.0"):
        required += ("fidelity-type",)
    if version in ("3.0", "4.0"):
        required += ("did-win",)
    if version == "4.0":
        required += ("postback-sequence-index",)
        optional += ("source-domain", "coarse-conversion-value")
    return required, optional


def optional_source(data, version, environment):
    """Privacy-suppressed publisher values stay unavailable instead of guessed zero."""
    source, domain = data.get("source-app-id"), data.get("source-domain")
    contract.require(not ("source-app-id" in data and "source-domain" in data),
                     "SKAdNetwork publisher app and domain are mutually exclusive")
    if source is not None:
        contract.integer(source, 0 if environment == "Development" else 1, 9223372036854775807)
    if domain is not None:
        contract.require(version == "4.0", "SKAdNetwork domain requires version 4")
        contract.identifier(domain)


def validate(data, version, app_id, environment):
    """Check exact signed value types before native verification."""
    required, optional = layout(version)
    contract.fields(data, required, optional)
    contract.identifier(data["ad-network-id"])
    contract.app_scope(data["app-id"], app_id)
    contract.postback_id(data["transaction-id"])
    if version == "4.0":
        contract.source_id(data["source-identifier"])
        contract.integer(data["postback-sequence-index"], 0, 2)
    else:
        contract.integer(data["campaign-id"], 1, 100)
    for field in ("redownload", "did-win"):
        if field in data:
            contract.boolean(data[field])
    if "fidelity-type" in data:
        contract.integer(data["fidelity-type"], 0, 1)
    optional_source(data, version, environment)


def signed_fields(data, version):
    """Recreate Apple's exact version-specific order, excluding conversion values."""
    names = ["ad-network-id", "source-identifier" if version == "4.0" else "campaign-id",
             "app-id", "transaction-id"]
    if version != "1.0":
        names.insert(0, "version")
        names.append("redownload")
    for name in ("source-app-id", "source-domain", "fidelity-type", "did-win", "postback-sequence-index"):
        if data.get(name) is not None:
            names.append(name)
    return {name: data[name] for name in names}


def message(signed):
    """Concatenate exact UTF-8 U+2063 values with lowercase Boolean text."""
    values = [str(value).lower() if type(value) is bool else str(value) for value in signed.values()]
    return "\u2063".join(values).encode("utf-8")


def verified(raw,app_id,environment):
    """Return sanitized claims only after verification with a pinned Apple public key."""
    contract.environment_name(environment)
    data = contract.body(raw)
    version = data.get("version", "1.0")
    contract.require(isinstance(version, str) and version in VERSIONS, "SKAdNetwork version is unsupported")
    validate(data, version, app_id, environment)
    sequence = data.get("postback-sequence-index", 0)
    unsigned = contract.conversions(data, sequence)
    signed = signed_fields(data, version)
    spki, curve = keys.skan_key(version)
    signature = native.der_signature(contract.base64_bytes(data["attribution-signature"], 80), curve)
    native.verify(spki, curve, message(signed), signature)
    conversion = "unavailable" if version == "1.0" else "redownload" if data["redownload"] else "download"
    return contract.result("SKAdNetwork", version, signed, unsigned, app_id, environment,
                           data["transaction-id"], conversion, sequence, data.get("did-win", True))
