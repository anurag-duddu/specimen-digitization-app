# Tenant cost meter

Authority: the owner's approval of 2026-10-20, relayed by the coordinator
session: "Yes, build the in-app tenant cost meter (option A): per organization
and collection totals, per-tenant budget caps, shared Google costs split by
usage, monthly check against the real bills."

The meter is built in five pull requests. This document describes what the
first one (the ledger of record) does; the last section lists what the others
add. The program allowance (G30) and its ledger are unchanged: the meter reads
what each run already records and never decides whether a call may be made.

## What the meter records

Every paid call a run makes is recorded on the run itself, in `run.paid_calls`
(`lane_costs._record`, and `field_research.step.record_cost` for field
research). The meter copies each of those entries into one `CostEntry` row
(`dataconnect/schema/cost_entry.gql`), in the run's own organization and
collection. `application/cost_ledger.py` builds the rows; it has no I/O.

| Row field | From the paid call |
|---|---|
| `source` | always `paid_call` in this change |
| `specimenId`, `runId` | the specimen and the run that made the call |
| `step`, `attempt` | the call's step and step attempt |
| `stage` | the step's stage, below |
| `kind` | `model`, `service` or `tool` |
| `ordinal` | the call's place among the run's calls with the same step, attempt and kind, in list order; 0 for nearly every call |
| `provider` | `huggingface` for a model route, `google_cloud` for the SAM 3 service, `tool` for a paid tool (neither the price list nor a registry names a tool's provider) |
| `resource` | the route id, the service (`sam3`) or the tool id |
| `usage` | the call's usage as recorded: numbers, booleans and nulls only. A call whose usage holds a string is refused with `cost_usage_not_numeric` and its run is not written |
| `reservedMicros` | the call's reservation |
| `costMicros` | the cost the meter counts (below) |
| `listCostMicros` | equal to `costMicros` for a paid call; shared Google costs will differ by the free allowance |
| `costBasis` | the call's basis: `computed`, `billed`, `reserved` or `refused` |
| `outcome`, `failureCode` | the call's outcome and failure code |
| `priceListVersion`, `priceListAsOf` | the price list the call was priced at |
| `occurredAt`, `month` | the call's `at`, in UTC, and its UTC month (`YYYY-MM`) |

Stages: `segment` is `label_finding`, `transcribe:*` is `reading`,
`first_pass:*` is `first_pass`, `parse` is `structuring`, `classify` is
`classification` and `field_research` is `field_research`. Any other step is
named by its prefix before the first `:`.

### Held and spent

`costMicros` is what the run's own accounting charges for the call:

- `computed` or `billed`: what the call cost.
- `refused`: zero. The provider refused the call before any work.
- `reserved`: the call's spend is unknown (a timeout, a 5xx, no usage
  reported), so its whole reservation is held, as the program ledger holds it.
  The API reports these sums as `held_micros` beside the totals they are part of.
- A call with no cost recorded counts at its reservation, with basis
  `reserved`; with no reservation either, at zero.

### Ids

A row's id is `projection.derived_id("cost", specimen_id, run_id, step,
attempt, kind, ordinal)`. The same call always derives the same id: a resent
save, the sweep, another process and a history-restored copy of the run
(`history_restore.restored_specimen` keeps the run's id and copies its calls)
all write the same row. The connector recomputes the id from the row's own
fields with `uuid_generate_v5` and refuses a row whose id does not match.

## How rows are written

### On every save

`SqlConnectRepository._commit`, after `write_projection`, and `_receipted`,
for a replayed save, call `write_costs(scope, specimen)`. It maps the active
run's paid calls to rows and sends, through `UpsertCostEntriesV1`, only the
rows this process has not sent as they now stand: it remembers each row's
digest for the last 256 specimens it saved. A call carries at most 200 rows.

`write_costs` never raises. The snapshot is the record of the run; a row the
pass could not write is repaired by the sweep. Its warning names a code (the
ledger's code for a call it cannot record, else the error's class) and never a
value. `UpsertCostEntriesV1`
is not one of `REPEATABLE_MUTATIONS`, so after a dropped connection it is not
sent again in the same pass; that set holds the saves whose receipt refuses a
committed repeat, and the upsert has no receipt. The next save or the sweep
sends the row again, which the upsert absorbs.

### The sweep

At the start of each collection's drain, under the collection's fence and
before any run is stepped, the worker runs `cost_sweep.sweep`. It reads pages
of ten specimens saved at or after its watermark (`ListRunPaidCallsV1`), takes
each run's paid calls and upserts that specimen's rows. Every run was the
active run of some revision, and paid calls stay inline in every snapshot's
run (`active_graph.run_summary` keeps them), so earlier and compacted runs are
covered too.

- The watermark is a `worker_cursor` document with id
  `uuid5(NAMESPACE_URL, "cost-meter-sweep:{organization}/{collection}")` and
  payload `{"sensitive": false, "swept_since", "after_id", "pass_started_at"}`,
  written by compare-and-set. The first sweep, with no document, reads every
  specimen.
- A sweep stops after 60 seconds, after 40 pages, at the drain window's close
  or at a stop signal, whichever comes first; a call already sent finishes
  first. The watermark is saved after the last page done in full, so the next
  sweep resumes there. A completed pass moves `swept_since` to the time that
  pass began, less one hour, because the connector stamps saves with its own
  clock.
- It fails open: a refused record or an unreadable run is logged and passed
  over, any other failure ends the sweep with a warning, and the drain goes on
  as it would have without it.
- `ListRunPaidCallsV1` lists only the records the caller may see, and the
  worker's membership is not allowed sensitive records, so the worker's sweep
  reads none. A sensitive record's rows come from saves made by members who
  may see it.

`POST /v1/organizations/{organization_id}/costs/refresh` starts the worker job
through the dispatcher the API uses for intake, so an administrator can bring
the meter up to date without waiting for the next request.

## The connector operations

All three are in `dataconnect/connector/cost_meter.gql`, at
`@auth(level: NO_ACCESS)`, with the caller's uid bound to `$actorUid`. Each
checks an active organization membership and then the collection membership
before anything else, and repeats those conditions inside its SQL.

| Operation | Variables | Who | What |
|---|---|---|---|
| `UpsertCostEntriesV1` | `organizationId`, `collectionId`, `specimenId`, `actorUid`, `rowsJson` | an active operator, reviewer, manager or admin of the collection, for a record they may see (`NOT sensitive OR canViewSensitive`) | Upserts one specimen's rows (1 to 500), keyed by (organization, collection, id), in one transaction. Any malformed row (an unknown kind or basis, a negative, fractional or 16-digit amount, another scope or specimen, an id that is not the row's derived id, a month that is not the time's UTC month) writes no row and the call is refused. A row whose values are unchanged keeps its `updatedAt` |
| `ListRunPaidCallsV1` | `organizationId`, `collectionId`, `actorUid`, `afterId`, `since`, `limit` (1 to 25) | any active member of the collection, for the records they may see | One page of specimens (id after `afterId`, saved at or after `since`, in id order): for each of their runs, its paid calls from the latest revision holding it, and the page's last id. Returned as JSON text |
| `CostTotalsV1` | `organizationId`, `actorUid`, `fromMonth`, `toMonth` | an active admin of any collection of the organization | The organization's collections (id, name, parent) and the sums of its rows in the month range, by collection, month, stage, source, kind, provider, resource and basis: cost, list cost, count and latest `updatedAt`. Sums are text, so no amount loses precision |

`scripts/data/cost-meter-test.mjs` runs all three against PostgreSQL and the
SQL Connect emulator (engine contract stage `sql.cost-meter`).

## The API

`GET /v1/organizations/{organization_id}/costs?from=YYYY-MM&to=YYYY-MM`

- The caller must be an active admin of a collection of the organization;
  anyone else gets 403 `access_denied`.
- `to` defaults to the current UTC month and `from` to `to`. A month that is not
  `YYYY-MM`, a range out of order or longer than 24 months is 422
  `invalid_input`.
- A repository without the cost meter (the synthetic and SQLite ones) is 503,
  `cost_meter_unavailable`. A cycle in the collection tree is 503,
  `cost_collection_tree_invalid`.

```json
{
  "organization_id": "uuid",
  "currency": "USD",
  "from_month": "2026-10", "to_month": "2026-10",
  "updated_at": "2026-10-20T15:04:05Z",
  "totals": {"cost_micros": 0, "held_micros": 0, "list_cost_micros": 0, "entries": 0},
  "organization_cap": null,
  "collections": [
    {"collection_id": "uuid", "name": "Insects", "parent_id": null,
     "own": {"cost_micros": 0, "held_micros": 0, "list_cost_micros": 0, "entries": 0},
     "total": {"cost_micros": 0, "held_micros": 0, "list_cost_micros": 0, "entries": 0},
     "cap": null}
  ],
  "months": [
    {"month": "2026-10", "totals": {"cost_micros": 0, "held_micros": 0, "list_cost_micros": 0, "entries": 0},
     "stages": [{"stage": "reading", "cost_micros": 0, "held_micros": 0, "list_cost_micros": 0, "entries": 0}]}
  ],
  "models": [
    {"month": "2026-10", "stage": "reading", "provider": "huggingface", "resource": "handwriting-qwen",
     "cost_micros": 0, "held_micros": 0, "list_cost_micros": 0, "entries": 0}
  ],
  "meter": null
}
```

- `collections` lists every collection of the organization, ordered by name.
  `own` is the collection's own rows; `total` adds every descendant over the
  `parentId` tree. A parent that is not a collection of the organization makes
  a root. Rows of a collection not listed still count, under a `null` name.
- `months` lists every month of the range, in order, with its stages that have
  rows. `models` sums the paid-call rows by month, stage, provider and
  resource.
- `updated_at` is the latest `updatedAt` of the rows in range, or `null`.
- `organization_cap`, each `cap` and `meter` are `null` until the changes
  below.

`POST /v1/organizations/{organization_id}/costs/refresh` takes no body,
answers `{"started": true}` when the worker job was started and
`{"started": false}` when it could not be (no worker job configured, or the
start failed). Same 403 rule.

## Telemetry

The "Process specimen checkpoint" span carries `organization_id` beside
`collection_id`. `observability.model_trace_context` carries the organization
and collection ids to the isolated model, classifier and SAM 3 children as
explicit keys (the W3C carrier still drops baggage), and
`isolated_model_span` sets them as `specimen.organization.id` and
`specimen.collection.id`. The metadata-only encoder (`bounded_telemetry`)
allows those identifiers. All of them are ids.

## What the later changes add

- PR 2: per-tenant monthly caps, in a settings table, enforced beside the
  program allowance's reservation; `organization_cap` and each `cap` become
  `{"monthly_cap_micros", "month", "spent_micros", "remaining_micros"}`, and
  `PUT .../costs/caps` sets them.
- PR 3: shared Google costs (the SAM 3 service's idle time, the worker, the
  API, storage and the database) split by usage into `allocation` rows, with
  the free allowance as credits; `meter` reports how far allocation has run.
- PR 4: a monthly check of the meter's totals against the real Hugging Face
  and Google bills.
- PR 5: the screen that shows it.
