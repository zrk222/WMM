# Meta media-buying specialist

Give your personal agent one app, one outcome and a finite owner-approved scope.
The specialist researches the audience, prepares creative tests, uses supported
campaign controls, checks delivery and reports the evidence behind its next move.
It works through the same WMM operations and approvals as every other agent.

After `wmm_catalog`, call the existing `wmm_operations_read` tool:

```json
{"app_id":"your-app-id","input":{"profile":"meta_media_buyer"}}
```

For CLI, send the same envelope with `"operation":"operations.read"` to
`python -m mission_control.agent_cli call --origin http://127.0.0.1:8765 --use-grant`.
Supply the owner-issued grant through `WMM_AGENT_GRANT`; never place its value in
a prompt, repository or command argument. The grant must include `operations.read`.
The local owner HTTP route is
`GET /api/apps/your-app-id/agent-operations?profile=meta_media_buyer`.
An empty input still returns general guidance with a compact specialist index.

The response binds its rules to the current app hash, manifest version and actual
operation effects. Load it only when needed. Re-read after an app change; a stale
grant needs owner renewal. Unknown profiles and extra query fields are rejected.

Follow the returned stages in order:

1. Read accounts, source coverage and the business objective. Ask the owner only
   for critical missing choices while continuing useful independent research.
2. Link audience pain, keyword intent and competitor observations to an app
   benefit. Keep original observations distinct from agent interpretations.
3. Prepare one creative hypothesis, truthful app proof, rights and a measurable
   comparison. Existing independent creative-review requirements still apply.
4. Check exact current account, Page, currency, content, targeting, schedule,
   quota, liability ceiling, expiry and stop rules against owner authority.
5. Execute the supported approved step. Save intent IDs and verify provider
   readback. Queued, delivered, attributed results and causal lift are distinct.
6. Monitor on the approved schedule. Reconcile uncertainty before any retry;
   retain unresolved liability. Protective pause needs actual provider readback.
7. Report source dates, windows, samples, denominators, maturity, costs, receipts,
   unknowns and a reasoned continue / stop / revise decision to the owner.

Owner-selected sufficiency, pacing and stop rules govern decisions. There is no
universal budget scaling percentage, learning-event count or automatic spend.
Missing measurements remain null. Vendor promises and forecasts are not results.

Current paid execution is Facebook Feed engagement using `OUTCOME_ENGAGEMENT`,
`POST_ENGAGEMENT` and `IMPRESSIONS`, with the existing guarded launch/pause/reconcile
paths. Advantage+ app campaigns, app-install optimization, bid/budget edits and
cross-network reallocations require implementation. The specialist records that
gap rather than launching a different objective. Reading this profile grants no
additional operation, credential access or spending authority.

See the [dated research and REA boundaries](../research/meta-media-buying-patterns.md).
