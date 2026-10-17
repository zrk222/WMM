# Optional social OAuth callback relay

The core WMM workspace does not need a relay. Social providers may need a public
HTTPS redirect URL, while WMM itself must remain on localhost.

This folder contains a small Cloudflare Worker that relays an OAuth callback
to a local browser flow. It is not an authorization server or a token exchange.
Deploy it in your own Cloudflare account, using the included `wrangler.jsonc`
and your already installed official Wrangler CLI, or the Cloudflare dashboard.
No account ID, secret, existing tenant URL or paid resource is preconfigured.

1. Inspect `worker.mjs` and deploy it as your own Worker.
2. Keep request logs and tracing disabled: OAuth callback URLs contain sensitive
   transient values. Do not add analytics to this endpoint.
3. In each provider developer console, register the exact supported callback
   path on your own HTTPS origin. Grant only the scopes your app needs.
4. Enter your relay origin and your own developer-app setup in WMM's social
   connection flow. Review the requested account and scopes before consenting.
5. Follow the browser return flow and verify the connection in WMM. An open
   consent page alone is not proof of a completed connection.

Provider app review, granted scopes and platform-specific requirements are not
bypassed by deploying this worker. Never expose the local WMM server publicly.
