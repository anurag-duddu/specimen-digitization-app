# Live rollout status

Started 2026-09-08 from a53f855. Coordinator branch is isolated from main.
See LIVE_ROLLOUT_PLAN.md for authority, scope, ownership and completion gates.

## Decisions and outstanding inputs

- Cloud hosting and inference spending limit.
- Initial administrator supplied; private decisions file records the email.
- User authorizes first 10 existing cloud specimens only; manifest discovery blocked on Google reauthentication.
- No expansion until user reviews and approves the ten-specimen end-to-end results.

Implementation, local verification and PR preparation proceed while these are pending.

## Task registry

| Owner | Task | Branch | Worktree | State |
|---|---|---|---|---|
| API | `01a08219-2fc7-79e3-a2a9-bace605c5862` | `codex/live-api-runtime` | `2bfe` | Active; runtime/auth contracts published |
| Data | `01a08219-2fc9-7f83-979f-3e034ad8c698` | `codex/live-data-platform` | `0cf0` | Active; cloud inventory and exact-ten manifest |
| Processing | `01a08219-2fcd-7001-9433-1ab249f1ac64` | `codex/live-processing` | `908e` | Active; durable worker and engine/hosting decision |
| Client | `01a08219-3044-7c91-9907-5c3bc7d95548` | `codex/live-client-auth-repair` | `ac08` | Active; verified identity/access and App Check |
| Delivery | `01a08219-348e-7f41-92d2-a3619b3896f6` | `codex/live-delivery` | `f88c` | Active; guarded delivery contract and non-deploy CI |
| QA | `01a08219-3527-7523-8365-7c3a85c3ca67` | `codex/live-acceptance` | `73c3` | Active; independent auth/manifest/acceptance harness |

All six tasks confirmed active through wait_threads. GPT-6 Astra is the configured
model; high effort for API/data/processing/delivery/QA and medium for client.
Coordinator heartbeat `coordinate-live-specimen-rollout` is active every 15 minutes.

## Current interface and risk register

- API: containers/api/Dockerfile; PORT default 8080; /health/live, /health/ready,
  /version; explicit source/configuration provenance. Readiness must not require
  unnecessary permissions or present local checks as live dependency proof.
- Client: SPECIMEN_API_BASE_URL and SPECIMEN_RECAPTCHA_SITE_KEY; /v1/session identity
  must match Firebase UID and contain valid memberships; Authorization and
  X-Firebase-AppCheck on all protected resources; no self-assigned membership.
- API candidate enforces verified email and revoked-user checks. Actual Google-issued
  Auth and App Check verification remains a live acceptance gate.
- Data/worker/QA must agree one private ten-specimen manifest with exact source
  object generations, SHA256, size, specimen/org/collection bindings and pinned
  manifest hash. No phantom sample IDs or denominator changes.
- Processing now has a runnable CPU SAM container with local build/version smoke.
  QA found missing response provenance enforcement; correction is underway. Actual
  cloud model serving and paid reader inference remain unverified.
- Runtime/data release needs an explicitly reviewed separate contract. Delivery
  continues non-deploy CI/build/validation while preparing that contract.
- No owner currently needs Python dependency changes; future lock changes require
  a handshake before editing shared files.

## Release state

Current main/Hosting: 1d297db520a6e31021e7bfa5e5f81b77e90cf618,
run 34260264888, all six jobs passed including Deploy Firebase Hosting.
PR 5 was merged externally on GitHub during this rollout. Delivery independently
verified the exact public marker and rendered setup screen; coordinator independently
confirmed all six job results and reran the exact-SHA public Hosting smoke.
The prior a53f855 release is historical.
Hosted frontend shows Collection connection required; live backend is not yet wired.
Existing supervised local synthetic review at localhost:3000 is preserved.
The external PR 5 merge deployed the frontend. Other owner PRs remain unmerged;
no runtime/data provisioning or paid inference has been performed by rollout owners.


## Coordinator review checkpoint

Delivery contract v1 was read in full and accepted as the design basis for
candidate PR implementation. The future narrowly scoped AGENTS/deployment
amendment must be visible in the PR and approved in the user's later merge phase;
current main does not yet authorize separate runtime/data deployment. Existing
Hosting guards remain unchanged. Non-deploy CI and production guards can be
implemented and tested on feature branches now; no cloud execution is authorized.

Data owner confirmed both CLI token refresh and ADC discovery are unavailable.
The coordinator requested the user reauthenticate the existing Google account.
Cloud metadata and exact-ten manifest remain blocked; local implementation and
emulator/backup/bootstrap validation continue. Initial administrator is supplied;
cloud dollar budget remains unspecified. A concrete minimal-resource cost proposal
is due from data/delivery/processing before any billable provisioning.


## Reused work and verification

A separate user-owned task `01a081fd-b4cf-74a3-8254-cc25800382a7` has an isolated
`codex/real-model-integration` checkout with uncommitted evaluation helpers and
REAL_MODEL_TEST.md. It reports real pinned SAM CPU execution on one separately
authorized photograph; paid transcription is still pending. Coordinator connected
that owner directly with processing to reuse the implementation and preserve
provenance. This photograph is not counted in the new cloud ten-specimen pilot.
No uncommitted code was copied or overwritten by the coordinator.

Coordinator baseline canonical verification passed (355 Python, 26 gated skips;
76 Flutter, seven live skips; analysis, scanners, release web). The two new
coordination documents are documentation-only and receive normal commit/push
hooks. Every implementation owner must independently validate its changed tree.


## Pilot implementation decision and owner milestones

Coordinator accepted a narrow evidence-only pilot implementation proposal on the
processing feature branch. It must bind the frozen ten manifest, exact source,
draft profile, model/prompt/configuration, authorized scope and positive durable
budget reservation. Normal production behavior stays unchanged. It may retain
actual SAM regions and two blind readings, then stops processing_blocked with
pilot_evidence_review_required and no disposition. It must not publish a draft
profile, invent calibrated risk, parse/resolve authorities, finalize or clear.
API/client/QA coordinate real evidence inspection and permitted correction/history;
outside-ten, missing approval and mutated bindings must fail. This is a pilot
milestone, not full pipeline or institutional-quality acceptance. Cloud execution
and later merge remain separately gated.

## Frozen candidate checkpoint — 2026-09-08

These are candidate implementation results, not cloud acceptance. CI statuses are
point-in-time and must be rechecked against the latest PR head before any merge.

| PR | Owner | Snapshot | Verification / remaining work |
|---|---|---|---|
| 4 | Coordination | c95da138 | Five CI checks passed; this documentation update supersedes that snapshot |
| 6 | Delivery | 67336e0037507edba722add86ed0f13d9a23f399 | Updated-main canonical passed; latest CI running; QA 86 targeted tests passed |
| 7 | QA harness | e9f75d4e035007e552baf439b823b8664cbc9e15 | All five checks passed, run 34260268109; 45 adversarial tests and 24 local fixture checks |
| 8 | Data | 3d60a1b87027c7321d409be8617a73401cc82b3b | Canonical 428 Python / 26 skipped, 76 Flutter / 7 skipped; all five CI checks passed, run 34260978476 |
| 9 | Processing | 8e889dcb8da015e1ad7514b32cb6cf309a0ab884 | Code e497d949; canonical 413 Python / 26 skipped and 76 Flutter / 7 skipped; provenance fix will supersede head |
| 10 | API | 09b790a08b399cd1afaf617d058dbf95daa24974 | Code fedfaaeefc4646251f6a287c0a6deb76649dbb47; canonical 394 Python / 26 skipped and 76 Flutter / 7 skipped; final CI pending |

Client correction continues on codex/live-client-auth-repair after external PR 5
merge. It requires a new corrective PR. Thirty targeted tests and analysis passed;
full canonical verification is running. QA must independently retest the frozen fix.

### Open acceptance findings

- Client authorization denial can be swallowed by protected preview/history/intake
  paths, leaving editable access. The correction must invalidate parent access,
  stop queued intake, reject stale responses, and unlock only after a complete
  verified session/membership recheck. This remains open pending exact-head QA.
- API list responses advertise pilot lifecycle actions that detail/workspace deny
  with HTTP 409. Mutation enforcement is intact; action projection consistency
  is being corrected and requires independent exact-head verification.
- SAM consumer accepted missing or mismatched request, manifest, source and model
  provenance and unpinned mask references. Worker owner is correcting shared
  canonical digest computation and response binding before downstream transcription.
  Passing old tests does not close this finding.
- Delivery's stale-source packet and ambiguous structure/readiness findings were
  independently closed on 67336e0037507edba722add86ed0f13d9a23f399 (86 tests).
  Structure validation explicitly means NOT READY; actual release readiness,
  trusted workflow context and combined container/model serving remain separate gates.

### Integration and data recovery

Delivery owns codex/live-integration in the isolated live-integration-20260908
worktree. It reconciles externally merged main history and imports frozen owner
heads. Current imports include data 61ea1e5, delivery ba85d9d, API 4a0ad030 and
worker 7c745a79. Client and SAM corrections still block acceptance. Combined gates
and API/worker/SAM images must use the final assembled SHA; per-owner image
provenance is insufficient for the combined release.

Data's final owner rehearsal restored 27 tables / 26,315 synthetic rows including
22,139 specimens. The earlier 16,251-row report describes a different fixture.
Two SQL Connect restarts removed four nonunique paging/search indexes; explicit
reviewed DDL restored them, repeated repair was idempotent, core schema uniqueness
remained intact, writers were quiesced and ANALYZE was required for expected plans.
Delivery independently reproduced recovery in a disposable local cluster; proof
artifact suffix specimen-data-test.FXkDFz/backup-restore-proof.json and log
/tmp/specimen-live-integration-data-verify-2.log. This is not a cloud restore test.
QA independently reproduced the same frozen data candidate on ports 15579/19529
(proof suffix byHoa1/backup-restore-proof.json): table/row equality, both restarts,
all repair/idempotence checks, core uniqueness and indexed query results passed.
The first attempt safely refused occupied 5579; integration owns 5579/9529.
User demo ports 3000/8000 remain untouched.

### Gates still required for the ten-specimen live pilot

- Reauthenticate Google access; discover and privately freeze exactly ten existing
  specimens with generation, content hash and application bindings.
- Present one coherent infrastructure/inference budget proposal for user approval;
  the supplied administrator identity does not specify a spending limit.
- Finish client/SAM repairs, exact-head independent review, combined CI and all
  three container provenance/smoke checks.
- Review separate runtime/data deployment contracts and candidate PRs in the user's
  later merge phase; provision only through the approved release mechanism.
- Verify actual Google identity, App Check, memberships, database/storage access,
  pinned model serving, durable budget enforcement and ten-specimen evidence flow.
- Stop evidence-only runs at pilot_evidence_review_required with no disposition;
  user reviews results before any expansion. Static Hosting green is insufficient.
