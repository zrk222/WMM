# WMM personal cloud relay (reference)

This is a **single-owner** reference service for the personal-cloud connection in WMM. Deploy it on a host you control, terminate HTTPS at a trusted proxy, then enter its base URL and bearer token in Connections ? Personal cloud.

## What it does

- `GET /v1/health` ? token check, no evidence.
- `POST /v1/install-batches` ? bearer token + `Idempotency-Key`; stores the exact batch in SQLite and returns a receipt. Reusing a key with different content returns `409`.
- One tenant, one token, no user sign-up, no WORM audit, no multi-tenant isolation.

## Run locally (test only)

```sh
export WMM_CLOUD_TOKEN="$(openssl rand -hex 32)"
python cloud/relay.py
curl -H "Authorization: Bearer $WMM_CLOUD_TOKEN" http://127.0.0.1:8787/v1/health
```

Plain HTTP is loopback-only. Do **not** expose it directly.

## Deploy

Docker:

```sh
docker build -t wmm-cloud cloud
docker run -d -p 127.0.0.1:8787:8787 -v wmm-cloud:/data \
  -e WMM_CLOUD_TOKEN="$(openssl rand -hex 32)" --name wmm-cloud wmm-cloud
```

Put it behind an HTTPS reverse proxy (Caddy, nginx, Fly.io, Render, Railway or your VPS). Requirements:

- persistent volume for `/data/wmm-cloud.sqlite3`;
- long random token kept only in the host secret store;
- HTTPS certificate and no plain-HTTP public listener;
- backups of the SQLite volume;
- one owner/tenant only.

On Fly.io, for example: create an app, set `WMM_CLOUD_TOKEN` as a secret, mount a volume at `/data`, expose port 8787, and use the generated HTTPS hostname. Exact platform commands depend on your account.

## Verify from WMM

1. Connections ? Personal cloud (optional).
2. Enter the HTTPS base URL and the same token.
3. **Test connection**. Expect `TESTED`.
4. Send an import only through an explicit action; health testing sends no evidence.

## Limits

This relay is not a hosted WMM service, not an MMP, and not enterprise-certified. It has no SSO, tenant isolation, audit WORM, retention policy or DPA. Do not offer it to external clients. Use the local export path as the default.
