# Approved cumulative budget amendment — September 14, 2026

> 2026-09-23: The owner's decisions in
> [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> supersede parts of this document for the go-live program. Each superseded
> clause keeps its original text and carries a dated note naming the decision.
> The [go-live amendment](#go-live-amendment-2026-09-23-g9) at the end records
> the USD 25 ceiling. [`golive/RELEASE.md`](golive/RELEASE.md) lists the code
> that still enforces a superseded clause until a later go-live pull request
> changes it.

The user approved the combined release decision at 2026-09-14T02:03:08.382Z in
integration task `01a07f48-a57c-71b0-9642-c9430886049c`. The unchanged ten original
specimens, every actual region, both readers and human save/reopen acceptance
remain required. The new total and daily ceilings are USD12. Every previous
cost, reservation and unknown liability stays counted across sessions and days.
This is a ceiling, not a price quote or evidence that production is ready.

> 2026-09-23: Superseded for the go-live program by
> [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G2 and G9. The ceiling is USD 25, cumulative, infrastructure and models
> together, and the ten pilot specimens are the acceptance cohort, processed one
> at a time in order, while new uploads are processed on demand too.

The exact original user-record SHA256 is
`3303d129e5fde28d828729cd5b034a7981968c5cbbbad882a05367a5c361df2a`.
Private original context and approval bytes remain with the coordinator. A new
source-bound packet, independent review and current complete cost reservation
are still required. No historical packet, capture time or consumed fence changes.

> 2026-09-23: Superseded for the go-live program by
> [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G11. Releases need no packet, independent review report or release cost
> reservation; they deploy on merge after the required checks pass and the PR
> steward approves. G30's per-call reservations stand (PLAN 4.3; the
> coordinator's ruling on the mechanism).

## Release inputs

> 2026-09-23: This section is superseded for the go-live program by
> [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G11. The release packet, `shared-release-reservations/v2`,
> `release-cost-ledger/v3` and the coordinator snapshot retire with the
> envelopes and the release cost ledgers. G30's per-call reservations stand
> (PLAN 4.3; the coordinator's ruling on the mechanism).

The outer `protected-release/v1` packet and its three evidence keys remain
unchanged. The approved budget explicitly selects
`shared-release-reservations/v2`: the original budget fields plus
`approval_sha256` equal to the fixed user-record digest above. Total and daily
limits are strict positive integers, daily <= total <= 12,000,000 microUSD.
All eleven reservation categories remain mandatory. Legacy reservations/v1
continue to permit at most 5,000,000 and cannot select the new ledger.

The new budget requires `release-cost-ledger/v3`. It has every v2 ledger field
plus `predecessor: {sha256, json}` containing the exact original v2 ledger bytes.
Its fixed original digest is
`4eabef12c337ced7379a26c3cda45ec7546802de8ba4f5f072071deadd5d7a6d`.
Every original workflow and operator row, unknown carry, manifest, accounting
start and coordinator identity must remain unchanged. New liabilities append;
renaming, omission, refunds and resets cannot qualify as this amendment.

The current accounting snapshot selects
`coordinator-cumulative-release-budget/v2`, keeping the v1 fields and adding
`approval_sha256` and `predecessor_snapshot_sha256`. It may use a limit up to
12,000,000. Its predecessor digest must match the unchanged snapshot inside the
original ledger. Original snapshot entries, frozen metadata, accounting identity,
prior evidence and uncertainty remain exact. The original snapshot retains its
v1 schema and <=5,000,000 limit; raising its number is rejected.

The current snapshot still binds each operator and prior hold. Workflow amounts,
operator holds and the prior aggregate count once cumulatively. The prior
aggregate also counts against every represented day because its service-day
allocation remains unknown. Existing replay and exact active-reservation checks
remain in force. A larger shared budget does not enlarge provider/SAM allocations
or permit an extra worker execution.

> 2026-09-23: The single worker execution is superseded for the go-live program
> by
> [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G2. The API starts an execution of the worker job whenever work is due, and
> the worker drains it one specimen at a time (PLAN section 4.6).

The source loader must qualify both `scripts/ci/release_admission.py` and its new
pure dependency `src/specimen_digitization/release_budget.py`; importing an
unqualified copy from an ambient environment is insufficient.

## Review evidence

> 2026-09-23: This section is superseded for the go-live program by
> [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G1 and G11. `cohort-budget/v2` and its review evidence retire with the
> release and cohort cost ledgers. G30's per-call reservations stand (PLAN
> 4.3; the coordinator's ruling on the mechanism). Both
> `human-review-release-scope` artifacts carry
> `"automated_clearance": "deferred"`, which G1 replaces: a record the harness
> resolves is cleared without a human.

`cohort-budget/v2` retains all v1 fields and adds the fixed `approval_sha256` and
`release_ledger: {path, sha256}`. The relative artifact holds the complete v3
ledger. Its workflow/operator rows must project exactly to review budget entries;
the retained prior aggregate is counted separately, once cumulatively and on every
day. Omitting it, assigning it an invented category, or duplicating it cannot
qualify. The eleven reconciled cost-category artifacts are still required.

Full acceptance requires explicit `--budget-approval-sha256` selection for v2.
Human review instead selects the exact canonical `human-review-release-scope/v2`
artifact and digest. It preserves the original human scope, adds the direct
approval digest, original scope digest and daily limit, and changes only its
version, date and budget limits. Skeleton, evaluation and CLI use that same
selected scope. A v1 report cannot be reused as v2 evidence, or vice versa.
The new human-scope digest is
`5c460d9ca7acc86ee0407584732d0cf1e27b1bc685a968f8094ce7ca133dfc15`.
The original human-scope digest remains
`14f6b1140f7d45e46c022e4a1c4f60cd775bafbef73ca363a677f278e0eafd1a`.

The companion [worker timing contract](APPROVED_WORKER_TIMING.md) specifies the
approved single 3,500-second execution. The complete release remains subject to
[protected deployment](../DEPLOYMENT.md) and the original data/privacy scope.

> 2026-09-23: The single 3,500-second execution is superseded for the go-live
> program by
> [`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G2; protected deployment now follows G11.

## Go-live amendment, 2026-09-23 (G9)

For the go-live program, the owner's decision G9 in
[`docs/execution/golive/PLAN.md` section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
sets the spending ceiling at USD 25, cumulative, infrastructure and models
together. It replaces the USD12 total and daily ceilings above.

The ceiling covers every paid model call (the readers, the LLM first pass and
the agentic harness) and the project's infrastructure: Cloud Run, Cloud SQL,
Cloud Storage, Artifact Registry, Secret Manager, Logfire and the Google Maps
Platform. PLAN section 4.3 says how it is held: the pipeline records every paid
call's cost on its run and refuses a paid step whose estimate would cross the
configured model allowance, and a Cloud Billing budget alert watches the whole
project. Release runs reserve and reconcile no cost, because the release
ledgers retire under G11. G30's per-call reservations stand (PLAN 4.3; the
coordinator's ruling on the mechanism).

Until the release workstream retires the envelope admission, the old figures are
still enforced in code: `APPROVED_LIMIT_MICROS` and the v3 ledger checks in
`src/specimen_digitization/release_budget.py`, and the human-review scope digests
in `scripts/ci/mint_release_packet.py`. [`golive/RELEASE.md`](golive/RELEASE.md)
tracks their removal.
