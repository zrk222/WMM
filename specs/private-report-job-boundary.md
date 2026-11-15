# Keep scheduled owner reports private

- Ordinary workspace and job views show the status of a scheduled private report without its content, failure detail, request key, or plan inputs. This also applies to older rows.
- A newly completed worker job keeps only a completion marker. The full report and its fingerprint stay in the existing owner-bound report store and owner Results views.
- A general job cancel cannot cancel a scheduled private report. Its existing exact owner plan stop remains available.
- The generic run modal shows status and points to Private campaign outcomes without rendering a report, downloading it, or presenting a generic cancel action.
