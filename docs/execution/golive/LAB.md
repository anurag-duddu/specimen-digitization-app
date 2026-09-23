# Acceptance lab

Workstream S7 of the go-live program ([PLAN.md](PLAN.md) sections 5, 6 and 8).
This page holds the lab's spec deltas, newest topic last.

## T1: the lab runner (2026-09-23)

### Purpose

`scripts/lab/run_specimen.py` runs one specimen through the lane of the current
commit on this workstation with real models, and records the evidence PLAN
section 8 step 3 asks for. It is test tooling. It changes no product behaviour
(G5) and deploys nothing (G11, `AGENTS.md`). It drives the app only through
`create_app(adapters=...)` and the app's own HTTP routes, as the client does,
and it scores what the app recorded rather than what it expected.

### Command

```bash
uv run python scripts/lab/run_specimen.py subject_105526321
```

| Option | Default | Meaning |
|---|---|---|
| `--segmentation` | `sam3` | `sam3` calls the endpoint in `SPECIMEN_SAM3_ENDPOINT`. `reviewed-region` leaves it unset, so segmentation blocks with the app's own `sam3_serving_contract_not_configured_use_reviewed_regions`; the runner then draws the label box (left 32 percent of the frame, full height) through the reviewer route `POST .../specimens/{id}/regions`, and the report marks segmentation as substituted |
| `--persistence` | `sql-emulator` | a fresh PostgreSQL-backed SQL Connect emulator per run (`scripts/data/serve-local.sh` on private ports), dumped after the run. `sqlite` keeps only the snapshot |
| `--logfire` | on | lab traces with `APP_ENV=lab` through `configure_observability`; the SDK reads its own local credentials. `--no-logfire` sends nothing |
| `--max-load` | 12 | refuse to start while the one-minute load average is at or above this (PLAN 7.4) |
| `--max-run-usd` | 0.75 | the most one run may cost under the app's own call and token limits |
| `--lab-allowance-usd` | 5.00 | the lab's share of G9: refuse to start when recorded lab spend plus `--max-run-usd` exceeds it |
| `--timeout-seconds` | 1800 | stop driving the record after this |
| `--dry-run` | off | preflight and image fetch only: no app, no paid call |

### Phases

1. **Preflight.** The subject id is `subject_` and digits. Load and allowance
   are checked. The inference switch and token are present; only presence is
   read, never a value.
2. **Fetch.** `gs://specimen-digitization.firebasestorage.app/microscopic-slides/<subject>.jpeg`
   with application default credentials. Size, generation, MD5 and SHA-256 are
   recorded.
3. **Ingest.** The upload routes (batch, item, content, complete), as the
   client uses them. The app starts processing on completion.
4. **Process.** The runner drives the record until it is finalized, blocked
   with no lab action left, or out of time. Its only action is the
   reviewed-region substitute. It waits out a lease; it never retries a paid
   step itself.
5. **Collect.** The specimen with its previous runs and audit, the workspace
   view, crops, each reading's raw response, every SQL row, timings, costs and
   trace ids.
6. **Check.** Each PLAN 4.1 stage is scored from what the app recorded.
7. **Report.** The files below. The subject report is rebuilt from every run
   of that subject.

### Stage checks

| Stage | Passed when | Otherwise |
|---|---|---|
| 1 Images in storage | the asset's SHA-256 equals the fetched object's, and its file name is the subject's | failed |
| 2 Label segmentation | the run has regions made by SAM 3, with its parameters on the run | blocked, with the app's blocker; substituted when the lab drew the region |
| 3 VLMs | every region has one reading per profile route, each with model, provider, prompt version, input hash and a stored raw response | failed, or blocked with the blocker |
| 4 Raw transcripts to SQL | normalized observation rows exist, one per reading, keyed to specimen and run | absent when SQL holds only the snapshot |
| 5 Disagreement score | every region's transcript carries a ratio and `bounded-levenshtein-fraction-v1` | failed or absent |
| 6 LLM first pass | the run records the first pass's decision and what each reader handed to the harness | absent |
| 7 Agentic harness | the run records tool calls with typed outcomes | absent, or partial for deterministic lookups only |
| 8 Queue decision | exactly one disposition with reasons, or an operational block with its blocker | failed |
| 9 Linkage | every region, reading, transcript and row points to this specimen, asset and run | failed |
| Tracing | the run stores its trace id (DoD-5) | absent; the lab's own root trace id is always recorded |

Statuses are passed, failed, blocked, substituted, absent (the stage is not on
this commit) and not checked. Checks for stages 4, 6 and 7 follow the contracts
as S5 and S4 merge them. Until then the runner reports absent rather than guess
at field names.

### Files

```text
~/specimen-golive/runs/<subject>/<UTC timestamp>/
  run.json  report.md  runner.log
  inputs/<subject>.jpeg  inputs/source.json
  snapshot.json  workspace.json
  crops/<region id>.png
  responses/<observation id>.json
  rows/<table>.json
  state/  the app's blobs and local database for this run
~/specimen-golive/reports/<subject>.md
```

### Costs

The app records tokens, not money (`BudgetUsage` in `domain.py`; stage costs
are reservations only). The runner prices each reading's tokens with the route
prices in `docs/execution/LIVE_PILOT_COST.md` 42-47. It prices any other tokens
the run used, such as the extraction call, at the highest known price and labels
that figure an upper bound. SAM 3 on this workstation costs nothing. Every run's
cost goes into `run.json` and its report, and the lab's spend is the sum over
all runs.

### Secrets

The runner never writes a token value. Every text artifact passes through a
redactor that removes the values of the known token variables and anything
shaped like a Hugging Face token, a bearer header, a Google access token or a
JWT. The runner never reads `.env` or `.logfire/`.

### Tests

`scripts/lab/test_run_specimen.py` and `scripts/lab/test_lab_checks.py` use
fakes for storage and the lane. `scripts/lab/test_lab_lane.py` drives the real
app factory with the synthetic adapters and SQLite, so the driver is proven
without paid calls or network.

### Known limits on `709ae3c`

- SAM 3 cannot run locally until S3's lab mode lands (S3 T3). The server needs
  Cloud Run, a Google ID token, a bucket and a ten-item manifest, and the client
  accepts only `https://*.run.app`. Until then the lab uses `reviewed-region`.
- Uploads in synthetic mode get the synthetic profile (`api.py` 1242-1246),
  whose approvals are a local fixture; the report says so. Under that profile
  the finalize integrity check expects each reading's input hash to be the
  image's rather than the crop's (`integrity.py` 112-116), so a run with real
  readers ends at `evidence_integrity_failure`. That is a fixture artifact, not
  a production defect.
- The run stores no trace id and model spans carry metadata only, until S3's
  tracing work (S3 T5).
