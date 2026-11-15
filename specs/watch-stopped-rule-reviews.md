# Show stopped Results reviews in Watch

- When an active owner opens the current app, Watch uses the existing Weekly Review classifier to show a stopped or unreadable schedule in plain language. It exposes no schedule or report identifiers, owner identity, or saved rule inputs.
- Watch does not read the schedule when the viewer is signed out or lacks the current app owner role. It drops the exception when the app revision no longer matches. Normal OFF, expired, exhausted and healthy schedules remain quiet.
- The exception opens the existing Results rule disclosure, focuses its summary, and reads saved recommendations. Weekly Review uses the same navigation. Neither action starts, changes or restarts a schedule, provider operation or grant.
- When the rule read fails, Watch retains other workflow exceptions and offers a local review or refresh.
