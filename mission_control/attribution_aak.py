"""Pinned AdAttributionKit JWS verification with explicitly unsigned observations."""
from . import attribution_contract as contract
from . import attribution_keys as keys
from . import attribution_native as native

REQUIRED = ("ad-network-identifier", "source-identifier", "advertised-item-identifier",
            "conversion-type", "postback-identifier", "did-win", "postback-sequence-index", "impression-type")


def compact_parts(value, environment):
    """Reject key URLs, certificates, crit headers and algorithm negotiation."""
    contract.require(isinstance(value, str) and 0 < len(value) <= 131072,
                     "AdAttributionKit compact JWS size is invalid")
    parts = value.split(".")
    contract.require(len(parts) == 3, "AdAttributionKit compact JWS must have three parts")
    header = contract.body(contract.base64_bytes(parts[0], 1024, url=True))
    contract.fields(header, ("alg", "kid"))
    contract.require(header["alg"] == "ES256" and isinstance(header["kid"], str),
                     "AdAttributionKit JWS algorithm is unsupported")
    spki, curve = keys.aak_key(header["kid"], environment)
    payload = contract.body(contract.base64_bytes(parts[1], 65536, url=True))
    signature = contract.base64_bytes(parts[2], 64, url=True)
    contract.require(len(signature) == 64, "AdAttributionKit ES256 signature requires 64 bytes")
    return parts, header, payload, signature, spki, curve


def validate_payload(payload, app_id, environment):
    """Require typed signed claims and preserve privacy-suppressed optional fields."""
    contract.fields(payload, REQUIRED, ("publisher-item-identifier", "marketplace-identifier"))
    contract.app_scope(payload["advertised-item-identifier"], app_id)
    contract.identifier(payload["ad-network-identifier"])
    contract.source_id(payload["source-identifier"])
    contract.postback_id(payload["postback-identifier"])
    contract.boolean(payload["did-win"])
    contract.integer(payload["postback-sequence-index"], 0, 2)
    contract.require(payload["conversion-type"] in ("download", "redownload", "re-engagement"),
                     "AdAttributionKit conversion type is unsupported")
    contract.require(payload["impression-type"] == "app-impression",
                     "AdAttributionKit impression type is unsupported")
    publisher = payload.get("publisher-item-identifier")
    if publisher is not None:
        contract.integer(publisher, 0 if environment == "Development" else 1, 9223372036854775807)
    if payload.get("marketplace-identifier") is not None:
        contract.identifier(payload["marketplace-identifier"])


def outer_observations(data, sequence):
    """Keep country and interaction unsigned alongside conversion values."""
    result = contract.conversions(data, sequence)
    country, interaction = data.get("country-code"), data.get("ad-interaction-type")
    if country is not None:
        contract.require(isinstance(country, str) and len(country) == 2 and
                         country.isascii() and country.isalpha() and country.isupper(),
                         "AdAttributionKit country must contain two uppercase ASCII letters")
    if interaction is not None:
        contract.require(interaction in ("click", "view"), "AdAttributionKit interaction is invalid")
    result.update({"country_code": country, "ad_interaction_type": interaction})
    return result


def verified(raw,app_id,environment):
    """Authenticate exact JWS bytes; never return the raw JWS or private payload."""
    contract.environment_name(environment)
    data = contract.body(raw)
    contract.fields(data, ("jws-string",), ("conversion-value", "coarse-conversion-value",
                                         "country-code", "ad-interaction-type"))
    parts, header, payload, signature, spki, curve = compact_parts(data["jws-string"], environment)
    validate_payload(payload, app_id, environment)
    unsigned = outer_observations(data, payload["postback-sequence-index"])
    native.verify(spki, curve, (parts[0] + "." + parts[1]).encode("ascii"), signature)
    return contract.result("AdAttributionKit", header["kid"], payload, unsigned, app_id, environment,
                           payload["postback-identifier"], payload["conversion-type"],
                           payload["postback-sequence-index"], payload["did-win"])
