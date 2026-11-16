# Apple campaign file collection

In **Apple analytics → Measure App Store campaign downloads**, an app owner can
paste the app's Apple campaign link and collect daily App Downloads Detailed
files by processing date. The form starts with the latest seven calendar days
available in the saved inventory and can request up to 31 days and 31 files.
Processing dates describe the files; the separate results form uses download
dates and storefront. Apple can include delayed events or corrections.

Admission uses the current app, connection and the exact displayed inventory.
The local queue commits the whole selection together. Repeating a selection
returns the existing jobs; a new inventory lets the owner retry unsuccessful
reads without repeating successful or in-flight reads. The link and campaign
token are not written into collection jobs. The worker reuses the existing
Apple read path. Collection never publishes, spends, changes the App Store
listing, or enables a schedule.

Activity provides the individual jobs. Results show the Apple processing date
and source fingerprint for each retained download date. A matching count,
including an explicit zero, is provisional until its file was processed at
least two calendar days after the download date. Ready to review does not mean
final: a later Apple correction may replace the retained count. Results
distinguish a missing file from a retained file with no matching first-time
download row. Both leave the count unknown. If a date needs more evidence,
collect newer files for the same dates and keep the saved review window.
Synthetic acceptance proves
admission, replay and recovery behavior. Live campaign acceptance also requires
a current Apple connection, the exact campaign link used in distribution, and a
dated live read result; it does not imply growth or causal lift.
