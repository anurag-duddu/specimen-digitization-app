# Live processing implementation report

Owner: processing task `01a08219-2fcd-7001-9433-1ab249f1ac64`.
Coordinator: `01a07f48-a57c-71b0-9642-c9430886049c`.
Baseline: `a53f855e963b457c3ee2065f387609a193bb6f32`.
Branch: `codex/live-processing`.
Worktree: `/Users/anuragduddu/.codex/worktrees/908e/specimen-digitization-app`.
Initial implementation SHA (superseded by SAM provenance correction below):
`e497d949657b74270d21f932ac179a72644ed189`.
PR head includes this code plus report-only handoff updates; use the PR checks page
for current exact-head CI, avoiding a self-referential report-commit SHA.
GitHub main advanced externally to `1d297db520a6e31021e7bfa5e5f81b77e90cf618`
via PR5 during this work. This branch remains based on a53f855; local evidence is
not combined latest-main coverage. Delivery owns final integration/revalidation.

## Objective and scope

Deliver a runnable bounded production worker and SAM service for exactly the
first ten specimens frozen by the data owner. Processing owns worker, workflow,
reliability, provider adapter sections, worker containers and this report.
Data adapters, API, Flutter, deployment workflows and existing local services are
owned elsewhere and unchanged here. AGENTS and DEPLOYMENT were read completely.

No cloud object was downloaded, no museum image inferred, no paid provider call,
cloud provisioning, IAM change, migration, merge or deployment occurred here.
No fixtures count toward the ten. The earlier single-photo CPU SAM experiment is
external evidence of feasibility, not a pilot result or a calibrated benchmark.

## Decision and alternatives

Propose a single bounded Cloud Run Job using the existing SQL checkpoint engine:
1 task, parallelism 1, retry count 0, 1 vCPU/1 GiB, task timeout 1800 seconds,
worker loop lifetime 1500 seconds, individual external effects at most 120 seconds.
Timeout margin accommodates the final effect and process cleanup. A SIGTERM stops
new admissions; a host SIGKILL during an effect leaves its durable unknown intent.
A later execution reconstructs the ledger and blocks rather than automatically
repeating an uncertain paid effect. No background infinite service is required.

[Engine comparison](PROCESSING_ENGINE_COMPARISON.md) includes actual application
process-kill tests and an isolated Temporal worker AND persisted dev-server
kill/restart experiment. Temporal retries repeated an unguarded fixture effect;
the application guard prevented repetition. Google Workflows remains
**Not run**, documentation-based only. The proposed host is **Not confirmed
live**; this is not a completed cloud benchmark or production qualification.

## Worker launch contracts

`containers/worker/Dockerfile` installs the frozen existing `uv.lock`, runs as
UID10001, copies only explicit source/build files, includes no credentials and
uses Python3.12/uv0.12.5 image digests resolved from the registries on 2026-09-08.
No pyproject/uv changes were needed. Delivery owns image publication/runtime
provisioning; this branch adds no deployment automation.

Entrypoint: `specimen-worker --mode production --launch-policy /private/launch.json
--source-manifest /private/manifest.json`. Options `--check-config` (no ADC,
network or model use), `--once`, and `--max-seconds 1..1500` are supported.
No-config production exits2 with fixed JSON blocker
`pilot_launch_and_source_manifest_required`. `--help` exits0.

Required configuration:

- `SPECIMEN_WORKER_ACTOR_UID`: private assigned actor, rechecked against SQL
  memberships every tick; no administrator inferred or hardcoded.
- Existing SQL Connect/GCS configuration and least-privilege runtime ADC, owned
  by data/API. Actor context is established before SQL access.
- `SPECIMEN_APPROVED_INFERENCE=true`: coordinator authorization, not a budget.
- `HF_TOKEN`: existing secret injected by approved runtime; never printed.
  `SPECIMEN_HF_SECRET_RESOURCE`: matching numeric Secret Manager version path,
  `projects/specimen-digitization/secrets/<existing-secret>/versions/<number>`.
  `latest` is rejected by the launch contract. Existing secret name/version and
  live token rights are **Not confirmed** in this task.
- `SPECIMEN_SAM3_ENDPOINT`: approved HTTPS Cloud Run service URL, and
  `SPECIMEN_SAM3_REVISION`: exact existing `SAM3_MODEL.revision`.
- `SPECIMEN_LAUNCH_POLICY_SHA256`: independent raw-file digest for launch policy.
  Production rejects emulator environment variables.

The private `PilotLaunch` JSON model in `worker_launch.py` is version
`authorized-ten-v1`. It contains the raw data manifest SHA, matching authorization
reference, one exact scope, exactly ten unique specimen IDs and immutable
application `sha256:generation` references, timezone-aware expiration,
positive total/per-specimen cost limits, per-specimen call/token caps, per-effect
timeout and the pinned HF secret reference. Ten conservative per-specimen cost
allocations must fit the total. This is a post-import binding, not an importer.

The source file must be data's `specimen-pilot/v1`, `ready`, exact ordered ten
with matching scope, source object generation/hash/size and matching
application_source/source_object_index mapping. A `metadata_frozen` inventory
cannot launch. Both raw file hashes are checked before cloud clients are made.
Data owns the authoritative private source selection and hash extraction. No
runtime flag may expand this denominator. A new cohort needs user review.

Discovery uses only ten explicit IDs and never queries the collection-wide due
queue. Admission validates scope, original digest, object generation, non-synthetic
profile, remaining deadline and positive bounded execution budgets. The workflow
rechecks admission on the actual fetched snapshot before effects, preventing a
read/admission race from bypassing the guard.

A SQL CAS document `kind=pilot_launch`, UUID derived from the frozen manifest SHA,
reserves the full conservative per-specimen cost allowance before first effect.
It pins run ID, execution policy and routes. Restarts reuse reservations;
reprocess/new-run or changed policy/config requires reconciliation. Reservations
are not refunded on crash, rejection, uncertain outcome or partial success.
Same-cohort revised launch configuration cannot silently reset the ledger.
This bounds authorized estimates; it is not a provider-enforced dollar account
limit. The approved request reservation must cover each stage's maximum model
requests/tokens, and authoritative prices must be reviewed before launch.

The two transcription routes remain Qwen/Novita and Muse/DeepInfra with separate
image-only calls; prior readings are not input to the other route. Raw provider
responses, crop identity, model/provider/prompt and usage are retained by existing
adapters. SAM now checks the inference approval flag before remote work, closing
an existing gap. Model HTTP5xx errors are ambiguous and cannot auto-retry;
definitive authentication/rate-limit rejections retain existing policy behavior.

## SAM and policy gates

A deployable optional CPU SAM target is implemented from the earlier proven
Transformers implementation; see final SAM artifact section below. Model access,
license acceptance, runtime artifact qualification and actual authorized-ten
execution remain separate gates. No GPU provision is proposed for this pilot.

The normal non-synthetic workflow currently cannot reach raw inference:
`collection_runtime.classify_and_select` calls `select_profile` with a draft
insects profile; `profile_runtime.bind_profile_rules` requires resolved risk
registry; `Sam3Service.segment` independently checks `pinned_risk_resolution`.
Do not activate a synthetic policy or invent approval/calibration to bypass it.

Coordinator approved implementation of the separate `EvidencePilotWorkflow`
entrypoint in `evidence_pilot.py`. It pins draft source/profile/SAM/language
settings, preserves risk as unmeasured/blocked, retains segmentation and two
independent readings, creates unresolved transcripts for explicit human correction,
and stops as `processing_blocked`, disposition None,
`pilot_evidence_review_required`. It never classifies/parse/lookup/finalizes/clears.
The normal path remains unchanged except an explicit denial of any pilot marker.
No profile is published and no institutional risk policy is invented.

Enable only with `--evidence-only --evidence-profile /private/draft-profile.json`,
launch `evidence_only=true`, `evidence_profile_sha256` matching raw private profile
file and `SPECIMEN_APPROVED_EVIDENCE_PILOT=true`. The file must be a non-synthetic
unapproved draft `CollectionProfile` with explicit SAM settings, existing two
model routes and matching collection ID. Every step revalidates the exact marker,
profile snapshot and current adapter/prompt/provider pins. Only a pristine run may
enter. The retained marker has exactly version, launch_sha256,
source_manifest_sha256, profile_sha256, runtime_pins_sha256. Empty/malformed marker
presence never counts as an uninitialized run.

API owner independently blocks pilot lifecycle actions, reprocessing, ordinary
process, classification, approve/defer and geometry changes that replace a Run;
corrections retain original marker/risk/blocker and no disposition or human
approval. These API/client changes are integration dependencies, not in this PR.
Existing dispositions are unchanged. Full institutional processing stays gated.

## Cost inputs for approval

Indicative us-central1 compute only, no free tier assumed:
worker 1vCPU/1GiB for1800s costs about $0.036 at job rates
$0.000018/vCPU-s and $0.000002/GiB-s. CPU SAM4vCPU/16GiB for ten120s requests costs
about $0.1632 at active request rates $0.000024/vCPU-s and
$0.0000025/GiB-s, plus request and startup time. Earlier unrelated single-image
CPU evidence took about50s total on4CPU/8GiB; pilot performance is not measured.
These are arithmetic estimates from [Cloud Run pricing](https://cloud.google.com/run/pricing),
checked2026-09-08, not a project spending cap. Cloud SQL baseline, builds,
artifacts, checkpoint storage/download, network and HF inference are excluded.
HF stage reservations need separately reviewed current route prices and max
image/token/request counts. Dollar budget is still **Blocked: user input**.

## Verification and artifact evidence

- `uv sync --frozen`: passed,81 packages; host Python3.11.16, containerPython3.12.
- `uv run pytest tests/test_worker_launch.py tests/test_worker_recovery.py -q`:
  21 passed,1 skipped (seeded SQL required),1.34s at initial guard milestone.
- Engine failure tests:13 passed,1 real-SQL deselected; Temporal fixture outcomes
  retained under `qa-evidence/processing-engine/` with hashes.
- `docker build -f containers/worker/Dockerfile -t specimen-worker:processing-local .`:
  passed; local OCI manifest list `sha256:b4f6ae06b8b29cc6f0e2574e9f617935accc809d2fea6c5ed42e76386acd57d4`.
  This is a local build, not a registry publication or deployed revision.
- Full tests, canonical `scripts/ci/verify.sh`, container smoke, SAM tests and PR CI:
  final local results appended below; PR CI recorded after submission.
- A mistaken `uv run pytest tests/test_production.py -q` found no such file (exit4,
  no tests); corrected to actual adapter/worker suites. No gate was weakened.

Additional safety review found and fixed two issues: silent success with ten
blocked records, and generic retry clearing an unknown run blocker. Each pilot
step now creates a durable CAS dispatch token before workflow entry; only a
positively returned matching retained revision clears it. Unknown/orphan tokens
survive a process crash and API state changes, requiring reconciliation. A crash
during a local-only step may conservatively block too. Admission problems persist
as sanitized blockers only for matching authorized records. Final summaries
re-read all ten and persist exact counts/per-ID status; evidence review is distinct
from completion, pending/blocked never exits as success. CLI emits exit2 for
`evidence_review_required` to avoid implying full pipeline completion.

Private configuration reads reject Git-contained paths, symlinks, pipes/devices,
group/world permissions and oversized files before parsing. Files must be staged
owned/readable by worker UID10001 with0600/0400 and identical raw hashes; a root
owned0444 projected mount is not directly usable. Data's richer source freezer
and this runtime ready-schema validator must be cross-checked on the frozen packet.

## Recovery and remaining ownership

Stop the approved Job execution to stop new work. Retain SQL records, manifests,
claims and evidence. A restarted worker may resume known checkpoints with the
same launch binding; unknown external outcomes require downstream receipt
inspection and explicit reconciliation. Never erase a ledger, regenerate a
manifest, or create a new run merely to retry a potentially accepted call.
Delivery rollback chooses a reviewed immutable worker image; rolling back code
cannot establish that a remote effect failed. Revalidate the exact image,
source/schema/secret pins, SQL restart/cancellation fencing and provider receipts.

Data: freeze/import exact10 and prove SQL/GCS durability. Coordinator: concrete
budget/provider policy and evidence-only-mode decision. Delivery: separately
approved Job/service/IAM rollout. QA: authorized source bounds, restart/fencing,
real independent observations, review persistence and no automatic clearance.
No cloud launch or completed end-to-end product is claimed by this report.

PR: [9](https://github.com/anurag-duddu/specimen-digitization-app/pull/9).
[Current PR checks](https://github.com/anurag-duddu/specimen-digitization-app/pull/9/checks).
Initial exact implementation run:
[34261014978](https://github.com/anurag-duddu/specimen-digitization-app/actions/runs/34261014978).
All five jobs were in progress at report submission. Report-only updates may
supersede that initial run; the live PR checks page is authoritative. Final CI
outcome is also sent to coordinator with full head SHA. No merge authorized.

## SAM CPU serving target and evidence (2026-09-08)

Confirmed implementation: `src/specimen_digitization/application/sam3_server.py`
exposes `POST /v1/segment` and `GET /health/live`; import, `--help` and `--version`
never load a checkpoint. `containers/worker/sam3.Dockerfile` is an opt-in separate
CPU image with a full `SOURCE_SHA` build argument and OCI revision label. Its
61-package Python 3.13 / Linux amd64 dependency lock includes artifact hashes;
`torch==2.8.0+cpu`, `torchvision==0.23.0+cpu`, `transformers==5.14.0` and
`pillow==12.3.0` are fixed. No pyproject/uv lock edits were needed for SAM.

The engine reuses the Transformers CPU loading path from the separately authorized
real-model owner's `scripts/evaluation/sam3_local.py`. That owner's
`docs/execution/REAL_MODEL_TEST.md` reports actual pinned SAM3 CPU execution on one
other image, in a Linux container limited to 4 CPUs / 8 GiB, at 27.04 seconds for
`label` and 22.96 seconds for `insect specimen`. Those observations support trying
a bounded CPU service; they do not prove performance, image coverage, transport,
or results for this pilot's ten specimens. No source image or private result from
that task was reused. Native SAM GPU installation was investigated, then excluded
because the CPU route had actual local execution evidence.

The supported upstream API and original-pixel masks are documented by
[Hugging Face SAM3](https://huggingface.co/docs/transformers/model_doc/sam3).
The server downloads only `facebook/sam3` at
`3c879f39826c281e95690f02c7821c4de09afae7`, records SHA256 for every safetensors
file, then loads with `local_files_only=True` and `trust_remote_code=False`.
The model's [gated SAM license/access](https://huggingface.co/facebook/sam3)
requires human acceptance and a permitted existing HF secret. Access by the live
service identity and exact checkpoint acquisition remain Not confirmed.

Candidate hosting: private authenticated Cloud Run CPU service, 4 vCPU, 8 GiB,
concurrency 1, max instances 1, min instances 0. Budget approval, CPU/architecture
fit, region, startup cold-load time and memory including downloaded checkpoint
cache remain deployment gates. The request has a 120-second hard process deadline;
Cloud Run request timeout alone does not stop model computation. Each launch has
an absolute expiry at most one hour away, including model loading, and refuses
new work within 125 seconds of expiry. Those limits bound application admission;
they are not a cloud billing cap. Deployment must retain external spending
controls and reviewed scale/shutdown settings.

Runtime configuration: `SPECIMEN_SAM3_ENABLE=authorized-pilot`,
`SPECIMEN_SAM3_BUDGET_AUTHORIZATION`, `SPECIMEN_PILOT_MANIFEST_PATH`,
`SPECIMEN_PILOT_MANIFEST_SHA256`, `SPECIMEN_SAM3_EXPIRES_UNIX`,
`SPECIMEN_SAM3_AUDIENCE`, `SPECIMEN_SAM3_CALLER_EMAIL`,
`SPECIMEN_SAM3_OUTPUT_BUCKET`, pinned Secret Manager `HF_TOKEN`, and Cloud Run's
`K_SERVICE` / `PORT`. Never commit actual values or the manifest. The source
manifest is a private externally hash-pinned `ready` specimen-pilot/v1 document
with exactly ten unique specimens in one organization/collection. Its schema is
aligned with the data owner; integrated validator conformance remains QA-owned.

Authorization uses worker-only Cloud Run Invoker IAM plus application verification
of Google ID token audience, verified email and exact caller identity, following
[Google service authentication](https://docs.cloud.google.com/run/docs/authenticating/service-to-service).
The client supplies the signed `Authorization` header. SAM requests now include
specimen, organization and collection IDs alongside asset and source hash/reference.
Every field must match the manifest before storage or model calls. Read operations
address only the manifest's original GCS bucket/name/generation and verify exact
size and SHA256. Read byte limits and a 16-megapixel decode bound fail closed.

The SAM identity needs source-object get and evidence-prefix object create/get;
no listing, overwriting or deleting objects. Create-only GCS claims fence each
manifest/specimen before inference. A matching completed request returns its
retained response on restart. An existing claim without a matching completed
response blocks with `sam3_outcome_unknown_requires_reconciliation`; changing
run IDs cannot cause another automatic inference. A shutdown, storage failure,
invalid model output or timeout never clears the claim. Recovery requires explicit
inspection of downstream artifacts; never delete claims to obtain automatic retries.

Binary PNG masks preserve original image dimensions, have immutable generation,
SHA256 and byte-size evidence, and retain scores and fixed 0.5 confidence/mask
thresholds. Region boxes are derived from the retained binary masks. The response
retains request hash, manifest hash, source generation/hash/size, model revision,
checkpoint hashes and implementation versions. No masks, no usable regions, invalid
scores/shape/binary values and output bounds produce explicit blocked errors;
there is no synthetic fallback or fabricated mask reference.

Local fixture verification: `uv run pytest -q tests/test_sam3_server.py` passed
20 tests in 1.07 seconds. Tests cover scope/source denial before side effects,
request and source bounds, private ready10 manifest/hash, output integrity,
immutable mask evidence, changed-request and pending-claim replay denial across
server instances, concurrency and expiry, redacted errors, and exact checkpoint
pin/local-only loading. These tests inject CPU fixtures and do not run SAM inference.
Focused pre-commit checks passed all applicable filename/security/format checks.
Docker build and network-disabled import/help/version/blocked-start checks
passed; exact artifacts and outcomes are appended below. No paid model
calls, model downloads, cloud mutations, GPU provisioning or deployments occurred.

SAM review corrections: masks now use the application's canonical
`application/sha256/<hash>` object path and `sha256:generation` Region reference,
so the existing worker `GcsBlobs.get` and evidence integrity checks can read them.
`SPECIMEN_SAM3_OUTPUT_BUCKET` must equal the worker's evidence bucket. Existing
content-addressed masks are reused only after generation/size and bounded streamed
SHA256 verification; mismatches block. GCS source and receipt reads also stream
with a byte limit independent of Range or Content-Length. Pending claims remain
under `sam3/<manifest-sha>/<specimen-id>/` and are never overwritten.

The private manifest reader now opens with no symlink following and nonblocking
flags, then verifies a private regular file, so FIFOs/symlinks cannot block startup.
Delivery must stage a manifest readable by container UID 10001 with private mode;
default world-readable secret-volume files are rejected. Image provenance is
written into `/app/specimen_digitization/_build.json` at build time; `--version`
reads this artifact and ignores any runtime SOURCE_SHA environment override.

Memory sizing correction: the previous 8 GiB CPU test mounted its 3.44 GB model
from host disk. Cloud Run downloads into an in-memory writable filesystem, so an
8 GiB cold start has not been shown to fit. Use 4 CPU / 16 GiB as the review
candidate unless a reviewed model artifact mount avoids that overlap. Cold-start
memory and timing still require measurement. No GPU resource is required by this
implementation.

Final SAM local validation checkpoint:

- `uv run pytest -q tests/test_sam3_server.py`: **24 passed**, 0.86 seconds.
  Additional checks exercise the real worker `GcsBlobs.get` reference grammar
  against a streamed fixture, immutable mask reuse/mismatch and symlink/FIFO
  manifest rejection. No real inference is counted by these fixture tests.
- Final focused pre-commit: all applicable hooks passed, including both secret
  scanners. `git diff --check`: passed.
- `docker build --platform linux/amd64 --build-arg SOURCE_SHA=<baseline SHA>
  -f containers/worker/sam3.Dockerfile -t specimen-sam3-local:review .`: passed.
  Local OCI manifest list:
  `sha256:21c97926ffb0489a30c2f52e3b75227fe4851d9b1902ffd0a32abe754c0e6d4e`.
  Build log: `/tmp/specimen-sam3-final-build.log` (local, non-secret).
- Network-disabled containers at 4 CPU / 8 GiB / 128 PIDs passed `--help`,
  `--version`, and imports of `Sam3Model`, `Sam3Processor` and the server.
  `SPECIMEN_SOURCE_SHA=spoofed` could not override the embedded reported SHA.
- Network-disabled unconfigured startup exited 1 with the expected
  `sam3_requires_authorized_cloud_run_launch` block before checkpoint loading.
- This was an uncommitted working-tree build labeled with the baseline
  `a53f855e963b457c3ee2065f387609a193bb6f32`, **not a release provenance claim**.
  Delivery must rebuild with the final committed candidate SHA and record that
  image digest. No image was published and no cloud workload was launched.

## Final independent review changes

The integrated PilotWorker/EvidencePilotWorkflow local fixture produced exactly
one segmentation fixture call and two reading fixtures, retained the explicit
review block and no clearance, with zero worker errors/conflicts. This tests real
orchestration and SQL ledger behavior against generated fixtures, not real models.
Independent review found declarative processing-derivative lineage could admit
unfrozen pixels. The original-only evidence pilot now rejects any processing
derivative before image access; normal processing behavior is unchanged. API is
coordinating original-image review attribution separately. A forged finalized
pilot record is blocked and can never make the launch summary report completion.

Private-path checks now resolve ancestor directories, preventing a symlinked
ancestor from hiding Git membership, and require files owned by the process UID.
Malformed marker presence cannot initialize a pristine pilot run. Added regression
coverage: latest local worker/evidence suites32 passed,3 warnings,1.98s.

The first canonical `scripts/ci/verify.sh` passed all local gates including the
release web build. A final rerun includes the last independent-review fixes;
results and PR exact-head checks are recorded in the handoff below.

## Final canonical gate

`scripts/ci/verify.sh` completed successfully on the final code candidate:
413 Python tests passed,26 skipped,7 warnings in118.73s; Flutter analysis no issues;
76 Flutter tests passed,7 explicitly skipped; release web build passed. Repository
hooks, both secret scanners, actionlint and shellcheck passed. Skipped external
emulator/platform fixture tests are not live proof. Log:
`/tmp/processing-final-verify.log`. Final targeted guard/evidence regressions:
32 passed. No production deployment performed.

Worker image built with embedded baseline source provenance for local smoke;
`--version` ignored a spoofed runtime `SPECIMEN_SOURCE_SHA`, and no-config production
returned the expected exit2 blocker. Final committed source image rebuild and
PR CI provenance are separate handoff records below.

## Committed-source image proof

The worker candidate was rebuilt with
`SOURCE_SHA=e497d949657b74270d21f932ac179a72644ed189` using the frozen code commit.
Local OCI manifest list:
`sha256:d8b3f7ecd0ef16380a5f2c4b2361d50c382de33bd0007faf06148cc022bc8646`.
Build log `/tmp/processing-worker-candidate-build.log`. No image publication or
cloud run occurred. Delivery must rebuild from its final integrated commit;
local image proof does not qualify the future combined candidate.

## Independent QA correction: SAM response provenance

QA reproduced a P2 in the initial frozen implementation: the client accepted
valid-looking region geometry while ignoring missing/wrong request, manifest,
source and checkpoint metadata, and accepted a noncanonical mask reference.
That could allow paid reading of stale or unbound SAM regions. Initial image/test
proof above does not erase that finding; this corrective commit supersedes it.

The client now refuses outbound SAM work without an expected binding constructed
only from the private frozen ready manifest, worker evidence bucket and launch
policy. `PilotLaunch.sam3_checkpoint_files` is now required at production startup:
a reviewed exact filename-to-SHA256 map for model weights AND processor/config
JSON/text files, including at least one safetensors file. The map is part of the
pinned launch-policy digest and runtime dependency digest. It cannot be learned
from the untrusted response. No checkpoint hashes are guessed; generating and
approving that immutable model-artifact manifest is a remaining launch gate.

Server and client share compact, sorted, non-NaN canonical JSON hashing. A valid
response must match the submitted request hash, frozen manifest, exact source
bucket/object/generation/hash/size, fixed model revision/implementation, expected
checkpoint file map and its aggregate hash, and pinned thresholds. Each region
must have deterministic ID/order/asset/geometry and canonical immutable mask
reference matching output-bucket/path/hash/generation/size/encoding metadata.
Missing fields, malformed/duplicate-key JSON, forged self-consistent checkpoint
maps, wrong metadata or mask bindings stop processing before transcription.
The raw rejected response is retained with its rejection state; local input
identity is never represented as accepted model provenance when validation fails.

The normal production adapter also requires explicit expected SAM provenance;
it no longer accepts a configuration-free geometry-only service response.
No credentials, model artifacts, source samples, deployments or paid calls were
used to reproduce or correct the issue. Corrective local gates and exact-head CI
are reported via the PR checks and coordinator handoff.

## QA response-binding correction

The SAM client previously accepted a model ID/revision and region shape without
binding the response to the request, manifest, source or checkpoint artifacts.
`sam3_effect.validate_sam3_response` now requires all of those bindings. The trusted
launch supplies the exact manifest SHA, original bucket/name/generation/hash/size,
worker evidence bucket, and checkpoint artifact map. Missing expected bindings
prevent an outbound HTTP call. The returned checkpoint map must equal the trusted
map, including model safetensors and downloaded configuration/tokenizer JSON/text
files; a self-consistent forged map and aggregate hash are rejected. Client,
server and stored request provenance share canonical JSON byte serialization.

Responses also require canonical content-addressed mask paths and SHA/generation
references, matching evidence bucket, bounded size, fixed thresholds, finite scores,
ordered original-pixel geometry and deterministic region identities. Rejected raw
response bytes remain retained while region/transcription progression is blocked.

Validation: `uv run pytest -q tests/test_sam3_response_binding.py
 tests/test_sam3_server.py tests/test_sam3_runtime.py` passed **71 tests in 10.69s**.
This includes an actual localhost HTTP reply through the isolated transport and
Workflow: forged request hash remains retained, creates no regions/observations,
remains blocked after restart, and makes zero transcription calls. A separate
fixture drives the actual server response into the client validator. All model
and cloud data in these checks are fixtures; no live model or cloud call ran.
Focused pre-commit checks and `git diff --check` passed. Container/source SHA from
the earlier SAM checkpoint is superseded by this source change and must be rebuilt
by the processing/delivery owner on the final committed candidate.

Corrective focused suites:104 passed in11.17s. This includes71 SAM
server/response/runtime cases, a legitimate full server-to-client fixture,
missing/wrong request/source/manifest/checkpoint/mask provenance, and an actual
local HTTP forged response through Workflow. That run retained the rejected raw
body, stayed blocked with no regions/observations, and did not call SAM or a
reader after restart. These remain zero-model, zero-cloud fixtures.

Delivery's first combined SAM build used Docker's ARM64 host default and rejected
an ARM64 MarkupSafe wheel against the Linux AMD64 lock. Previous successful SAM
builds explicitly selected `--platform linux/amd64`. No hash was relaxed or vendor
hash silently added. The target now checks TARGETARCH=amd64 before installation.
Torch2.8.0+cpu and Torchvision0.23.0+cpu use exact official CPython3.13 LinuxAMD64
wheel URLs with SHA256 hashes; all other packages resolve only from PyPI.
The broad extra index and unsafe-best-match resolver option were removed.
The ordinary transitive package versions are unchanged. Both wheel URLs/hashes
were verified against the official PyTorch CPU indexes on2026-09-08.
The corrected container is being rebuilt before the corrective freeze.

The first corrective canonical run exposed one stale test fixture:
`test_profile_runtime` returned the old geometry-only SAM envelope and therefore
correctly blocked with `sam3_provenance_configuration_required`. Result was
457 passed,1 failed,26 skipped. The fixture now models the complete expected
response and immutable mask generation; the original profile/history assertions
are unchanged. Its targeted check passed (1 pass,1 explicit SQL skip). The full
canonical gate is rerun below before push; no response check was relaxed.

Corrected Linux AMD64 SAM image build passed with isolated package sources;
local review OCI `sha256:170fd73665810c7ea72c4146e0f6322990e89818e56f8643341b0189968e82a4`.
It is a working-tree review build labeled with prior head8e889dc; final release
images must use the actual committed/integrated source SHA. No model was loaded.

Runtime input materialization is owned by delivery after the corrective freeze:
`runtime_input_materialization.py` will copy explicitly mounted, hash-pinned
read-only inputs into UID10001-owned0600 files in a0700 directory, preserving raw
bytes, exclusive creation and cleanup. Delivery owns optional worker/SAM startup
wiring and real AMD64 non-root mount tests in the combined candidate. Existing
strict readers are unchanged; unmaterialized root0444 mounts remain rejected.

Corrective canonical `scripts/ci/verify.sh` passed after the fixture repair:
458 Python tests passed,26 skipped; Flutter analysis,76 Flutter tests (7 skipped),
release web build, repository and security gates all passed. Log:
`/tmp/processing-correction-final-verify.log`. Corrected SAM Linux AMD64
network-disabled imports and version smoke passed; no model was loaded.

A concrete model pin candidate is available privately at
`/Users/anuragduddu/.codex/private/live-rollout/processing/sam3-checkpoint-candidate-20260908.json`
(mode0600). It hashes eight existing cached model/config/text files; every cached
HF download metadata record matched the exact pinned SAM revision. No weights
were downloaded and no source image was read. Aggregate model-artifact SHA:
`9089029b241c8342be41225b51531bf0457f2db0c3b9896c844b22b3487ac9b8`;
private candidate file SHA:
`05f4e3e81d9e4a2cc645b433a4dbafff6b1fc0e262adc03a953adc4269b26c2b`.
Status remains cached model artifact candidate requiring review; this does not
approve inference, establish license/access today or replace the frozen-ten gate.
