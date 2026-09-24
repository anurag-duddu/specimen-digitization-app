# Go-live program: the full pipeline on the first ten specimens, one at a time

Status: active, started 2026-09-23, corrected the same day after the PR
steward's reviews of #72 and #74, both merged by auto-merge before their
reviews finished. Coordinator: the Claude session titled "App production launch plan";
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
| G2 | One specimen at a time, on demand, including new uploads, "instead of doing batch 10". The ten are the acceptance cohort, processed in order | `RELEASE_AUTHORIZATION.md` single worker execution with zero retries and exactly ten; `APPROVED_WORKER_TIMING.md`; `COHORT_READING_ADMISSION.md` all-ten barrier; `APPROVED_RELEASE_BUDGET.md` 73-74 |
| G3 | System prompts at every VLM, LLM and SAM 3 level, and the harness tracing, are visible in Logfire, linked to the specimen record | `APPROVED_LOGFIRE_TRACING.md` metadata-only scope; `RELEASE_AUTHORIZATION.md` 240-251; `OBSERVABILITY_AND_EVALUATION.md` (content mode for synthetic data only) |
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
| G14 | Chosen option "Use intake collection" (asked by S3): the profile comes from the collection a specimen was uploaded or imported into, resolved down the collection tree; a reviewer can correct the collection; there is no classification stage | `PRD.md` 9.2 steps 1-2 (186-187), collection prediction |
| G15 | Chosen option "Automatic coverage check": the lane checks the segmentation result itself with the specification's region-count and full-image cross-checks, and sends the record to the human queue when the check fails | nothing; QUE-002's coverage requirement stands and is now met automatically |
| G16 | Chosen option "Optional for now": `identified_by_irn` is recorded as not resolved and does not block clearance until EMu Parties is connected | its mandatory status in `PRD.md` 12.4, for the slide pilot |
| G17 | Chosen option "Steward merges": auto-merge stays off on go-live pull requests; the PR steward merges after its swarm approves | nothing; restates G4 and DoD-7 |
| G18 | Chosen option "Full swarm every time": the PR steward reviews every new head with a fresh four-reviewer swarm, including a head that differs from an approved one only by a merge from `main` | nothing |
| G19 | Chosen option "Harness tries raw readings" (asked by S4): when the LLM first pass picks no reading for a label, the harness runs its lookups on each reader's raw reading; fields that resolve clear on their own evidence, and a field still left with conflicting readings goes to needs human review | the first-pass prompt's "route material ambiguity to human review", which now means the first pass returns no reading |
| G20 | Chosen option "Yes, the lookup settles it" (asked by S4): when the readers disagree and a lookup confirms exactly one reader's literal, that literal is used with its provenance and the field can clear under G1; it counts as a resolved critical disagreement for QUE-002 | nothing |
| G21 | Chosen option "Turn off repo auto-merge": the owner switches off the repository's "Allow auto-merge", so that G17 holds for every session. Done 2026-09-23 and standing: the steward reports any auto-merge it finds and never changes the setting | nothing |
| G22 | Chosen option "Keep all four mandatory": the four elevation fields stay mandatory and nothing is derived, neither a conversion nor a filled-in endpoint; a label without all four values goes to human review, which is every pilot label | nothing; settles the "pending policy" of `CONTRACTS.md` 234-235 and `PRD.md` 563 (elevation conversion) |
| G23 | Chosen option "GBIF decides, others support" (asked by S4): GBIF species match v2 against the pinned COL XR checklist decides a taxonomy outcome; Global Names Verifier and Catalogue of Life are also queried and recorded as evidence; in the chosen option's words, "a disagreement is flagged but GBIF's result stands" and "BugGuide isn't used (North American only)". The flag is a warning finding, never a reason for review (section 4.1, stage 8) | settles `PRD.md` 565 (source precedence) |
| G24 | Chosen option "As written, '46 means 1946": a date clears at the precision written, and a two-digit year reads as 19xx for Insects, recorded as that rule. An uncertain date (a written "?") is outside G24 and keeps the existing date gate | settles the precision part of `PRD.md` 564; G29 settles its Roman-numeral months |
| G25 | Chosen option "Yes, at the label's rank": when a label identifies only to genus, a confirmed, accepted genus satisfies the taxon field | settles `GBIF.md` 126's "expected rank" for genus-only labels |
| G26 | Chosen option "Place ID only": from Google geocoding the pipeline keeps only the place ID, its own outcome and a fingerprint of the response; Google's names, address parts and coordinates are dropped everywhere, including Logfire traces | settles the storage and caching part of `PRD.md` 566; narrows `PRD.md` 541 (Google as a source of names and coordinates) and 544 (what an adapter keeps) for Google |
| G27 | Asked by the coordinator from S8's finding on 105526329 and 105526330: the label reads "Chimaltenago", one reader wrote that and the other silently wrote "Chimaltenango", and a place lookup matches the second exactly and the first only approximately. The owner chose neither offered option ("Exact match settles it", "Place yes, spelling to review") and answered: "raw transcript anyway will have exactly as written, for verbatim field it will be as written but final location will be exact actual as settled by harness. we are always capturing both so there isn't an issue if people want to change later". So the lookup settles the final value and the field clears; the verbatim is never replaced, neither by a lookup result nor by the spelling a lookup matched; when the first pass picked no reading and the readers' literals differ, each reader's reading is kept as captured and none is chosen; both are stored, linked to the specimen (the shape is in S5's data contract) | G20's "that literal is used" for the verbatim; S8's proposal D14 (#94) |
| G28 | Chosen option "Yes, same as places": taxon names follow G27; the taxon field keeps the label's spelling as its verbatim text, GBIF's settled name is the final value, and both are stored | nothing |
| G29 | Chosen option "Yes, read it as the month", with the owner's addition: "yes, read as month + this should be part of system prompt too, all permutations combinatinos. thats the whole point of the harness, we figure out all possible cases and try to get to final records that need to be ingested. this should be the prinnciple of th harness essentially. theres a broad range possible per collection/subcollection each subcollection will have its own harness, right now were on insects". So a Roman numeral I to XII in the month position is that month; the harness works through every reading a notation allows, for dates and for every other field, and settles the one the evidence supports; what it cannot settle goes to needs human review with the candidates (G1, G6); each subcollection's profile carries its own harness knowledge, and the pilot's is Insects | settles the Roman-numeral months of `PRD.md` 564; states `PRD.md` 44 and HAR-013 as the harness's principle |
| G30 | Chosen option "USD 5" (the coordinator's recommendation): production model calls may spend USD 5 of G9's USD 25, across every paid step (readers, SAM 3, first pass, harness): each call reserves its worst-case cost before it starts, so no call can cross the allowance, and is settled to its cost once the provider reports its usage or returns a billed amount, while any other outcome stays reserved in full (coordinator ruling on the mechanism, section 4.3); the acceptance lab's USD 5 share is separate, and infrastructure takes the rest; when the allowance is spent, paid steps block as `program_allowance_exhausted`, an operational block (QUE-005), until the owner raises it | sets section 4.3's "configured model allowance" |
| G31 | Chosen option "Not sensitive": the owner checked the ten pilot slides against `PRD.md` 718's criteria and classified them not sensitive on 2026-09-23, recorded in `~/specimen-golive/OWNER_ACTIONS.md`; their import declares them not sensitive on that verified classification | meets `CONTRACTS.md` 169-170 ("actual source classification must be verified") and closes `RELEASE_RUNTIME.md` 461-463's open item for these ten |
| G32 | Chosen option "Same settled value" (asked by S4): "The harness settles each label separately and clears the field when both settle to the same value, for example two spellings of one place. Otherwise it goes to review." So a field found on two labels of one slide is settled per label on its own evidence and clears when every label settles to the same value: the same place ID or GBIF usage, or, for a field without a lookup, the same text; otherwise it goes to needs human review with each label's reading kept, and every verbatim stays as written (G27) | the specification is silent on a field found on two labels (G5) |
| G33 | Chosen option "Every reading" (asked by S4): "Dates in every model's reading count, not only the chosen transcript. If they disagree on the order, the date goes to review. A misread can block a choice but never make one." So the numeric dates of every reading, the decided transcript's and the raw readings', are the evidence that fixes an all-numeric date's day and month order (a component over 12), and any disagreement among them fixes no order | settles what "the one the evidence supports" (G29) means for an all-numeric date |
| G34 | Answer to S8's D15 for the Google tool, asked with S4's regression case: "clear with place ID byt I want the harness for location retrospective georeferencing fully implemented". The option it takes: "The field clears with Google's place ID and no name; the label's spelling stays as the verbatim. Only when Google's name is one letter off and fits the other place fields, since a real test sends a Philippine label to Denali, Alaska." Engineering reading (coordinator): a place field whose literal matches no component by fold or alias clears with the place ID and no name only when the long name of Google's component at the field's levels, never a short name or code, is within one edit of the folded literal, it is the only such component, and every other admin field of the same reading, at least one, matches Google's result by fold or alias; the field carries a `near_spelling` warning finding that never routes the record; otherwise it goes to needs human review with the candidate. The retrospective georeferencing tool of S8's plan (#94) is to be fully implemented: S8 builds it behind S4's geography interface, and D1 to D13 remain the owner's | decides D15 for the Google tool; makes #94's retrospective tool a build |

`AGENTS.md`'s security rules are unchanged: nobody deploys from a workstation
or an agent shell, and nobody weakens branch protection, required checks,
environments, pinned action SHAs or identity conditions.

### 2.2 What the existing documents already fix

Sessions implement these as specified; none is a new decision.

| Topic | Source |
|---|---|
| Backend compute is Cloud Run: `specimen-api` service, `specimen-sam` service, `specimen-worker` job, `us-east4`. There are no Cloud Functions and the Cloud Functions API is not enabled | `scripts/ci/deploy_runtime.py` 31-32, 141-188; `firebase.json` |
| The workflow engine is the application's own SQL-checkpointed `Workflow`, no Temporal | `PROCESSING_ENGINE_COMPARISON.md` 10-15; `HARNESS_OPTIONS.md` 277-290 |
| The harness framework is Pydantic AI; tools are typed, allow-listed adapters with typed outcomes; the harness never invents values | `HARNESS_OPTIONS.md` 277-290; `PRD.md` HAR-001 to HAR-019 (323-341) |
| Readers: two independent readings per label, `handwriting-qwen` and `handwriting-muse`, provider-pinned, no automatic routing | `PRD.md` TRN-001 to TRN-010; `HUGGINGFACE_MODEL_ROUTING.md` |
| Raw reading provenance | `PRD.md` TRN-005; `CONTRACTS.md` 184 |
| Disagreement score `bounded-levenshtein-fraction-v1`, labelled as review priority and uncalibrated | `BACKEND_ADJUDICATION_PROVENANCE.md` 5; `READING_EVIDENCE.md` 70-89; `PRD.md` SCR-004, SCR-005 |
| The LLM first pass prompt is the managed prompt `transcription-disagreement-adjudication` | `src/specimen_digitization/prompts.py` 63-72 |
| Lookup sources: taxonomy through GBIF, which decides, with Global Names Verifier and Catalogue of Life as supporting evidence, and BugGuide isn't used (G23); geography through Google Maps (G10), keeping only the place ID, the outcome and a response fingerprint (G26). On `PRD.md` 567 (may a Google-only match clear): G10, G20 and G27 let a Google lookup settle a place field, so a Google-only match can support that field's clearance today; S8's proposal D1 in #94 would narrow that, and the owner decides it. Fields other than taxonomy, geography and parties resolution are transcribed as seen. Parties resolution (`identified_by_irn`) needs EMu Parties, which is not provisioned, so that field is optional for the slide pilot (G16) | `PRD.md` 12.4 (487-497, 532-544); `GBIF.md` |
| Typed lookup outcomes: the eleven of HAR-008, as `LookupStatus` encodes them; no outcome is added. The failure table: a missing or rejected credential is an authentication error and an operational block | `PRD.md` HAR-008 (330), 676-688; `domain.py` 43-54 |
| Queue definitions: exactly one of cleared, needs human review, deferred; deferred only for documented model-capability limits; missing configuration, rate limits, timeouts, invalid credentials, outages, budget exhaustion and code errors are operational blocks with retry, not a queue | `PRD.md` QUE-001 to QUE-005 (387-391); `CONTRACTS.md` 217-246, as modified by G1 |
| Field value states; only `supported` satisfies a mandatory field | `CONTRACTS.md` 221-237 |
| Collection hierarchy and bootstrap | `COLLECTION_HIERARCHY.md`; `FIRST_COLLECTION_BOOTSTRAP.md` |
| The worker acts as its own operator account with a membership that cannot see sensitive data, never as the administrator, so automated steps are recorded under their own identity. An upload declared Sensitive, which is the intake default, is therefore never processed by this worker (coordinator ruling from these sources); G2 and DoD-6 hold for uploads declared not sensitive. A Sensitive upload is never reclassified (`CONTRACTS.md` 137, 161), so it is not processed; the app says so on the record and where an upload's sensitivity is chosen, with the Sensitive default left preselected (`design/03` §1.7, `design/01` H2.6, in `design/02` §1.8's neutral wording). The ten pilot slides are not sensitive by the owner's verified classification (G31) | `LIVE_PROCESSING.md` 62-63; `BACKEND.md` 169-170; `infra/release/OWNER_INPUTS.md` 288; `CONTRACTS.md` "Explicit intake sensitivity"; `PRD.md` 67, 718 |

### 2.3 Owner inputs still outstanding

| Item | Needed by | How |
|---|---|---|
| The mandatory and optional field list for the slide pilot (G8); `identified_by_irn` is already optional (G16) | first-pass and harness workstream, before acceptance | owner sends it in chat |
| Google Maps Platform key (G10) | harness geography tool | done 2026-09-23: `specimen-google-maps-key` version 1, a key restricted to the Geocoding API |
| Logfire write token (G3) | tracing in production | done 2026-09-23: the owner's existing token, stored as `specimen-worker-logfire` version 1 and verified for the specimen project |
| Hugging Face token rotation | none | withdrawn by the owner on 2026-09-23; the existing `huggingface-runtime-token` version is used |
| Hugging Face Inference Providers credits: the account's included monthly credits ran out on 2026-09-23 and routed calls return HTTP 402 | every model call: readers, first pass, harness, the acceptance lab | done 2026-09-23: the owner bought pre-paid credits, and routed calls succeed again |
| The repository's "Allow auto-merge" switched off (G21) | G17 for every session | done 2026-09-23 (`allow_auto_merge` is false) |
| A Logfire read token for the acceptance lab (optional) | reading each run's trace back for DoD-5 | owner copies the existing read token, under the owner's 2026-09-23 decision to reuse existing credentials; a separate, revocable lab token can replace it later; the acceptance lab's entry in `~/specimen-golive/OWNER_ACTIONS.md` |
| Standing IAM grants for the release and runtime identities (G11), the one-time, time-bounded grants for initialization and bootstrap that `DEPLOYMENT.md` 889-895 and the setup-window path require, and read access to the secrets `specimen-source-registry`, `specimen-collection-bindings` and `specimen-worker-actor-uid`, which the owner created on 2026-09-23 (version 1 each) | first data and runtime releases | owner runs the exact reviewed list the release workstream prepares (#119); once its part 1 is applied, the next setup window waits for #123 and a fresh window packet |
| S8's D1 to D13 (#94): the product choices inside the retrospective georeferencing tool the owner asked to have fully implemented (G34) | S8's build of that tool; each part waits for the D items that decide it | the coordinator puts them to the owner as neutral questions once S8 has revised #94 for G34 (its D1 recommendation conflicts with G34) |
| A Firebase account for the worker, with an operator membership that cannot see sensitive data (section 2.2) | automated steps recorded under their own identity | account done 2026-09-23: disabled, with no email, password, phone or sign-in provider; its UID is `specimen-worker-actor-uid` version 1. Still to run: its membership, applied once, with read-back, by the protected data release, never from an agent shell (S5's document in #96, in S2's T3e, with the UID from a temporary environment secret, after a read-only check that the account exists, is disabled, and has no email, password, phone or sign-in provider; disabled is required because production's email-link sign-in allows sign-up and would reach any enabled account that ever held an address, while the worker never signs in and acts through its service account; coordinator ruling, from #96's security review): an active organization membership and one collection membership on the pilot collection only, resolved from the committed key `insects` against the approved hierarchy artifact, whose approval hash the owner holds and supplies apart from the artifact, never computed from it (#96's `WORKER_MEMBERSHIP.md` rule, which the hierarchy bootstrap follows too), role `operator`, which cannot approve (`api.py` 323-342), with `canViewSensitive: false`. Never the admin membership document of `scripts/data/bootstrap_admin.py`, which hard-codes role `admin` (51, 71) |

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
| 2 Label segmentation | SAM 3 | Client, server, pinned revision, concept prompt `label` and 0.5 thresholds from the offline preflight | Authorize per run instead of per frozen manifest; stay up while work is due; record parameters and regions; confirm coverage automatically with the region-count and full-image cross-checks and send a failed check to the human queue (G15). Acceptance expects two labels on five pilot slides, and a missed label goes to human review |
| 3 VLMs | Several readers per label | Two provider-pinned routes, independent, raw responses kept | Run both routes in the on-demand lane |
| 4 Raw transcripts to SQL | Linked to the original image, which VLM gave what | Stored in the snapshot JSON only | Write the normalized tables in production (section 4.4) |
| 5 Disagreement score | Scoring for level of disagreement | `bounded-levenshtein-fraction-v1`, risk scores, uncalibrated | Run in the lane and persist per region |
| 6 LLM first pass | Decides which final raw transcript the harness runs against, and gives per VLM what was returned to the harness | Prompt only | A first-pass step on a Hugging Face model (G7) with the existing prompt; records the decision and, per reader, the reading and what was handed to the harness; when it picks no reading, the harness runs on each reader's raw reading (G19) |
| 7 Agentic harness | Runs lookups on the decided transcript through tools that depend on collection and subcollection, mandatory and optional fields; falls back to the raw readings if the decided transcript fails; if both fail, the relevant queue; graceful failures (G6) | Deterministic phases, GBIF adapter, unconfigured authorities | A Pydantic AI agent with the profile's typed tools (section 2.2 sources), the HAR-008 outcomes for no data found, errors and retries, the raw-reading fallback, every tool call recorded; GBIF decides taxonomy, with Global Names Verifier and Catalogue of Life as supporting evidence (G23), and a match succeeds as `GBIF.md` 126-130 defines, at the label's own rank for a genus-only label (G25); a lookup that confirms exactly one reader's literal settles a disagreement (G20); for places (G27) and taxon names (G28) the verbatim keeps the text as written and the final value is what the lookup settled, both stored; from Google only the place ID, the outcome and a response fingerprint are kept, everywhere including traces, test fixtures and lab folders, and the geocoding tool hands the agent only those (G26); when no reader's literal matched the settled place exactly, the final value is the place ID and the outcome with no name, because G26 keeps Google's names out; S8's D15 (#94) asks the owner to choose between that, where the field clears (option b), and sending the field to review (option c), and G34 decides it for the Google tool: where no reader's literal matches even after folding or through an alias, the field clears with the place ID and no name only when the long name of Google's component at the field's levels, never a short name or code, is within one edit of the folded literal, the only such component, and every other admin field of the same reading, at least one, matches by fold or alias, with a `near_spelling` warning finding that never routes the record, and otherwise goes to review with the candidate; S8 builds the retrospective georeferencing tool of #94 behind the same interface (G34), and D1 to D13 remain the owner's; the harness works through every reading a notation allows and settles the one the evidence supports, with the notations in the Insects harness knowledge that S4 writes and the profile names, rendered into the harness's system prompt (G29, section 4.2); a field on two labels is settled per label and clears when every label settles to the same value, or else goes to review with each label's reading (G32); the numeric dates of every reading, decided and raw, are the evidence for an all-numeric date's order, and any disagreement among them fixes no order (G33) |
| 8 Queue decision | Harness-resolved is cleared (G1); otherwise human review or deferred as the spec defines; no data for a mandatory field means the human queue (G1, G6) | Policy engine with human-only clearance; deferral only through the reviewer's action | Apply G1 in the policy: remove the gates that contradict it for the lane (`policy.py` 31-34 and 138-139); keep `label_coverage_unconfirmed` (35-36), which the lane's automatic check satisfies (G15); keep the reviewer's `capability_defer` action (`api.py` 1940-1967) and let the queue decision also return deferred under QUE-004; keep operational blocks with retry; validate the separately parsed date instead of the verbatim text (`policy.py` 119-126): a date clears at the precision written, a two-digit year reads as 19xx for Insects (G24), and a Roman numeral in the month position is that month (G29); keep the elevation gate (99-106, G22); `unresolved_transcription` (46-48) yields to G19 and G20, so a region whose first pass picked no reading passes when every field drawn from it resolved, on its own evidence or through a lookup that settled the disagreement, and a field still left with conflicting readings sends the record to needs human review; when the first pass picked no reading, the non-empty check reads the settled value with a success outcome, since no single verbatim was chosen (G27, G28), and the grounding check (75, `field.literal in excerpt`, which raises on that None literal) tests each reader's reading against its own evidence. The taxonomy gate (140-157) and finalize's operational check (163) read only `run.lookups[-1]`, which is arbitrary once G19 and G20 add a lookup per reader: the taxonomy gate reads the lookup that settled the taxon field, and the operational check catches an operational failure, not recovered by a retry, in any lookup the decision depends on. G23's flag and the readers' spelling difference under G27 are recorded as findings, never reasons for review. `pilot_clearance_forbidden` (`worker.py` 318-323) is off the lane's path and stays |
| 9 Linkage | Everything links to the specimen record | Stable ids throughout | Keep; the normalized rows carry specimen and run |

### 4.2 Profile

The slide pilot profile is configuration: readers, segmentation settings, tools
per field, the mandatory and optional field groups (G8), the risk policy
reference, and the clearance rule (G1). It maps to the `Insects` collection
beneath `Zoology`, and subcollections inherit their nearest ancestor's profile,
as `COLLECTION_HIERARCHY.md` 73-76 describes and the code does not yet do. A
specimen's profile comes from its intake collection, resolved down the tree, and
a reviewer can correct it (G14): the lane sets `run.classification_selection`
from the intake collection, which the `classify` step requires (`workflow.py`
308-331), and a reviewer corrects the profile collection through the existing
classification endpoint (`api.py` 2243); moving a specimen to another
collection stays refused (2262). `identified_by_irn` is optional for the slide
pilot (G16); the other nineteen fields stay mandatory until the owner's list
arrives (G8), and the four elevation fields stay mandatory with nothing derived
(G22). The profile carries the Insects date rules as versioned rules, which S3
writes and S4's date tool reads: a two-digit year reads as 19xx (G24), and a
Roman numeral I to XII in the month position is that month (G29). It also
names, by id and version, the Insects harness knowledge under G29: the
notations its labels use and every reading each allows, which S4 writes in a
module it owns and renders into the harness's system prompt, as the owner
asked (coordinator ruling on who writes what). Optional fields must survive at runtime and
be extracted and shown.

### 4.3 Budget

The USD 25 ceiling (G9) covers everything. The pipeline records every paid
call's cost on the run and refuses a paid step whose worst-case reservation
would cross the configured model allowance; a Cloud Billing budget alert
watches the whole project. The production model allowance is USD 5 (G30). By
coordinator ruling on the mechanism:
- Each paid call reserves its worst-case cost before it starts, in one atomic
  check-and-reserve on a shared ledger: S3's `worker_cursor` document, written
  through `SaveDocumentV2` only at the revision the check read.
- Only usage the provider reports, or a billed amount it returns, settles a
  call, which releases the rest of its reservation. A timeout, a transport
  error, a 5xx or a response without usage stays reserved in full, recorded as
  `cost_basis: reserved`. A settled cost above its reservation counts in full,
  never capped, and once the allowance is spent further paid steps block. A
  retry reserves again, and nothing settled or held reserved is given back when
  a run fails or is retried.
- A worst case exists only where a request is bounded: every first-pass and
  harness model request carries a cap on output tokens, and each harness run a
  cap on its model requests, set from the lab's measured runs. A run that
  reaches its cap is a harness failure under G6.
- SAM 3 is priced by its measured seconds, startup included, at the service's
  vCPU and memory rates, and its reservation bounds startup plus the
  240-second deadline.

Each paid call records its usage, its reservation and a cost computed from a
pinned price list whose version and date are recorded, or the billed amount
where a provider returns one. The acceptance lab's USD 5 share is separate and
runs under the same mechanism with its own ledger. Infrastructure takes the
rest, mostly the always-on database at about USD 10-11 a month.

### 4.4 Data

The existing normalized tables (`dataconnect/schema/schema.gql`) are written in
production for every run, next to the snapshot. The data workstream adds only
what the owner's requirements need and the schema cannot hold today, per
research report 03 section 4: the disagreement score per region; the
transcription's region (required by `CONTRACTS.md` 185) and the first pass's
decision with what each reader handed to the harness; the harness's tool calls;
the mandatory or optional group of each field; the automatic coverage check's
result and evidence (G15); the trace id. Everything is keyed per region, since a
specimen can carry several labels. From Google geocoding only the place ID, the
outcome and a response fingerprint are stored (G26). A place or taxon field
stores both its verbatim text and its settled final value (G27, G28). Its first pull request is the exact GraphQL
and the contract the other workstreams code against. Additive changes only,
meaning expand-only: new tables; new nullable columns; dropping NOT NULL, but
only on columns the data contract names with a reason, and never on a key
column, a column of any unique constraint, or the provenance and idempotency
keys (`ModelObservation.runId`, `regionId`, `provider`, `modelVersion`,
`stepKey`, and the TRN-005 provenance `rawAssetId`, `promptVersion` and
`inputSha256` on every table that carries them, `EvidenceItem`, `PipelineRun`
and `Checkpoint` included), since a nullable column switches a unique constraint off for
every null row; the gate reads a checked-in list of the allowed columns and
refuses all of these even when that list names them;
one closed exception, by coordinator ruling (#88): `SourceAsset`'s
`specimen_unique_1` on (bucket, objectName, generation) is replaced by
`source_asset_specimen_object` on (organizationId, collectionId, specimenId,
bucket, objectName, generation), because the blob store is content-addressed
and identical bytes are one object across specimens; every added column is an
existing NOT NULL column, since PostgreSQL treats NULLs as distinct; it takes
two applies, so that a unique constraint governs the table at every moment
while writers run: the first adds the new constraint beside the old, which
keeps governing; the second runs one fixed, reviewed statement in
`dataconnect/sql/` (S5's T2a) that drops the old, since a `COMPATIBLE` apply
never drops an object the schema stops declaring, and the data release runs it
only after its own read-back of the live database at apply time shows
`source_asset_specimen_object` in place, since the gate compares committed
text only; the gate admits exactly these two steps from its checked-in list, and any other change to a
unique constraint needs its own ruling; new indexes, unique constraints and
foreign keys over new columns only; new connector operations, each `@auth(level: NO_ACCESS)` with the
membership `@check`s (`DATA.md` 73). The data plane's gate refuses everything
else: dropped or renamed tables and columns, type changes, adding NOT NULL, key
changes, new or changed uniqueness over existing columns other than that
exception, changed or removed operations, and
operations at any other auth level. `AppendProfileVersionV2` is open to
operators so that the projection can record the profile snapshot each run
used, but its `approvedBy` stays null unless the caller is a reviewer or above
with sensitive access, which is main's rule for approval claims; the worker
writes null (coordinator ruling on #88's review).

### 4.5 Tracing

The lane uses the standard Logfire path in its existing `approved-content` mode
with binary content off (images stay in Storage). One trace per run with a root
span carrying specimen, run, collection and profile ids; a span per stage; SAM 3
parameters on its span, continued inside the SAM service; Pydantic AI
instrumentation with content on for readers, the first pass and the harness, so
system prompts, messages and tool calls are visible; the queue decision with its
reasons. The geocoding tool hands the agent only the place ID, the outcome and
the response fingerprint, so neither the traces nor the model provider see
Google's response (G26), and no span, log line, exception text, stored error, tool-call result, test fixture or lab folder records the Geocoding
request URL, which carries the key, since the repository is public. The trace id is stored on the run and linked from the record in the
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
link to the Logfire trace, which opens through `url_launcher`, flutter.dev's
first-party plugin, a new app dependency (coordinator ruling for #122). The
queue shows needs human review, deferred and cleared, plus processing and
blocked. Its reason filter offers the reason codes S3 publishes in the
collection configuration's `reason_codes`, generated from the lane policy's
codes, and S5's T5 search matches a code with its suffixed entries; the new
run states (pending, retry scheduled, paused, cancelled) are picked in the
filter sheet, with no new status chips (coordinator rulings for S6). Intake starts processing and shows live
status. The client defects in section 3 are fixed first.

## 5. Sequencing

Two tracks run at once and meet at the first production run.

**Release track (workstream S2).**
1. Contract amendments recording the owner decisions of section 2.1 in every
   affected document (docs only).
2. Auto-on-merge data and runtime workflows (G11), with the first data
   initialization matching the real state (database exists and is empty).
3. The exact IAM and secret list: standing grants for the release and runtime
   identities, and the one-time, time-bounded grants for initialization and
   bootstrap; the owner runs it.
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
| S1 | Steward go-live PRs through review and merge | Review every PR with a fresh swarm, CI to green, merge, post-merge deploy checks, push back | no source; PR comments; reruns; merges (G17) | Opus 5.5, high |
| S2 | Release data and runtime planes on merge | Contract amendments, auto-on-merge planes, IAM and secret lists, first releases, repository variables, deploy health | `AGENTS.md` deployment paragraph, `docs/DEPLOYMENT.md`, release and approval docs, `.github/workflows/`, `scripts/ci/` release and deploy code, `infra/`, `containers/` | Opus 5.5, xhigh |
| S3 | Build the on-demand processing lane | On-demand trigger and source import in production, worker drain, SAM 3 per run, profile configuration and inheritance, optional fields at runtime, budget, tracing | `api.py` processing and source routes, `worker*.py`, `sam3_*.py`, `production.py` adapters (535-910), `workflow.py` step bodies before `adjudicate` (pin_dependencies, classify, quality_check, segment, transcribe), `cli.py`, `transcription.py`, `collection_*.py`, `profile_runtime.py`, `observability.py`, `bounded_telemetry.py`, `tracing.py`, `provider_privacy.py` | Opus 5.5, high |
| S4 | Build the LLM first pass and agentic harness | LLM first pass, agentic harness and tools, fallback, graceful outcomes, queue rule G1 | new first-pass and harness modules, `harness.py`, `evidence_harness.py`, `lookup.py`, `parties.py`, `geography.py`, `policy.py`, `prompts.py`, `model_gateway.py` routes, `workflow.py` step bodies from `adjudicate` to finalize, including `parse` (685-719) and the stage 5 scores (the disagreement ratio in `adjudicate`, the risk score in `finalize`) | Opus 5.5, high |
| S5 | Build the pipeline data model and thread API | Data contract, schema additions, normalized projection, thread API, contract snapshots | `dataconnect/`, `scripts/data/`, `storage.py`, `search.py`, `active_graph.py`, `production.py` `SqlConnectRepository` (80-534), a new thread-route module, `scripts/ci/release_sql_catalog.sql` and the table-count assertion in `scripts/ci/test_data_release.py`, `docs/execution/backend-*.json` | Opus 5.5, high |
| S6 | Build the record thread UI | Client defects, thread view, queue, processing status, trace link | `apps/specimen_digitization/` (sole owner of goldens) | Opus 5.5, high |
| S7 | Run the acceptance lab one specimen at a time | Local and production runs one specimen at a time, run reports, defect routing | new `scripts/lab/`, `~/specimen-golive/runs/`, `~/specimen-golive/reports/`, GitHub issues labelled `golive` | Opus 5.5, high |
| S8 | Research retrospective georeferencing for the harness | The owner's georeferencing charter (G12): historical toponyms, tiered resolution, uncertainty, Darwin Core mapping; a plan for the owner (#94), then the retrospective georeferencing tool behind S4's geography interface (G34) | `docs/product-requirements/GEOREFERENCING.md`, `scripts/research/georeferencing/`, and the tool's modules once a plan PR names them | Opus 5.5, high |

Shared files (`domain.py`, `workflow.py`, `api.py`, `production.py`) take
additive, small changes; new behaviour goes in new modules where possible.
`domain.py` has no single owner: changes are additive (new types, new fields
with defaults), each pull request lists its additions in its body, and where
two sessions need the same shape, S5 decides it. A change to a file another
session owns, such as `storage.py` (S5), needs that session's sign-off as a
comment on the pull request before the steward merges it. Only S0 edits this page.
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
  acceptance lab may become fixtures, except that a Google geocoding response is
  first reduced to the place ID, the outcome and the fingerprint (G26), and no
  recorded request keeps its URL, which carries the key.
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
- Open a pull request as a draft and confirm your session's PR panel shows
  auto-merge off before marking it ready (defence in depth after G21).
- Never enable auto-merge (G17); the repository's setting is off (G21, done
  2026-09-23). The steward merges with `gh pr merge N --merge` once its
  swarm approves the current head. Every new head gets a fresh swarm, reverts
  included (G18), so a pull request is brought up to date with `main` only when
  it is next to merge, and by its owning session: GitHub's server-side merge
  ignores the `merge=union` rule for `docs/SESSION_LEARNINGS.md`. When the
  steward says your PR is next, run `git fetch origin && git merge origin/main`
  (a merge, not a rebase), push, and reply "PR #N ready".

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
  steward's reviews, reruns and merges. Repository variables and
  settings are owner actions. Never pass `--project` to `gh`.
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
2. Import and process it in production through the app, declared not
   sensitive on the owner's verified classification (G31), since the worker
   never sees a record declared Sensitive (section 2.2).
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
section 4 specifies, not that every record cleared. Under G22 every pilot label
lacks at least one mandatory elevation value, and most lack a taxon and a
determiner, so the expected outcome for each of the ten is needs human review
with the right reasons.
