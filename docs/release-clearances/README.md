# Release clearances

A release approval is recorded in GitHub after the signed packages are built.
It does not require a receipt committed under the SHA it approves.

1. Configure the GitHub `release` environment with an independent required
   reviewer, prevent self-review, and restrict it to main. Set
   `WMM_RELEASE_REVIEWER_ID` to the numeric GitHub ID of the eligible reviewer.
   Configure a real trusted Windows signer separately. The release workflow
   refuses publication without an actual environment approval from that ID.
2. Dispatch the official release workflow for the exact merged main SHA and
   unused tag. The package jobs build and check the signed installers. The
   **prepare** job verifies their attestations with no release write permission. It publishes a
   SHA-256 fingerprint over the source, tag, workflow run and attempt, signer,
   and every staged payload and provenance file digest.
3. The reviewer who did not author or direct the release reviews the exact
   source and prepared assets, verifies the signer and lifecycle evidence, and
   completes the private [IP inventory](../IP-DILIGENCE.md). Do not approve if
   any of that evidence is missing. In the GitHub environment approval comment
   use the instruction from the **prepare** summary:

   ~~~text
   wmm-preview <prepare fingerprint> IP-CLEARED <private inventory SHA-256>
   ~~~

4. The protected publish job downloads the immutable artifact from the same
   run and attempt, checks the same fingerprint, and verifies the exact
   approval in GitHub's deployment review history. It publishes those bytes
   without rebuilding. A different run, attempt, tag, installer or inventory
   needs fresh review.

The comment is a human declaration, not proof of ownership or a legal opinion.
Keep private supporting records out of the repository and public run logs.
The automated identity check excludes GitHub's author of the exact candidate
commit, the original dispatcher, and the rerun initiator. The reviewer must
also be independent of the underlying work, including its co-authors and
anyone who directed it; a commit identity alone cannot establish that.
