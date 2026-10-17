"""Bounded credential-free public HTTPS reads, pinned against DNS rebinding."""
import hashlib
import http.client
import ipaddress
import queue
import re
import socket
import ssl
import threading
import time
from urllib.parse import quote, unquote, urljoin, urlsplit, urlunsplit
from .common import Invalid
from .aeo_tls import trust_context

AGENT = "AppGrowthMissionControl"
DNS_SLOTS = threading.BoundedSemaphore(4)
REDIRECTS = {301, 302, 303, 307, 308}


class ReadError(Invalid):
    """Closed error classification, never a raw network exception disclosure."""
    def __init__(self, code):
        """Carry only a closed operational code to callers."""
        self.code = code
        super().__init__("Public page check failed: " + code)


def url_parts(value):
    """Reject authority ambiguity and secret-bearing URL components."""
    if not isinstance(value, str) or len(value) > 2400 or re.search(r"[\x00-\x20\x7f\\]", value):
        raise ReadError("URL_INVALID")
    u = urlsplit(value)
    if u.scheme != "https" or u.username is not None or u.password is not None or u.port not in (None, 443):
        raise ReadError("URL_INVALID")
    if "?" in value or "#" in value:
        raise ReadError("URL_INVALID")
    return u


def hostname(value):
    """Require a normalized DNS name, never a literal or single-label host."""
    try:
        host = value.encode("idna").decode("ascii").lower()
    except (AttributeError, UnicodeError) as exc:
        raise ReadError("URL_INVALID") from exc
    labels = host.split(".")
    if len(labels) < 2 or len(host) > 253 or not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", p) for p in labels):
        raise ReadError("URL_INVALID")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return host
    raise ReadError("URL_INVALID")


def url_path(value):
    """Bound paths and reject encoded control characters before request framing."""
    path = value or "/"
    if len(path) > 2048 or re.search(r"[\x00-\x1f\x7f\\]", unquote(path)) or re.search(r"%(?![a-fA-F0-9]{2})", path):
        raise ReadError("URL_INVALID")
    return quote(path, safe="/%:@!$&'()*+,;=-._~")


def public_url(value):
    """Canonical public origin and path; queries/credentials never enter reads."""
    try:
        u = url_parts(value)
        return urlunsplit(("https", hostname(u.hostname), url_path(u.path), "", ""))
    except (ValueError, AttributeError, UnicodeError) as exc:
        raise ReadError("URL_INVALID") from exc


def origin(value):
    """Exact normalized origin, never a substring/suffix host comparison."""
    return "https://" + urlsplit(public_url(value)).netloc


def remaining(deadline):
    """Carry a single deadline through DNS, redirects, TLS and body reads."""
    seconds = deadline - time.monotonic()
    if seconds <= 0:
        raise ReadError("DEADLINE")
    return min(seconds, 10.0)


def dns_lookup(host, deadline):
    """At most four bounded concurrent lookups, without an unbounded queue."""
    slots = DNS_SLOTS
    if not slots.acquire(blocking=False):
        raise ReadError("DNS_BUSY")
    result = queue.Queue(maxsize=1)
    def resolve():
        try:
            result.put(socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM))
        except OSError:
            result.put(None)
        finally:
            slots.release()
    threading.Thread(target=resolve, daemon=True).start()
    try:
        return result.get(timeout=remaining(deadline))
    except queue.Empty as exc:
        raise ReadError("DEADLINE") from exc


def address(host, deadline):
    """Reject mixed public/private DNS answers before any socket connection."""
    answers = dns_lookup(host, deadline)
    if not answers or len(answers) > 64:
        raise ReadError("DNS_FAILED")
    for row in answers:
        try:
            ip = ipaddress.ip_address(row[4][0])
        except (ValueError, IndexError) as exc:
            raise ReadError("DNS_INVALID") from exc
        if not ip.is_global or ip.is_multicast or ip.is_reserved or getattr(ip, "ipv4_mapped", None):
            raise ReadError("ADDRESS_BLOCKED")
    return answers[0][4][0]


class DeadlineFile:
    """Enforce the whole-run deadline inside HTTP header and chunk framing."""
    def __init__(self, fp, sock, deadline):
        """Wrap the buffered file without replacing socket ownership."""
        self.fp, self.sock, self.deadline = fp, sock, deadline
        self.line_bytes = 0

    def __getattr__(self, name):
        """Preserve ordinary file close/state operations."""
        return getattr(self.fp, name)

    def read1(self, size):
        """Reset timeout before each underlying receive, including slow streams."""
        self.sock.settimeout(remaining(self.deadline))
        return self.fp.read1(size)

    def readline(self, size=-1):
        """Bound line framing bytes and wall time, not just inactivity time."""
        limit = 65537 if size < 0 else min(size, 65537)
        parts = []
        while len(parts) < limit:
            byte = self.read1(1)
            if not byte:
                break
            self.line_bytes += len(byte)
            if self.line_bytes > 16384:
                raise ReadError("HEADERS_TOO_LARGE")
            parts.append(byte)
            if byte == b"\n":
                break
        return b"".join(parts)

    def read(self, size=-1):
        """Keep HTTP chunk safe-read loops within the same deadline and byte cap."""
        limit = 1048577 if size < 0 else size
        if limit > 1048577:
            raise ReadError("BODY_TOO_LARGE")
        chunks = []; total = 0
        while total < limit:
            chunk = self.read1(min(16384, limit-total))
            if not chunk:
                break
            chunks.append(chunk); total += len(chunk)
        return b"".join(chunks)


class DeadlineResponse(http.client.HTTPResponse):
    """Use ordinary HTTP parsing with a deadline-aware underlying file."""
    def __init__(self, sock, deadline, **kwargs):
        """Keep the standard parser's framing checks and ownership semantics."""
        super().__init__(sock, **kwargs)
        self.fp = DeadlineFile(self.fp, sock, deadline)


class PinnedHTTPS(http.client.HTTPConnection):
    """Connect only to a checked address, preserving original Host and TLS SNI."""
    def __init__(self, host, ip, context, deadline):
        """Bind the checked address, original hostname and shared deadline."""
        super().__init__(host, 443, timeout=remaining(deadline))
        self.ip, self.context, self.deadline = ip, context, deadline
        self.response_class = lambda sock, **kwargs: DeadlineResponse(sock, self.deadline, **kwargs)

    def connect(self):
        """Wrap only the pinned socket, closing it on any handshake failure."""
        raw = socket.create_connection((self.ip, 443), timeout=remaining(self.deadline))
        try:
            raw.settimeout(remaining(self.deadline))
            self.sock = self.context.wrap_socket(raw, server_hostname=self.host)
            self.stream_socket = self.sock
        except BaseException:
            raw.close()
            raise


def response_headers(response):
    """Keep only bounded diagnostic metadata, excluding cookies/authentication."""
    rows = response.getheaders()
    if sum(len(k) + len(v) for k, v in rows) > 16384:
        raise ReadError("HEADERS_TOO_LARGE")
    keep = {"content-type", "content-encoding", "content-length", "location", "x-robots-tag"}
    result = {}
    for key, value in rows:
        if key.lower() in keep:
            result.setdefault(key.lower(), []).append(value)
    return result


def body_length(headers, cap):
    """Check declared framing and reject compression before reading any body."""
    encoding = headers.get("content-encoding", ["identity"])
    if encoding != ["identity"]:
        raise ReadError("ENCODING_UNSUPPORTED")
    lengths = headers.get("content-length", [])
    if lengths and (len(lengths) != 1 or not lengths[0].isdigit() or int(lengths[0]) > cap):
        raise ReadError("BODY_TOO_LARGE")
    return int(lengths[0]) if lengths else None


def response_body(response, headers, cap, conn, deadline):
    """Reject compression and over-limit bodies without decompressing anything."""
    length = body_length(headers, cap)
    chunks = []; size = 0
    while True:
        conn.stream_socket.settimeout(remaining(deadline))
        chunk = response.read1(min(16384, cap + 1 - size))
        if not chunk:
            break
        size += len(chunk)
        if size > cap:
            raise ReadError("BODY_TOO_LARGE")
        chunks.append(chunk)
    if length is not None and length != size:
        raise ReadError("BODY_INCOMPLETE")
    return b"".join(chunks)


class PublicReader:
    """One six-request/two-redirect, thirty-second public inspection budget."""
    def __init__(self):
        """Allocate one bounded diagnostic run using existing CA trust."""
        self.deadline = time.monotonic() + 30
        self.requests = 0; self.redirects = 0
        self.context = trust_context()

    def once(self, url, cap):
        host = urlsplit(url).hostname; ip = address(host, self.deadline)
        conn = PinnedHTTPS(host, ip, self.context, self.deadline)
        try:
            conn.request("GET", urlsplit(url).path or "/", headers={"User-Agent": AGENT+"/1.0", "Accept-Encoding": "identity", "Accept": "text/html,text/plain,application/xml;q=0.9"})
            response = conn.getresponse(); headers = response_headers(response)
            raw = b"" if response.status in REDIRECTS else response_body(response, headers, cap, conn, self.deadline)
            return {"url": url, "status": response.status, "headers": headers, "body": raw,
                    "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        finally:
            conn.close()

    def read(self, value, cap, permit=None):
        url = public_url(value); initial = origin(url)
        if type(cap) is not int or not 1 <= cap <= 1048576:
            raise ReadError("LIMIT_INVALID")
        while True:
            remaining(self.deadline)
            if permit is not None and not permit(url):
                raise ReadError("ROBOTS_TARGET_BLOCKED")
            if self.requests >= 6:
                raise ReadError("REQUEST_LIMIT")
            self.requests += 1
            resource = self.safe_once(url, cap)
            if resource["status"] not in REDIRECTS:
                return resource
            url = self.redirect(resource, initial)

    def safe_once(self, url, cap):
        """Classify transport failures without exposing connection details."""
        try:
            return self.once(url, cap)
        except ssl.SSLError as exc:
            raise ReadError("TLS_FAILED") from exc
        except (TimeoutError, OSError, http.client.HTTPException) as exc:
            raise ReadError("NETWORK_FAILED") from exc

    def redirect(self, resource, initial):
        """Carry the shared redirect budget and exact origin to the next hop."""
        self.redirects += 1
        locations = resource["headers"].get("location", [])
        if self.redirects > 2 or len(locations) != 1:
            raise ReadError("REDIRECT_LIMIT")
        url = public_url(urljoin(resource["url"], locations[0]))
        if origin(url) != initial:
            raise ReadError("REDIRECT_ORIGIN")
        return url


def text(resource):
    """Only strict UTF-8, including an optional BOM, is interpreted as text."""
    types = resource["headers"].get("content-type", [])
    for value in types:
        charset = re.search(r"charset\s*=\s*[\"']?([^\s;\"']+)", value, re.I)
        if charset and charset[1].lower() not in ("utf-8", "utf8"):
            raise ReadError("CHARSET_UNSUPPORTED")
    try:
        return resource["body"].decode("utf-8-sig")
    except UnicodeError as exc:
        raise ReadError("UTF8_INVALID") from exc


def evidence(resource):
    """No raw body, cookies or network exception text enters durable reports."""
    result = {key: resource[key] for key in ("url", "status", "bytes", "sha256")}
    allowed = {"content-type", "content-encoding", "content-length", "x-robots-tag"}
    result["headers"] = {key:list(value) for key, value in resource["headers"].items() if key in allowed}
    return result
