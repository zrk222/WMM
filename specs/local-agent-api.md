# Spec: local-agent-api
Status: draft

## MUST - Functional core
### Description
Allow explicitly selected local model servers through the existing reviewed draft workflow. Preserve public HTTPS BYOK and official subscription adapters. This packet does not claim arbitrary provider OAuth compatibility or waive full-domain agent coverage.

### Requirements (EARS)
- The system shall accept only explicit HTTP loopback model-server endpoints, normalize localhost to a numeric loopback address and reject remote or ambiguous authority before connecting through `local_endpoint`.
- The system shall store app-owned local model profiles with an optional protected bearer key of at most 1800 characters, required model, explicit request consent and separate local routing without exporting keys through `local_profiles`.
- The system shall return validated structured drafts through the existing OpenAI-compatible chat protocol with fixed loopback destination, bounded response, shared deadline, no redirects and no tool execution through `bounded_inference`.
- The system shall reject changed app facts, profile, routing, source or approval older than 1800 seconds through the existing job guard before and after local inference without replay or silent fallback through `approval_currentness`.
- The system shall return local-server setup and routing controls in Your agents with clear purpose, required model and endpoint, optional key, explicit consent and source-specific reporting through `local_interface`.
- The system shall preserve existing API-key and official subscription adapters and emit real loopback server, worker, UI, failure and credential-privacy proof without claiming actual local model quality or real provider acceptance through `provider_regression`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: local_endpoint
  Given an isolated app and explicitly configured local model server
  When `local_endpoint` is exercised
  Then the valid bounded request succeeds and changed or unauthorized scope is rejected
Scenario: local_profiles
  Given an isolated app and explicitly configured local model server
  When `local_profiles` is exercised
  Then the valid bounded request succeeds and changed or unauthorized scope is rejected
Scenario: bounded_inference
  Given an isolated app and explicitly configured local model server
  When `bounded_inference` is exercised
  Then the valid bounded request succeeds and changed or unauthorized scope is rejected
Scenario: approval_currentness
  Given an isolated app and explicitly configured local model server
  When `approval_currentness` is exercised
  Then the valid bounded request succeeds and changed or unauthorized scope is rejected
Scenario: local_interface
  Given an isolated app and explicitly configured local model server
  When `local_interface` is exercised
  Then the valid bounded request succeeds and changed or unauthorized scope is rejected
Scenario: provider_regression
  Given an isolated app and explicitly configured local model server
  When `provider_regression` is exercised
  Then the valid bounded request succeeds and changed or unauthorized scope is rejected
```

## SHOULD - Technical
- Reuse deadline-aware HTTP framing, strict JSON, draft schema, protected vault and approved worker guard.
- A local server may proxy a paid cloud model; endpoint locality is not evidence of model locality or free execution.
- No model downloads, package installation, native sign-in or live provider mutation.
- OpenAI chat compatibility reference: https://docs.ollama.com/api/openai-compatibility inspected 2026-10-23; actual vendor/model acceptance is separate.

## Authorized parameters
MAX_RESPONSE_BYTES = 1048576
DEADLINE_SECONDS = 30
DEFAULT_LOCAL_PORT = 11434
MAX_PORT = 65535
MAX_SECRET_LENGTH = 1800
MAX_PROMPT_BYTES = 32768
MAX_TOKENS = 2048
max_tokens = 2048
