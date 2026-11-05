# Spec: four-channel-workflow-preview
Status: owner-authorized visibility and preview update

## MUST - Functional core
### Description
Show Facebook Page, Instagram Reels, TikTok and YouTube Shorts together, from the WMM front door to the actual research assignment and public preview. Clearly name current delivery support by channel. Reuse the existing research, creative and governed Facebook paths.

### Requirements (EARS)
- When the owner opens Set your goal, the system shall return 1 shortcut through `channel_workflow` into existing agent video research and expose exactly 4 named platform choices without issuing any grant or assignment on navigation.
- When the owner or visitor inspects the distribution paths, the system shall return 4 channel descriptions and 4 local platform marks through `delivery_status`, showing Facebook Page delivery behind existing approvals, basic Instagram and TikTok identities, and YouTube Shorts research without an in-app publisher.
- When a visitor selects a channel in the synthetic demo, the system shall return the selected channel in 1 approved sample plan and report through `channel_preview`, with 0 provider calls and no reused approval after a channel change.
- When the repository preview shows the current example, the system shall return 1 real synthetic browser screenshot through `channel_screenshot` with the named channel and the existing synthetic provenance gate.

### Acceptance criteria (Gherkin)
```gherkin
Scenario: channel_workflow
 Given the local workspace
 When `channel_workflow` opens video research
 Then the four named choices are available with the existing owner gates
Scenario: delivery_status
 Given the app and overview channel descriptions
 When `delivery_status` is read
 Then each platform mark is paired with its readable name and metadata research and direct Facebook delivery are clearly distinct
Scenario: channel_preview
 Given an approved local sample plan
 When `channel_preview` changes the selected channel
 Then consent resets and the next completed export names the new channel with zero provider effects
Scenario: channel_screenshot
 Given the actual rendered sample
 When `channel_screenshot` is refreshed
 Then it shows the chosen channel and matches the current synthetic capture hash
```

## Scope
No new provider connector, publishing transport, spending or authority. Preserve the existing 100,000 views AND 10 times a documented creator baseline requirement and the UGC path. The new preview illustrates supported preparation; actual delivery state is explicit for each channel.
