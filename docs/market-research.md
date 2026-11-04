# Choose the next words to test

WMM compares your supplied listing text with keyword phrases and competitor
excerpts. It shows linked evidence, phrase coverage, overlaps and suggested copy
tests. This helps an operator choose a specific experiment instead of guessing
from a list of keywords.

Open **Results → Subscription growth review → Import keyword research**.
Choose your agent's JSON file, inspect the app/market/source summary, then select
**Save researched packet**. Open the saved entry to inspect sources and findings
or download its report as JSON or through Print / Save as PDF.

Ask your agent to read `wmm_catalog.domain_contracts.market_research`. The exact
schema lives there. Existing `growth.save` accepts `kind: "MARKET_RESEARCH"`
with the current app manifest version and `data: {"release": "...", "snapshot": ...}`.
For a human import, save only that **data object** as the JSON file. Agents can
save/read the same record through CLI or MCP with an owner-issued grant containing
`growth.save` / `growth.read`; this introduces no new tool or permission.

Each packet declares platform, current app locale/release and territory. Sources
carry dates, URLs, excerpt hashes and complete/partial/no-results coverage.
Phrases link to those sources and keep supplied observations separate from
analyst intent/relevance. Competitor and own-listing excerpts retain their source
identity. Use permitted source text and omit credentials or personal data.

There are at most 20 sources, 50 phrases and 10 competitors per snapshot. Source
and listing excerpts hold up to 1,000 characters; phrases up to 120. The snapshot
is capped at 64 KiB; the file/request import is capped at 1 MiB. A source older
than 90 days is marked stale. Phrase coverage counts linked phrases, not market
search demand. Candidate ordering uses supplied competitor overlap, own-listing
overlap and alphabetical order; it is not a forecast of performance.

Search volume, rank and difficulty remain unknown unless a linked source supplies
a value. Even supplied numbers are operator assertions, not verified provider
reads. Public views and paid Apple Ads counts never become organic rank or
demand. Test proposals do not approve reuse, publishing or spending.

Malformed files stay selected for correction. Repeating an identical request
returns the same immutable entry; different evidence needs a new entry identity.
If app setup changes, reopen the form in the intended app. Saved/imported history
keeps its original source context and is marked for review when that context is
stale. No research URL is fetched by this workflow.
