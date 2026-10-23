# Monthly budget caps per organization and collection

The cost meter's second part (PR 2 of five). The owner approved the meter on
2026-10-20, as relayed by the coordinator session: "Yes, build the in-app tenant
cost meter (option A): per organization and collection totals, per-tenant budget
caps, shared Google costs split by usage, monthly check against the real bills."

This change builds the mechanism and the setting. Choosing a cap's value is the
owner's spending decision: this change sets no cap anywhere. It adds no
`TenantBudgetCap` row, as a seed, a bootstrap row or otherwise, and with no cap
set a paid step runs as before (below).

The code is `src/specimen_digitization/application/tenant_budget.py`; the
tests are `tests/test_tenant_budget.py`, `tests/test_tenant_budget_api.py`,
`tests/field_research/test_tenant_budget_headroom.py` and
`tests/field_research/test_tenant_budget_research_limits.py`.

## What a cap is

A `TenantBudgetCap` row (`dataconnect/schema/tenant_budget_cap.gql`), keyed by
the organization and a `collectionKey`: `organization` for the organization's
own cap, or the id of one of its collections. `monthlyCapMicros` is the cap in
micros of a US dollar for one UTC calendar month; null is no cap. `updatedBy`
and `updatedAt` say who set it last and when. The table has no foreign key, as
`research_harness.gql` keeps none for financial history; the connector's
membership checks keep every row inside its organization.

Two connector operations (`dataconnect/connector/tenant_budget.gql`), both
server only (`@auth(level: NO_ACCESS)`):

- `TenantBudgetCapsV1($organizationId, $collectionId, $actorUid)`: any active
  member of that collection reads the organization's caps and its collections'
  ids and parents. The worker reads it before each paid step.
- `SetTenantBudgetCapV1($organizationId, $collectionId, $collectionKey,
  $monthlyCapMicros, $actorUid)`: an active `admin` of `$collectionId` sets or
  clears one cap by a native upsert. The key must be `organization` or a
  collection of the organization, and the cap must not be negative.

## Which caps apply to a run

The organization's cap, the cap of the run's collection, and the cap of each
of that collection's ancestors (`Collection.parentId`). A sibling's cap does
not apply. When any cap is set, an answer that cannot say which apply blocks
the run as `tenant_budget_unavailable`: a collection tree with a cycle, a run
collection the tree does not hold, a malformed or duplicate row, or more than
1,000 rows.

## The monthly ledgers

Each applicable cap is enforced through its own ledger for the month, a
`worker_cursor` document with id
`uuid5(NAMESPACE_URL, "tenant-budget:{org}/{collectionKey}/{YYYY-MM}")`, kept
beside the program's ledger (scope: the organization and the run's
`program_ledger_collection`, or the run's own collection when it has none). The
first reservation of a month creates it at zero; two workers creating it at
once conflict and one retries on a fresh read.

A ledger has the program ledger's semantics (`lane_allowance.ProgramLedger`,
LANE.md T2b and T2c):

- A paid step reserves its worst case before the call, by compare-and-set,
  retried on a fresh read up to `lane_allowance.ATTEMPTS` (five) times.
- One entry per step attempt, keyed `[specimen, run, step, attempt]`: replaying
  a reservation or a settlement changes nothing, and a different amount for the
  same attempt is refused. So is a reservation of an entry already settled
  (`tenant_budget_unavailable`): replayed, it would hold nothing for a new
  call. An attempt whose hold was released (below) holds next under
  `[specimen, run, step, attempt, generation]`, the generation counting its
  released holds.
- A reservation the month's cap cannot cover is refused; one that fills the cap
  exactly is admitted.
- A step settles to what its calls cost once every call reported its usage, a
  billed amount, or was refused before any work (an HTTP 429 to its first
  request settles to zero). Unknown spend stays held in full. Spend above the
  reservation counts in full. Nothing is released except by a settlement to
  less; an attempt given up unsent settles its holds at zero (below).
- The cap is passed in at each reservation and is not part of an entry: a cap
  changed while an attempt is held never makes that hold unreadable.

## The month

The UTC calendar month of the attempt's first reservation. The run records it,
with the ledgers it reserved in and the amount, in
`run.dependencies["tenant_budget"]`
(`"<step>:<attempt>": {"month", "keys", "ledger_collection", "micros"}`, with
`"generation"` when it is not 0 and `"released": true` once the hold is
released). A run stored inline (under `active_graph.GRAPH_THRESHOLD`) comes
back from SQL Connect's Struct transport with `micros` and `generation` as
doubles; a whole double is read as that integer. Settlement reads that record,
never the clock or the caps: a step reserved in October and settled in
November settles October's ledger, and a cap removed or unreadable since does
not keep its hold. Like `ordinary_cost_settlements`, the record changes
`run.dependencies` after the append-once pipeline-run row may have been written
(HARNESS.md, #146); with no cap set nothing is recorded.

## The order at a paid step

1. The caps are read (`TenantBudgetCapsV1`; field research also reads them
   for its headroom, below). With none applicable, nothing else here happens:
   no ledger is read or written and the step goes on to the program's
   allowance as before.
2. Every applicable ledger, and the program's ledger when the run carries the
   allowance, is read. A step any of them would refuse is blocked holding
   nothing. When both a cap and the allowance would refuse, the cap's code is
   the one recorded.
3. Each applicable ledger reserves the step, and the run records the ones that
   hold it.
4. The program's allowance reserves as before (`lane_allowance.reserve_step`).

A refusal after step 2 (another worker took the room meanwhile) keeps the holds
already made. They are on the run's record, so the same attempt replays them
rather than reserving twice when it comes round again (a person's retry). It
reserves the recorded amount again (`tenant_budget.recorded_micros`), whatever
the step's reservation would be now: field research's would be smaller by the
attempt's own hold, and a different amount could never replay. Tested for field
research refused by the program's allowance and by a second cap, and for SAM 3
refused by the allowance.

A worker that holds and stops before the run is saved leaves the hold and no
record. In the same month, field research finds the hold on the ledger
(`tenant_budget.room`) and reserves that amount again; any other step reserves
its reservation as computed now, and an amount that differs from the hold
blocks the run as `tenant_budget_unavailable`, as the program's ledger does. In
a later UTC month the retry reserves on the new month's ledger, and the old
month keeps that hold, counted and never settled: an over-count, never an
under-count.

## An attempt given up unsent after its holds

A held attempt refused later in the chain may, on its retry, be given up
unsent: field research whose run limits other than money leave it no room
(below). The run proves that attempt was never sent: it records the attempt's
holds, and the attempt's number was never saved, while an attempt's number is
saved with its intent before any call (`tenant_budget.recorded_micros`). The
give-up marks the record `"released": true` (`tenant_budget.release_unsent`).
Once the run is saved with that mark, each ledger the record names settles the
attempt at zero, a known zero as for a call refused before any work
(`tenant_budget.settle_released`); settling again changes nothing. A save that
keeps another state (the active graph's limit, `save_recoverably`) settles
nothing, and a ledger that cannot be read or settled keeps the hold, an
over-count; so does a worker that stops between that save and the settlement,
since nothing settles a released record later.

These stay held as before: an attempt whose number was saved, a hold the run
has no record of (a worker that stopped before saving), a record that cannot
be read, a field research give-up that the step's rules turn into a block
(`FieldResearchStep.give_up` raising), and the first pass's and the
extraction's unsent give-ups, which release nothing.

A give-up does not advance the attempt's number, and field research can be
queued again on the same run (`requeue_completed_field_research`, for one).
That attempt's next reservation is a fresh hold under the next generation's
entry, so the released entry is never replayed for a call. Tested for field
research held, refused by the program's allowance, given up on retry, and
queued again.

## Failing closed

- Caps the connector refuses, or answers it cannot trust (above), block the run
  as `tenant_budget_unavailable` before any call.
- A ledger that cannot be read (another actor created it, or it names another
  tenant or month) or whose compare-and-set keeps losing blocks it as
  `tenant_budget_unavailable`.
- A reservation the month's cap cannot cover blocks it as
  `tenant_budget_exhausted`.
- A connector that cannot be reached at all is not read as no cap: the step
  stops before any reservation or call, as a program ledger read that cannot
  reach the connector does.
- A repository that cannot hold caps (the local SQLite store) has none.

Both codes block the run like the program's allowance does: `processing_blocked`,
with no disposition. The drain does not recover them on its own and the run is
not given up on; once an administrator raises the cap, a person's retry
queues the run again. The app names them "Monthly cost limit reached" and
"Monthly totals not readable" (`lib/src/blocker_words.dart`,
`lib/src/vocabulary.dart`).

## Field research

`FieldResearchStep.reservation` caps the step's headroom by the least any
applicable ledger has left this month, as it does by the program allowance's
remainder. When that is less than one expert request it keeps the headroom, so
the reservation blocks the record. An attempt that already holds (above)
reserves that amount instead. A retry whose run limits other than money
leave no room is given up on unsent unless a cap would refuse it, or cannot be
read: then the money block is kept, as for the allowance. The caps' answer
comes from `tenant_budget.admits`, by `reserve_step`'s own rule: an attempt that
already holds is checked in the month and the ledgers it holds in, and its
hold counts once, so it is given up (releasing that hold, above) rather than
blocked as `tenant_budget_exhausted` by its own hold.

The research broker of `SPECIMEN_RESEARCH_HARNESS=on`
(`research_harness/program_budget.py`, not used in production, which runs
`fields`) reserves on no monthly ledger, so it sends nothing while any cap
applies or the caps cannot be read: `HeldUnknown("tenant_budget_unavailable")`.

## A result lost after its call

A reading or first pass whose worker stopped after its call and before saving
it is settled by the next worker (`Workflow._settle_lost_reading`). With the
program's allowance, the program's ledger says what was settled, as before, and
the monthly ledgers are settled to the same amount. Without it, the monthly
ledgers the attempt reserved in say, when they all hold one settled amount;
otherwise the attempt stays held in full.

## Setting a cap

An active admin of any collection of the organization:

```
PUT /v1/organizations/{organization_id}/costs/caps
{"collection_id": null, "monthly_cap_micros": 5000000}
```

`collection_id` is null for the organization's cap or the id of one of its
collections; `monthly_cap_micros` is a whole number of micros from 0 to
2^53 - 1, or null to clear the cap. Both keys are required. The answer lists
every cap that is set:

```
{"organization_id": "...", "caps": [{"collection_id": null, "monthly_cap_micros": 5000000}]}
```

The route acts as the caller's first active admin membership in the
organization, by collection id. Any other member, or an admin row that is not
active, gets 403 `access_denied`; a body outside the contract, or a collection
that is not the organization's, gets 422 `invalid_input`; a deployment whose
store keeps no caps gets 503 `cost_meter_unavailable`. Caps whose answer
cannot be trusted (a malformed collection id, a value that is not a cap) get
503 with the message `tenant_budget_unavailable`. A read or a write the store
refuses (a `Conflict`, which is also how `SqlConnectRepository.tenant_caps`
reports an answer that is not a list or is too long) is checked against the
caller's memberships, read again: 403 `access_denied` when they no longer hold
an active admin row in that collection, otherwise 503 with the message
`tenant_budget_unavailable`. A cap applies from the next reservation.

## In the cost report

`GET /v1/organizations/{org}/costs` (COST_METER.md) fills `organization_cap`
and each collection's `cap` with the cap's position for the current UTC month,
whatever range was asked for: `{"monthly_cap_micros", "month", "spent_micros",
"remaining_micros"}`, null where no cap is set (`tenant_budget.report_caps`).
Spent is that month's paid-call cost entries, settled and held, and a
collection's counts every descendant's; the shared-cost allocation rows
(COST_METER.md, "Shared Google costs"), credits among them, are no run's
reservation and are left out. It can trail the worker's ledger by reservations in
flight, which the ledger holds before a cost entry exists. The caps are read
as the membership the PUT route acts as, the caller's first active admin
membership in the organization; when the range does not include the current
month, that month's totals are read once more, only if a cap is set.
`caps_status` is `"ok"`, or `"unavailable"` when the caps (or that month's
totals) cannot be read: the report is then returned whole with every cap null.

## Not in this change

- The report does not read the ledgers: they are creator-only worker
  documents the API cannot read, so a cap's position comes from the cost
  entries (above).
- No screen sets a cap; the app only names the two blockers.
- An organization's ledgers are shared across its collections through the
  run's `program_ledger_collection`, which `lane.queue` sets on every run the
  published allowance covers. A run without one keeps its ledgers in its own
  collection.
