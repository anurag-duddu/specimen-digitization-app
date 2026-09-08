# Release runtime qualification — 2026-09-08

Owner task `01a082b4-a9bd-7392-a73b-57ca45532fb7`, model/effort
`gpt-6-astra/xhigh` confirmed by coordinator inspection of turn context.
Worktree `/Users/anuragduddu/.codex/worktrees/7471/specimen-digitization-app`,
branch `codex/release-runtime`, base `61d82aed64816802cd6ac00ac11e307a30c2bd8e`.
Coordinator `01a082b2-c2c3-70d2-be90-7bfb622c9102` owns integration/release.

Status: runtime source through d859ac6 passes canonical checks and independent
scoped review; actual connector integration and production processing remain
separate gates. Production processing is **Not confirmed**.
The baseline main already includes prior API, worker, SAM and materialization
corrections. Historical unmerged statements in LIVE reports are not current
blockers. The total shared first-ten spending ceiling is USD 5, with USD 4 as
the working target, without a reset between sessions, retries or days.

## Confirmed repairs and TDD evidence

1. SAM's expiry timer was non-daemon. A model construction exception or normal
   return from Uvicorn kept Python alive until expiry, potentially one hour.
   Two actual subprocess tests failed after eight seconds on the original code;
   neither reached a model/provider/cloud effect. The timer is now daemonized
   and cancelled in `finally` after failure or completed serving. The absolute
   expiry remains active throughout model loading and serving.
2. The pinned SAM container's Hub client attempted a remote repository-tree
   request with cached weights and `HF_HUB_OFFLINE=1`, then failed with
   `OfflineModeIsEnabled`. SAM now explicitly forwards the SDK's parsed offline
   setting as `snapshot_download(local_files_only=...)`. Both online/offline
   forwarding regressions failed before the fix. Model ID/revision and
   `trust_remote_code=False` remain unchanged; no dependency lock changed.

Positive shutdown control: actual SIGTERM during a stuck synchronous SAM handler
already terminated the original runtime after about five seconds. It remains
covered; this was not a reproduced defect and no replacement server was added.

Executed baseline: `uv run pytest -q`, **781 passed / 26 opt-in skipped**, 122.37s.
Lifecycle/provenance/server/materialization focused pass after repair 1:
**82 passed**. Lifecycle/server pass after repair 2: **29 passed**.
Implementation commit: `87117c2067cef01c093fc6e99e2af670d7d93e7e`.
Canonical `scripts/ci/verify.sh` exited 0: **785 Python passed / 26 opt-in
skipped**, **120 Flutter passed / 7 opt-in skipped**, Flutter analysis, release
web build and repository/security checks passed. Log:
`/tmp/specimen-release-runtime-verify-20260908.log`. The final test-boundary
assertion/formatting-only follow-up passed **29 focused tests**; commit hooks
also passed. No runtime-owned PR or push was performed.
The initial Git branch/cache/Docker socket sandbox restrictions required approved
escalations; none was bypassed. No current tool wait is represented as a pass.

## Runtime/configuration contract for delivery

| Runtime | Start/configuration | Health/version | Stop/restart |
| --- | --- | --- | --- |
| API | Existing `containers/api/Dockerfile`; embedded exact `SOURCE_SHA`; `specimen-api --mode production`; PORT defaults 8080; explicit Firebase project/number/app allowlist, exact CORS origins, SQL location/service/connector, approved bucket and pinned readiness object/generation from LIVE_API | `/health/live` is process-only; `/health/ready` is cached read-only named SQL query plus object metadata, not model or write proof; `/version` embeds source/contract/mode | Existing 8s ASGI drain and 9s hard watchdog; one process; data remains external |
| Worker | Existing `containers/worker/Dockerfile`; `specimen-worker --mode production --launch-policy <private> --source-manifest <private>` plus evidence-only/profile flags when authorized; external launch hash, exact ten manifest/checkpoint pins, actor and HF secret version, inference approval and approved SAM endpoint/revision | `--version` reads embedded source; `--check-config` validates private launch inputs and returns `live_services_verified:false`; final summary reloads all ten and cannot equate pending/unknown with completion | SIGTERM sets stop between work steps; active model subprocess is bounded by launch timeout; durable dispatch/intent fences prevent replay. `--max-seconds` 1..1500 is a scheduling bound, not a hard bound on cloud SDK teardown |
| SAM | Existing AMD64-only `containers/worker/sam3.Dockerfile`; UID10001; authorized-pilot enable flag, budget reference, K_SERVICE, pinned private ready manifest, caller/audience, evidence bucket, offline read-only checkpoint cache with required aggregate pin, and absolute expiry; no HF credential; startup window >125s and <=3600s | CLI `--version` gives source/model/revision/implementation without loading; `/health/live` is exposed only after synchronous model construction. No separate deployed readiness/version HTTP endpoint exists | One process, one model request at a time; 120s request hard timer, 5s drain, absolute expiry including startup. New timer repair prevents a failed startup or returned server from waiting until expiry |

`--materialize-config` keeps strict readers intact while copying hash-pinned
read-only mounts into private UID-owned runtime files. No credentials, images,
model weights or private packets belong in build context. API must not receive
provider credentials. Worker/SAM require separate narrowly scoped identities.

Worker SQL constructor currently uses fixed defaults: project
`specimen-digitization`, location `us-east4`, service
`specimen-digitization-service`, connector `specimen-server`, and the approved
Firebase Storage bucket. Unlike the API, worker startup does not read API SQL
environment overrides. Delivery must bind the same actual endpoint in both
processes; a changed SQL endpoint requires an explicit worker configuration
repair. Workflow initialization attaches graph blob storage, so large retained
graphs do have storage in the production worker after construction.

## Audit of processing and persistence

Auth uses real Firebase Admin signature/claim verification, revoked/disabled
user checks, verified email, numeric App Check audience, exact issuer and app
allowlist. Existing local RSA tests are stronger than mocked claims, but do not
prove acceptance of Google-issued production tokens. Memberships remain server
SQL rows and the verified actor is carried into scoped named operations.

Intake and object reads retain generations, digests, size limits and scoped
binding. SQL records use revision/CAS saves; large graphs are immutable blob
references. Model work is reserved before dispatch. The stable manifest ledger
rejects policy replacement and unknown dispatches across restarts. SAM receipts
bind request/manifest/source/checkpoint/mask artifacts before reading proceeds.
Each reader receives only its own source crop and pinned prompt; peer readings
are excluded. Raw responses, crop hashes, model/provider/prompt and token usage
are retained. Evidence-only runs stop at `pilot_evidence_review_required`, with
unresolved readings, no disposition, no invented calibrated risk and no clearance.

Actual issued Auth/App Check tokens, production ADC, SQL operations, object
writes/reads, ten-source model results and deployed restart recovery remain
**Not confirmed**. Local suites and image/container construction do not close
those gates.

## Current pricing, cardinality and conservative reservations

Public primary sources checked 2026-09-08: [Novita pricing](https://novita.ai/pricing)
lists Qwen input/output USD 0.20/0.70 per million tokens; [DeepInfra Muse API](https://deepinfra.com/meta-models/Muse-Glimmer-30B/api)
lists USD 0.30/1.20 and context 131,072. Coordinator's current authenticated HF
catalog check confirms both pinned routes at those rates/context. [HF billing](https://huggingface.co/docs/inference-providers/pricing)
describes passing through provider rates. No free credit or cache discount is
assumed. Catalog/access and pricing must be rechecked before approved paid work.

This calculation requires coordinator commit
`2964e7b8288ab2e9baf195955519389e67e8b644` (PR15), which caps each generation at
4,096 tokens and preserves the two-request limit. It is not included in this
runtime branch's baseline. Conservatively reserve each of two requests for the
full 131,072 input tokens plus 4,096 output tokens; that overcounts a shared
context window deliberately and does not rely on first-response usage reporting.

| Stage | Conservative reservation USD |
| --- | ---: |
| Qwen/Novita one reader adapter, including schema retry | 0.0581632 |
| Muse/DeepInfra one reader adapter, including schema retry | 0.0884736 |
| Both independent readers for one region | 0.1466368 |
| Twenty regions across the ten specimens, readers only | 2.932736 |

Current runtime crops original pixels and encodes PNG without a token-count
preflight or provider-specific image-token constraint. A pixel/byte limit alone
does not establish the billed token count after provider preprocessing and
schema retries. The reviewed public API documentation did not establish a lower
shared image/token bound for these exact routes. A tighter assumed 10,000-token
scenario is not an enforceable reservation. No images were downsampled, regions
removed, tokenizer substituted or model/provider policy changed to fit the cap.

SAM accepts 1..64 masks. For R retained label regions, the evidence lane needs
`1 + 2R` external stages and at most `1 + 4R` external requests without workflow
retries, including two schema requests per reader adapter. A safe workflow retry
reserves another complete stage allocation; default maximum attempts is three.
Unknown outcomes remain fenced instead of receiving that retry. The illustrative
cohort totals above do not additionally budget workflow retries. Workflow reserves 16,000 tokens per
stage including SAM, so the default 160,000-token budget admits only four
complete label pairs before blocking. The real frozen-ten cardinality is still
unknown; the separately authorized photo is not its denominator or a predictor.

The initial audited `ExecutionPolicy` supplied one uniform positive cost reservation per
billable stage, including SAM. USD 0.09 safely rounds up either reader stage;
ten specimens with two labels each then reserve USD 4.50 (50 stages), leaving
at most USD 0.50 for separately bounded incremental infrastructure. It does not
fit the USD 4 working target. At 64 labels each, even readers alone reserve
USD 93.847552. The runtime must retain budget-blocked cases; it must not truncate
regions or claim complete ten-source reading.

A proposed stage-specific ledger could reserve USD 0.059 for Qwen and USD 0.089
for Muse, plus independently priced SAM request/startup and cloud overhead.
Twenty regions would then reserve USD 2.96 for readers. Such a change must bind
the full cost map into the immutable launch/policy digest, reject absent or
nonpositive stage entries, reserve before each attempt, retain unknown outcomes
and test exhaustion/restarts. It is a proposal, not implemented authority or a
measured all-in ceiling. The authorized follow-up below implements the ledger;
data/delivery still owns the complete USD 5 resource packet.

## Reused local real-model work and remaining gates

The retained `codex/real-model-integration` checkout at a53f855 has four
untracked report/helper files. Inspected read-only; no changes or copies over
its work. Its prior actual CPU result concerns one separately authorized image;
it provides zero Firebase-cohort credit. The paid helper remains unexecuted.

Fresh qualification reuses the existing pinned production SAM image with this
working tree's source mounted read-only, cached checkpoint, no network/provider
credential, UID10001, 4 CPUs, 8GiB memory/swap and 128 PIDs. An initial script
import-path mistake failed before model loading; the corrected attempt exposed
the offline-cache defect above. Actual execution after the repair completed:

- Production `Sam3Engine`, pinned CPU `torch 2.8.0+cpu`, Transformers 5.14.0,
  Pillow 12.3.0, existing image `specimen-ci-sam:0119fc42ee8dc497e99458d531227b4a8ce36750`.
- Eight checkpoint files match aggregate
  `9089029b241c8342be41225b51531bf0457f2db0c3b9896c844b22b3487ac9b8`.
- Actual load 14.787 seconds; label inference 132.388 seconds; two label masks;
  peak process RSS 4,532,052 KiB. Same previously authorized source confirmed.
- **Target deadline Not qualified:** this AMD64 container ran on an ARM64 host;
  measured inference exceeded the serving request deadline of 120 seconds.
  Native target timing must be measured before admitting the ten-source pilot.
  The deadline and image pixels were not changed to force a pass.
- Prior separate CPU execution masks are not byte-identical, even without
  ordering. Different CPU package/platform kernels may explain this, but that
  is unconfirmed. Numerical/geometric tolerance and expert coverage acceptance
  remain unqualified; two detections are not ground truth.
- Private evidence retained under `/tmp/specimen-runtime-qualification-20260908`.
  No source identity, image, mask or private receipt was added to Git.

This is a local component test, not an immutable release artifact or cloud serving
test; rebuild all three images from the integrated committed SHA for release.

Remaining launch gates: working cloud authentication; private frozen-ten
manifest and source cardinality; same API/worker SQL endpoint; narrowly reviewed
runtime/data release contract; complete cost reservation and shutdown packet;
production auth/authorization/storage/database/model acceptance; independent
review of the integrated candidate. No manual deploy, cloud mutation, paid call,
model/provider change, Temporal selection, push, merge or pruning occurred here.

## Authorized follow-up: stage reservations and offline SAM

Coordinator subsequently confirmed the user's protected runtime/data release
and bounded Google setup approvals, recorded in `RELEASE_AUTHORIZATION.md` in
the canonical checkout. This supersedes the earlier pending-authority statement
above. Cloud readiness, exact action/cost packets and acceptance remain factual
gates. The user still authorizes only one worker execution, exactly ten specimens
and USD 5 shared incremental spend. No cloud actions were performed here.

The stage-specific proposal above is now implemented as an optional
`stage_cost_reservations` field in both `ExecutionPolicy` and `PilotLaunch`:

- `version` must be exactly `stage-cost-reservations-v1`.
- `cost_micros` maps stage names to strictly positive integer microdollars,
  at most `2**53 - 1` for exact protobuf transport. Direct configuration rejects
  boolean, string, float, zero, negative and empty values. The
  runtime embeds no provider prices; the reviewed launch owner supplies them.
- Evidence-only launches require exactly `segment`,
  `transcribe:handwriting-qwen` and `transcribe:handwriting-muse`. Ordinary
  launches also require `classify` and `parse`. Unknown/missing stages fail.
- Run and launch maps must match exactly. A map-enabled run never falls back to
  the old uniform reservation. Full maps participate in policy and launch
  digests. A revised map cannot reset the stable source-cohort ledger; mutation
  of a live launch object is also rejected.
- Each reader allocation includes the entire bounded agent invocation, including
  its schema retry. A safe workflow retry reserves that stage again before the
  effect. Unknown outcomes keep their reservation and are not replayed. The
  existing token, call, time, per-run and cohort dollar limits remain enforced.
- Legacy uniform policies remain supported. Absent new fields are omitted from
  serialization, preserving existing policy/launch digests rather than adding
  a null field that would invalidate prior ledgers.

Seven initial new-contract regressions failed before implementation. Eighteen
cost-map tests then passed using real SQLite with fixture effects. Effects
observed already-persisted reservations of 17, 76 and 165 fixture microdollars
for successive segmentation/Qwen/Muse stages. A known retry increased the retained
reservation to 135 and then blocked the next stage at its limit; unknown outcome
retained 76 across restart with one invocation only. Missing/lower/extra/revised
maps were denied. These arbitrary fixture values are not provider quotes.

Combined admission/recovery/pilot/SAM suites initially passed **143 tests / 1
opt-in skip** at `24e6550a10b6cc02d0dd319ada22c2bff9c54885`. A subsequent real
protobuf boundary regression demonstrated that integer microdollars arrive from
`Struct` as integral floats. Strict configuration validation then rejected a
valid, integrity-checked stored snapshot. Commit
`d859ac6dfa9c64d7fb68037da03283b823303736` restores safe integral floats only
when `active_graph.unpack` supplies persisted-snapshot context. It copies the
map; fractional, unsafe, nonfinite, boolean and string values remain rejected.
The existing snapshot and graph digest checks are unchanged. Direct launch
configuration still rejects even `17.0`.

The new full-specimen regression uses actual protobuf `ParseDict`, `Struct` and
`MessageToDict` through `SqlConnectRepository._snapshot`, checks integer types,
unchanged policy digest and successful admission. The final cost suite contains
25 tests. Canonical `scripts/ci/verify.sh` at d859ac6 exited zero: **816 Python
passed / 26 opt-in skipped; 120 Flutter passed / 7 skipped**, analysis,
repository/security checks and release web build. Retained log:
`/tmp/specimen-release-runtime-protobuf-final-verify-20260908.log`.

Acceptance independently reviewed the corrected code: **103 passed / 1 opt-in
skip**, no blocking scoped finding, retained
`/tmp/specimen-ac0d-runtime-persistence-review-20260908.log`. It also compared
old and new absent-map policy/launch JSON and digests with default, nondefault
and concrete ten-source inputs; all remained identical. These results do not
substitute for the data workstream's actual HTTP SQL Connect round trip.

Data's initial real-emulator split produced one passing snapshot/get/history
case and one failing launch-ledger case. The REST snapshot returned integer JSON
values and passed even at 24e6550; it did not reproduce the protobuf-float defect.
Keep that distinction: d859ac6's regression proves the actual `Struct` transport,
while the emulator test independently proves connector persistence. The failing
case exposed `CreateDocument` rejecting `kind=pilot_launch` in `auxiliary.gql`
before admission. Data owns the narrowly authorized control-document repair and
its creator/CAS/membership/sensitivity denial tests. Runtime has not weakened
admission or bypassed that connector gate.

### Minimum deterministic SAM cache contract

Production SAM now requires offline mode, rejects the HF token and its known
aliases, and validates a required `SPECIMEN_SAM3_CHECKPOINT_SHA256` before model
construction. Offline snapshot lookup explicitly uses `token=False`, so the
inference secret belongs only to the worker. Direct online engine construction
remains available for separately authorized component evaluation; the production
server entrypoint forbids it.

Use a read-only cache mount with `HF_HOME=/model-cache`. Place only these eight
reviewed files under
`/model-cache/hub/models--facebook--sam3/snapshots/3c879f39826c281e95690f02c7821c4de09afae7/`:
`config.json`, `merges.txt`, `model.safetensors`, `processor_config.json`,
`special_tokens_map.json`, `tokenizer.json`, `tokenizer_config.json`, `vocab.json`.
No `refs/main`, credential file or download-metadata directory is required for
this explicitly pinned revision. If `HF_HUB_CACHE` is set, it must point to that
same `/model-cache/hub` directory. Set `HF_HUB_OFFLINE=1` and
`TRANSFORMERS_OFFLINE=1`. The current approved artifact candidate's aggregate is
`9089029b241c8342be41225b51531bf0457f2db0c3b9896c844b22b3487ac9b8`;
delivery must verify that value against the actual copied files, not infer it
from this report.

The aggregate is SHA256 of the application's canonical JSON encoding of the
exact `{filename: file_sha256}` map. Extra/missing/changed matching artifacts
therefore change the aggregate. The guard runs before `from_pretrained` for
model and processor. The coordinator must populate an immutable, reviewed
Storage cache prefix with content/generation-bound copies and keep it unchanged
during serving. SAM receives read access only; weights never enter Docker build
context. No upload or permission grant is performed by this runtime task.

Credential-free red/green evidence: the first offline test failed with
`KeyError: HF_TOKEN`; two missing/changed hash cases previously loaded without
rejection. Guards now pass those cases and deny online/credential-bearing startup.
Actual cached model construction then passed without any HF credential or
network, at UID10001 in the existing AMD64 CPU image with current source mounted
read-only: **8 files verified, load 15.623 seconds, zero source images read**.
This is local component evidence, not a new cohort run or release image.

### Native SAM qualification inside the one authorized execution

No separate qualification job is necessary. Existing `EvidencePilotWorkflow`
orders quality, segmentation and only then readers. `Sam3Service` runs the
authenticated request under the existing at-most-120-second external deadline.
It retains `run.segmentation.blob_ref`, `sha256`, `model_id`, `model_revision`,
`input_sha256`, `http_status`, `validation`, `settings`, `request_sha256` and
`elapsed_seconds`; raw receipt bytes additionally contain source/manifest/model
artifact/mask bindings. Only a valid response returns regions and permits the
reader stage. Timeout, malformed response, mismatched provenance or unclean
process outcome blocks progression and retains uncertainty.

`elapsed_seconds` measures the complete worker-side request, including identity
and transport. Join that receipt to delivery's verified native Cloud Run
revision/image/source evidence. The first successfully bounded actual native
SAM response can qualify continuation within that same ten-source execution;
a timeout never qualifies. Each later specimen still needs its own valid SAM
result. The 120-second deadline remains unchanged and full native/end-to-end
acceptance remains Not confirmed until these receipts exist.

### Full pipeline scope and remaining configuration

An evidence-only pilot is an intermediate evidence collection step. It does not
exercise ordinary classification, structured extraction, the complete authority
harness, or clearance, and it cannot establish full application acceptance.
The user subsequently selected this first-release scope through coordinator
task `01a082b2-c2c3-70d2-be90-7bfb622c9102`: **process all ten, compare readings,
correct and save records; defer automated classification and clearance**.
Acceptance therefore requires actual ten-source processing and human correction,
save, reopen and immutable history evidence. A generic blocked record, successful
setup or an evidence-only worker exit is insufficient. Unconfigured automatic
profile/classifier/risk policy is now deferred work, not a gate for that approved
human-review release. No automatic clearance or calibrated risk is implied.

The following findings concern the shipped production entrypoints at d859ac6;
current cloud configuration and museum approval artifacts remain Not confirmed.

| Stage | Implemented behavior and exact remaining gate |
|---|---|
| Classification | `classifier_runtime.configured_classifier` can read an exact model/provider/prompt configuration from `SPECIMEN_CLASSIFIER_CONFIG_JSON`, but this branch establishes no approved classifier configuration. `collection_runtime.classify_and_select` always uses explicit human collection confirmation; classifier scores are uncalibrated. A model result alone cannot select the profile. |
| Profile and risk rules | `application_registry(False)` always returns Insects `0.1.0-draft`. `CollectionProfileRegistry.resolve` rejects that state. Production worker startup supplies no profile or risk registry; `bind_profile_rules` defaults to an empty production risk registry. A real active nonsynthetic profile must bind explicit language and segmentation rules plus an exact published risk-policy reference. Existing dependency-injection contracts can accept these values, but production needs a reviewed immutable configuration loader shared by API and worker. Changing an environment approval flag cannot publish this profile. |
| Segmentation and readers | Ordinary SAM requires the resolved pinned profile rules. The evidence pilot uses its separately pinned draft settings and cannot make those settings institution-approved. Each native SAM result still needs bounded timing and complete provenance, followed by both pinned independent readers for every retained region. |
| Adjudication and extraction | Literal comparison resolves only matching nonempty readings with no unreadable spans and a valid alignment. Disagreements remain unresolved. The deterministic parser handles explicit known `key:value` lines; `extract_with_agent` also exists and uses the first pinned reader route. Its candidates must quote exact substrings of resolved source transcripts. It supplies no unsupported values or clearance authority. Normal launch reservations must include the whole bounded `parse` invocation and its possible schema retry. |
| Authority harness | Typed plan/lookup/resolve/normalize/validate phases exist. GBIF taxonomy has a production adapter. Parties and geography receive an empty `AuthorityRegistry(version="unconfigured")`; real institution-scoped sources, operations, data classifications, versions and prices are required when the profile/mandatory fields request them. Parties identity selection and approval remain separate. A successful taxonomy request cannot establish those other authority capabilities. |
| Clearance | `policy.evaluate` requires institutional-policy and mandatory-semantics approval, confirmed label coverage, two independently sourced observations per region, resolved transcripts, source-supported mandatory values, valid lineage and field checks, successful or explicitly resolved taxonomy, and human approval. Missing evidence stays in review or blocked. No fixture, synthetic approval, risk score or evidence-pilot result satisfies these conditions. |

Reusable code is available for these stages, but no approved normal-pipeline
configuration was established in the inspected production factories and tracked
configuration material. The approved infrastructure packet does not establish
museum policy, semantics, risk weights, authority mappings, or human findings.
Delivery should first locate and validate any existing real approval artifacts;
if none exists, the corresponding institutional decision remains outstanding.
Runtime must not manufacture one or copy synthetic wire examples into production.

For a later normal-pipeline release, after those artifacts exist, wire the same
immutable profile/risk/authority configuration into API and worker, bind the
approved classifier configuration,
and prove the normal path locally with retained denial/recovery tests. This is
deferred scope; the current one-execution authorization is for the approved
ten-source human-review release and cannot be reused as a second execution.
Any later execution must have applicable authority and fit the remaining budget;
the shared USD 5 does not reset. Its complete packet must include `classify` and
`parse` in the exact stage map, all authority and infrastructure costs, retries
and shutdown.
Do not add a paid qualification execution, discard regions, reset the cohort
ledger or imply that ten records must clear. Finish live review/clearance checks
only against the actual evidence and authorized reviewer decisions.
