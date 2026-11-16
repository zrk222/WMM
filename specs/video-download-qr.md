# Spec: video-download-qr
Status: draft

## MUST - Functional core
### Description
Put a scannable link to the promoted app inside every newly published WMM social video before the owner reviews its bytes.

### Requirements (EARS)
- When a Hypit render has a numeric App Store ID, the system shall encode its canonical App Store product URL through `store_binding`.
- When the app has no App Store ID and has an Android package, the system shall encode its canonical Google Play product URL through `play_binding`.
- When the final video is rendered, the system shall add a high-contrast QR code with a four-module quiet zone inside the upper-left safe area from first through last frame through `rendered_qr`.
- If a render has no current store-bound QR receipt, WMM shall refuse a new Facebook, Instagram, TikTok, YouTube, or LinkedIn video publication through `no_unbound_video`.
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
  Then WMM refuses the effect and instructs the owner to update App setup or render again
Scenario: recovery_preserved
  Given an existing publication receipt
  When `recovery_preserved` inspects prior effects
  Then the original bytes and receipt remain unchanged and an owner can read provider state
```

## SHOULD - Technical
- Derive both destinations server-side; the QR URL is never caller-controlled and makes no network request.
- Preserve draft rendering without a store ID, original footage, and existing approval hashes. App Store is the default when both store IDs are configured.
- Keep the QR and its download link visible in the owner preview. On-video placement must preserve the title and captions.
- This change adds no provider writes, paid services, new publication channels, or change to text posts.
