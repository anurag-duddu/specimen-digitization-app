# Processing lane: specification deltas

Owner: go-live workstream S3, session "Build the on-demand processing lane".
Authority: [`PLAN.md`](PLAN.md) section 2 (owner decisions G1 to G18) and the
existing specification it cites. Each topic below is added by its own pull
request, before the code that implements it, and changes nothing outside what
it names.

## Topics and order

The coordinator approved this order on 2026-09-23: T1 (two pull requests, T1a
and T1b), then T4, T3, T2 and T5. T4 and T3 come before T2 because the
acceptance lab needs the published pilot profile and SAM 3's lab mode to run
real models end to end (issue #79). Production needs all five.

## How the lane applies G13 and G14

| ID | Consequence for the lane |
|---|---|
| G13 | A request is never refused because another specimen of the collection is processing. It waits as `pending`, and the worker, not the API, enforces one active run per collection (T2) |
| G14 | No classification stage and no classifier call in the lane. A request records the existing `ManualSelection` for the intake collection, as synthetic mode already does (`workflow.py` 316-321); a reviewer can still correct it with `POST /specimens/{id}/classification` |

## T1. On-demand trigger and source import in production

Implements G2 and G13, and the selection half of G14. Budget enforcement across
runs, the worker's drain and the one-active-run fence are T2.

### Run states

One stage is added before a run's first step. Everything after the first step is
unchanged, and every status stays one of the run states of `CONTRACTS.md` 209.

| Stage | Status on the wire (`summary().status`, SQL `state`) | Due for the worker | Meaning |
|---|---|---|---|
| `pending` | `pending` | yes, from `queued_at` | Processing was requested and the run waits its turn (G13). The connector's due-work query already treats `pending` as due |

`Run.queued_at` records when the run was requested. The worker takes pending
runs in `queued_at` order (T2), which is "the order requested" of G13. The field
is omitted from a run that was never queued, so older snapshots serialize as
before.

Synthetic mode is unchanged. Its runs are never queued, and synthetic intake
still drains in the request's background task.

### Requesting processing

A request moves a run to `pending`. In the same write it sets the run's budget
from the collection's allowance, records the G14 intake selection, and sets
`queued_at`. After the write commits, the API asks the worker plane to start (see
"Starting the worker").

Processing starts on intake and on request (PLAN 4.1 row 1, G2). Outside
synthetic mode, five things make a request:

1. Upload completion. Every accepted upload becomes a processing job (`PRD.md`
   9.1 step 6), and the uploader is the requesting actor. A duplicate upload
   requests nothing.
2. Import from a source. Adding a source photograph to the queue is intake, so
   each specimen an import creates is queued the same way, and the worker is
   started once per import. This supersedes, for this program, the rule that an
   import dispatches nothing (`CONTRACTS.md` 654-662), which rested on the budget
   G9 has since set.
3. `POST /specimens/{specimen_id}/process`, with an `Idempotency-Key`. It keeps
   the endpoint's existing authorization: any member who can see the specimen.
   The response is `202` with the specimen summary plus `dispatch` (see below).
   Synthetic mode keeps its existing behaviour: it drains the specimen inside the
   request and returns the workspace.
4. The run actions `retry`, `resume` and `reprocess` (`POST /runs/{id}/actions`).
   Their checks are unchanged. The run they leave behind (the same run for
   `retry` and `resume`, a new one for `reprocess`) is made `pending` in the same
   write, and the worker is started.
5. The reviewer corrections that start a new run, `POST /specimens/{id}/regions`
   and `POST /specimens/{id}/classification`, the same way. A decision that
   leaves the run due starts the worker without changing the run.

The lane never processes a record marked sensitive. Sensitive information is
not sent to an unapproved provider (`PRD.md` section 3, principle 9), and the
worker's membership cannot see sensitive records anyway. Intake creates such a
record `processing_blocked` with the blocker `sensitive_record_not_processed` and
starts no worker. A process request or a run action on it is refused with `409`
and that code. A stored record's sensitivity cannot be lowered, so the image is
processed by uploading or importing it into a batch declared non-sensitive.

If intake cannot queue a specimen because its collection has no resolvable
allowance, the specimen is still created. It is created `processing_blocked`
with the blocker `collection_processing_unconfigured`, and a `retry` queues it
once the allowance is published. A request that cannot queue a run is refused
with `409` `collection_processing_unconfigured`, and nothing is written.

What `POST /specimens/{id}/process` does depends on the current run:

| Current run | Result |
|---|---|
| `pending`, or started and still due (any processing stage) | unchanged; `202`; worker started again. This is how a request whose start failed is retried |
| never requested (`ingested`, created before this change) | becomes `pending`; `202`; worker started |
| `processing_blocked`, `retry_scheduled`, `paused`, `cancelled` | `409` `run_action_required`; the run actions own these transitions |
| finished (`finalized`, a disposition is set) | `409` `run_action_required`; `reprocess` starts a new run |
| an evidence-pilot run | `409`, as today |

### The collection's allowance

`CollectionProfile` gains an optional `processing` allowance with two fields:

- `run_cost_limit_micros`, the budget of one run.
- `stage_cost_micros`, the existing `StageCostReservations`: per-stage
  reservations supplied by the owner, not provider prices.

A request copies both into the run's `profile.execution` as
`approved_cost_limit_micros` and `stage_cost_reservations`. The existing workflow
checks enforce them per paid step (`workflow.py` 191-231), and classification
carries `execution` forward unchanged (`collection_runtime.py` 108). A profile
without `processing` serializes and hashes exactly as before.

The allowance comes from the profile the run will use. That is the collection a
reviewer selected, if one did; otherwise it is the intake collection (G14),
found by `CollectionProfileRegistry.resolve`. T4 adds resolution down the
collection tree and publishes the slide pilot's profile. Until then, a production
request fails closed with `collection_processing_unconfigured`, because the only
production profile is a draft (`collection_profiles.py` 227-276).

### Starting the worker

The API starts one execution of the Cloud Run job named by `SPECIMEN_WORKER_JOB`
(`projects/<project>/locations/<region>/jobs/<job>`). It calls the Cloud Run Admin
API v2 `jobs:run` method with no overrides, authenticated as the API's runtime
identity. It does not wait for the execution or read its status; SQL is the only
record of work.

The outcome is reported as `dispatch.status`:

- `requested`: the platform accepted the run.
- `failed`: the call failed. `dispatch.reason` names only the HTTP status or
  the error class. The run stays `pending`, and a later request, or any worker
  that drains the collection, picks it up.
- `unconfigured`: no job is configured. This is local modes, and production
  before the release plane sets the variable.

Starting more than one execution is harmless by design. A worker that finds
another run of the collection in progress exits and leaves the queue to the
worker already draining it (T2).

### Source import in production

`production_app` passes a `SourceRegistry` read from `SPECIMEN_SOURCE_REGISTRY_JSON`
and a `GcsSourceReader` to `create_app`. The value is a JSON list of registered
sources, in the existing `RegisteredSource` shape. An absent value or `[]` means
no sources, which is today's behaviour. An invalid value stops the API at start.
The release plane injects the value from Secret Manager, because it names private
collection identifiers. The routes, their roles and the integrity rules are
unchanged (`CONTRACTS.md` 482-685).

Both new API variables fail closed at start, in `RuntimeConfig`:

- `SPECIMEN_WORKER_JOB` must name a job in the configured project.
- Every source must be a valid `RegisteredSource` with no extra keys, in the
  approved bucket (`SPECIMEN_GCS_BUCKET`), and registered once.

A first capture of `microscopic-slides/` digests about 1,000 objects and took
256 s when measured (`SESSION_LEARNINGS.md`, 2026-09-14 entry). Until capture moves
to the worker plane, `CONTRACTS.md` 540-547 makes it an operator call with a long
deadline, so the API's request timeout is 600 s.

### Tests

- Requesting processing, for each row of the table above, in `emulator` mode with
  a fake dispatcher: the budget and the selection written in one save, the due
  rule, and re-requests that write nothing.
- Upload completion and source import with and without an allowance. Run
  actions leave the run `pending` and start the worker.
- The dispatcher's request shape, and its `failed` and `unconfigured` outcomes.
- Runtime configuration parsing for both new variables, and the production
  wiring of the registry, reader and dispatcher.
- Synthetic-mode tests stay green unchanged.
