# Live rollout status

Started 2026-09-08 from a53f855. Coordinator branch is isolated from main.
See LIVE_ROLLOUT_PLAN.md for authority, scope, ownership and completion gates.

## Decisions awaiting user input

- Cloud hosting and inference spending limit.
- Initial administrator supplied; private decisions file records the email.
- User authorizes first 10 existing cloud specimens only; manifest discovery underway.
- No expansion until user reviews and approves the ten-specimen end-to-end results.

Implementation, local verification and PR preparation proceed while these are pending.

## Task registry

| Owner | Task | Branch | Worktree | State |
|---|---|---|---|---|
| API | `01a08219-2fc7-79e3-a2a9-bace605c5862` | `codex/live-api-runtime` | `2bfe` | Active; runtime/auth contracts published |
| Data | `01a08219-2fc9-7f83-979f-3e034ad8c698` | `codex/live-data-platform` | `0cf0` | Active; cloud inventory and exact-ten manifest |
| Processing | `01a08219-2fcd-7001-9433-1ab249f1ac64` | `codex/live-processing` | `908e` | Active; durable worker and engine/hosting decision |
| Client | `01a08219-3044-7c91-9907-5c3bc7d95548` | `codex/live-client` | `ac08` | Active; verified identity/access and App Check |
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
- QA identified email_verified policy gap; API/client must resolve and test.
- Data/worker/QA must agree one private ten-specimen manifest with exact source
  object generations, SHA256, size, specimen/org/collection bindings and pinned
  manifest hash. No phantom sample IDs or denominator changes.
- SAM currently has a client adapter but no runnable cloud model server. Processing
  owns concrete deployment option/gaps; real HF route compatibility remains untested.
- Runtime/data release needs an explicitly reviewed separate contract. Delivery
  continues non-deploy CI/build/validation while preparing that contract.
- No owner currently needs Python dependency changes; future lock changes require
  a handshake before editing shared files.

## Release state

Current main/Hosting: a53f855, run 34255830137, all six jobs passed.
Hosted frontend shows Collection connection required; live backend is not yet wired.
Existing supervised local synthetic review at localhost:3000 is preserved.
No new rollout PR merged or production resource changed in this phase.


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

Owner-reported milestones (independent live acceptance not yet performed):

- Processing: 21 local pilot/worker tests passed, one real-SQL test skipped;
  bounded restart/effect experiments and reuse of existing CPU SAM implementation.
- API: 32 new runtime tests passed, including actual TCP and SIGTERM during a
  stuck synchronous handler; full suite/container/canonical verification running.
- Data: 18 manifest and 22 admin-bootstrap unit tests passed. Local restore
  reconstructed 27 tables/16,251 test rows. SQL Connect 3.2.0 startup removes four
  supplemental paging/search indexes despite COMPATIBLE mode; reviewed post-schema
  index DDL and final catalog/query tests are required. No cloud restore claim.
- Delivery: 68 packet/context guard tests reported; original Hosting restrictions
  retained, canonical verification and independent review underway.
- QA: 24 independent local fixture recovery/auth checks and 27 adversarial
  evidence-gate tests passed. Actual Google identity/data/provider checks remain
  blocked by environment/access, and the ten cloud specimens are not yet frozen.

Coordination PR 4 tracks plan/status on codex/live-rollout-coordination. CI is
observed by delivery and coordinator; no new workstream PR is merged to main.
