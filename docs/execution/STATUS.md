# Product build status

Updated 2026-09-08. This file is maintained by the coordinating task. Detailed commit, command, and test evidence lives in the workstream reports and Git history.

## Current result

The complete local application was independently assessed at **ee4bec83715bf262deb9c7bff4598ad9211ddd44**. The final narrow UI repair is integrated at **c144c05f5a3217208d6aab09e68ff3cdd2ddefa4**; backend source is unchanged.

Integration verification passed:

- Canonical repository checks, secret scans, Python tests: **351 passed; 26 explicitly gated tests skipped**.
- Flutter: **68 passed; 7 live tests skipped**, analysis and release web build passed.
- Separate fresh PostgreSQL/SQL Connect integration suite: **71 passed**.
- Separate actual Flutter HTTP runtime test: passed.

Independent final QA passed and is committed as `ca693d7`: canonical checks, fresh 71-test SQL suite, nine optional codec tests, newly executed runtime fixtures, actual Flutter HTTP, browser policy/telemetry, and HEIC crop editing/reopen with exact pixel and source-byte checks. All 20 acceptance criteria are mapped with local and external limits. QA found only a minor stale coordinate-validation message, repaired by `21b3e6b` and integrated at `c144c05`. The owner passed 70 Flutter tests; independent targeted browser QA reports the message lifecycle and saved/reopened geometry now pass. Its durable closure report is being finalized.

**The product is not yet accepted for production.** The final closure documentation, exact-head canonical check, complete PR update, and current-head remote CI remain required. Production configuration, representative model-quality approval, institutional semantics, and operational acceptance are separate gates.

## Git and release state

- Repository: `anurag-duddu/specimen-digitization-app`.
- Existing draft PR: https://github.com/anurag-duddu/specimen-digitization-app/pull/3.
- Published first-candidate head: `a11724aed21914bf718d83b43ef531fa6bc7ac2d`; all five checks passed in run `34194874601`, including Android and unsigned iOS. Those checks do not establish CI status for the newer local candidate.
- Later work is assembled locally on `codex/product-wave2`; it has not yet been pushed.
- Production remains at `82fd60eff90684d2c630a37c59e1250604ad1cae`. Integration freshly verified remote main, public deployment marker, and title smoke against that SHA.
- No production merge, cloud provisioning, database/rules deployment, or paid inference was performed.
- Before the full PR update: complete QA corrections, run the canonical verification gate, push without force, and wait for every current-head check. Production merges remain unauthorized pending the user's answer.

## Coordination and ownership

The parent task plans, coordinates, documents, and reviews. Product implementation occurs in separate tasks and worktrees. The first candidate and later implementation branches are retained independently.

| Workstream | Task ID | Worktree suffix | Latest state |
|---|---|---|---|
| Architecture | `01a07f47-c8a6-7983-9d45-adfccf0971a9` | `969e` | All 20 acceptance criteria mapped; final code gaps assigned and handed off |
| Backend | `01a07f47-f5cc-7c10-bc1f-571b086e9cd2` | `3782` | Final runtime and test follow-up handed off through `25bac56`; available for QA repairs |
| Flutter | `01a07f48-2c8e-72b1-99bc-d81f2729c429` | `6b01` | Final client `06f7616` handed off; available for QA repairs |
| Data | `01a07f48-6017-7af2-930d-ac2edda9ad9e` | `39c2` | Schema, storage, paging, search, and V3 checksum handoffs complete |
| Integration | `01a07f48-a57c-71b0-9642-c9430886049c` | `80e6` | Final local candidate verified; preparing PR and handoff documentation |
| Independent QA | `01a07f4a-f674-7243-a6c8-f91cd82c1d27` | `14dd` | Final assessment passed; minor UI repair independently rechecked, closure report pending |
| Collection profiles/codecs | `01a07f6f-fd00-7011-827b-c03257df69bf` | `23ec` | Profile rules, codecs, preflight, and process boundary handoffs complete |
| Evidence/risk/circuits | `01a07f70-854b-7b50-be5a-9d19ab8747c0` | `5178` | Authority, reading, risk-policy, and circuit handoffs complete |
| HF classifier | `01a0801b-caea-7232-9947-f73ac93f205a` | `36e1` | Configured adapter handed off and integrated; live quality unverified |

Worktree suffixes expand to `/Users/anuragduddu/.codex/worktrees/<suffix>/specimen-digitization-app`.

Coordinator task: `01a07f44-7d89-7052-b968-5e96753493ad`. Shared planning worktree: `/Users/anuragduddu/code-projects/fieldmuseum/specimen-digitization-coordination`, branch `codex/product-coordination`.

The `coordinate-specimen-product-build` heartbeat runs every 15 minutes to resume coordination. It should stay quiet without meaningful changes and be paused when all actionable work is complete or requires user input.

## Implemented and locally exercised

The candidate includes the responsive Flutter intake/review product, resumable uploads and duplicate reconciliation, SQL Connect persistence, immutable object provenance, independent transcription paths, review corrections, deterministic final dispositions, recovery and history, versioned profiles, configured HF classification, segmentation adapters, authority/evidence phases, language/script declarations, scoped risk assessments, search, and observability.

Important implementation details and limits:

- SQL V3 create/save operations enforce scoped checksum uniqueness and immutable source hashes. Real PostgreSQL races demonstrated one complete winner and no partial loser effects. Legacy nullable rows and pre-V3 writers require a reviewed migration/retirement plan before production rollout.
- Provider circuits and model/SAM child-process boundaries preserve leases, fenced outcomes, and unknown external-call results. Local subprocess and SQL workflow tests are not production worker/ADC rollout evidence.
- Actual HEIC/DNG fixtures were decoded, uploaded, processed, reopened, and reviewed in an explicitly permitted local codec environment. Optional codec licensing, runtime memory enforcement, arbitrary RAW families, and physical-device behavior remain separately qualified.
- Large active graphs are stored as verified immutable artifacts while current rows remain bounded. Complete history and evidence stay retrievable; oversize responses distinguish a committed mutation from a failed action.
- Published language, scoring, and segmentation settings resolve explicitly. Missing or unsupported policies fail closed. Unmeasured risk is not zero and never grants clearance.
- Model observations retain actual provenance and telemetry. Human language/script declarations supersede separately, preserve model evidence, and invalidate approval as required.
- The classifier adapter is runnable when appropriately configured, but calibration is absent and human confirmation remains required. Test models and local authority fixtures are never represented as approved museum inference.

## Independent QA milestones and repairs

Each result applies only to its recorded candidate and tested local scope. Reports retain original failures and reproducible evidence.

| Candidate/report | Independent result |
|---|---|
| First candidate `4c71e13` | Found upload replay, malformed-image, evidence-integrity, and audit-capacity defects |
| Repairs through `290a2a7` | Closed B01-B04 and F01-F04 in local scope; verified source geometry, accessibility, complete history, and unchanged legacy snapshots |
| Backend/UI `a398583` | Verified actual browser picker/upload, exact source bytes, classification, qualified authority selection, separate approval, history, rotated regions, filters, and responsive layouts |
| Hardening `906e134` | Found H01: local blob filename exposed before write completion |
| `906e134` + `38fa32f` + `c8001bb`; report `8a405ee` | Closed H01 with deterministic barriers, empty/corrupt cases, and five four-way SQL HTTP races: five winners, fifteen duplicates, twenty exact replays |
| Graph `745127a`; report `9405374` | Reconstructed all 377 GUI pages and 20 observations exactly; verified a 4.8 MB artifact, hashes, authorization, committed-action recovery, history, corruption rejection, and restart; compact row about 13 KB |
| Declarations `3dfb478`; report `ec3da7c` | Verified mixed/conflicting/unknown cases, invalid requests without effects, supersession, replay, stale writes, approval invalidation, immutable model evidence, revocation, and actual browser forms |
| Final source `ee4bec8`; report `ca693d7` | Full scoped independent assessment passed, including newly generated runtime evidence, actual browser workflow and HEIC crop pixel oracle; external gates remain open |
| Minor UI repair `c144c05` | Independent browser validation-message lifecycle, invalid/reasonless zero-effects checks, and exact saved/reopened bounds passed; durable closure report pending |

The final report must distinguish independent passes, integration passes, owner-only evidence, explicitly skipped tests, and externally blocked criteria. No historical passing CI run substitutes for final-head checks.

## Authorization and external gates

The user confirmed configured CLI, browser, and computer access. The team used existing resources and local tooling; access is not treated as approval for new spending or production mutation.

Still unanswered: overnight spending cap, cloud provisioning permission, and production merge authorization. Existing web/Android/iOS targets were used provisionally; unsigned native build success is not signing, store distribution, or physical-device acceptance.

Verified production gaps and decisions to resolve:

- API/runtime and App Check build configuration are not established. Relevant API inspections returned `SERVICE_DISABLED`; alternative runtime presence was not assumed either way.
- SQL schemas/connectors, Storage rules, worker runtime, IAM, and indexes require reviewed delivery separate from Hosting. No workstation deployment is permitted.
- Existing SQL backups were disabled at inspection; backup/restore acceptance is a hard launch gate. Zonal deployment and different SQL/Storage regions are owner tradeoffs, not automatic migration mandates.
- Representative data, quality thresholds, approved model/provider routes, institutional field semantics and Parties authority access remain acceptance dependencies. Synthetic profile approval cannot leak into production policy.
- Production secrets must remain server-side and use the documented keyless/Secret Manager boundaries. No secret values belong in Git, client configuration, fixtures, or trace output.

The default local gcloud project points to `fm-specimen-pipeline`; every command for this product must explicitly target `specimen-digitization`.

## Final handoff requirements

Integration has prepared `HANDOFF.md`, a README refresh, a documentation index/dataflow, verified startup and demo commands, and a concrete runtime proposal. After final QA documentation and current-head CI, it will launch a clearly labeled local synthetic review instance with isolated state and documented cleanup. Preserve the existing `AGENTS.md` and complete `docs/DEPLOYMENT.md` contract.

Before reporting completion, provide the final PR/head, current-head CI, independently tested user journeys, exact local startup instructions, supported/tested platform distinctions, and remaining owner actions. Do not describe the full production product as complete while external release and institutional gates remain open.
