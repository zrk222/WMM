# Release clearances

A public desktop release is blocked unless `docs/release-clearances/<sha>.json`
exists for the exact 40-character candidate SHA and passes
`tools/check_release_clearance.py`.

The receipt is a human attestation, not an agent self-assessment. Store sensitive
supporting evidence outside the public repository and put only its SHA-256 in the
receipt.

~~~json
{
  "schema": "wmm.release-clearance.v1",
  "candidate_sha": "<40 lowercase hex>",
  "independent_review": {
    "reviewer": "<human reviewer>",
    "reviewed_sha": "<same 40 lowercase hex>",
    "pr": 123
  },
  "ip_diligence": {
    "status": "CLEARED",
    "inventory_sha256": "<64 lowercase hex>"
  },
  "signing": {
    "windows": "AUTHENTICODE_VERIFIED",
    "verification_receipt_sha256": "<64 lowercase hex>"
  }
}
~~~

Use the inventory required by [IP-DILIGENCE.md](../IP-DILIGENCE.md). The release
environment must require manual approval from a human who did not author the
candidate.
