# Go-live program: the full pipeline on the first ten specimens, one at a time

Status: active, started 2026-09-23, corrected the same day after the PR
steward's review of #72, which auto-merge had merged before the review
finished. Coordinator: the Claude session titled "App production launch plan";
its topic branches are `golive/plan-*`.
This page is the program's master plan. Workstream briefs are in
[`briefs/`](briefs/). Live status, research reports and the owner-actions
queue live outside the repository in `~/specimen-golive/` (section 7.6).

## 1. Goal and definition of done

The owner's goal, stated in chat on 2026-09-23: take the app live with the ten
pilot specimens and run the whole pipeline end to end, one specimen at a time.
The pipeline, in the owner's words, is: "images in storage - label
segmentation - VLMs - raw transcript back to sql connect against original image
with tracking back to which VLM gave what - scoring for level of disagreement -
LLM does first pass at which final RAW transcript should run against (it should
also give at a VLM level what was returned to the harness) agentic harness takes
the finally decided raw transcript runs lookups (can rely on raw for a final
check if LLM decided transcript output fails, if both fail send to relevant
queue) with databases identified, (function call tool call etc this can be
dependent on collection/subcollection, mandatory vs optional) - mandatory fields
if cleared then cleared, and once harness returns decide queue (human,
deferred, cleared) obviously everything should link back to the specimen
record/id." Every stage's system prompts, at every VLM, LLM and SAM 3 level, and
the harness tracing must be visible in Pydantic Logfire. Storage, the SQL
database and the backend compute must run in production, and the front end must
reflect each record's whole thread. After the ten, the owner runs a new record
and checks that it goes end to end.

Done means all of the following hold, each with recorded evidence:

| ID | Condition | Evidence |
|---|---|---|
| DoD-1 | The public site serves the merged `main` commit and is connected to the production API | `deployment.json` marker, smoke result, a signed-in session resolving the collection |
| DoD-2 | Cloud SQL carries the schema the pipeline needs; the connector is deployed; the collection tree and administrator are bootstrapped | data release run and its checks |
| DoD-3 | The API service, the worker job and the SAM 3 service run from attested images built from `main` | runtime release run and readiness checks |
| DoD-4 | `subject_105526321` to `subject_105526330` were processed one at a time in production, in order, each end to end through every stage in section 4.1, with every artifact in SQL keyed to the specimen and run | SQL rows, thread API output, run reports |
| DoD-5 | Each run is one Logfire trace, linked from the record in the app, that shows SAM 3's parameters, every model call's system prompt and text input and output, the LLM first pass, the harness's tool calls and the queue decision | trace links in the run reports |
| DoD-6 | The owner's own new record runs end to end with no intervention | owner confirmation, run report |
| DoD-7 | Every change reached `main` through a pull request with green required checks and a fresh-swarm review by the PR steward, merged by the steward (G17), and every session appended its closeout to `docs/SESSION_LEARNINGS.md` | PR links, closeout entries |

## 2. Decisions

### 2.1 Owner decisions, 2026-09-23 (chat with the coordinator)

These are the authority for this program. Where they differ from an earlier
approval, they supersede it for this program, and the release workstream's
first pull request records that in each affected document with a dated entry.

| ID | Decision (owner's words in quotes) | Supersedes |
|---|---|---|
| G1 | The pipeline in section 1 is the scope. "When I say something that harness was able to resolve is cleared it is cleared." | `HUMAN_REVIEW_RELEASE.md` (automated clearance deferred), `GO_LIVE_RUNBOOK.md` ("not full-pipeline acceptance"; GBIF lookups and automated clearance out of scope), `RELEASE_RUNTIME.md` 373-391, the `automated_clearance: deferred` scope artifact |
| G2 | One specimen at a time, on demand, including new uploads, "instead of doing batch 10". The ten are the acceptance cohort, processed in order | `RELEASE_AUTHORIZATION.md` single worker execution with zero retries and exactly ten; `APPROVED_WORKER_TIMING.md`; `COHORT_READING_ADMISSION.md` all-ten barrier; `APPROVED_RELEASE_BUDGET.md` 46-47 |
| G3 | System prompts at every VLM, LLM and SAM 3 level, and the harness tracing, are visible in Logfire, linked to the specimen record | `APPROVED_LOGFIRE_TRACING.md` metadata-only scope; `RELEASE_AUTHORIZATION.md` 142-153 |
| G4 | Spec-driven and test-driven. Multiple branches with a worktree per branch, in parallel sessions. A separate PR steward session reviews every pull request with a new agent swarm each time, babysits CI/CD until green, merges, and pushes big fixes back to the owning session to fix and resubmit. Never work on `main` directly. "Managing context is key for all sessions" | extends `AGENTS.md` |
| G5 | "I dont want you to make new design decisions like building a new adjudication layer or changing queue logic." Build the stated pipeline and the existing specification. Where the specification is silent or cannot be met as written, ask the owner through the coordinator | nothing |
| G6 | "graceful failures are important. no data found, an error occurred, retry and so on. I am aware there is not always available data and thats when it goes to the need a human queue. As long as agentic harness is able to resolve it will and it can. We need to have a strong harness layer that will be improved but we need to first have a fully functional one" | nothing |
| G7 | The LLM first pass and the agentic harness run on a Hugging Face model, through the existing gateway and token | open item in `PRD.md`; no adjudication model was named anywhere |
| G8 | Mandatory and optional fields for the slide pilot: the owner will supply the list. Until it arrives, the profile is configuration-driven and carries the specification's list (all 20 mandatory, `PRD.md` 12.4) | nothing yet |
| G9 | Spending ceiling USD 25, cumulative, infrastructure and models together | `APPROVED_RELEASE_BUDGET.md` USD 12 |
| G10 | Geography lookups use Google Maps as `PRD.md` 12.4 specifies; the owner creates the Maps Platform key | nothing |
| G11 | Data and runtime releases deploy automatically on merge, like Hosting: once the required checks pass and the PR steward approves, a merge to `main` deploys runtime code and additive schema changes. Branch protection, the required checks, keyless identities and main-only environments stay. Envelopes, cost ledgers, independent-review reports and authorization artifacts retire for this program | `AGENTS.md` deployment paragraph (envelope, independent review), `DEPLOYMENT.md`, `RELEASING.md`, `RELEASE_AUTHORIZATION.md`, `RELEASE_DATA.md`, `RELEASE_RUNTIME.md`, `PROTECTED_RELEASE_HARNESS.md` |
| G12 | "for location parts in the harness a different approach might be needed, spin this off as a new task". A research session (S8) produces a retrospective georeferencing plan from the owner's charter for the owner to review. Until the owner accepts a plan, the harness keeps geography behind its typed tool interface with the Google Maps tool of G10 as the initial version | nothing; G10 stands until the owner accepts S8's plan |
| G13 | Chosen option "Queue it" (asked by S3): a request to process a specimen while another run in the same collection is active waits, and runs go one at a time in request order | nothing; the per-specimen limit of `CONTRACTS.md` 219 stays |
| G14 | Chosen option "Use intake collection" (asked by S3): the profile comes from the collection a specimen was uploaded or imported into, resolved down the collection tree; a reviewer can correct the collection; there is no classification stage | nothing |
| G15 | Chosen option "Automatic coverage check": the lane checks the segmentation result itself with the specification's region-count and full-image cross-checks, and sends the record to the human queue when the check fails | nothing; QUE-002's coverage requirement stands and is now met automatically |
| G16 | Chosen option "Optional for now": `identified_by_irn` is recorded as not resolved and does not block clearance until EMu Parties is connected | its mandatory status in `PRD.md` 12.4, for the slide pilot |
| G17 | Chosen option "Steward merges": auto-merge stays off on go-live pull requests; the PR steward merges after its swarm approves | nothing; restates G4 and DoD-7 |
| G18 | Chosen option "Full swarm every time": the PR steward reviews every new head with a fresh four-reviewer swarm, including a head that differs from an approved one only by a merge from `main` | nothing |

`AGENTS.md`'s security rules are unchanged: nobody deploys from a workstation
or an agent shell, and nobody weakens branch protection, required checks,
environments, pinned action SHAs or identity conditions.

### 2.2 What the existing documents already fix

Sessions implement these as specified; none is a new decision.

| Topic | Source |
|---|---|
| Backend compute is Cloud Run: `specimen-api` service, `specimen-sam` service, `specimen-worker` job, `us-east4`. There are no Cloud Functions and the Cloud Functions API is not enabled | `scripts/ci/deploy_runtime.py` 31-32, 141-188; `firebase.json` |
| The workflow engine is the application's own SQL-checkpointed `Workflow`, no Temporal | `PROCESSING_ENGINE_COMPARISON.md` 10-15; `HARNESS_OPTIONS.md` 277-290 |
| The harness framework is Pydantic AI; tools are typed, allow-listed adapters with typed outcomes; the harness never invents values | `HARNESS_OPTIONS.md` 277-290; `PRD.md` HAR-001 to HAR-019 (322-340) |
| Readers: two independent readings per label, `handwriting-qwen` and `handwriting-muse`, provider-pinned, no automatic routing | `PRD.md` TRN-001 to TRN-010; `HUGGINGFACE_MODEL_ROUTING.md` |
| Raw reading provenance | `PRD.md` TRN-005; `CONTRACTS.md` 184 |
| Disagreement score `bounded-levenshtein-fraction-v1`, labelled as review priority and uncalibrated | `BACKEND_ADJUDICATION_PROVENANCE.md` 5; `READING_EVIDENCE.md` 70-89; `PRD.md` SCR-004, SCR-005 |
| The LLM first pass prompt is the managed prompt `transcription-disagreement-adjudication` | `src/specimen_digitization/prompts.py` 63-72 |
| Lookup sources: taxonomy through Global Names Verifier, Catalogue of Life and GBIF (BugGuide is for North American material only, and the pilot slides are from the Philippines and Guatemala); geography through Google Maps (G10). Fields other than taxonomy, geography and parties resolution are transcribed as seen. Parties resolution (`identified_by_irn`) needs EMu Parties, which is not provisioned, so that field is optional for the slide pilot (G16) | `PRD.md` 12.4 (484-494, 529-541); `GBIF.md` |
| Typed lookup outcomes: the eleven of HAR-008, as `LookupStatus` encodes them; no outcome is added. The failure table: a missing or rejected credential is an authentication error and an operational block | `PRD.md` HAR-008 (329), 673-685; `domain.py` 43-54 |
| Queue definitions: exactly one of cleared, needs human review, deferred; deferred only for documented model-capability limits; missing configuration, rate limits, timeouts, invalid credentials, outages, budget exhaustion and code errors are operational blocks with retry, not a queue | `PRD.md` QUE-001 to QUE-005 (386-390); `CONTRACTS.md` 217-246, as modified by G1 |
| Field value states; only `supported` satisfies a mandatory field | `CONTRACTS.md` 221-237 |
| Collection hierarchy and bootstrap | `COLLECTION_HIERARCHY.md`; `FIRST_COLLECTION_BOOTSTRAP.md` |

### 2.3 Owner inputs still outstanding

| Item | Needed by | How |
|---|---|---|
| The mandatory and optional field list for the slide pilot (G8); `identified_by_irn` is already optional (G16) | first-pass and harness workstream, before acceptance | owner sends it in chat |
| Google Maps Platform key (G10) | harness geography tool | owner enables the Geocoding API, creates a restricted key and stores it in Secret Manager; exact commands in `~/specimen-golive/OWNER_ACTIONS.md` |
| Logfire write token (G3) | tracing in production | owner mints it in the Logfire console and stores it with `scripts/ci/worker_trace_setup.py store` or the command the release workstream supplies |
| Hugging Face token rotated to a fine-grained inference token | production readers, first pass, harness | owner, as a new secret version |
| Hugging Face Inference Providers credits: the account's included monthly credits ran out on 2026-09-23 and routed calls return HTTP 402 | every model call: readers, first pass, harness, the acceptance lab | owner buys pre-paid credits within G9 |
| Standing IAM grants for the release and runtime identities (G11), and the initialization identity's one-time grant, time-bounded as `DEPLOYMENT.md` 809-815 requires | first data and runtime releases | owner runs the exact reviewed list the release workstream prepares |

## 3. Verified starting state, 2026-09-23

Six read-only research reports are in `~/specimen-golive/research/`. Summary:

| Area | State |
|---|---|
| Hosting | Live at `709ae3c` (run `35777324319`); after sign-in the client shows "Collection connection required" because it was built with no API origin |
| GitHub | `main` protected; repository public; no repository variables; the protected data and runtime workflows fail closed at admission on every push (runs `35777324461`, `35777324525`) |
| Cloud | No Cloud Run services or jobs anywhere; registry empty; Cloud SQL `specimen-digitization-instance` runnable, database and IAM users exist, never migrated; Data Connect placeholder schema, no connector; only the Hugging Face secret exists; all ten images present under `microscopic-slides/` |
| Pilot slides | Four localities from two collecting events (S8's reading, checked by eye; table in `~/specimen-golive/research/S8-pilot-localities.md`). 321-327: Mindanao, Philippines, 1946 (CNHM; F.G. Werner, H. Hoogstraal), written "P.I." or "Philippine Islands". 328-330: Yepocapa, Chimaltenango, Guatemala, 1948 (R.D. Mitchell); the label misspells "Chimaltenago". On 324-328 the locality, date, elevation and collector are on the right-hand label, and the left one holds only determination or preparation notes. Codes on the top edge such as `IX-17-66-2` are slide-preparation codes, not collection dates |
| Stages 1 to 4 | Wired in production only inside the frozen ten-specimen evidence-only lane; readings persist only inside the snapshot JSON |
| Stage 5 | Built, inactive in production; risk registry empty |
| Stage 6, LLM first pass | Absent; the prompt exists and no code calls it; the `adjudicate` step resolves only identical readings |
| Stage 7, harness | Deterministic, no tool calling, no fallback to raw readings, authority registry unconfigured, EMu Parties blocked |
| Stage 8, queue | Built; clearance always needs a human (`policy.py` 138-139), plus institutional-approval and semantics gates (`policy.py` 31-34), `label_coverage_unconfirmed` (`policy.py` 35-36; only a person sets `coverage_confirmed` for real profiles, `api.py` 1990 and 2220) and, in the evidence-only `PilotWorker`, `pilot_clearance_forbidden` (`worker.py` 318-323); deferral is the reviewer's `capability_defer` action (`api.py` 1940-1967) |
| On-demand processing | Impossible in production today: processing is scheduled only in synthetic mode (`api.py` 1292-1293, 2387-2396), the production worker runs only the frozen ten, SAM 3 rejects anything outside the manifest and shuts itself down within an hour, the Insects profile is a draft with no segmentation settings, and real records carry no budget so every paid step blocks |
| Persistence | 27 tables; production writes only the snapshot; the 13 normalized `Append*` mutations are called only by an emulator test; `data-apply/v1` refuses to run once the API or worker exists |
| Profiles | Code only; one Insects profile, all 20 fields mandatory; optional fields dropped at runtime; no inheritance down the collection tree |
| Tracing | Metadata only, worker only, custom allowlist exporter; only reader calls have their own spans; no trace id stored or returned; the standard path already has an `approved-content` mode (`observability.py` 232-276) |
| Client | Shows the image, readings with model and provider, a difference fraction, fields and history; defects: "State unknown" on every record without a disposition, identical readings labelled as differing, the full image re-downloaded every 20 seconds; SAM boxes hidden for the pilot originals |
| Release path | At least four steps fail even for the original scope (research report 02, section 7); retired by G11 |
| Unmerged branches worth reading | `codex/initialize-firebase-placeholder` (initialize from the empty Firebase onboarding schema), `codex/reader-trace-linkage` (link model telemetry to specimen observations) |

## 4. What gets built

Everything here implements section 1 with the sources in section 2.2. A
workstream that finds the specification silent or contradictory stops and asks
the coordinator; it does not decide (G5).

### 4.1 Stages

| Stage | Owner's requirement | Exists | To build |
|---|---|---|---|
| 1 Images in storage | Images in Cloud Storage feed the pipeline; new uploads too | Upload flow; source import from the bucket (not wired in production) | Wire source import in production over `microscopic-slides/`; start processing on intake and on request (G2); a request during an active run in the same collection waits and runs in request order (G13); the intake collection selects the profile (G14) |
| 2 Label segmentation | SAM 3 | Client, server, pinned revision, concept prompt `label` and 0.5 thresholds from the offline preflight | Authorize per run instead of per frozen manifest; stay up while work is due; record parameters and regions; find every label on the slide (five pilot slides carry two); confirm coverage automatically with the region-count and full-image cross-checks and send a failed check to the human queue (G15) |
| 3 VLMs | Several readers per label | Two provider-pinned routes, independent, raw responses kept | Run both routes in the on-demand lane |
| 4 Raw transcripts to SQL | Linked to the original image, which VLM gave what | Stored in the snapshot JSON only | Write the normalized tables in production (section 4.4) |
| 5 Disagreement score | Scoring for level of disagreement | `bounded-levenshtein-fraction-v1`, risk scores, uncalibrated | Run in the lane and persist per region |
| 6 LLM first pass | Decides which final raw transcript the harness runs against, and gives per VLM what was returned to the harness | Prompt only | A first-pass step on a Hugging Face model (G7) with the existing prompt; records the decision and, per reader, the reading and what was handed to the harness |
| 7 Agentic harness | Runs lookups on the decided transcript through tools that depend on collection and subcollection, mandatory and optional fields; falls back to the raw readings if the decided transcript fails; if both fail, the relevant queue; graceful failures (G6) | Deterministic phases, GBIF adapter, unconfigured authorities | A Pydantic AI agent with the profile's typed tools (section 2.2 sources), the HAR-008 outcomes for no data found, errors and retries, the raw-reading fallback, every tool call recorded |
| 8 Queue decision | Harness-resolved is cleared (G1); otherwise human review or deferred as the spec defines; no data for a mandatory field means the human queue (G1, G6) | Policy engine with human-only clearance; deferral only through the reviewer's action | Apply G1 in the policy: remove the gates that contradict it for the lane (`policy.py` 31-34 and 138-139); keep `label_coverage_unconfirmed` (35-36), which the lane's automatic check satisfies (G15); keep the reviewer's `capability_defer` action (`api.py` 1940-1967) and let the queue decision also return deferred under QUE-004; keep operational blocks with retry. `pilot_clearance_forbidden` (`worker.py` 318-323) is off the lane's path and stays |
| 9 Linkage | Everything links to the specimen record | Stable ids throughout | Keep; the normalized rows carry specimen and run |

### 4.2 Profile

The slide pilot profile is configuration: readers, segmentation settings, tools
per field, the mandatory and optional field groups (G8), the risk policy
reference, and the clearance rule (G1). It maps to the `Insects` collection
beneath `Zoology`, and subcollections inherit their nearest ancestor's profile,
as `COLLECTION_HIERARCHY.md` 73-76 describes and the code does not yet do. A
specimen's profile comes from its intake collection, resolved down the tree, and
a reviewer can correct the collection (G14). `identified_by_irn` is optional for
the slide pilot (G16); the other nineteen fields stay mandatory until the
owner's list arrives (G8). Optional fields must survive at runtime and be
extracted and shown.

### 4.3 Budget

The USD 25 ceiling (G9) covers everything. The pipeline records every paid
call's cost on the run and refuses a paid step whose estimate would cross the
configured model allowance; a Cloud Billing budget alert watches the whole
project.

### 4.4 Data

The existing normalized tables (`dataconnect/schema/schema.gql`) are written in
production for every run, next to the snapshot. The data workstream adds only
what the owner's requirements need and the schema cannot hold today, per
research report 03 section 4: the disagreement score per region; the
transcription's region (required by `CONTRACTS.md` 185) and the first pass's
decision with what each reader handed to the harness; the harness's tool calls;
the mandatory or optional group of each field; the automatic coverage check's
result and evidence (G15); the trace id. Everything is keyed per region, since a
specimen can carry several labels. Its first pull request is the exact GraphQL
and the contract the other workstreams code against. Additive changes only,
meaning expand-only: new tables; new nullable columns; dropping NOT NULL; new
indexes, unique constraints and foreign keys over new columns only; new
connector operations. The data plane's gate refuses everything else: dropped or
renamed tables and columns, type changes, adding NOT NULL, key changes,
uniqueness over existing columns, and changed or removed operations.

### 4.5 Tracing

The lane uses the standard Logfire path in its existing `approved-content` mode
with binary content off (images stay in Storage). One trace per run with a root
span carrying specimen, run, collection and profile ids; a span per stage; SAM 3
parameters on its span, continued inside the SAM service; Pydantic AI
instrumentation with content on for readers, the first pass and the harness, so
system prompts, messages and tool calls are visible; the queue decision with its
reasons. The trace id is stored on the run and linked from the record in the
app. Local lab runs use the same instrumentation with `environment=lab`.

### 4.6 Runtime and releases

The existing topology, changed only where G2 and G11 require:

- the API may start executions of the worker job (`run.invoker` on that job
  only), and processing starts on intake and on request;
- the worker drains due work one specimen at a time and exits when none is due;
- SAM 3 serves any run the worker authorizes, scales to zero, and no longer
  shuts itself down after an hour;
- a merge to `main` deploys: Hosting as today; the runtime images, built from
  the merged commit, attested and deployed with readiness checks; additive
  schema changes applied with an automated additive-only check, including while
  the runtime is running.

### 4.7 Client

The record screen shows the thread: the original image with its region
overlays, several on a two-label slide;
per region, each reader's reading with its model, provider and prompt version;
the disagreement score; the first pass's decision and what each reader handed
to the harness; the harness's lookups with their outcomes; the fields, mandatory
and optional, with state and evidence; the queue decision and its reasons; and a
link to the Logfire trace. The queue shows needs human review, deferred and
cleared, plus processing and blocked. Intake starts processing and shows live
status. The client defects in section 3 are fixed first.

## 5. Sequencing

Two tracks run at once and meet at the first production run.

**Release track (workstream S2).**
1. Contract amendments recording the owner decisions of section 2.1 in every
   affected document (docs only).
2. Auto-on-merge data and runtime workflows (G11), with the first data
   initialization matching the real state (database exists and is empty).
3. The exact IAM and secret list: standing grants for the release and runtime
   identities, and the initialization identity's one-time, time-bounded grant;
   the owner runs it.
4. First data release (schema, connector, collection tree, administrator) and
   first runtime deploy on the code then on `main`; repository variables set;
   Hosting rebuilt. The app is connected and visibly live (DoD-1 to DoD-3).
5. From then on, every merge deploys.

**Pipeline track (S3, S4, S5, S6).**
1. The data contract (S5) first, because S3 and S4 write to it.
2. The on-demand lane, SAM 3 per run, profile, budget and tracing (S3).
3. The LLM first pass, the agentic harness and the queue rule (S4).
4. The normalized projection and the thread API (S5).
5. The thread view and queue (S6).

**Acceptance (S7).** Local runs with real models start at once on specimen 1 to
flush out environment and stage failures, and follow the pipeline track as it
lands. Once the release track reaches step 4 and the pipeline track is merged,
production runs begin: specimen 1, fix, rerun until flawless, then specimen 2,
and so on to specimen 10 (section 8). Then the owner's new record.

## 6. Sessions, ownership and branches

Each side session runs in its own worktree, cuts topic branches
`golive/<ws>-<topic>` from a freshly fetched `origin/main`, and opens pull
requests labelled `golive` with the title prefix `[golive:<ws>]`.

| ID | Session title (also its messaging name) | Scope | Owns (writes) | Model and effort |
|---|---|---|---|---|
| S0 | App production launch plan | Plan, decisions, merge order, owner liaison, acceptance sign-off | `docs/execution/golive/PLAN.md`, `briefs/`, `~/specimen-golive/MERGE_ORDER.md` | Opus 5.5, max |
| S1 | Steward go-live PRs through review and merge | Review every PR with a fresh swarm, CI to green, merge, post-merge deploy checks, push back | no source; PR comments; `gh pr update-branch`; merges (G17) | Opus 5.5, high |
| S2 | Release data and runtime planes on merge | Contract amendments, auto-on-merge planes, IAM and secret lists, first releases, repository variables, deploy health | `AGENTS.md` deployment paragraph, `docs/DEPLOYMENT.md`, release and approval docs, `.github/workflows/`, `scripts/ci/` release and deploy code, `infra/`, `containers/` | Opus 5.5, xhigh |
| S3 | Build the on-demand processing lane | On-demand trigger and source import in production, worker drain, SAM 3 per run, profile configuration and inheritance, optional fields at runtime, budget, tracing | `api.py` processing and source routes, `worker*.py`, `sam3_*.py`, `production.py` adapters (535-910), `workflow.py` step bodies before `adjudicate` (intake to score), `collection_*.py`, `profile_runtime.py`, `observability.py`, `bounded_telemetry.py`, `tracing.py`, `provider_privacy.py` | Opus 5.5, high |
| S4 | Build the LLM first pass and agentic harness | LLM first pass, agentic harness and tools, fallback, graceful outcomes, queue rule G1 | new first-pass and harness modules, `harness.py`, `evidence_harness.py`, `lookup.py`, `parties.py`, `geography.py`, `policy.py`, `prompts.py`, `model_gateway.py` routes, `workflow.py` step bodies from `adjudicate` to finalize, including `parse` (685-719) | Opus 5.5, high |
| S5 | Build the pipeline data model and thread API | Data contract, schema additions, normalized projection, thread API, contract snapshots | `dataconnect/`, `storage.py`, `active_graph.py`, `production.py` `SqlConnectRepository` (80-534), a new thread-route module, `scripts/ci/release_sql_catalog.sql` and the table-count assertion in `scripts/ci/test_data_release.py`, `docs/execution/backend-*.json` | Opus 5.5, high |
| S6 | Build the record thread UI | Client defects, thread view, queue, processing status, trace link | `apps/specimen_digitization/` (sole owner of goldens) | Opus 5.5, high |
| S7 | Run the acceptance lab one specimen at a time | Local and production runs one specimen at a time, run reports, defect routing | new `scripts/lab/`, `~/specimen-golive/runs/`, `~/specimen-golive/reports/`, GitHub issues labelled `golive` | Opus 5.5, high |
| S8 | Research retrospective georeferencing for the harness | The owner's georeferencing charter (G12): historical toponyms, tiered resolution, uncertainty, Darwin Core mapping; a plan for the owner, optionally a read-only prototype | `docs/product-requirements/GEOREFERENCING.md`, `scripts/research/georeferencing/` | Opus 5.5, high |

Shared files (`domain.py`, `workflow.py`, `api.py`, `production.py`) take
additive, small changes; new behaviour goes in new modules where possible.
`domain.py` has no single owner: changes are additive (new types, new fields
with defaults), each pull request lists its additions in its body, and where
two sessions need the same shape, S5 decides it. Only S0 edits this page.
Everyone appends to `docs/SESSION_LEARNINGS.md`.

## 7. Rules for every session

### 7.1 Branches and worktrees
- Work only in your own worktree; never in the root checkout (it is someone
  else's dirty codex branch) and never on `main`.
- One topic per branch and per pull request. Start each topic from a fresh
  `git fetch origin` and `origin/main`.
- Subagents that write code get their own worktree (`isolation: "worktree"`) or
  their own sub-branch; the session integrates.
- Never use bare `git stash`; the stash stack is shared across worktrees.

### 7.2 Spec first, test first
- Each topic starts with the spec delta (a short section in your workstream's
  doc under `docs/execution/golive/`, citing section 2) and failing tests, in
  their own commit, then the implementation. The PR body names both commits.
- Tests use fakes for paid and external calls; recorded real responses from the
  acceptance lab may become fixtures.
- Nothing may contradict the owner decisions in section 2.1 or add product
  behaviour the owner did not ask for (G5). Where the specification is silent
  or contradictory, stop and ask the coordinator; do not decide.

### 7.3 Pull requests
- Title `[golive:<ws>] <what>`, label `golive`, body sections: Spec, Tests (red
  and green commits), Gates run locally, Risk, Depends on.
- Keep each PR under about 600 changed lines, excluding generated files and
  goldens, so a fresh review swarm can hold it.
- Include your `docs/SESSION_LEARNINGS.md` closeout entry in the PR.
- When the PR is open, message the PR steward: first line "PR #N ready: <title>".
- When the steward pushes back, fix on the same branch and message it again.
  When it runs `gh pr update-branch`, pull before your next push.
- Never enable auto-merge (G17). The steward merges with `gh pr merge N --merge`
  once its swarm approves the current head. Every new head gets a fresh swarm
  (G18), so the steward brings a pull request up to date with `main` only when
  it is next to merge.

### 7.4 Local gates and machine load
- Start every shell with `export DEVELOPER_DIR=/Library/Developer/CommandLineTools LANG=en_US.UTF-8 LC_ALL=en_US.UTF-8`.
- Run targeted tests while developing. Before a push, run the gates for what you
  changed, one at a time, never the whole `verify.sh` in one command: pre-commit
  always; `uv run pytest scripts/ -q` and `uv run pytest tests/ -q` for Python;
  the Flutter gates (with `lib/firebase_options.dart` copied from
  `firebase_options.ci.dart` and removed afterwards) only for the app. CI runs
  everything.
- Start a full suite only when `uptime` shows a one-minute load below 12. Never
  run git operations in a worktree while a gate runs there.
- Write long output to a file and read at most 50 lines of it. Never pipe
  `flutter test` progress into a result.

### 7.5 Context
- Your brief and your status file are your memory. After a compaction or
  restart, reread both before acting.
- Send broad reading to Explore subagents and ask for conclusions with
  `file:line`, not dumps. Start a fresh subagent per task.
- Commit at every green step; the branch is the durable record.

### 7.6 Status, owner actions, messages
- `~/specimen-golive/status/<session-id>.md`: at most 30 lines, overwritten at
  every milestone: branch, worktree, open PRs, current step, blockers, next step.
- Anything only the owner can do goes into `~/specimen-golive/OWNER_ACTIONS.md`
  (exact command or console path, why, what it unblocks); then message the
  coordinator. Do not ask the owner directly; the coordinator batches requests.
- Messages go by `SendMessage` to the session title (`ListAgents` shows names).
  The first line is a complete sentence saying what the message is about.
- Research reports are in `~/specimen-golive/research/` (01 pipeline, 02 release
  planes, 03 data, 04 observability and prompts, 05 client, 06 specification).

### 7.7 Security
- Never put secrets, tokens, the administrator's identity, instance addresses,
  billing or organization ids into the repository, a pull request, an issue, a
  log you share, or a message. Private artifacts stay in `~/specimen-release-private/`.
- No deploys from a shell. `gcloud` calls are read-only and always carry
  `--project specimen-digitization`. `gh` writes only what your brief assigns:
  your own pull requests and their comments, GitHub issues (S7), and the
  steward's reviews, branch updates, reruns and merges. Repository variables and
  settings are owner actions. `gh` takes no `--project` flag.
  `firebase dataconnect:sql:diff` is not read-only (it moves the live schema's
  update time); do not run it.
- Do not read `.logfire/` credential files or `.env` files into context.

### 7.8 Closeout
Append the session's outcome, evidence, learnings, failed approaches and
follow-ups to `docs/SESSION_LEARNINGS.md` before any handoff, merge, branch
deletion or worktree removal (`AGENTS.md`).

## 8. The per-specimen acceptance loop

For each specimen in order, `subject_105526321` first:

1. Run it locally with real models through the latest merged lane (S7); fix
   what fails before touching production.
2. Import and process it in production through the app.
3. Check, and record in `~/specimen-golive/reports/<subject>.md`: every stage
   ran; SQL holds the regions, each reader's reading with provenance, the
   disagreement scores, the first pass's decision with what each reader handed
   to the harness, every tool call and outcome, the fields with their groups and
   states, and the queue decision with reasons, all keyed to the specimen and
   run; the Logfire trace shows every stage with its prompts; the app shows the
   whole thread; cost and timings.
4. Any failure: a defect to the owning session, a fix through a pull request,
   an automatic deploy, and a new run of the same specimen until it passes with
   no intervention.
5. Then the next specimen. By the tenth, a run should pass the first time.

A record the harness could not resolve and that went to the human queue with
the right reason is a correct run; correct means the pipeline behaved as
section 4 specifies, not that every record cleared.
