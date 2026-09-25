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
| `--segmentation` | `sam3` | `sam3` calls the endpoint in `SPECIMEN_SAM3_ENDPOINT`. `reviewed-region` leaves it unset, so segmentation blocks with the app's own `sam3_serving_contract_not_configured_use_reviewed_regions`; the runner then draws the slide's label boxes (below) through the reviewer route `POST .../specimens/{id}/regions`, and the report marks segmentation as substituted |
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
| 2 Label segmentation | the run has regions made by SAM 3 with its parameters on the run and, for each of the ten, a distinct region covering at least half of every label box below; an uncovered label is still correct when the lane's own coverage check (G15) caught it and sent the record to review | failed when the lane let an uncovered label through; not built when the run carries no coverage check (S3 T3b); blocked, with the app's blocker; substituted when the lab drew the regions |
| 3 VLMs | every region has one reading per profile route, each with model, provider, prompt version, input hash and a stored raw response | failed, or blocked with the blocker |
| 4 Raw transcripts to SQL | the run's `pipeline_run` row names this specimen, and there is one `model_observation` row with `independent` true per reading, with the snapshot's ids (DATA_CONTRACT.md 2) | not built while SQL holds no `pipeline_run` rows; blocked or failed when the run has no readings to project; failed on any mismatch |
| 5 Disagreement score | every region's transcript carries a ratio and `bounded-levenshtein-fraction-v1` | failed, or not built |
| 6 LLM first pass | the run records the first pass's decision and what each reader handed to the harness | not built |
| 7 Agentic harness | the run records tool calls with typed outcomes | failed on any GBIF occurrence request while D4 is held; otherwise not built (the detail lists any deterministic lookups) until S4's checks land |
| 8 Queue decision | exactly one disposition with its reasons; for the ten, needs human review with the right reasons (below) | failed when one of the ten clears or the record has no disposition; blocked while `processing_blocked` or `retry_scheduled`, naming the blocker and the app's next step |
| 9 Linkage | every region, reading, transcript and row points to this specimen, asset and run | failed |
| Tracing | the run's trace shows what DoD-5 names (PLAN 1): SAM 3's parameters, every model call's system prompt with its text input and output, the first pass, the harness's tool calls and the queue decision, and the run stores its id | not built while the run stores no trace id; not checked until the lab holds a Logfire read token (owner action) to read the trace; the lab's own root trace id is always recorded |

Statuses are passed, failed, blocked, substituted, not built (the stage is not on
this commit) and not checked. A blocked stage names the blocker and the step
the app would run next (`Workflow.next_step`). Checks for stages 4, 6 and 7 follow the
contracts as S5 and S4 merge them. Until then the runner reports not built rather
than guess at field names.

### Label layout of the ten pilot slides

From S8's reading of the images and the lab's own look (2026-09-23). Boxes are
fractions of the frame's width over its full height. The barcode's printed
catalog number (`FMNHINS ...`) sits just outside the handwritten label, so the
boxes include it.

| Subjects | Labels | Boxes |
|---|---|---|
| `subject_105526321` to `323`, `329`, `330` | one label, locality included | 0 to 0.37 |
| `subject_105526324` to `328` | notes on the left; locality, date, elevation and collector on the right, next to the barcode | 0 to 0.34 and 0.62 to 1 |

The reviewed-region substitute draws these boxes. Under G15 they are also the
ground truth for the lane's own coverage check: the lab reports its hits and
misses per subject, and stage 2 fails only a miss the lane let through. Slides
324 to 327 are from Mindanao; 328 also has a right-hand label, and 328 to 330 are
from Yepocapa, Guatemala, 1948 (R.D. Mitchell). The codes on the
top edge are slide-preparation codes, not collection dates.

### Expected outcome for the ten (G42, and the owner's decisions G35 to G45)

All ten go to needs human review, with the right reasons: G42 keeps `PRD.md`
12.4's twenty mandatory fields, no label carries a determination date, and none
can be derived, so no slide can clear. A run that clears one of the ten, or
sends it to review for a wrong or missing reason, fails stage 8 once the lane
reaches the queue decision. The owner's words and the coordinator's readings
(PLAN 2.1) are kept apart below.

- **Derived fields (G37).** The owner: "these can be derived if other location
  related fields have returned a final value. If even those are unclear then it
  will wait for human review." The coordinator's reading adds that a derived
  value fills the field, mandatory fields included, with its authority and
  evidence recorded. A derived value without recorded evidence, or derived from
  unsettled inputs, is a failure.
- **A stated elevation (G41).** The owner chose "Convert and fill": "The label's
  own number fills both From and To, and the metre fields are converted from it
  exactly (1 ft = 0.3048 m), each marked as derived with evidence." The
  coordinator's reading adds that a stated range keeps its own endpoints and
  that map data fills an elevation only where the label states none. A unit is
  never guessed (`GEOREFERENCING.md` 172, 229), so the conversion is expected
  only where a reading carries the unit. On 322 both readers dropped the foot
  mark, so its elevation may wait for review. Where the unit is read, the
  expected values are:

  | Slides | Feet, from and to | Metres, from and to |
  |---|---|---|
  | 321-323 | 6400 | 1950.72 |
  | 324-326 | 3300 | 1005.84 |
  | 328-330 (Guatemala) | 4800 | 1463.04 |

  A run fails if it converts by any other factor, fills a stated elevation from
  map data, or leaves unresolved an elevation whose unit it read. 327 states no
  elevation; map data may fill it only at a settled place (G37).
- **Places only the museum's records know (G36).** The owner: "McKinley I think
  is denali. That's what google search returned. I wonder how they arrived and
  the conclusions. We cant make wrong conclusions", then chose "Curator
  confirms": confirmed entries settle a field, unconfirmed ones never do. The
  coordinator's reading: the Davao "Mt. McKinley" (the labels read "Davao Prov.,
  Mindanao, P.I.") is not Denali, and S8's Mount Talomo is unconfirmed. Slides
  321 to 326 therefore go to review for their place until a curator confirms an
  entry, and a run that settles their place from any unconfirmed entry,
  Denali included, fails. Mt. Apo on 327 is a mapped peak: its place may settle
  from gazetteer evidence or stay unresolved (coordinator, 2026-09-24).
- **No Google content stored (G35, keeping G26).** From Google only the place
  ID, its outcome and a fingerprint are kept; Google's names, address parts and
  coordinates are never stored. Stored coordinates come only from credited open
  sources. Any of Google's content in a row, trace, log or lab folder is a
  failure.
- **D4 is off, D5 records findings.** While the owner holds D4 (the museum's
  published GBIF points), its occurrence check is off and sends nothing, so any
  GBIF occurrence request fails the run. D5's checks (their limits) record
  findings and never change a verdict (PLAN 2, coordinator rulings).
- **A single collecting date (G44).** The owner chose "Fill To, derived": "Date
  Visited To gets the same date, marked as derived from Date Visited From, so
  the record can clear on it." It is therefore not a reason on any of the ten.
- **The kind of a value (G45).** The owner chose "Yes, check the kind": "In
  fields no lookup checks, a value that doesn't look like its field's kind goes
  to review with a reason." A slide-preparation code (for example "VI-24-68-7")
  in such a field must bring that reason, and a run whose decision lacks it
  fails. In `verbatim_dts`, whose meaning is unconfirmed, it is a finding only.
- **`identified_by_irn`** is never on a label and does not block (G16, G43).
  Only 328 names a taxon, which may settle at genus (G25). Dates settle as
  written (G24).

What each label carries is tabled in `~/specimen-golive/reports/field-coverage.md`,
and the expected outcome per slide is in
`~/specimen-golive/reports/expected-outcomes.md`, both outside the repository.

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
that figure an upper bound. Until production's reserve-then-settle ledger
lands, every paid attempt without settled usage (an unknown outcome, or a call
that returned and then failed) is held at the full per-call bound: 16,000
tokens at the highest known price (coordinator, 2026-09-23; after #86). SAM 3 on
this workstation costs nothing. Every run's cost and the lab's running total
against its USD 5.00 share go into `run.json` and its report (G9, G30).

### Secrets

The runner never writes a token value. Every text artifact passes through a
redactor that removes the values of the known token variables and anything
shaped like a Hugging Face token, a bearer header, a Google access token or a
JWT. It also removes instance addresses, which PLAN 7.7 keeps out of shared
logs and issues: the SAM 3 endpoint's value and any `*.run.app` address, which
the app pins into a run's dependencies, and the SAM lab token. The runner never
reads `.env` or `.logfire/`.

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
  the integrity check expects each reading's input hash to be the image's rather
  than the crop's (`integrity.py` 112-116). A run with real readers therefore
  stops at `parse`, where the evidence phase raises the integrity error and the
  workflow records it as `external_outcome_unknown`. Specimen 1's first run
  found both: the seam in #79 (S3) and the recording in #80 (S4). Profiles in
  production are not affected. Synthetic mode stays a teaching fixture; the lab
  moves to `create_app(mode="emulator", ...)`, which gives production run
  semantics on local stores, once S3's on-demand trigger (T1a) and published
  pilot profile (T4) merge.
- The run stores no trace id and model spans carry metadata only, until S3's
  tracing work (S3 T5).
