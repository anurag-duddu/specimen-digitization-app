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

## T4. The slide pilot profile as configuration

Implements PLAN 4.2 with G8, G14, G16, G22, G24 and G29, and fixes issue #79.

### The published registry

The published collection profiles are one committed configuration file,
`src/specimen_digitization/application/profiles/published.json`, loaded at start
by the API and the worker. It holds:

- the collection tree: the public keys, names and parents of
  `infra/reference/fieldmuseum-collection-tree.json` (a test keeps the two equal);
- the published profiles;
- one mapping per collection that has its own profile.

Changing a profile, including its field groups (G8), is one edit to this file.
The edit adds a new profile version and moves the mapping to it; a published
version is never replaced (`collection_profiles.py` 182-185).
`insects_registry()` and `application_registry()` keep today's draft and
synthetic registries for the existing tests and for synthetic mode.

### Resolution down the collection tree

A collection with no mapping of its own uses the mapping of its nearest ancestor
that has one, as `COLLECTION_HIERARCHY.md` describes. Resolution walks the parent
chain up to the root. A collection with no mapped ancestor, an ambiguous mapping
or an inactive profile resolves to review with the existing reasons.

### Private collection identifiers

SQL collection identifiers are minted privately (`COLLECTION_HIERARCHY.md`,
"The pilot's scope"), so the committed file names collections by key.
`SPECIMEN_COLLECTION_BINDINGS_JSON` is a JSON object from collection identifier
to key, set on the API and the worker; the release plane injects it from Secret
Manager. Resolution translates an identifier through the bindings, and a key
resolves as itself (the reviewer's correction route and the tests pass keys).

Bindings never appear in the registry's serialized form, in `GET /collections`
or in a run. A binding to an unknown key, or a value that is not a JSON object,
stops the process at start.

### The risk policy

The profile references the existing uncalibrated policy: the `RiskPolicy`
defaults (`review_risk.py` 125-147), id `review-risk-draft`, version
`review-risk-draft-1`, with no calibration dataset. The production risk registry
publishes it. Its scores stay labelled `calibrated: false` and carry no
clearance authority (`review_risk.py` 165, 329-331).

### The slide pilot profile

| Setting | Value | Source |
|---|---|---|
| Identity | `zoology_insects_slides` version `1.0.0`, state `active`, mapped to `insects` beneath `zoology` | brief T4 |
| Readers | `handwriting-qwen`, `handwriting-muse` | PLAN 2.2 |
| Segmentation | `sam3-settings-v1`, concept prompt `label`, the pinned revision; the server's 0.5 thresholds and 64-region limit | brief T4. T3 makes the thresholds explicit, together with G15's values |
| Mandatory fields | the 19 keys of `MANDATORY` other than `identified_by_irn`, the four elevations included | G8, G16, G22 |
| Optional fields | `identified_by_irn` | G16 |
| Tools per field | `taxon`: `taxonomy_verifier`. `country`, `province_state`, `county`, `city`, `precise_location`: `geography_lookup`. `fmnh_ins_number`: `catalog_number_validator`. The three dates: `date_parser`. Every other field: none (transcribed as seen). `tools` is their union | PLAN 4.2; S4 owns the tools |
| Risk policy | the existing uncalibrated policy, above | brief T4 |
| Clearance policy | `insects-clearance-v1`. S4's G1 change moves it to v2 with a new profile version | S4 |
| Allowance | `run_cost_limit_micros` 500,000 (USD 0.50). Reservations: `segment` 45,000; each reader 20,000; `parse` 20,000. Each bounds its step's worst case (T2). `max_tokens` 480,000; `max_external_calls` 96. Provisional; the owner's USD 25 ceiling (G9) bounds them all | T1, G9 |
| Routes for the first pass and the harness | `first_pass_route` and `harness_route` fields exist, unset until S4's routes are approved | S4 |
| Date rules | `date-rules-v1`: a two-digit year reads as 19xx (`two_digit_year_century` 1900), and a Roman numeral I to XII in the month position is that month (`roman_numeral_months`). S4's date parser stamps each rule, its version and the profile on every parsed date that uses it, so the reading stays visibly derived (`CONTRACTS.md` 234-235) | G24, G29 |

`max_tokens` and `max_external_calls` join the allowance because the defaults
(160,000 tokens, 32 weighted calls) admit only ten billable steps per run. A
three-label slide already uses eight, before S4's first pass and harness steps.
A request copies them into the run's `profile.execution` with the cost fields.
The institutional-approval and semantics flags stay false; the G1 policy change
(S4) owns those gates.

### Optional fields at run time

When classify binds the profile, the run gets a `FieldValue` for every mandatory
and optional key. `Run.field_groups` maps each key to `mandatory` or `optional`,
which is S5's shape. S4's `parse` extracts both groups, and only mandatory fields
gate clearance. Synthetic profiles have no optional fields, so their runs are
unchanged. A regions correction starts a run that does not classify again, so it
carries the bound profile's field groups, with every field reset.

### Wiring

`production_app` passes the published registry with the bindings, and the
production risk registry, to `create_app`. The worker gets the same in T2.

The acceptance lab runs `mode="emulator"` with `ProductionAdapters`, the same two
registries and a binding for its local collection. Its runs are then
non-synthetic, which is what #79 needs: a real reader's input is its region crop,
the reading provenance a non-synthetic run requires (`integrity.py` 107-112).

### Tests

- The published file loads, its tree equals the reviewed tree, and the pilot
  profile has every value in the table.
- Resolution through bindings and down the tree, and the refusals.
- The risk reference resolves in the production risk registry.
- Classify gives the run every mandatory and optional field with its group.
- The bindings variable parses and fails closed, and `production_app` passes
  both registries.
- An emulator-mode run with production-like readers, queued on upload and
  drained, passes `parse` (the failure of #79).

## T3. SAM 3 per run, lab mode and the label-coverage check

Implements PLAN 4.1 row 2 with G6, G15 and the acceptance lab's requirements. It
lands as two pull requests: T3a (serving per run, failures, lab mode) and T3b
(parameters in the profile, recorded detections, G15).

### Serving each run (T3a)

The SAM 3 service gains a per-run mode, `SPECIMEN_SAM3_ENABLE=authorized-run`,
beside the frozen pilot's manifest mode, which is unchanged.

- **Authorization.** In per-run mode the service serves any well-formed request
  from its authenticated caller: the worker's Google identity token in
  production, loopback in the lab. The worker authorizes a run by reserving the
  segment step's cost within the run's budget before it calls. There is no
  manifest, budget-authorization variable or launch window.
- **Source integrity.** Unchanged. The request names the application copy
  (`blob_ref`, `sha256`, size), and the service reads exactly that generation
  and refuses bytes whose digest differs.
- **One inference per run.** A create-only claim at
  `application/sha256/sam3-runs/{run_id}/claim.json` holds the request digest,
  with the response stored beside it. A repeated request with the same digest
  returns the stored response without running the model again.
  - A claim with no response, older than the service's hard deadline, belongs to
    an attempt that died with its process, and the next attempt takes it over.
  - A younger claim answers `409 sam3_busy`, which is retryable.
- **Lifetime.** No self-shutdown. The service scales to zero between runs.
- **Pins.** Unchanged: the pinned revision, the offline checkpoint and its
  digest, and no Hugging Face token.
- **Response binding.** The worker checks the response against its own request
  and pins: the model and revision, the request digest, the source, the
  checkpoint digest it pinned for the run, and region and mask provenance. Region
  ids derive from the run id and the region's index.

### Failures (T3a, G6)

A timeout, `429`, `409 sam3_busy` or `5xx` from the service is a retryable
failure on the existing retry schedule (`workflow.py` `schedule_retry`); once
the attempts are spent, it is an operational block. The per-run claim makes the
retry safe: a finished inference is returned, not repeated. A failure of the
service is never a coverage verdict. A response that fails its provenance check
blocks the run, as today.

### Lab mode (T3a, acceptance lab)

- **Switch.** `SPECIMEN_SAM3_ENABLE=lab`. The service refuses it when `K_SERVICE`
  is set or `APP_ENV=production`.
- **Callers.** Instead of an identity token, the service accepts a shared lab
  secret, `SPECIMEN_SAM3_LAB_TOKEN` (at least 32 characters, compared in constant
  time), set on both the service and the worker. The lab runs the image in
  Docker, where a loopback check cannot work: the caller appears as Docker's
  gateway. The runner publishes the port on host loopback only
  (`-p 127.0.0.1:<port>:8080`), which bounds exposure.
- **Storage.** Objects live in a local directory, `SPECIMEN_SAM3_LAB_DIR`, laid
  out as the application's `LocalBlobs` so the worker's finalize integrity check
  can read the masks. The source is read from it, and masks, claims and
  responses are written to it. References are the bare digests `LocalBlobs` uses.
- **Worker side.** `SPECIMEN_SAM3_ENDPOINT=http://127.0.0.1:<port>` is accepted
  only when `SPECIMEN_SAM3_LAB=true` and `APP_ENV` is not production. The worker
  then sends the lab secret instead of fetching an identity token.
- **Checkpoint digest.** The image's entrypoint with `--checkpoint-digest`
  (`python -m specimen_digitization.application.sam3_server --checkpoint-digest`)
  prints the digest of the local offline checkpoint without loading the model,
  so the lab gives the service and the worker the same
  `SPECIMEN_SAM3_CHECKPOINT_SHA256`.
- **Everything else** is the per-run path above: authorization, claims and no
  shutdown.

### Parameters and recorded detections (T3b)

The pilot profile's segmentation settings pin the values the service applies:

- label threshold 0.5 and mask threshold 0.5;
- a recording floor of 0.1;
- at most 64 detections per concept;
- the cross-check concept `text`.

Settings without these values keep today's bytes and digests.

The service runs the label concept and the cross-check concept on the same
decoded original. For each concept it returns every detection at or above the
floor, the 64 highest-scoring, each with box and score, and it returns the
parameters it applied. It stores masks only for label detections at or above the
label threshold. Those become the regions, as today.

Settings without these values keep the service's previous contract: a 0.5 label
threshold that is also the floor, 64 detections and no cross-check. In per-run
mode, no label detection at or above the threshold is an empty result, not a
service error; the coverage check then fails it.

The worker checks that the response applied exactly the requested parameters,
that every detection lies inside the image at or above the floor, and that the
regions are the label detections at or above the threshold, in order.

The worker keeps the whole response as the segmentation evidence, so the lab can
sweep thresholds offline. `Run.segmentation` summarises it: concept, thresholds,
floor, revision, checkpoint digest, region count and per-region scores.

### Label-coverage check (T3b, G15)

The segment step checks the result. All three rules must hold for
`run.coverage_confirmed`:

1. Geometry: the existing `check_regions` (`image_quality.py` 213-251). At least
   one label region, and none out of bounds. Overlap is recorded, not failed.
2. Region count: after merging label regions that overlap at IoU of 0.9 or more,
   between 1 and 3 regions.
3. Full-image cross-check: every cross-check detection scoring 0.5 or more lies
   at least 50% inside the union of the label regions. A detection outside is
   recorded, with its box, as a possible missed label.

The values are the coordinator's approved starting values, pinned in the
profile. The owner signs off the final values after the lab measures them on the
ten. Changing a value is one profile edit.

A failed check sets `coverage_confirmed` false with the reason
`label_coverage_unconfirmed`. The run still goes through every stage, and the
policy gate (`policy.py` 35-36) sends it to needs human review.

`Run.coverage_check` records the evidence in S5's shape:

- `version` `coverage-check-v1`;
- `outcome`, `region_count` with the rule's `min_label_regions` and
  `max_label_regions`, `cross_check` and `reason_codes`;
- `evidence_ref` and `evidence_sha256`, the segmentation response;
- `checked_at`.

### Production shape (S2)

- **Environment.**
  - Unchanged: `SPECIMEN_SAM3_ENABLE` (value `authorized-run`),
    `SPECIMEN_SAM3_AUDIENCE`, `SPECIMEN_SAM3_CALLER_EMAIL`,
    `SPECIMEN_SAM3_OUTPUT_BUCKET` (the application bucket),
    `SPECIMEN_SAM3_CHECKPOINT_SHA256` and `HF_HUB_OFFLINE=1`.
  - Retired for per-run mode: `SPECIMEN_SAM3_BUDGET_AUTHORIZATION`,
    `SPECIMEN_PILOT_MANIFEST_*`, `SPECIMEN_SAM3_EXPIRES_UNIX` and the manifest
    volume.
- **Worker.** Adds `SPECIMEN_SAM3_CHECKPOINT_SHA256`, so it can pin the
  checkpoint it expects.
- **Storage.** The service's identity reads and creates objects under
  `application/sha256/` in the application bucket.
- **Timing.** Two concepts on one image cost about twice the single-concept
  time, measured at about 25 s on a workstation CPU. The service's hard deadline
  becomes 240 s and the request timeout 300 s. The pilot's allowance sets the
  worker's external-call timeout to 270 s with a 300 s lease, and keeps readers
  at 120 s. The allowance refuses timeouts that do not fit the lease.

## T2. The worker drains the queue, within the budget

Implements PLAN 4.3 and 4.6 (the worker's part) with G2, G6, G9 and G13. The
coordinator approved the mechanism and the cost basis on 2026-09-23, and the
owner set the model allowance (G30).

### Drain mode

`specimen-worker --mode production --drain` runs the lane's worker. The frozen
pilot's worker is unchanged and still needs its launch files.

- **Command.** `--max-seconds` is the job's task deadline: 3600 by default, more
  than 600 and at most 3600. The command refuses `--once` and the pilot's inputs
  (`--launch-policy`, `--source-manifest`, `--evidence-only`,
  `--evidence-profile`, `--materialize-config`). `--check-config` checks the
  settings and exits.
- **Process.** The drain runs in the job's own process, not under the pilot's
  supervisor. The supervisor hard-stops its worker group on `SIGTERM`, which
  would leave the fence held until its lease expired. Each external call keeps
  its own bounded effect and deadline.
- **Settings.** No launch policy, manifest or timing files. Before it takes any
  work, the worker checks its settings and exits 2 if any of these is missing
  or wrong:
  - its actor (`SPECIMEN_WORKER_ACTOR_UID`);
  - the inference switch;
  - the SAM 3 service on Cloud Run (`SPECIMEN_SAM3_ENDPOINT`), pinned at the
    reviewed revision (`SPECIMEN_SAM3_REVISION`);
  - the readers' `HF_TOKEN`.

  It also refuses emulator settings and SAM 3 lab mode. The collection bindings
  (`SPECIMEN_COLLECTION_BINDINGS_JSON`) and the worker job
  (`SPECIMEN_WORKER_JOB`, for the hand-over) are optional. An error names the
  setting, never its value. The SQL endpoint and the bucket are the API's. The
  worker resolves profiles with the same published registries as the API.
- **Collections.** The actor's operator-or-above memberships, one collection at
  a time.
- **Fence.** Two executions of the job must never process two runs of one
  collection at once (G13). A snapshot's compare-and-set alone cannot prevent
  that when both executions act as the same actor, because they replay each
  other's receipts. So the worker first takes the collection's fence: a
  compare-and-set document holding the execution's id, the run it is working on,
  and a lease of 300 s renewed after every step.
  - A live fence held by another execution means that execution is draining the
    collection, and this one moves on. An expired fence is taken over.
  - The document is marked not sensitive, since the worker's membership cannot
    view sensitive records. The provider circuit's state documents, which the
    worker also writes, are marked not sensitive for the same reason. A
    circuit document left sensitive by an earlier worker can be neither read
    nor replaced by this one.
  - The holder is the Cloud Run execution and task index. A retried attempt of
    the same task takes over at once, because its predecessor has exited.
  - A worker that stalls past its lease and loses the fence leaves the
    collection to the new holder.
- **Order.**
  - The run a dead execution left under the fence is finished first, once it
    is due. Its step's own lease can outlive the fence's, so a run still
    leased is waited for like a retry.
  - After that, the oldest due run is stepped until it stops. It comes by
    `queued_at` through `ListDueWorkV2`: never sensitive, and only `pending`,
    `running` or `retry_scheduled`. The SQLite store lists the same states. The
    run stops at a disposition, a block, a pause, a cancellation, a scheduled
    retry or an unknown outcome. Then the next one is taken.
  - A save that conflicts with a concurrent edit is read again and stepped
    again, up to three times in a row.
  - A due run whose step changes nothing would be taken again and again. It is
    blocked with `lane_run_not_progressing`, where people can see it, and the
    queue moves on. Its resume action requests it again.
- **Retries.** A run that stops with a scheduled retry is waited for, once no
  other run is due, if the retry falls inside the window. Nothing else would
  start the job for it. Retry delays are at most 300 s plus jitter. A retry
  after the window is written into the fence when it is released, and the next
  holder waits for it as it would for its own. `ListDueWorkV2` cannot look
  ahead, because its cutoff may not pass the database's clock.
- **Window.** The worker takes no new run 600 s before its task deadline
  (3600 s). It exits 0 when nothing is due and no retry is pending in the
  window. On `SIGTERM` it stops taking work, lets the current step's result
  save, and releases the fence.
- **Hand-over.** The coordinator approved it on 2026-09-23 with three bounds.
  - The worker starts the next execution only when requested work is due as
    its window closes (in a collection it drained, or one it did not reach), or
    when a retry it hands over through the fence falls within the next
    execution's window. A drained queue or a stop signal starts none.
  - It releases its fences first, so the next execution takes them (G13). It
    uses T1's job start: the job as deployed, with no changed arguments,
    environment or task count. The worker's service account may run that job
    only (S2 grants `run.invoker` on it, never overrides or project-wide).
  - The fence counts consecutive hand-overs without progress. On the third,
    the worker stops handing over. It blocks the waiting run with
    `lane_handover_without_progress`, an operational block, and G30 caps model
    spend but not Cloud Run time.

  A failed start leaves the work queued for the next request, as in T1.
- **Output.** One JSON summary: the status (`drained`, `window_closed` or
  `stopped`), the specimens processed, the collections skipped, the
  collections whose hand-over stopped, the retries pending, and the hand-over's
  outcome (`requested`, `failed`, `unconfigured` or none).
- **Blocks the drain records.** Both are operational blocks, never queue
  outcomes (QUE-005). The operator's `retry` or `resume` action requests the
  run again, as for every operational block.

  | Code | What it means | What to check |
  | --- | --- | --- |
  | `lane_run_not_progressing` | The worker stepped this due run and the step changed nothing. | The run's last step in the thread, and the worker's log for that step. Then retry. |
  | `lane_handover_without_progress` | Three worker executions in a row handed this collection on without making progress. | The worker job's task timeout (more than 600 s) and its logs. Then retry. |

- **Readiness before the first drain.** On 2026-09-23 S2 confirmed, read-only,
  that the production Data Connect schema is the empty placeholder, and the
  first initialization applies the schema to an empty database. Before the
  first drain, the owner or S2 runs three read-only counts on the protected
  path. Each must be zero:
  1. `worker_cursor` documents marked sensitive, which the worker could neither
     read nor replace;
  2. specimens in `pending`, `running` or `retry_scheduled` with a due time
     that no lane request set (`queued_at` absent);
  3. rows in those states with no due time (#88, section 9).

### Program allowance (G9)

The published profiles carry the program's model allowance in micro-dollars.
The owner set it at USD 5 (G30): 5,000,000 micro-dollars for production's
readers, SAM 3, first pass and harness. The lab's USD 5 share is separate, and
the rest of G9's USD 25 is left for infrastructure. It rises only by the owner's
decision, through a profile edit.

The ledger is a compare-and-set document in the scope of the collection the
setting names. It adds every paid step's reservation before the call, alongside
the run's own budget check (`workflow.py` 191-231). A step whose reservation
would cross the allowance is not called. The run blocks with
`program_allowance_exhausted`, an operational block with no queue outcome
(QUE-005).

G30 caps what production's model calls spend (PLAN 4.3, #104; the coordinator's
ruling of 2026-09-23). T2b and T2c build it:

- Every reservation is one atomic check-and-reserve on the shared ledger,
  before the call. Once the allowance is spent, paid steps block with
  `program_allowance_exhausted`.
- A call settles to its cost when the provider reports usage or returns a
  billed amount, which releases the rest of its reservation. A settled cost
  above its reservation counts in full.
- An unknown outcome (a timeout, a transport error, a 5xx, or a response
  without usage) stays reserved at its full amount, recorded as
  `cost_basis: reserved`. A retry reserves again.
- The run's own budget settles the same way (the coordinator's ruling of
  2026-09-24). A paid step's reservation is released to its settled cost when
  every call reported usage or a billed amount; an unknown outcome stays
  reserved in full. The run's limit stays 500,000. With no allowance
  configured, the ledger is not consulted, and the run's budget still
  settles.

Every reservation bounds its step's worst case, so no call can cross the
allowance (PLAN 4.3; the coordinator's ruling of 2026-09-24). The pilot's, at
the pinned prices (T2c):

- `segment` 45,000: at 136 micro-dollars a second (4 vCPU and 16 GiB at Cloud
  Run's request-based rates). Cloud Run bills a request-based instance while it
  starts, serves and shuts down (S2, from the billing settings page, updated
  2026-09-21). A request must be answered within the 300 s request timeout,
  cold start included (the container runtime contract), and shutdown is the
  10 s grace period. (300 s + 10 s) × 136 plus the request is about 42,161.
  The rest is margin for anything else billed at start, such as an image
  pull, which the pages do not mention.
- A model call that sends a crop reserves, before it starts, for each
  request it may make. A reading makes at most two, and its retry resends the
  crop with the first answer and at most 8,192 bytes of feedback (HARNESS.md
  section 15). Each request reserves the lesser of:
  - (a) the route's context length at the input price, plus the answer's cap
    (4,096 tokens) at the output price;
  - (b) where the route documents its image-token rule, the crop's tokens
    under that rule, plus the prompt and the answer's cap.

  A route without a documented rule reserves (a). The stage's reservation,
  20,000, is the floor.
  - The readers document their rules (T2c lists them), so (b) applies, and
    it is far below (a): 29,082 a request on qwen and 44,237 on muse. For
    every crop up to a source image's 40,000,000 pixels, the two requests
    come to at most 16,284 on qwen and 18,391 on muse. Both readers reserve
    the 20,000 floor.
  - The first pass's route (GLM-5.3-Flash) documents no image rule: not on
    DeepInfra's page, zai-org's model card or Z.ai's documentation. It will
    reserve (a) when it lands: with its 1,048,576-token context and 1,024-token
    answers, 157,799 a request, 315,598 for two. First passes run one at a
    time, and the run's budget settles, so a run's 500,000 holds.
- `parse` 20,000: today's extraction agent sends text only, with the same
  request and answer limits on the qwen route, about 10,000 at most. The
  harness (S4) replaces it with its own route and up to four geocoding
  requests, each with at most three attempts (HARNESS.md section 11); its
  reservation moves with it, bounded the same way.

Every reservation also records the program's position on the run: the
allowance, the total reserved after this step, and what remains. The thread
shows it, so a block is never a surprise.

How T2b builds it:

- **Setting.** `processing.program_allowance` in a published profile holds
  `allowance_micros` and `ledger_collection`, a public tree key. Every profile
  that carries an allowance must carry the same one, so the program has a
  single allowance. The pilot's is 5,000,000 micro-dollars, with its ledger in
  `insects`.
- **The ledger's collection.** The tree key is resolved through the private
  bindings and must be bound to exactly one collection. Otherwise a request to
  process is refused with `program_allowance_unavailable`, and an upload's run
  is `processing_blocked` with that blocker. At request time the run copies the
  allowance and the ledger's collection into its execution policy, like the
  rest of the collection's allowance.
- **When it reserves.** For a paid step with a stage cost. The reservation comes
  after the run's own budget check and the provider circuit's admission, and
  before the step's intent is saved. A circuit refusal therefore reserves
  nothing.
- **The document.** A `worker_cursor` document in the ledger collection's
  scope, marked not sensitive. Its id derives from the organization and the
  ledger collection. It holds the reserved total and the last reservation
  (specimen, run, step, attempt, amount, allowance, time).
  - Collections may share the ledger, so a compare-and-set conflict is retried
    against a fresh read, up to five times.
  - A ledger that stays busy or cannot be read blocks the run with
    `program_allowance_ledger_unavailable`, also an operational block.
- **On the run.** `Run.program_allowance` holds the allowance, the reserved
  total after the step, what remains, the ledger's revision and the time. A
  refused reservation records the same, with the amount it asked for.
- **Blocks and refusals.** Both blocks are operational (QUE-005), and the
  operator's `retry` or `resume` action requests the run again.

  | Code | What it means | What to check |
  | --- | --- | --- |
  | `program_allowance_exhausted` | The next paid step would take the program past its model allowance, so it was not called. | The allowance and the remaining amount on the run. Only the owner raises the allowance, by a profile edit. Then retry. |
  | `program_allowance_ledger_unavailable` | The worker could not read or update the program's ledger. | The worker's membership in the ledger's collection, and that the ledger document is its own. Then retry. |
  | `program_allowance_unavailable` | A request was refused: the ledger's tree key is not bound to exactly one collection. | `SPECIMEN_COLLECTION_BINDINGS_JSON`. Then request processing again. |

### Cost of every paid call

`Run.paid_calls` records one entry per paid call:

- the step key and attempt;
- the reservation;
- the usage: tokens for a model call, measured seconds for SAM 3;
- the outcome;
- a cost labelled `computed`, from the profile's pinned price list, with that
  list's version and date. Where a provider returns a billed amount, it is
  recorded instead and labelled `billed`.

Model calls are priced per million input and output tokens for their route.
SAM 3 is priced by its measured request seconds times the service's configured
vCPUs and memory at the pinned Cloud Run rates. A price changes only through a
reviewed profile edit. The run's `usage.actual_cost_micros` is the sum of its
calls' costs.

How T2c builds it:

- **Price list.** `processing.price_list` in a published profile holds its
  `version`, the date it was read (`as_of`), its `sources`, and whole
  micro-dollar prices:
  - `models`: per route, per million input tokens and per million output
    tokens. Each also carries the route's `context_tokens` and, where the
    route documents one, its `image_tokens` rule: pixels per token, the
    maximum tokens for one image, and the rule's source. Both size a reading's
    reservation (PLAN 4.3, above);
  - `segmentation`: SAM 3's service, its vCPUs and memory in GiB, and the price
    per million vCPU-seconds, GiB-seconds and requests;
  - `tools`: per request, for the tools that are paid.

  Every route the profile names, and its segmentation, must be priced, and
  every route that reads crops needs its context length. At request time the
  run copies the list with the rest of the collection's allowance.
- **The reservation.** `lane_reservations.step_reservation` gives a paid
  step's reservation: the stage's amount, or for a reading its PLAN 4.3 worst
  case with the stage's amount as the floor. The workflow reserves it, and
  the cost record reports it, so the two never differ. A reading whose route
  has no context length, or whose crop the run does not have, cannot be sized
  and blocks before the call (`approved_cost_budget_unavailable`).
- **Records.** `lane_costs.record_model_usage`, `record_segmentation` and
  `record_tool_usage` append one entry per paid call to `Run.paid_calls`:
  - the step, the attempt, and the step's reservation;
  - the usage and the outcome;
  - the cost and its basis, with the price list's version and date.

  They add the cost to `usage.actual_cost_micros`. Costs round up to whole
  micro-dollars. A provider's billed amount, when given, is recorded instead as
  `billed`. A call that reported no usage is recorded by `record_reserved` at
  its step's full reservation, as `reserved`. A call with no price is a
  configuration error: the step fails and keeps its reservation.
- **Where.** After each reading and SAM 3 step, the workflow records the
  reader's tokens from its observation, or a completed SAM 3 call's measured
  seconds, which include waiting for a cold start. It records the step's
  outcome with them: `completed`, `failed`, or `unknown` when the outcome of
  the call is unknown. A reading that failed before reporting tokens, and a
  SAM 3 call that did not complete (a busy 409 or 429, a 5xx, a timeout), are
  recorded as `reserved`. The harness records its own model
  requests and tool calls in `parse` (S4, T3c). A run without a price list
  records nothing.
- **Settlement (G30).** After a paid step, the ledger settles the attempt to
  the cost of the calls recorded for it, giving back the rest of the
  reservation. It does so only when every call reported usage or a billed
  amount; a settled cost above the reservation counts in full. A step with a
  `reserved` call, or whose calls nobody recorded, stays fully reserved. A
  step's next attempt reserves again, and no call starts if its reservation
  would cross the allowance, however little has been spent.
- **Pilot prices, read on 2026-09-23 and again on 2026-09-24, unchanged**
  (`pilot-prices-2026-09-24`, which adds the context lengths and image rules).
  - Context lengths, from the Hugging Face router's `/v1/models` for each
    route's pinned provider: 131,072 for both readers.
  - Image rules, from each model's processor configuration:
    `handwriting-qwen` (Qwen3-VL-30B-A3B-Instruct) makes one token per 32 by
    32 pixels (a 16-pixel patch, merged two by two) and at most 16,384 for
    one image (its `max_pixels`, 16,777,216); `handwriting-muse`
    (Muse-Glimmer-30B) one per 28 by 28 pixels (a 14-pixel patch, merged two
    by two) and at most 4,096 (`max_image_tokens`).
  - Readers, from the Hugging Face router's `/v1/models` pricing for their
    pinned providers: `handwriting-qwen` (novita) 200,000 input and 700,000
    output per million tokens; `handwriting-muse` (deepinfra) 300,000 and
    1,200,000.
  - SAM 3, from cloud.google.com/run/pricing for a request-based service in
    us-east4, with S2's shape of 4 vCPU and 16 GiB. The rates are
    24,000,000 per million vCPU-seconds, 2,500,000 per million GiB-seconds and
    400,000 per million requests: USD 0.000024, 0.0000025 and 0.40 per
    million. That comes to 136 micro-dollars a second.
  - `geography_lookup`, from developers.google.com/maps/billing-and-pricing:
    the Geocoding API's Essentials price after the free 10,000 requests a
    month, USD 5.00 per 1,000, so 5,000 per request. The free tier is ignored,
    which errs on the safe side.
- **Sensitive intake.** Processing starts on intake only for records declared
  not sensitive (#104). A Sensitive upload or import creates no due run and
  never holds a collection's queue. A test now covers the import path.
