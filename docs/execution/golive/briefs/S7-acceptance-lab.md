# S7 brief: acceptance lab

Session title: **Run the acceptance lab one specimen at a time**. Recommended
model Opus 5.5 at high effort.

## Mission

Find failures one specimen at a time, locally and then in production, and prove
every stage works on real data, until specimen 10 passes the first time
(PLAN section 8).

## Read first

1. `docs/execution/golive/PLAN.md`: sections 1, 4 and 8.
2. `~/specimen-golive/research/01-backend-pipeline-stages.md`,
   `04-observability-and-prompts.md`, `06-product-spec-and-approvals.md`.

## Facts you should not have to rediscover

- Local real inference: `create_app(adapters=...)` in `application/api.py` is the
  seam; `ProductionAdapters` (`application/production.py`) runs under
  `mode="synthetic"`. Two locks: `SPECIMEN_APPROVED_INFERENCE=true`, and the
  run's pinned `dependencies["segmentation"]` must equal
  `{endpoint: $SPECIMEN_SAM3_ENDPOINT, revision: $SPECIMEN_SAM3_REVISION}`.
- The SAM 3 container is amd64 only and runs on this Mac under
  `--platform linux/amd64` emulation. Cached images such as
  `specimen-pr23-root-20260910-sam:f542604dc67ae12a6579b3dfe0d01d1e4b5b2e46`
  (3 GB) need no rebuild. Entrypoint
  `python -m specimen_digitization.application.sam3_server`; the checkpoint
  downloads at runtime with `HF_TOKEN` into `HF_HOME=/tmp/huggingface`. The
  server refuses to start outside Cloud Run (it checks `K_SERVICE`); work out a
  local mode with S3 rather than patching around it. The Docker VM has 8 GB and
  12 CPUs; SAM 3 on CPU takes about 25 s per image.
- Reader routes verified on 2026-09-14: `handwriting-qwen` (novita) and
  `handwriting-muse` (deepinfra), 5 to 7 s per read. A local Hugging Face token
  exists for paid calls; never print it or read `.env` into context.
- Images: `gs://specimen-digitization.firebasestorage.app/microscopic-slides/subject_105526321.jpeg`
  to `...330.jpeg`, about 300 KB, 1780 by 590 px. Application default
  credentials work on this Mac.
- The label is roughly the left 30 percent of the frame, with a DataMatrix
  barcode reading `FMNHINS <catalog>`; the labels are from the 1946 expedition to
  Mindanao (CNHM; F.G. Werner, H. Hoogstraal).
- `application_registry(synthetic=True)` force-sets approvals. For real runs use
  the pilot profile from S3, or record plainly that approvals are a local
  fixture.
- Persistence: the Data Connect emulator (`--persistence sql-emulator`, loopback
  project `demo-specimen-data`) exercises the real connector; local SQLite keeps
  only JSON.
- Logfire: local runs send traces with `environment=lab`; the SDK reads the
  local `.logfire/` credentials itself. Never open that directory.

## Pull requests and work, in order

**T1. The lab runner.** `scripts/lab/run_specimen.py` runs one specimen through
the latest lane locally (real SAM 3 container, real readers, and later the first
pass and harness; emulator persistence; Logfire lab traces). It writes
`~/specimen-golive/runs/<subject>/<timestamp>/` (inputs, crops, raw responses,
snapshot, a dump of the normalized rows, timings, costs, trace id) and a report
`~/specimen-golive/reports/<subject>.md`. Test the runner's own logic with fakes
first; then run it for real.

**T2. Specimen 1 on today's `main`,** with whatever stages exist (segmentation
and readers), to flush out environment failures. Record everything.

**T3. Follow the pipeline.** As S3, S4 and S5 merge, rerun specimen 1, then 2,
then 3, one at a time. Each failure becomes a GitHub issue (label `golive` plus
the workstream; no secrets or identities) and a message to the owning session
and the coordinator. Rerun after the fix merges. Offer recorded real responses
to S4 as test fixtures.

**T4. Production acceptance,** once DoD-1 to DoD-3 hold, following PLAN section
8 through the app. The owner signs in; agree with the coordinator how you drive
the signed-in app (the in-app browser after the owner signs in there, or the
owner's Chrome with permission). Check the SQL rows (read-only), the Logfire
trace (every stage, prompts visible) and the thread in the app; write the
report; rerun until the run is flawless; then the next specimen.

Record every run's cost in its report and keep the program within G9.

## Done

Ten passing reports and a summary for the coordinator.
