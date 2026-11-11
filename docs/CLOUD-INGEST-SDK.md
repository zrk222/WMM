# Personal-cloud ingest SDK (BYOC)

Status: **client and optional connection settings implemented; local is the default and no live cloud endpoint is configured.**

This is the first deliverable for the local/cloud SDK discussion. It is a small client for a **personal cloud endpoint you operate** that implements the WMM v1 contract. It does not host a service, store tokens, or silently fall back to local.

## Contract

`GET /v1/health` with `Authorization: Bearer <token>`

```json
{"schema":"wmm.cloud.v1","status":"READY","tenant":"optional","version":"1"}
```

`POST /v1/install-batches` with the same bearer token, `Idempotency-Key`, and:

```json
{"batch": {"source":"APPSFLYER","campaign_token":"...","window":{},"coverage":{},"installs":[]}}
```

Accepted response:

```json
{"schema":"wmm.cloud.v1","status":"ACCEPTED","receipt":"provider-or-tenant-receipt","tenant":"optional"}
```

`DUPLICATE` is accepted with its original receipt. Any other status is a failure.

## Client

```python
from mission_control.cloud_ingest import CloudIngest

client = CloudIngest("https://cloud.example.com", token)  # token from your protected config
client.health()                                            # no evidence is sent
client.send_batch(validated_batch, "request-0001")         # explicit only
```

Rules:

- HTTPS only; plain HTTP is accepted only for `127.0.0.1` tests.
- No redirects, URL credentials, query strings or paths.
- Token is sent only in the Authorization header and is never logged by this client.
- No retry, no fallback and no implicit send on save/import.
- The cloud endpoint receives only the batch the caller explicitly sends.

## Connection settings

Connections ? **Personal cloud (optional)** lets the owner enter an HTTPS base URL and a write-only token. The token is stored in the OS vault, never SQLite. **Test connection** sends only `GET /v1/health`. **Return to local** deletes the token and restores the default mode. MMP import and reporting do not require this connection.

## Not built yet

- automatic local?cloud sync and conflict resolution;
- explicit "send this local batch to my cloud" action;
- hosted deployment, tenant auth, SSO, WORM audit and DPA;
- live provider postbacks and mobile SDKs.

Those require the endpoint, tenancy and security decisions in [TEAM-SESSION-SECURITY-REVIEW.md](TEAM-SESSION-SECURITY-REVIEW.md) and [ENTERPRISE-READINESS.md](ENTERPRISE-READINESS.md).
