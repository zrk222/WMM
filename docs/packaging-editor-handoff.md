# Prepare a video project from a reviewed shot plan

Open the saved shot checklist and choose an original clip with current reuse
permission for every shot. Choose the start and end frame, whether to keep its
audio, and an output shape. Use a current saved video direction for the same app.

Agents with an explicit `packaging.editor-prepare` grant can call
`wmm_packaging_editor-prepare` with the current app version, exact shot plan
and video-direction references, title, purpose, output shape and ordered clips.
Each clip carries the saved shot ID and its exact managed source identity.
Use the live WMM catalog and the video project definition for the clip fields.

The response contains the editable definition and its source receipt. To create a
draft, use the separate `editor.save` permission and send the returned definition
as revision zero. Open the saved project in the desktop video editor to adjust
timing, framing or audio. Use a new project when the shot plan or reviewed video
direction changes. Existing revisions retain their original references.

Preparation and draft creation are local. Rendering, export and publication
each follow their existing review and approval paths.
