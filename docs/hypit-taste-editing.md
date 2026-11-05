# Taste-guided Hypit edits

Open **Advanced tools → Research → Open video projects → Edit project**.
Expand **Review app-demo clarity proposal** to inspect the suggested controls.
**Apply proposal to draft fields** changes fit to CONTAIN and reduces speeds above
100% to normal speed. Source identities, trims, sound, effects and other fields
stay unchanged. Save explicitly to create a revision; rendering is a separate action.
Use the existing undo, redo and saved revisions to compare or restore the edit.

The same recipe is included in the personal-agent operating manifest. It adapts
the review/apply/inspect approach from the installed tasteskill v2 and ECC
tasteforge-video guidance. Their source hashes are recorded in the recipe.
This integration uses existing local controls; it does not install a renderer,
run TasteForge generation, or certify video quality with a web-page audit.

For a captured app-screen demo, keep controls legible and preserve the full
picture. Hypit footage compositions place added captions below the captured
picture. Inspect the encoded opening, transitions, caption lines and ending;
shorten captions that wrap badly. Record the output hash, timestamps, the visible
issue, the reason for the edit, and the before/after comparison.

For **viral repurposing**, follow the selected workflow: discover a social source,
verify at least 100,000 views AND 10 times a documented comparable creator
baseline, inspect its hook/beat/treatment, record the owner's reuse decision,
revise for the app, review, publish under current authority, then monitor/report.
An original app demo is a different workflow and cannot silently replace this
path. UGC remains a separate intake option exempt from viral qualification.

The owner authorizes reuse. WMM retains the source identity, decision and evidence;
a discovery result or taste verdict never grants rights. An owner can separately
approve bounded standing generation through the existing Organic Video policy.
The draft clarity button alone does not activate that policy or automatically
approve a rendered result. Taste-agent auto-approval of exact rendered outputs
requires its own implemented and tested owner-selected review scope.

Owner-selected public demo MP4s can be imported through
`POST /api/apps/{app_id}/organic-video/import-demo`. Send `application/octet-stream`
with the original bytes, the current same-origin owner session and CSRF token, and
one `X-WMM-Demo-Selection` JSON header:

```json
{"request_id":"unique-request","manifest_version":1,"release":"your-current-release","filename":"demo.mp4","source":"OWNER_SELECTED_DEMO_MP4","app_owned":true,"contains_private_data":false,"uses_personal_account":false}
```

This retains source media and provenance. A separate owner rights review is still
required. It neither renders nor publishes and cannot manufacture a completed
WMM render record for an externally produced video.
