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
| 2 Label segmentation | the run has regions made by SAM 3 with its parameters, and the lane's coverage check (G15) ran, as `coverage_check.outcome` on the run (#111; DATA_CONTRACT.md 4.1): for the ten, `confirmed` with the lab's own measure (every label box below at least half covered by a distinct region) agreeing, or `unconfirmed` while the lab's measure finds a miss, since the lane then sent the record to review, whatever its reason code | failed when `confirmed` passes a label the lab's measure finds uncovered; not checked for a false alarm (`unconfirmed` while the lab's measure finds every box covered: G15 sends the record to review, and the lab records it for calibration), for any other outcome, and outside the ten, where the lab has no layout; not built while the run carries no coverage check; blocked, with the app's blocker; substituted when the lab drew the regions |
| 3 VLMs | every region has one reading per profile route, each with model, provider, prompt version, input hash and a stored raw response | failed, or blocked with the blocker |
| 4 Raw transcripts to SQL | the run's `pipeline_run` row names this specimen, and there is one `model_observation` row with `independent` true per reading, with the snapshot's ids (DATA_CONTRACT.md 2) | not built while SQL holds no `pipeline_run` rows; blocked or failed when the run has no readings to project; failed on any mismatch |
| 5 Disagreement score | every region's transcript carries a ratio and `bounded-levenshtein-fraction-v1` | failed, or not built |
| 6 LLM first pass | the run records the first pass's decision and what each reader handed to the harness | not built |
| 7 Agentic harness | the run records tool calls with typed outcomes | failed on a GBIF occurrence request while D4 is held. PLAN 4.8's table lists GBIF only for species match (G23) and the held occurrence search. A request is: a GBIF record (by `source`, `provider`, `source_id`, `tool` or `tool_id`) whose identity or percent-decoded path names the occurrence search, with or without a host, or which carries occurrence query keys; any record naming `api.gbif.org/v1/occurrence`; a plain or escaped `"museum_published": true`, or an occurrence signal that supports or conflicts; receipt blobs showing any of these; or a request the runner counts, before sending, at `bounded_http` in the parent or on an injected `httpx` client, to `api.gbif.org` with the `/v1/occurrence` path or occurrence query keys. Failed on any GADM call (a `gbif_gadm` source or `gbif-gadm` adapter): PLAN 4.8 does not use GADM, not even as a measurement (coordinator ruling, 2026-09-25). GADM is not an occurrence request, so it stays outside D4. A call held by policy sent nothing and is skipped. Any other GBIF call is outside PLAN 4.8's table and is reported for the coordinator. Not checked while the runner's count is unavailable, or while tool calls are recorded (S4's checks to come); not built when the run records neither |
| 8 Queue decision | for the ten, needs human review with its reasons, their expected outcome (PLAN 8, 879-883); a person compares the reasons against the expected outcomes below and records any wrong one as a failure in the run's `verdict.md`, so the stage reads not checked; for other subjects, exactly one disposition with its reasons | failed when one of the ten gets any other disposition, goes to review with no reason, or has no disposition; blocked while `processing_blocked` or `retry_scheduled`, naming the blocker (or the reasons, when there is none) and the app's next step |
| 9 Linkage | every region, reading and transcript points to this specimen, asset and run. In SQL, stage 4 covers the readings; the check that SQL holds every artifact the final snapshot has (DoD-4; PLAN 8, 864-869) arrives with the lab's T3a | failed |
| Tracing | DoD-5 (PLAN 1): "Each run is one Logfire trace, linked from the record in the app, that shows SAM 3's parameters, every model call's system prompt and text input and output, the LLM first pass, the harness's tool calls and the queue decision" | not built while the run stores no trace id (`Run.trace_id`); not checked while it does, until the lab holds a Logfire read token (owner action) to read the trace; the lab's own root trace id is always recorded |

Statuses are passed, failed, blocked, substituted, not built (the stage, or the
record it is judged on, is not on this commit) and not checked (the record
exists, but the lab does not judge it automatically yet, or a person compares
it by hand, or the runner could not observe it, as when its request count is
unavailable). A blocked stage names the blocker and the step the app would run
next (`Workflow.next_step`). Checks for stages 4 and 6 follow the contracts as
S5 and S4 merge them; until then they read not built rather than guess at field
names. Stage 7 reads not checked once tool calls are recorded.

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

### Expected outcome for the ten (PLAN 8, 879-883)

All ten go to needs human review, with the right reasons: G42 keeps `PRD.md`
12.4's twenty mandatory fields, no label carries a determination date, and none
can be derived, so no slide can clear. A run that clears or defers one of the
ten, or sends it to review with no reason, fails stage 8 once the lane reaches
the queue decision; a person who finds a wrong reason records that failure in
the run's `verdict.md`, which the subject report carries (PLAN 8 step 3). The owner's words and the coordinator's readings
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

  A run fails if it converts by any other factor, converts an elevation that no
  reading gives a unit for, fills a stated elevation from map data, or leaves
  unresolved an elevation whose unit it read. 327 states no
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
  in such a field must bring that reason; a person who finds the decision
  without it records the failure in the run's `verdict.md`. In `verbatim_dts` it is a finding only: a coordinator hold (PLAN 2.3),
  since what that field holds is an open question and the owner's answer is
  pending.
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
  verdict.md  a person's verdict: written by a person, never by the runner;
              the subject report carries it
  state/  the app's blobs and local database for this run, unredacted: never
          shared or attached anywhere
~/specimen-golive/reports/<subject>.md
```

### Costs

The app records tokens, not money (`BudgetUsage` in `domain.py`; stage costs
are reservations only). The runner prices each reading's tokens with the route
prices in `docs/execution/LIVE_PILOT_COST.md` 42-47. It prices any other tokens
the run used, such as the extraction call, at the highest known price and labels
that figure an upper bound. Until production's reserve-then-settle ledger
lands, every paid attempt without settled usage is held at the full per-call
bound, 16,000 tokens at the highest known price: an unknown outcome
(coordinator ruling, 2026-09-23) and, as the lab's own extension after #86, a
call that returned and then failed. SAM 3 on
this workstation costs nothing. Every run's cost and the lab's running total
against its USD 5.00 share go into `run.json` and its report (G9, G30).

### Secrets

The runner never writes a token value. Every text artifact passes through a
redactor that removes the values of the known token variables (`HF_TOKEN`,
`HUGGING_FACE_HUB_TOKEN`, `HUGGINGFACEHUB_API_TOKEN`, `LOGFIRE_TOKEN`,
`LOGFIRE_READ_TOKEN`, `SPECIMEN_SAM3_ENDPOINT`, `SPECIMEN_SAM3_LAB_TOKEN`,
`SPECIMEN_GOOGLE_MAPS_API_KEY` and `HF_BILL_TO`) and anything
shaped like a Hugging Face token, a bearer header, a Google access token or a
JWT. It also removes what PLAN 7.7 keeps out of shared logs and issues:

- instance addresses: the SAM 3 endpoint's value, which the app pins into a
  run's dependencies, and any `*.run.app` host or address;
- the administrator's identity: any email address (an ADC error names the
  caller); the fields that name a person, redacted by field wherever they
  appear: `asset.uploader`, `audit[].actor`, `Transcript.actor`, and the SQL
  columns `actor_uid`, `created_by`, `uid`, `user_id`, `uploader_uid`
  (`SourceAsset.uploaderUid`) and `approved_by` (`ProfileVersion.approvedBy`); and the private values the file
  `LAB_REDACT_VALUES_FILE` lists, such as a signed-in UID and the GCP project
  number. That file must be under `~/specimen-release-private/` (PLAN 840), never
  in a repository. The runner refuses any other path, and writes nothing when
  the variable is unset or the file is unreadable or empty;
- billing and organization ids: `HF_BILL_TO`'s organization and the Logfire
  project URL's organization slug;
- more secrets: the SAM lab token, the Logfire read token, the Geocoding key
  (`SPECIMEN_GOOGLE_MAPS_API_KEY`), and the `AIza...` and `pylf_...` shapes.

Values under 8 characters are matched as whole words. The runner never reads
`.env` or `.logfire/`.

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
