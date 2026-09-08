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

## Explicit sensitivity through intake, persistence and human review

The actual connector investigation identified another first-release blocker:
`SqlConnectRepository._commit` always wrote `sensitive=True`, every auxiliary
document operation required sensitive permission, and API history and image
access denied non-sensitive members unconditionally. The approved initial admin
has no sensitive-data elevation. Coordinator authorized a bounded correction to
preserve declared non-sensitive records while leaving legacy evidence protected.

Runtime implementation is `e7f4985064c5b6a778b556852c0e4d0d247f456d`, separate
from the earlier budget/SAM work. It changes domain/API/repository code,
`worker_launch.py`, `tests/test_sensitivity_runtime.py` and `CONTRACTS.md` only:

- Batch and item creation accept strict boolean `sensitive`, default true. The
  item must match its retained batch. False must be explicit; membership never
  supplies it. Upload completion retains that declaration on the Asset.
- Default true is omitted from serialization, preserving legacy request,
  snapshot and launch digests. Absent, malformed or unknown legacy classification
  cannot grant non-sensitive access. Only the literal boolean false qualifies.
- V3 writes pass the actual asset sensitivity. Current SQL metadata must match
  the retained Asset. SQLite and SQL save paths reject downgrading sensitive or
  unknown history. The data connector must enforce the same constraint atomically,
  including older save versions; local checks do not replace that dependency.
- The repository calls `GetDocumentV2`, `ListDocumentPageV2`, `CreateDocumentV2`
  and `SaveDocumentV2`; list sensitivity derives from fresh scoped membership,
  and returned column/payload classifications must agree exactly. Data owns the
  default-sensitive column, V2 authorization/CAS/creator rules, and all legacy
  operation guards. No data or Flutter file was changed by this runtime task.
- Current workspace, source/view images, history, active graphs, retained
  artifacts and exact run lookups recheck scope and classification. Requested
  historical content checks its own Asset as well as the current record.
  Revocation during metadata lookup cannot expose the resulting event stream.
- An explicitly false `PilotLaunch` admits only explicitly false source Assets
  and creates a false control ledger. The declaration participates in the launch
  digest and cannot reset or downgrade an existing ledger. Default launches and
  generic worker cursors remain sensitive.

TDD evidence: six initial intake/history/repository regressions failed before
implementation. Three additional tests reproduced current-column disagreement,
numeric false in auxiliary metadata, and membership revocation during event
lookup. Two further legacy cases showed that null and zero passed a truthiness
check; the final guard now permits only literal false. An early test used the
wrong specimen action URL and was corrected to the existing run action route.
A simulated historical fixture initially triggered the existing current-snapshot
integrity check; advancing the current revision allowed the test to isolate
historical sensitivity without weakening that check.

Final canonical `scripts/ci/verify.sh` exited zero with **837 Python passed /
26 opt-in skipped; 120 Flutter passed / 7 skipped**, analysis, repository/security
checks and release web build. The 21 new tests include real local HTTP
upload/save/reopen/history/pixel reads, revocation and negative classification
cases. Final implementation commit hooks passed. Logs are
`/tmp/specimen-runtime-sensitivity-red-20260908.log`,
`/tmp/specimen-runtime-sensitivity-binding-red-20260908.log`,
`/tmp/specimen-runtime-sensitivity-unknown-red-20260908.log` and
`/tmp/specimen-runtime-sensitivity-canonical-20260908.log`.

Acceptance subsequently completed independent review of e7f4985: **109 tests
passed**, no blocking source finding, log
`/tmp/specimen-ac0d-sensitivity-review-20260908.log`. It compared default Asset
and concrete ten-source PilotLaunch serialization and digests against the actual
parent Git source; both matched. Actual V2 connector integration remains a
separate data-owned gate and is Not confirmed here. The data owner's newly
available real object inventory has
not established non-sensitive classification of the actual cohort. These tests
demonstrate a guarded capability; they do not classify real source images,
elevate the administrator, or substitute local fixture records for the frozen ten.

## Worker graph reconstruction and supplied SQL sessions

Delivery raised a possible graph-storage gap at production worker construction.
Independent inspection and behavioral tests distinguish two paths:

- Both ordinary and evidence-pilot workers construct `Workflow` before reading
  any specimen. `Workflow.__init__` attaches the worker's blob store whenever the
  repository has none. The existing worker path therefore preserves external
  graphs; no worker production repair was necessary.
- Delivery's standalone `verify_imported_cohort` reads SQL snapshots without a
  Workflow. A repository without `graph_blobs` rejects a large graph snapshot;
  constructing it with the corresponding blob adapter succeeds. Delivery owns
  the explicit graph adapter wired to its already admitted credentials/session.

New text-only fixtures exercise actual `worker._run`, both Workflow constructors,
`PilotWorker` summary and `SqlConnectRepository` reconstruction/save/history.
All ten records contain **64 regions and 128 readings each**, with each external
graph exceeding 256 KiB. The worker reads all ten, retains all region/reading
values, writes a full checkpoint, and reopens both the new and original historical
graph. The fixtures correctly retain review-required status and exit 2; they do
not assert clearance. Named SQL transport, configuration validation and external
adapter construction are local test substitutes. No image bytes, model or cloud
service is accessed, and this is not actual connector or live cohort evidence.

A separate constructor defect was reproduced: `SqlConnectRepository(session=...)`
still queried ambient ADC before using the supplied session. This prevented
readback from relying solely on its admitted credential context. Commit
`d1c59fedf0c1879aa7a189e7010f96c74489c081` now discovers ADC only when the session
argument is None; an explicitly supplied session is reused directly. A regression
forces ADC to fail and proves that the supplied session still performs its named
membership request. A positive control preserves default ADC construction.

Verification: the constructor regression was red before repair; the new five-case
suite passed after repair. Combined graph/recovery/launch/materialization/sensitivity
checks passed **90 tests / 2 opt-in skipped** in 11.38 seconds, log
`/tmp/specimen-runtime-worker-graph-focused-20260908.log`. The final fixture-only
rewrite also passed all five new tests. Commit hooks passed; a scanner false
positive on a dummy resource path was resolved without changing scanner rules.
An initial evidence-adapter test substitute lacked its required `blobs` property;
correcting the substitute allowed the existing worker behavior to pass. Neither
that fixture error nor the already-working workflow attachment is reported as a
production defect. Delivery still owns actual activation graph/session wiring and
the integrated release verification.

## Data connector evidence update

Data subsequently exercised the sensitivity connector against the current runtime
source. Runtime inspected the test and retained output read-only: **four local
connector cases passed in 0.93 seconds**, log
`/tmp/specimen-release-sensitivity-runtime-roundtrip-20260908.log`. Snapshot and
pilot-ledger reconstruction each ran for legacy-sensitive and explicitly false
records. Only the false cases create an isolated principal scope with
`canViewSensitive=false`; legacy-sensitive cases use the existing privileged
fixture. Each case persists one metadata specimen with ten synthetic launch
bindings, not a ten-source processing result. Observed REST cost values remain
integers; this does not reproduce or replace the separate protobuf regression.

The retained PostgreSQL log
`/tmp/specimen-release-sensitivity-postgres-20260908.log` records V2 auxiliary
classification/creator/CAS/revocation denials, all named specimen save versions,
27-table restore equality, and two restored restarts with explicit supplemental
index repair. At inspection, these DATA changes were uncommitted atop
`6276af09d7c8a9dad79bb32be1348320dd269b4a`. DATA's final source SHA, canonical
verification and independent source review remain separate integration gates.
No runtime code change, cloud action, image access or real cohort reclassification
was performed for this evidence update.

## Independent DATA sensitivity review

**PASS: no blocking finding in the reviewed slice.** Runtime independently reviewed
DATA commit `0fb70aa5e26e421e68e64a7f550a20d77e65e30a` against
`6276af09d7c8a9dad79bb32be1348320dd269b4a`, in the DATA `4a25` worktree.
The eight inspected schema/connector/test files were hashed before execution and
matched afterward and at the committed tip; the DATA worktree was clean. The
single PostgreSQL harness change adds the sensitivity suite. This review covered
DATA-authored SQL, not runtime's own Python implementation.

The named V2 operations bind payload and column classification, default missing
legacy declarations to sensitive, and prevent sensitive-to-false changes.
All three older specimen save versions and the older document save enforce the
same invariant. Both membership levels remain mandatory. Parent references bind
history and receipt authorization to the current classification; foreign keys
retain organization, collection, kind and document identity. Control documents
remain creator-only even for another privileged member. Lists exclude controls
and filter sensitive parents. Mutations remain transactional and require the
expected revision before creating their history and receipt.

Independent execution used DATA's retained local PostgreSQL/SQL Connect fixture
on ports 5589/9569. The fixture processes and DATA source were left untouched;
test requests created isolated synthetic metadata scopes.

- DATA's `scripts/data/sensitivity-test.mjs` passed again, including creation,
  promotion, legacy defaults, malformed declarations, active membership, client
  denial, list filtering, all named specimen versions and historical access.
  Log: `/tmp/specimen-runtime-data-sensitivity-independent-20260908.log`.
- A separately authored probe passed **217 successful-result/denial checks**.
  It tests malformed values on V1/V2 document saves; an allowed explicit-false
  compatibility save; stale CAS with no extra receipt or version; privileged-peer
  control denials; the same creator losing old receipt/history access after
  promotion and sensitivity-permission revocation; both-membership keyset denial;
  and malformed snapshot values on all three specimen saves without changing
  revision, history or receipts. Script and log:
  `/tmp/specimen-runtime-data-extra-review-20260908.mjs` and
  `/tmp/specimen-runtime-data-extra-review-20260908.log`.
- The four actual HTTP repository stage-cost/sensitivity/ledger round trips passed
  independently in **0.95 seconds**, using DATA's test file and the current runtime
  source through explicit `PYTHONPATH`. The imported production module was checked
  as the `7471` path. Log:
  `/tmp/specimen-runtime-data-roundtrip-independent-20260908.log`.
  As above, these are one-specimen metadata cases with ten synthetic bindings;
  REST values remained integers, and no real specimen processing is established.

The source manifest is retained at
`/tmp/specimen-runtime-data-review-source-20260908.sha256`; all eight checks and
the committed diff whitespace check passed. DATA's separate canonical log was
also inspected: **805 Python passed / 30 skipped, 120 Flutter passed / 7 skipped**,
analysis, security and web build green, at
`/tmp/specimen-release-sensitivity-verify-20260908.log`. Those canonical counts are
DATA's branch, not the combined release. This closes the preceding local DATA
source-review gate. Production integration, real source sensitivity, image/model
execution and the ten human correction/save/reopen/history journeys remain
separate coordinator gates under the existing authorization and budget.
