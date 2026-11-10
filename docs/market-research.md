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

## Group phrases by what buyers want

Agents can add up to ten optional `snapshot.intent_clusters` to an existing
research packet. Each cluster links phrases, separate sources for demand,
competitor gap and proof from the app, and one proposed change with a hypothesis.
Demand sources must already be linked to one of the cluster's phrases. Missing
evidence can be left empty. Use the optional schema in
`wmm_catalog.domain_contracts.market_research`; older packets still work.

Open the saved report to see which experiments are ready for review and exactly
what evidence to collect for the rest. Review requires a current listing, one
hypothesis and three distinct, nonempty, current evidence excerpts. Source roles
are analyst assertions. Review the excerpts to confirm they support the roles,
then preregister the control, primary metric, sample and stopping rule before
launching any experiment. The ordering reflects missing evidence, not predicted
rank, installs or revenue. Imported and outdated app scopes need rechecking.

For an intent packet, the saved report opens with marketing decisions. Expand
**Sources and research details** to inspect the dated excerpts and hashes.
**Report / Save PDF** prints the same decisions, the complete source register and
the saved app/release scope. **Download report JSON** keeps the report sections
structured for handoffs. The reports count saved intents and evidence states;
they do not contain a ranking or install forecast.
