# Tenant cost meter

Authority: the owner's approval of 2026-10-20, relayed by the coordinator
session: "Yes, build the in-app tenant cost meter (option A): per organization
and collection totals, per-tenant budget caps, shared Google costs split by
usage, monthly check against the real bills."

The meter is built in five pull requests. This document describes what the
first one (the ledger of record) and the third (shared Google costs, in
[Shared Google costs](#shared-google-costs)) do; the last section lists what
the others add. The program allowance (G30) and its ledger are unchanged: the
meter reads what each run already records and never decides whether a call may
be made. The owner's words of 2026-10-17 apply to the third: "remember I want
actual costs attributed properly".

## What the meter records

Every paid call a run makes is recorded on the run itself, in `run.paid_calls`
(`lane_costs._record`, and `field_research.step.record_cost` for field
research). The meter copies each of those entries into one `CostEntry` row
(`dataconnect/schema/cost_entry.gql`), in the run's own organization and
collection. `application/cost_ledger.py` builds the rows; it has no I/O.

| Row field | From the paid call |
|---|---|
| `source` | always `paid_call` for a paid call; `allocation` rows are described in [Shared Google costs](#shared-google-costs) |
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

The allocation's three are in `dataconnect/connector/cost_allocation.gql`,
under the same rules.

| Operation | Variables | Who | What |
|---|---|---|---|
| `CostAllocationInputsV1` | `organizationId`, `collectionId`, `actorUid`, `dayStart`, `dayEnd`, `monthStart`, `gapSeconds` (1 to 3,600) | an active operator, reviewer, manager or admin of the collection | For every collection of the deployment, all organizations: its saves (request receipts) in the day and in the month so far, the caller's processing seconds (the gap before each of its saves, at most `gapSeconds`, counted to the collection of the save that ends it), the SAM 3 request seconds and direct micro-USD of its paid-call rows, and at the day's end the bytes of its source assets and the specimens it holds. Ids and numbers only, as text; sensitive records count in them. A window out of shape (an end not after its start, a day longer than 26 hours, a start before `monthStart` or more than 31 days after it) answers `admitted: false` and no collection |
| `UpsertCostAllocationsV1` | `organizationId`, `collectionId`, `actorUid`, `rowsJson` | an active operator, reviewer, manager or admin of the collection | Upserts one collection's allocation rows (1 to 500) in one transaction. Any malformed row (another scope, a specimen or run, a step other than `allocation:<resource>`, an unknown stage or method, an id that is not the row's derived id, an `occurredAt` that is not its billing day's start in the zone its details name, a month that is not that time's UTC month, a negative amount other than a `sam-residual` or a `free-allowance` credit, a credit with a list cost, a cost that differs from its list cost outside a credit) writes no row and the call is refused. An unchanged row keeps its `updatedAt` |
| `CostAllocationStatusV1` | `organizationId`, `actorUid` | an active admin of any collection of the organization | The latest `occurredAt` of the organization's allocation rows, in UTC, or `null`, and their count |

`scripts/data/cost-allocation-test.mjs` runs them against PostgreSQL and the
emulator (engine contract stage `sql.cost-allocation`).

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
  "meter": {"allocated_through": "2026-10-19", "allocation_status": "ok"}
}
```

- Amounts are signed: a free-allowance credit, or a SAM 3 residual below the
  per-request charges, is negative (see [Shared Google costs](#shared-google-costs)).
  `cost_micros` sums are after Google's free allowance and `list_cost_micros`
  sums before it; `entries` is never negative.
- `collections` lists every collection of the organization, ordered by name.
  `own` is the collection's own rows; `total` adds every descendant over the
  `parentId` tree. A parent that is not a collection of the organization makes
  a root. Rows of a collection not listed still count, under a `null` name.
- `months` lists every month of the range, in order, with its stages that have
  rows. `models` sums the paid-call rows by month, stage, provider and
  resource.
- `updated_at` is the latest `updatedAt` of the rows in range, or `null`.
- `meter` is how far the shared costs are allocated for the organization,
  whatever the month range: `allocated_through` is the billing day (a
  `YYYY-MM-DD` day in America/Los_Angeles) of its latest allocation row, or
  `null`; `allocation_status` is `never_run` with no allocation row, `behind`
  when more than two complete billing days follow `allocated_through` (a day is
  complete three hours after it ends), else `ok`. It is read with
  `CostAllocationStatusV1` (the API cannot read the worker's cursors). An
  organization none of whose collections had a share on any allocated day, or
  whose collections no worker job serves, has no row, so it shows `never_run`.
  A repository without that read (the
  synthetic and SQLite ones) answers `null`; a failed read is 503
  `cost_meter_unavailable`.
- `organization_cap` and each `cap` are `null` until the change below.

`POST /v1/organizations/{organization_id}/costs/refresh` takes no body,
answers `{"started": true}` when the worker job was started and
`{"started": false}` when it could not be (no worker job configured, or the
start failed). Same 403 rule.

## Shared Google costs

Google bills some services for the whole deployment, not per call: the worker
job's machine, SAM 3's idle instance time, the API, the bucket and the
database. The worker splits each complete billing day's measured usage of them
across the collections into `allocation` rows (one per collection, service and
method) and writes Google's monthly free allowance as negative credit rows.
`application/cost_allocation.py` computes the rows (pure),
`cost_monitoring.py` reads Cloud Monitoring and `cost_allocator.py` runs the
pass.

### When it runs

- At the start of each collection's drain, right after the sweep, under the
  collection's fence and before any run is stepped
  (`DrainWorker._allocate_costs`). There is no scheduler: worker executions
  are started by intake and actions, by the drain's own continuation and by
  `POST .../costs/refresh`.
- A pass allocates the complete billing days after the collection's cursor,
  from 2026-10-01 on the first pass, at most 7 days. A day is complete three
  hours after it ends. A pass stops after 45 seconds or at the drain window's
  close, checked before each Cloud Monitoring page and each day, and at a stop
  signal, checked before the readings and each day; a read already sent
  finishes first (each read times out at 10 s).
- It reads Cloud Monitoring once per worker execution, for the invoice month
  so far (again only when a later collection needs an earlier start). For
  each day it reads the day's measures once per execution
  (`CostAllocationInputsV1`), computes every collection's rows, writes this
  collection's (`UpsertCostAllocationsV1`, at most 200 a call) and only then
  moves the cursor past the day.
- The cursor is a `worker_cursor` document with id
  `uuid5(NAMESPACE_URL, "cost-meter-allocation:{organization}/{collection}")`
  and payload `{"sensitive": false, "allocated_through": "YYYY-MM-DD"}`,
  written by compare-and-set.
- It fails open. Until the owner's setup below has run, the worker may not read
  Cloud Monitoring: the first read is refused (HTTP 401 or 403), the worker
  logs `cost allocation stopped: cost_allocation_monitoring_unavailable` once
  per execution, writes no row and leaves every cursor as it was. Any other
  failure (another HTTP status, an answer it cannot read, a refused write, a
  cursor changed meanwhile, a bucket location the price file does not name) is
  logged by its code; the cursor stays on the last day whose rows were all
  written, and the drain goes on as it would have.

### Billing days

- A billing day is a calendar day in America/Los_Angeles
  (`cost_allocation.BILLING_ZONE`): Google's billing reports start "A 24-hour
  time period" at midnight US Pacific time and follow daylight saving
  (docs.cloud.google.com/billing/docs/how-to/reports). A day has 23, 24 or 25
  hours; every reading is hourly (an alignment period of 3,600 s), so a day is
  its own hours.
- A row's `occurredAt` is the day's start in UTC (07:00 or 08:00), so its UTC
  `month` is the Pacific invoice month. Its `allocationMethodDetails` records
  the day, the zone, its UTC start, end and hours; the worker, SAM 3, API and
  storage rows also record the day's hourly readings, and a credit row the
  pool's state.
- Not confirmed: an earlier reading of the billing console took the day as
  05:00Z to 05:00Z. The monthly check (PR 4) confirms the boundary from the
  bills.

### Rates

From `application/profiles/infrastructure_prices.json` (version
`infrastructure-prices-2026-10-20`, as of 2026-10-20, us-east4, Cloud Run
Tier 1, read from the official pages on 2026-10-20), in micro-USD; every row
carries the version as `priceListVersion` and `priceListAsOf`. The profile's
price list (`profiles/published.json`) is not used.

| Item | Rate | Source |
|---|---|---|
| Cloud Run instance-based (SAM 3 and every job) | 18 per vCPU-second, 2 per GiB-second | cloud.google.com/run/pricing |
| Cloud Run request-based (the API) | 24 per vCPU-second, 2.5 per GiB-second, 0.4 per request | cloud.google.com/run/pricing |
| Cloud Run free tier, per month | instance-based 240,000 vCPU-s and 450,000 GiB-s; request-based 180,000 vCPU-s, 360,000 GiB-s and 2,000,000 requests | cloud.google.com/run/pricing |
| Cloud Storage, Standard | 23,000 per GiB-month in us-east4, 26,000 in the US multi-region; a month is 730 hours | cloud.google.com/storage/pricing |
| Cloud SQL, db-f1-micro in us-east4 | 11,200 per hour, plus 10 GiB of SSD at 181,900 per GiB-month | cloud.google.com/sql/pricing; firebase.google.com/docs/sql-connect/pricing |

The shapes are the deployed ones (`scripts/ci/runtime_settings.py`, and a test
holds the price file to them): SAM 3 4 vCPU and 16 GiB, the API 1 and 1, every
worker job 1 and 1.

### Methods

Each row names its method in `allocationMethodId`. A service's day total is
rounded to a whole micro-USD, half to even; the collections' parts add up to
it exactly (each takes its floor, then the largest remainders one more, ties by
organization and collection id). A collection whose part is zero gets no row.

1. `worker-processing-time` (resource: the job, such as `specimen-worker`;
   stage `worker`). The job's billable seconds that day
   (`run.googleapis.com/container/billable_instance_time` of its
   `cloud_run_job`) x (1 x 18 + 1 x 2), split by each collection's processing
   seconds that day: the gaps between consecutive saves (request receipts) of
   the job's worker actor, each at most 900 s (the longest step lease a profile
   may set), each counted to the collection of the save that ends it; a save
   with no earlier save within 900 s counts 900. With no such save that day,
   by the month's so far; with none this month, evenly over the collections
   the job serves. Each job's drains write its rows; one worker actor per job
   is assumed.
2. `sam-residual` (resource `specimen-sam`, stage `label_finding`). SAM 3's
   billable seconds that day x (4 x 18 + 16 x 2), less the day's direct SAM 3
   charges already in the ledger (the paid-call rows of resource `sam3` whose
   `occurredAt` is in the day, every basis, every collection), split by each
   collection's SAM 3 request seconds that day (paid-call
   `usage.instance.request_seconds`, else `usage.seconds`); else the month's;
   else evenly over every collection. When the per-request charges came to
   more than the measured time the residual is negative and is written as it
   is. `billable_instance_time` counts time, so the startup CPU boost's extra
   vCPU is not in the measure (the per-request charges include it).
3. `api-requests` (resource `specimen-api`, stage `api`). The API's billable
   seconds x (24 + 2.5) + its requests (`run.googleapis.com/request_count`,
   every response code) x 0.4, split across organizations by the log-based
   metric's requests that day (an organization with no collection is left
   out); with no request counted, by each organization's saves that day, else
   the month's, else evenly. Within an organization, by each collection's saves
   that day, else the month's, else evenly over its collections.
4. `storage-bytes` (resource: the bucket; stage `storage`). The bucket's mean
   bytes over the day's hours (`storage.googleapis.com/storage/v2/total_bytes`,
   every class and type, soft-deleted objects included, which are billed; the
   v1 `total_bytes` when v2 has no series; an hour without a reading holds the
   last earlier one, read from a day before the month) / 2^30 x the bucket
   location's Standard rate x the day's hours / 730, split by the bytes of each
   collection's source assets created before the day's end; else evenly. A
   location the price file does not name stops the day with
   `cost_allocation_storage_location_unpriced` until the price file names it.
5. `database-specimens` (resource `cloud-sql`, stage `database`). The day's
   hours x (11,200 + 10 x 181,900 / 730), split by the specimens each
   collection created before the day's end; else evenly over every collection. A
   Data Connect no-cost trial may make the bill zero; the monthly check
   compares.
6. `free-allowance` (the service's resource and stage; `listCostMicros` 0,
   `costMicros` zero or negative). Cloud Run's monthly free tier, drawn day by
   day from the Pacific invoice month's first day by this project's usage: the
   instance-based pool by SAM 3 (4 vCPU-s and 16 GiB-s a second) and every
   Cloud Run job (1 and 1), the request-based pool by the API (1, 1 and its
   requests). A day that would overdraw a pool takes what is left, shared by the
   services in proportion to what each drew that day. A service's credit is
   the units it consumed at the pool's rates (Google applies the free tier as a
   spending-based discount at Tier 1 prices), split across the collections as
   the service's own cost was that day. So `costMicros` sums are after the
   allowance and `listCostMicros` sums before it.

The same readings and measures always give the same rows, so another
collection's worker writes the same values for its own rows. A collection no
worker job serves gets no rows; its share is in no total.

Rows: `source` and `kind` `allocation`, `costBasis` `allocated`, `provider`
`google_cloud`, `step` `allocation:<resource>`, `attempt` 1, `ordinal` 0, no
specimen or run; `usage` is the collection's measure (for example
`{"processing_seconds": 412.5}`); `allocationMethodDetails` holds the day,
zone and window, the share (measure, basis `day`, `month` or `even`,
numerator, denominator) and the day's allocated (for a credit, credited)
micro-USD; a cost row also
its rates and list micro-USD (and, but for the database, its hourly
readings), a credit row the pool's state. The id is
`projection.derived_id("cost-allocation", billing_day, resource,
collection_id, method)`.

### Reading Cloud Monitoring

`cost_monitoring.read_usage` calls `projects.timeSeries.list` through
`google.auth.default` and an `AuthorizedSession`, scope `monitoring.read`, with
`aggregation.alignmentPeriod=3600s` and a per-series aligner (`ALIGN_SUM` for
the counters, `ALIGN_MEAN` for the storage gauge) and no cross-series reducer:
Python sums the series by service, job, organization and hour. It reads
billable instance time of the `cloud_run_revision` series of `specimen-sam` and
`specimen-api` and of every `cloud_run_job`, the API's `request_count`,
`logging.googleapis.com/user/specimen_api_requests_by_organization` by its
`organization_id` label, and the bucket's total bytes with its `location`
resource label. It follows `nextPageToken` (at most 20 pages a read). A 404 is
a metric with no data; 401 and 403 are `cost_allocation_monitoring_unavailable`.

### The owner's setup step

`bash scripts/ops/owner_setup.sh --cost-meter-only` (add `--dry-run` to see
it first). It needs a project Owner signed in to `gcloud`, not `gh`, and
starts nothing. It:

- creates or reconciles the custom role `specimenCostMeterRead`, with the one
  permission `monitoring.timeSeries.list`, and binds it on the project to
  `specimen-worker-runtime`;
- creates (or sets back) the user-defined counter log-based metric
  `specimen_api_requests_by_organization` over `specimen-api`'s request logs
  (`log_id("run.googleapis.com/requests")`, URLs containing
  `/v1/organizations/`), with the label `organization_id` from
  `REGEXP_EXTRACT(httpRequest.requestUrl, "/v1/organizations/([0-9a-fA-F-]{36})/")`.

The full owner setup keeps both. A log-based metric counts only log entries
received after it exists, so for earlier days the API is split by saves.
User-defined log-based metrics are chargeable Cloud Monitoring custom metrics
(8 bytes a point); Monitoring reads cost USD 0.50 per million series returned
after the first million a month.

### Who sees what

`CostAllocationInputsV1` gives server code calling as an active operator or
above of any one collection the aggregate numbers of every collection of the
deployment (saves, seconds, bytes, specimen counts, SAM 3 micro-USD): the
platform worker sees other tenants' aggregate numbers, never a record id or
content. Each collection's rows are written only by a member who may write it.
An administrator reads only their organization's rows (`CostTotalsV1`,
`CostAllocationStatusV1`).

### Not confirmed

- That a custom role with only `monitoring.timeSeries.list` suffices for the
  reads; that `gcloud logging metrics describe` reports a missing metric with
  `NOT_FOUND`, and `update --config-from-file` behaves as `create` does.
- The query strings against the live API (the tests answer from fixtures in
  the documented response shape); the monitored resource a log-based metric's
  series carry.
- Whether Cloud Run jobs share one free-tier pool with instance-based services;
  whether `billable_instance_time` includes the 1-minute minimum of jobs; that
  the free tier is drawn chronologically; this project is assumed to be the
  only one on its billing account.
- The bucket's storage class and location (read from the series' label at run
  time); that the database is the db-f1-micro equivalent, and how a Data
  Connect trial appears on the bill.
- The Pacific day boundary (above); late paid-call rows after a day was
  allocated are not reallocated.
- The intake job (`specimen-intake`) draws on the instance-based pool but its
  own cost is not allocated.

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
- PR 3 (above): shared Google costs (the SAM 3 service's idle time, the
  worker, the API, storage and the database) split by usage into `allocation`
  rows, with the free allowance as credits; `meter` reports how far allocation
  has run.
- PR 4: a monthly check of the meter's totals against the real Hugging Face
  and Google bills.
- PR 5: the screen that shows it.
