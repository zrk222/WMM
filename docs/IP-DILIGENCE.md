# WMM rights and relicensing checklist

**Status: ownership and relicensing diligence open.** This is a review checklist,
not a chain-of-title opinion or a grant of rights.

| Material | Starting evidence | What the buyer should verify |
| --- | --- | --- |
| Prior Apache material | The last pre-transition tree is [`2fdf1986`](https://github.com/zrk222/WMM/tree/2fdf1986eb6200e5a51e8ea8cc17265ede6d5f93); the license changed in [`4938c29`](https://github.com/zrk222/WMM/commit/4938c290ca294809c265bad6ddfe6ebf5b99d98e). See the retained [Apache text](../licenses/Apache-2.0.txt). | Identify which portions of the proposed delivery retain Apache grants and carry forward the required notices. The commit boundary is a starting point for comparison, not proof of ownership for each file. |
| Later WMM changes | The [current license](../LICENSE) covers only material its licensor has authority to license. | Tie material changes to a rights holder and evidence of ownership, assignment, or sufficient license. A Git author name or repository account is not an assignment. |
| Dependencies, bundled tools and assets | Lockfiles, build manifests, `NOTICE`, and the actual shipped files. | Check the release payload and copied source/media separately. A build-environment SBOM alone does not establish what is shipped or which obligations apply. |
| Agent-assisted work | Human design decisions, edits and review records where retained. | Record the tool and terms applicable when used, known input sources, substantive human contributions and any suspected copied material. Record unknowns. Provider terms and agent output are not proof of training-data provenance or exclusive rights. |

For the exact candidate commit or release digest, keep a private inventory with
one row per material component: path or artifact, source revision, origin, rights
holder, applicable license, evidence location, and disposition. Use
**cleared**, **third-party obligations apply**, or **open**. Keep signed
agreements and sensitive work records outside the public repository. For new
contributions, ask authors to disclose material third-party or agent-assisted
inputs that need review and obtain any additional rights in writing.

Before a sale or a license change, have counsel verify the inventory, scope of
transfer, and any required contributor permission. A future license can only
grant rights the licensor is authorized to grant. Preserve prior Apache grants
and third-party obligations; clear, replace or exclude unresolved material
before representing it as transferable. No license change is made by this guide.

Official references: [Apache License 2.0, sections 2–4](https://www.apache.org/licenses/LICENSE-2.0)
and [U.S. Copyright Office reports on AI output and training](https://www.copyright.gov/ai/).
The relevant law and contract terms depend on the transaction and jurisdiction.
