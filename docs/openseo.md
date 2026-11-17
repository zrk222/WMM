# OpenSEO: turn search evidence into the next app-marketing test

WMM has a built-in OpenSEO connection, native Search Console retrieval and
app-owned growth reports. An agent can also import broader research from its
authorized OpenSEO MCP connection. WMM retains selected evidence, recommends one
next action, and exports the same report as JSON or Print / Save PDF.

## Built-in connection

In **Connections → OpenSEO**, enter the dedicated project's ID and API key,
confirm the app's configured website, choose a market, and consent to the read.
The default is page totals only. Select aggregate queries explicitly when
you are permitted to retain search phrases; query/page rows then ground
headline recommendations in actual search terms.
The key stays in the OS credential vault. WMM checks the actual returned
Search Console property and page paths. It requests final web-search data for
28 days ending four days ago, filtered to the selected country. It requests
no user IDs, contact records or device identifiers. Query mode rejects
contact-like strings rather than saving them.

Manual refresh is the default. Opt into the existing six-hour schedule if
needed. Rotation tests the new key before retiring the old one; disconnect
stops the schedule and removes the local key.

Open a saved reading and select **Use reading for next marketing test**. WMM
validates that exact app/source/version/report and saves its observations in
growth review. Agents use the existing source ID with `web.research.read`
and `web.research.save` under owner-issued grants. Both are documented in
`wmm_catalog.domain_contracts.web_search_evidence`.

This reader retains at most 20 page rows and labels truncation as PARTIAL.
No matching page rows is NO_RESULTS, never a zero-traffic assertion. The native
reader buys no SEO credits and cannot publish, submit indexing, modify projects
or start paid research. Broader keyword, backlink, rank and AI research follows
the separately authorized agent workflow below.

## Connect and choose the scope

1. Follow [OpenSEO's MCP setup](https://openseo.so/docs/mcp) in your agent host.
   The hosted endpoint is `https://app.openseo.so/mcp`. Authorize your own
   account, or use your own self-hosted endpoint. WMM does not receive or copy
   that agent credential. This optional path is separate from WMM's native key.
2. Use a separate OpenSEO project per app website. Confirm the exact project
   and website before researching. Add that website to the same WMM app profile.
3. Begin with connected Google Search Console, GA4 and saved reports. A
   provider call can cost money even when its name starts with "get" or
   "research". Research, rank checks, crawls and AI sampling need the owner's
   actual scope and any applicable cost ceiling. WMM's local save grants none.
   Use OpenSEO's estimator and saved context before buying repeat research.

## Hand the work to an agent

Ask the agent to read `wmm_catalog.domain_contracts.web_search_evidence`.
It defines the exact `WEB_SEO_EVIDENCE` data object and normalized fields.
Use the existing owner-issued `growth.save` grant; no new WMM operation is
required. Alternatively save that data object to JSON and use **Results →
Subscription growth review → Import OpenSEO evidence**. Review before saving.

Retain the exact query or page, market, reporting dates, device, source date,
permitted excerpt and its exact UTF-8 SHA-256. First-party property observations
need a canonical page URL inside the app's configured website. External
research uses a null page URL. Missing numbers remain null. Use source
coverage PARTIAL or NO_RESULTS when appropriate.

The app and release are fixed at save. Wrong websites, changed app versions,
contradictory counters, duplicate observations and altered immutable request IDs
are rejected. Reimported archives need rechecking. A new retrieval date does
not make an old reporting period fresh.

## Choose the next test

| Evidence | Action WMM helps choose | Measurement |
| --- | --- | --- |
| Indexing or canonical problem | Repair the owned page before testing copy | Rechecked URL inspection |
| Search Console query impressions and clicks | Match a page headline to the observed intent | Google clicks / impressions |
| GA4 organic sessions and store-bound sessions | Test one store call to action | Store-bound sessions / eligible organic sessions |
| Google keyword demand and competitor search results | Draft a differentiated long-tail landing page or creative angle | Owned query clicks and store-bound sessions |
| Google rank history | Review a trend within the same device and market | Observed Google position |
| Backlinks or AI citations | Inspect relevant referral or answer opportunities | Qualified referrals or repeat citation samples |

WMM orders repairs before research and owned opportunities before estimates.
Within one source and reporting window it prioritizes higher observed exposure.
It does not blend unlike metrics into a predicted growth score.

Generic GA4 key events are not store clicks. Supply store-bound sessions only
when a verified store-link event identifies eligible sessions. A website visit
is not an app install. Use the separate Apple campaign report for native
downloads and a verified app billing/source join for paid subscriptions.

OpenSEO's Search Console and a direct Google export are the same upstream
source. They are not independent confirmation. Do not sum their totals or
interpret web keyword volume as App Store volume. Imported source statements
remain operator assertions until separately checked against the provider.

## Scope and upstream

This integration reuses OpenSEO's agent tools instead of embedding its
deployment, billing, user database or crawler in the desktop installer.
Publication, indexing submissions, scheduling, billing and other external
writes remain separately authorized. WMM's import makes no network calls.

Reviewed upstream: [every-app/open-seo at 2df84ff](https://github.com/every-app/open-seo/tree/2df84ff91461cc55b6c8bb98f3ce0f195d2e463d),
[tool catalog](https://openseo.so/docs/mcp-tools) and
[software versus data costs](https://openseo.so/open-source-seo).
The upstream repository is MIT licensed; dependencies and provider data keep
their own terms. No upstream code is copied in this adapter.
