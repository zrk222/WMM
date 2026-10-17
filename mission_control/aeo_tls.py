"""Keep existing CA trust while excluding expired default-store anchors."""
from datetime import datetime, timezone
import ssl
from .common import Invalid


def item(raw, offset=0):
    """Read one bounded DER TLV, rejecting indefinite/nonminimal lengths."""
    if offset + 2 > len(raw):
        raise Invalid("Invalid trusted certificate encoding")
    tag, size = raw[offset:offset+2]; start = offset + 2
    if size & 128:
        count = size & 127
        if not 1 <= count <= 3 or start + count > len(raw) or raw[start] == 0:
            raise Invalid("Invalid trusted certificate length")
        size = int.from_bytes(raw[start:start+count], "big"); start += count
        if size < 128:
            raise Invalid("Nonminimal trusted certificate length")
    end = start + size
    if end > len(raw):
        raise Invalid("Truncated trusted certificate")
    return tag, raw[start:end], end


def certificate_times(raw):
    """Extract CA validity only; OpenSSL still verifies complete certificates."""
    if not isinstance(raw, bytes) or len(raw) > 65536:
        raise Invalid("Invalid trusted certificate size")
    tag, cert, end = item(raw)
    if tag != 48 or end != len(raw):
        raise Invalid("Invalid trusted certificate envelope")
    tag, tbs, _ = item(cert)
    if tag != 48:
        raise Invalid("Invalid trusted certificate body")
    offset = item(tbs)[2] if tbs[0] == 160 else 0
    for _ in range(3):
        offset = item(tbs, offset)[2]
    tag, validity, _ = item(tbs, offset)
    if tag != 48:
        raise Invalid("Invalid trusted certificate validity")
    first, offset = der_time(validity, 0)
    last, offset = der_time(validity, offset)
    if offset != len(validity):
        raise Invalid("Invalid trusted certificate validity fields")
    return first, last


def der_time(raw, offset):
    """Interpret only the canonical UTC X.509 time forms."""
    tag, value, end = item(raw, offset)
    try:
        text = value.decode("ascii")
        if tag == 23 and len(text) == 13:
            year = int(text[:2]); year += 2000 if year < 50 else 1900
            text = str(year) + text[2:]
        elif tag != 24 or len(text) != 15:
            raise ValueError
        parsed = datetime.strptime(text, "%Y%m%d%H%M%SZ").replace(tzinfo=timezone.utc)
    except (ValueError, UnicodeError) as exc:
        raise Invalid("Invalid trusted certificate time") from exc
    return parsed, end


def trust_context():
    """Use only currently valid members of the existing OS/default trust set."""
    defaults = ssl.create_default_context(); stamp = datetime.now(timezone.utc)
    accepted = []
    for raw in defaults.get_ca_certs(binary_form=True):
        try:
            first, last = certificate_times(raw)
            if first <= stamp <= last:
                accepted.append(ssl.DER_cert_to_PEM_cert(raw))
        except Invalid:
            continue
    if not accepted:
        raise Invalid("No current trusted certificates are available")
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = True
    context.load_verify_locations(cadata="".join(accepted))
    return context
