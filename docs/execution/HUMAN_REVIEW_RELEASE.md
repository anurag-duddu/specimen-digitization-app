# Approved first release: human review

On 2026-09-08 the user selected:

> Complete human review: process all 10, compare readings, correct and save
> records; defer automated classification and clearance.

This defines the first production release's acceptance scope. It supersedes
earlier wording that required automated classification or institutional clearance
to complete this release. It does not make those capabilities qualified or turn
unexecuted criteria into passes.

Required: the approved administrator can use the live public URL to access all
ten frozen Firebase specimens, run real segmentation and two independent readings,
compare their evidence, correct and save records, and reload/search/reopen the
persisted records and history with the correct original sources. Authentication,
collection scope, sensitive-data denial, original generations, provenance,
durable retries, restart recovery and the shared cost limit remain mandatory.
Missing or failed processing cannot be hidden by removing a specimen, using
synthetic output or substituting another source.

Deferred: automated collection classification and automated clearance. Draft
collection profiles, uncalibrated classifier scores, unconfigured risk policies
and unresolved external authorities must remain visibly unqualified. The system
may retain review-required dispositions while users complete the approved human
review journey; a setup screen, empty result or blocked processing run is not
end-to-end acceptance.

All infrastructure limits in [RELEASE_AUTHORIZATION.md](RELEASE_AUTHORIZATION.md)
remain unchanged: the same ten specimens and one cumulative USD 5 ceiling across
all days, sessions and retries. Initial administrator sensitive access stays false.

The user's actual selection is preserved in the owned private file
`human-review-release-scope-v1.json` under the coordinator's existing rollout-state
directory. Its SHA256 is
`14f6b1140f7d45e46c022e4a1c4f60cd775bafbef73ca363a677f278e0eafd1a`.
Private decisions reference that exact artifact. Approval is not execution proof;
public end-to-end acceptance remains **Not confirmed**.
