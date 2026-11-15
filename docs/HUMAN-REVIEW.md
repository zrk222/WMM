# Review one WMM change

Start with the pull request’s **Start here** and **Reproduce one important check** sections. The author supplies the commit, the first diff to inspect, the expected result, and any gaps.

1. **Check the commit.** Compare the recorded SHA with the PR’s current head. If it changed, review the new diff and update your record.
2. **Check one real behavior.** Open the linked diff and run the author’s check in a clean checkout of that SHA. Use synthetic data. For an authority, budget, credential, or publishing change, also check the relevant denial case. If you cannot run a check, record it as unrun.
3. **Leave a decision.** Put actionable findings on the affected lines. A short PR comment is enough for the rest:

~~~text
Reviewed SHA:
Scope:
Check and result:
Findings or unrun checks:
Disposition: Approve / Request changes / Needs evidence
~~~

An independent reviewer is a human who did not author or direct the change. CI, agent feedback and owner self-review are useful evidence with separate labels. The [owner review policy](REVIEW-POLICY.md) still applies, including its independent security review requirement for expansion. Never include credentials, private analytics, or customer records in a PR.
