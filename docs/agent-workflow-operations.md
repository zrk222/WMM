# Agent workflow operations

The fixed catalog includes `evidence.save`, `pipeline.prepare`, `jobs.read` and
`job.cancel`. Inspect `python -m mission_control.agent_cli catalog` for exact
envelopes. The same operations appear as MCP tools using underscores.

Use an owner-issued grant containing the required operations. For selected
writes, the owner can require independent human review. The agent prepares an
exact reviewed request, a separately authenticated checker approves it in
Activity & reviews, and the agent resumes with its exact revision and packet
hash. Agents cannot approve or replace the frozen input.

1. Read `workspace.read` for app version, required evidence and current gaps.
2. Save typed assertions with `evidence.save`: `id`, `manifest_version`, `kind`,
   `title`, `source`, `data`, and optional current record `version` for an edit.
   Domain validators and optimistic conflicts apply. Connection records require
   separate credential setup. Existing record kinds cannot change through this
   operation, including replacement of a connection record under another kind.
   Local assertions are not independent verification.
3. Prepare a pipeline job with input
   `{"action":"pipeline","data":{"stage":0},"request_key":"my-workflow-v1"}`.
   Stage zero prepares all twelve stages; stages one through twelve select one.
   Sync, render and additional nested job fields are rejected before transport.
4. Read `jobs.read` for up to 100 recent jobs belonging to this app. A successful
   checkpoint for `pipeline.prepare` proves job submission only. `QUEUED` is not
   completed preparation. Inspect the job's eventual status, result and outputs.
   The local pipeline produces artifacts; it never publishes or spends.
5. Cancel an active job with `job.cancel`, its `resource_id` and empty input.
   Cancellation records local job status. Inspect running work and its receipt;
   cancellation does not prove an external effect was stopped. Terminal jobs
   cannot be cancelled again. No automatic uncertain-write replay is provided.

CLI example, with the scoped token supplied in the process environment:

```powershell
'{"app_id":"your-app","operation":"pipeline.prepare","input":{"action":"pipeline","data":{"stage":0},"request_key":"my-workflow-v1"}}' | python -m mission_control.agent_cli call --origin http://127.0.0.1:57599 --use-grant
'{"app_id":"your-app","operation":"jobs.read","input":{}}' | python -m mission_control.agent_cli call --origin http://127.0.0.1:57599 --use-grant
```

For a grant requiring review, use the existing `review-prepare`, `review-status`
and `review-resume` commands instead of ordinary dispatch. See
`docs/agent-review-transport.md`. A trusted local browser session is a separate
adapter; it is not a verified human checker identity.

These operations extend the working catalog; they do not establish full-domain
agent coverage. Credential setup, human approvals, provider mutations, publishing,
spending and arbitrary shell or HTTP calls are not agent catalog operations.
