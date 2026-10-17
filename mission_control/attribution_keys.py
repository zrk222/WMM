"""Pinned Apple attribution public keys; no remote or operator-controlled trust."""
import base64
from .common import Invalid

P256 = "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEWdp8GPcGqmhgzEFj9Z2nSpQVddayaPe4FMzqM9wib1+aHaaIzoHoLN9zW4K8y4SPykE3YVK3sVqW6Af0lfx3gg=="
P192 = "MEkwEwYHKoZIzj0CAQYIKoZIzj0DAQEDMgAEMyHD625uvsmGq4C43cQ9BnfN2xslVT5V1nOmAMP6qaRRUll3PB1JYmgSm+62sosG"
DEVELOPMENT = {
    "apple-development-identifier/0": "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAELeEDzpJEP+/qRSE5hJVC1p1J0ssUnQGMzBBbvnACBok8OVGGLgxL0myrKiy6lvRtSlLRsWit87i+vftD8AEqeQ==",
    "apple-development-identifier/1": "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAE8YzdO7eM97s/IJ25kdW5CZ3A14USE5IJ5Ha/vhWaxI6UBI1ZxCEvjrKxVluVGe6qWwF1BDFq+QHqKfH5u+wxHQ==",
}


def skan_key(version):
    """Select only the documented key for a recognized wire version."""
    if version in ("1.0", "2.0"):
        return base64.b64decode(P192, validate=True), "P192"
    if version in ("2.1", "2.2", "3.0", "4.0"):
        return base64.b64decode(P256, validate=True), "P256"
    raise Invalid("SKAdNetwork version is unsupported")


def aak_key(kid,environment):
    """Development signing keys cannot cross into a production source."""
    if environment == "Production" and kid == "apple-cas-identifier/0":
        return base64.b64decode(P256, validate=True), "P256"
    if environment == "Development" and isinstance(kid, str) and kid in DEVELOPMENT:
        return base64.b64decode(DEVELOPMENT[kid], validate=True), "P256"
    raise Invalid("AdAttributionKit signing key does not match the source environment")
