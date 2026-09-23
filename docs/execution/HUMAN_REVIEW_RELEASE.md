# Approved first release: human review

> Amendment note (2026-09-22): the USD 5 ceiling and the version 1 scope
> digest named below were superseded on 2026-09-14 by the USD 12 ceiling and
> `human-review-release-scope/v2` (digest
> `5c460d9ca7acc86ee0407584732d0cf1e27b1bc685a968f8094ce7ca133dfc15`); see
> [APPROVED_RELEASE_BUDGET.md](APPROVED_RELEASE_BUDGET.md). The selection
> itself, the ten specimens and the human-review scope are unchanged.

> 2026-09-23: The owner's decisions in [`docs/execution/golive/PLAN.md`
> section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> supersede parts of this document for the go-live program. Each superseded
> clause keeps its original text and carries a dated note naming the
> decision. [`golive/RELEASE.md`](golive/RELEASE.md) lists the code that
> still enforces a superseded clause until a later go-live pull request
> changes it.

> 2026-09-23: Superseded for the go-live program by [`docs/execution/golive/PLAN.md`
> section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G1 and G9. The `human-review-release-scope/v2` artifact named above, whose
> scope carries `"automated_clearance": "deferred"`, is itself superseded: a
> record the agentic harness resolves is cleared without a human. The
> spending ceiling is also superseded again, now USD 25 cumulative,
> infrastructure and models together.

On 2026-09-08 the user selected:

> Complete human review: process all 10, compare readings, correct and save
> records; defer automated classification and clearance.

> 2026-09-23: Superseded for the go-live program by [`docs/execution/golive/PLAN.md`
> section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G1. The full pipeline of PLAN section 1 is in scope, including the LLM
> first pass and the agentic harness's lookups, and a record the harness
> resolves is cleared without a human instead of deferred; human review and
> deferral otherwise stay as the specification defines them.

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

> 2026-09-23: Superseded for the go-live program by [`docs/execution/golive/PLAN.md`
> section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G1. Automated clearance is no longer deferred: the agentic harness runs
> its lookups (including GBIF) on the decided transcript, and a record the
> harness resolves is cleared without a human. Records the harness cannot
> resolve still go to the human queue. Automated collection classification
> stays deferred: under G14 the profile comes from the collection a specimen
> was uploaded or imported into, and there is no classification stage.

All infrastructure limits in [RELEASE_AUTHORIZATION.md](RELEASE_AUTHORIZATION.md)
remain unchanged: the same ten specimens and one cumulative USD 5 ceiling across
all days, sessions and retries. Initial administrator sensitive access stays false.

> 2026-09-23: Superseded for the go-live program by [`docs/execution/golive/PLAN.md`
> section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G9 and G11. The spending ceiling is USD 25, cumulative, infrastructure and
> models together. The release envelope and authorization artifact that
> `RELEASE_AUTHORIZATION.md` describes are retired; releases now deploy
> automatically on merge once the required checks pass and the PR steward
> approves.

The user's actual selection is preserved in the owned private file
`human-review-release-scope-v1.json` under the coordinator's existing rollout-state
directory. Its SHA256 is
`14f6b1140f7d45e46c022e4a1c4f60cd775bafbef73ca363a677f278e0eafd1a`.
Private decisions reference that exact artifact. Approval is not execution proof;
public end-to-end acceptance remains **Not confirmed**.
