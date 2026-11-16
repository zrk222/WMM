# Agent-assisted contribution provenance

**Status: repository evidence recorded; provider terms and legal review remain
open.** This is an evidence record, not proof of authorship, ownership or
training-data provenance.

## Recorded evidence

| Evidence | Finding |
| --- | --- |
| Git author identities | 198 commits by `ZRK222 <rkatz22@gmail.com>`, 143 by `zrk222 <199277449+zrk222@users.noreply.github.com>`, 1 by `dependabot[bot]`. Both human identities resolve to the repository owner account; no second human author appears in local history. |
| Explicit agent co-author | `e45b939496beded0ef26389377d5dbd903123db4` carries `Co-authored-by: Instinct Agent <agent@instinct.com>`. |
| Agent branch prefixes | Many commits and PRs use `codex/*` branches. The prefix is evidence of agent-assisted tooling, not a complete tool log. |
| Current typing/audit sessions | opencode CLI using the configured model provider; repository files and user instructions were the inputs. No retention of full prompts, tool-call logs or provider responses is stored in the repository. |
| Human review records | Pull request comments and review decisions are the only retained review evidence. Agent persona reviews are labeled as agent evidence, not independent human approval. |

The per-file ledger marks files touched by the explicit `Instinct Agent` commit
with `agent_assisted: true`. The absence of that flag does not prove that a file
was written without agent assistance; most agent-assisted changes used the
owner's Git identity and left no trailer.

## Inputs and excluded material

- Inputs were repository content, synthetic fixtures, public provider documentation
  and user instructions.
- No customer records, credentials or private provider payloads are intentionally
  included in the inventory or provenance record.
- Third-party code is identified in [IP-INVENTORY.md](IP-INVENTORY.md); it is not
  claimed as agent-generated.
- Model training-data provenance, provider retention, and the legal effect of
  provider terms cannot be established from the repository.

## Open requirements

1. Retain the applicable provider/tool terms and account settings for each
   material agent-assisted change.
2. Record substantive human design, correction and review contributions where
   they exist.
3. Identify any externally sourced code, text, image, audio or video copied into
   agent output.
4. Obtain contributor permission where a contribution is not owned by the
   repository owner.

Do not represent this record as a copyright assignment or as proof that agent
output is free of third-party rights.
