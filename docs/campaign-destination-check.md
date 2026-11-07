# Check the destination before publishing a link post

WMM checks the exact approved destination before creating a new Facebook Page
link-post intent. A public HTTPS GET must return HTTP 200 with a nonempty bounded
response. The existing public reader pins a public DNS address, verifies TLS,
uses no cookies or provider credentials, and permits at most two same-origin
redirects within a ten-second deadline and a one-MiB response limit.

Failure stops before dispatch and gives a repair message. No publish intent is
created, so the same approved request can be retried after the page is repaired.
Existing saved or uncertain intents are returned for inspection instead of
checking and publishing them again. Authority is rechecked before the intent is
reserved and again at the provider boundary.

The post result retains observation time, approved-link hash, final URL, status,
response hash and byte count. It retains no response body. Reconciliation keeps
that original check. It proves reachability at that time, not rendered page
function, app-store availability, conversion, or continuing uptime.

Facebook link posts support public UTM parameters for source, medium, campaign,
content, and term. WMM sends the approved query in its original order and
encoding. A redirect that changes or drops the query stops dispatch.
Credentials, literal IP addresses, custom ports, fragments, other query
parameters, and duplicate tracking fields are rejected. Caption-only URLs in
Reels and paid-ad destinations are outside this link-post check.
