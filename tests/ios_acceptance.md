# Standalone Wize Marketing Machine native acceptance

This procedure covers the full `specs/ios-client.md` contract and T1–T14 in
`plans/ios-client.md`. It does not reduce acceptance to currently implemented
screens or passing shared Python fixtures. Current native acceptance is incomplete.

Run `python tools/check_platform_receipts.py --profile ios` from the repository
root. Missing `.factory/ios-acceptance/receipt.json` must return exit 1. An intact
receipt returns `EVIDENCE_CURRENT_REVIEW_REQUIRED`, never an iOS support or
security certification. Review the actual artifacts before making a support claim.
The checker runs offline and never signs, installs, invokes providers or uses keys.

## Collect actual evidence

1. Record the exact candidate inventory emitted by the checker, Git commit,
   Xcode/SDK, runtime source and framework hash. Build the native app and execute
   the nonempty test plans on available iPhone and iPad simulators. Keep both
   xcresult bundles, their inspected summaries and failed/skip results. A skipped
   physical-device test is not physical acceptance.
2. Install the signed candidate on an actual iPhone and iPad. Record model,
   exact OS patch, bundle/signing identity, app/runtime archive hashes and install
   readback. Turn off every other WMM installation and verify native operation
   without a computer, remote WMM service or loopback UI dependency.
3. Exercise every requirement identifier in the current spec on both physical
   families. Record expected and observed behavior and its original artifacts.
   Include every required owner and scoped-agent domain, human/standing approval
   boundary, stale/revoked/foreign/quota denial and exact source context.
4. Inspect device Keychain namespaces and protected files through lock/unlock,
   session expiration, reinstall/recovery boundaries and app lifecycle changes.
   Keep original media immutable. Import Photos/Files, exercise required transforms,
   trimming, speed, stitching, audio, Studio scenes, cancel/recover, decode frame
   order and share/export only after current rights and authority checks.
5. Record eligible background/deferred work, expiration, force termination,
   restart, network loss, memory pressure and uncertain external effects. Confirm
   that no uncertain model/provider request is automatically replayed.
6. Verify observed/unknown analytics, complete PDF/JSON/CSV reports and portable
   snapshots. Inspect real output bytes, page content, source hashes and privacy.
   Exercise VoiceOver, hardware keyboard, touch and large text on both devices.
7. For optional provider paths, retain credential-free account/scope, reconnect,
   callback, revocation and no-replay evidence. Do not execute live provider writes,
   publication or spending without the owner's exact existing authorization.
   Disabled optional connections must not prevent local workflows. Missing native
   provider capability remains an implementation gap, not an automatic N/A.

Do not populate passing observations for unfinished or unexecuted workflows.
Receipts must contain no credentials, private account profiles, customer events
or real research in Git. Keep evidence under ignored `.factory/ios-acceptance/`.

## Receipt shape

`receipt.json` uses schema `wmm.ios-acceptance.v1`, the emitted
`candidate_sha256`, `artifacts` and `profiles`. Each artifact has unique `id`,
relative `path`, SHA256, `family` (`iphone` or `ipad`) and `kind`.
Paths resolve inside the evidence directory; changed bytes invalidate the receipt.

Each physical profile has `family`, `physical: true`, `companion_offline: true`,
`device_model`, `os_version`, `xcode_version`, `sdk_version`, `python_version`,
`bundle_id`, `signing_identity`, `observed_at`, and `observations`. Every observation
has one exact requirement identifier, recorded `status`, and nonempty artifact-ID
references belonging to that same family. Every one of the 16 current requirements
must occur exactly once per physical family. Failed or NOT_RUN rows stay incomplete.

Required artifact categories per family are `xcresult_summary`, `signed_app`,
`runtime`, `install`, `domain`, `keychain`, `media`, `lifecycle`, `accessibility`,
`exports` and `provider_boundary`. These labels do not authenticate their contents.
Inspect original xcresult, signature verification, installation/device and workflow
readbacks independently. Never rename an unrelated log to fill a category.

The simulator workflow is currently declared in `codemagic.yaml`; Windows/Ubuntu
shared regressions remain in `.github/workflows/checks.yml`. The planned
`.github/workflows/platform-checks.yml`, native UI/device suite coverage and complete
signed acceptance receipts remain separate required deliverables. This guide and
receipt checker alone do not close T11–T14 or the full iOS goal.
