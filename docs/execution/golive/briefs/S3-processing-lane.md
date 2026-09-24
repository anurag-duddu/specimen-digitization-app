# S3 brief: processing lane

Session title: **Build the on-demand processing lane**. Recommended model Opus
5.5 at high effort.

## Mission

One specimen at a time runs on demand in production through stages 1 to 5 of
PLAN section 4.1 (stage 5's scores are computed in S4's `adjudicate` and
`finalize` steps), with the profile, budget and tracing that the rest of the
pipeline needs, and with clean seams for the first pass and harness (S4) and
for persistence (S5).

## Read first

1. `docs/execution/golive/PLAN.md`, all of it.
2. `~/specimen-golive/research/01-backend-pipeline-stages.md` (all),
   `04-observability-and-prompts.md` (all), `02-release-and-deploy-planes.md`
   section 3, `06-product-spec-and-approvals.md` section 1.
3. `docs/execution/ARCHITECTURE.md`, `PROCESSING_ENGINE_COMPARISON.md`,
   `CONTRACTS.md`.

Line numbers below come from the research at `709ae3c`; reverify them.

## Pull requests, in order

Each starts with its spec delta in `docs/execution/golive/LANE.md` and failing
tests, then the implementation. Order, approved by the coordinator on
2026-09-23 to unblock the acceptance lab: T1 (as T1a and T1b), T4, T3, T2, T5.
Production needs all five.

**T1. On-demand trigger.** `POST /specimens/{id}/process` works in production
with the endpoint's existing authorization (synthetic only today, `api.py`
2387-2396): it creates the run with a budget from the collection's allowance,
marks it due, and starts one execution of the worker job through the Cloud Run
Admin API (an injected client, faked in tests). Processing starts on intake for
every upload declared not sensitive (`PRD.md` 9.1 step 6; synthetic only today,
`api.py` 1292-1293); a Sensitive upload is not processed, so it creates no due
run and never holds G13's per-collection queue (PLAN section 2.2). A
request during an active run in the same collection waits and runs in request
order (G13), and the intake collection selects the profile (G14): set
`run.classification_selection` from it, which the `classify` step requires
(`workflow.py` 308-331); a reviewer corrects it through the existing endpoint
(`api.py` 2243). Wire source
import in production over `microscopic-slides/`
(`cli.py` 45-53 passes no source registry or reader today) so the ten can be
imported from Storage.

**T2. Worker drain mode in production.** The general polling worker
(`worker.py` 45-194, synthetic only today) becomes the production mode for the
lane: it claims due runs one at a time, runs each to a final disposition or an
operational block, and exits when nothing is due. The exactly-ten pilot worker
and launch contract are not used by the lane; do not break their tests without
replacing them. Enforce the per-run budget and the program allowance, USD 5 for
production model calls (G30), with the existing cost fields (`domain.py` 286;
`workflow.py` 208-213); a paid step past it blocks as
`program_allowance_exhausted`, an operational block (QUE-005). Each paid call
reserves its worst-case cost first, bounded per request as PLAN 4.3 states
(context length at the pinned input price plus the output cap, or the
documented image-token rule, for each request a call may make, with 20,000 as
the floor), in one atomic check-and-reserve on the
ledger (your T2b `worker_cursor` document, written only at the revision it was
checked against), so a step's reservation must bound its worst case (SAM 3's
startup, its 300-second request timeout and its 10-second shutdown, as #132
computes; SAM 3 settles as `computed`). The "fill the rest" review action
runs as a worker job you host, its paid calls reserved under G30 (PLAN
section 4.8). Only usage the provider reports,
or a billed amount it returns, settles a call and releases the rest of its
reservation; a timeout, a transport error, a 5xx or a response without usage
stays reserved in full as `cost_basis: reserved`; a settled cost above its
reservation counts in full; a retry reserves again; nothing settled or held
reserved is given back when a run fails or is retried. Record every
paid call's cost as PLAN section 4.3 rules: usage, reservation, and a cost
computed from a pinned price list whose version and date are recorded, or the
billed amount where a provider returns one; SAM 3 by its measured seconds,
startup included, at the service's vCPU and memory rates.

**T3. SAM 3 per run.** The client binding (`production.py` 851-852) and the
server (`sam3_server.py` 358-380, 590-622) authorize each run the worker sends
instead of the frozen manifest, and the server no longer shuts itself down after
an hour. Keep the pinned revision and offline checkpoint. Record the concept
prompt, thresholds, revision, region count and scores, and continue the trace
from the `traceparent` header. The release workstream (S2) builds and deploys
the service; agree its shape with S2 before you finish. Expect two labels on
five pilot slides, with the locality on the right-hand one (PLAN section 3); a
missed label goes to human review under G15, and retuning the pinned SAM 3
settings needs the coordinator first. Confirm coverage automatically (G15):
check the segmentation result with the specification's region-count and
full-image cross-checks (`PRD.md` 874), set `run.coverage_confirmed` from the
result, record the evidence, and let a failed check send the record to the
human queue with `label_coverage_unconfirmed`. The segment step's body in
`workflow.py` is yours. Write the concrete check into `LANE.md` and send it to
the coordinator before building it.

**T4. Profile.** `zoology_insects_slides` as configuration, published for the
pilot (G1), mapped to `Insects` beneath `Zoology`, with inheritance down the
collection tree (`collection_profiles.py` 198-224 does not walk parents). It
carries the segmentation settings (`label`, thresholds 0.5, at most 64
regions); the two readers; the tools per field (S4 implements the tools); the
mandatory and optional groups (G8: the owner's list, which is the
specification's (G42), with `identified_by_irn` non-blocking until EMu
Parties is connected (G16, G43) and no Parties tool
mapped to it, and the four elevation fields mandatory, filled with authority and evidence
(G37 and G41, revising G22); changing the groups must be one configuration edit); the
existing uncalibrated risk policy, labelled uncalibrated; and the clearance rule
reference (S4); the Insects date rules of G24 (a two-digit year reads as 19xx)
and G29 (a Roman numeral I to XII in the month position is that month),
recorded as versioned rules that S4's date tool reads, and the id and version
of the Insects harness knowledge that S4 writes (PLAN section 4.2); the lane
policy's reason codes under the configuration's `reason_codes` key, generated
from S4's `policy.py`, for S6's queue filter (coordinator ruling). Optional fields must survive at runtime and reach the run as
`Run.field_groups`, a new field whose shape S5 decides (today they are dropped: `domain.py` 324-336,
`collection_runtime.py` 106-118); S4 changes `parse` (`workflow.py` 685-719)
to extract them.

**T5. Tracing (G3).** The lane uses the standard path's `approved-content` mode
(`observability.py` 232-276), content on and binary content off. Remove the
metadata forcing for the lane (`worker.py` 751-754, `cli.py` 88-91,
`observability.py` 314) and the per-agent content overrides
(`provider_privacy.py` 24-29, `transcription.py` 75; `harness.py` 80 is S4's,
coordinate). One root span per run with specimen, run, collection and profile
ids (helpers exist unused in `tracing.py` 48-68); a span per stage carrying
`specimen.processing.stage` (the existing helper's attribute, `tracing.py` 65);
SAM 3 spans on both sides; the trace id stored on the run (S5
adds the column) and exposed to the thread API; identities and secrets
scrubbed, and no span, log line, exception text, stored error or tool-call
result records the Geocoding request URL, which carries the key (G26).
Update the leak tests to the new approval instead of deleting them. Wire the
Logfire project and token with S2. The unmerged branch `codex/reader-trace-linkage`
(four commits) may have reusable pieces.

## Local mode

The acceptance lab (S7) runs your lane locally with real models. Keep that
working: `create_app(adapters=...)` in `application/api.py` is the seam, and
`ProductionAdapters` runs under `mode="synthetic"`. Tell S7 when a topic merges.

## Coordination

S5's data contract (its T1) comes first; code against it. S2 deploys what you
build and grants what it needs. S4 consumes the profile, the tools per field
and the optional fields. `domain.py` has no single owner: add to it additively,
list your additions in the pull request body, and let S5 decide any shape that
S4 also needs. Where the specification is silent or contradictory, stop and ask
the coordinator; do not decide (G5).

## Done

A specimen imported or uploaded in production is processed on request, one at a
time, through segment, transcribe and compare, within budget and fully traced,
and hands off to S4's steps.
