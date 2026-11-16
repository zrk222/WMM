# Spec: video-download-qr
Status: draft

## MUST - Functional core
### Description
Offer a scannable app-store link on each newly published WMM social video. Render it by default and let the operator turn it off before reviewing the final bytes.

### Requirements (EARS)
- When a Hypit render has a numeric App Store ID, the system shall encode its canonical App Store product URL through `store_binding`.
- When the app has no App Store ID and has an Android package, the system shall encode its canonical Google Play product URL through `play_binding`.
- When QR is enabled and the store ID is configured, the system shall add a high-contrast QR code with a four-module quiet zone inside the upper-left safe area from first through last frame through `rendered_qr`.
- If a render has neither an explicit QR opt-out nor a current store-bound QR receipt, WMM shall refuse a new Facebook, Instagram, TikTok, YouTube, or LinkedIn video publication through `no_unbound_video`.
- When the operator turns off the QR, the system shall freeze the choice in the render inputs, skip stamping, and require the same publication approval through `optional_qr`.
- If an approval already exists, the system shall preserve its exact artifact bytes and allow read-only reconciliation of earlier effects through `recovery_preserved`.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: store_binding
  Given a workspace with a numeric App Store ID
  When `store_binding` resolves its direct download path
  Then the QR destination is apps.apple.com/app/id followed by that app's ID
Scenario: play_binding
  Given a workspace with only an Android package
  When `play_binding` resolves its direct download path
  Then the QR destination is play.google.com/store/apps/details with that package ID
Scenario: rendered_qr
  Given a valid store-bound artifact preview
  When `rendered_qr` decodes the opening and closing frames
  Then both QR codes resolve to the exact canonical download URL
Scenario: no_unbound_video
  Given a legacy video or changed store ID
  When `no_unbound_video` checks new publication
  Then WMM refuses the effect and explains how to render with or without a QR code
Scenario: optional_qr
  Given a reviewed request with include_download_qr set to false
  When `optional_qr` prepares the output
  Then no QR is added and only that reviewed artifact is eligible to publish
Scenario: recovery_preserved
  Given an existing publication receipt
  When `recovery_preserved` inspects prior effects
  Then the original bytes and receipt remain unchanged and an owner can read provider state
```

## SHOULD - Technical
- Studio and the organic render form expose a default-on checkbox. Agent callers use the optional boolean `data.include_download_qr` on `hypit.queue` or `render_input.include_download_qr` on the organic workflow.
- Derive both destinations server-side; the QR URL is never caller-controlled and makes no network request.
- Preserve draft rendering without a store ID, original footage, and existing approval hashes. App Store is the default when both store IDs are configured.
- Keep the QR and its download link visible in the owner preview. On-video placement must preserve the title and captions.
- This change adds no provider writes, paid services, new publication channels, or change to text posts.
