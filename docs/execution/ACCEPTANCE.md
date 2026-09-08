# P0 acceptance and verification contract

Source: PRD v0.6 section 19, all 20 criteria. Baseline: `82fd60e`.
This is a test specification and ownership matrix, not a pass report. Owners:
B = backend, F = Flutter, D = data/platform, R = release/integration,
Q = independent QA, M = museum/product/privacy/operations decision owner.
Q verifies every row independently after integration. Each acceptance ID below
is stable even when implementation test filenames change.

## Evidence rules

Status per row must become `Pass`, `Fail`, `Blocked`, or `Not tested`, with exact
commit, command/test selector, environment, fixture digest and retained output.
No row is initially Pass. Unit success may demonstrate a subcondition; it cannot
replace a representative dataset, real SAM 3, device capture, real persistence or
institutional approval. Store non-sensitive evidence in workstream/QA reports and
reference protected museum datasets by approved IDs/digests only.

The representative cohort, inclusion rules and difficulty slices must be frozen
before measuring results. Report denominator, exclusions with reasons, all three
queues and operational blocks together. Do not replace hard cases to improve
clearance rate. Synthetic clearable fixtures use explicitly synthetic policy and
authority evidence; they cannot activate institutional production clearance.

## All 20 P0 criteria

| ID | PRD demonstration | Owners | Concrete test and required evidence | Initial acceptance state |
|---|---|---|---|---|
| P0-01 | Capture/upload and recover interruption | F+B+D | Camera on agreed iOS/Android devices; JPEG/PNG/HEIC and approved TIFF/RAW decode fixtures; interrupt mid-upload, restart client, resume same upload/specimen IDs; verify bytes and manifest without duplicate jobs | Not tested; device/format proof required |
| P0-02 | Immutable original, checksum and provenance | D+B | Upload original, attempt overwrite via client and privileged application path; expect denial/precondition failure; create derivative and verify original bytes/hash/generation unchanged; inspect uploader/acquisition metadata | Not tested |
| P0-03 | Classification candidates, correction, right profile and supersession | B+F+D | Produce ranked candidates; correct class before and after downstream work; verify new pinned profile/run, old immutable history, no stale-worker finalization and one active run | Not tested |
| P0-04 | Reproducible SAM 3 regions and reviewer correction | B+F+D | Run pinned real SAM 3 on approved region gold set; inspect masks/crops/source transforms and coverage; add/delete/reorder/resize/rotate/merge region in UI and verify dependent invalidation | Blocked until real serving/sample gate passes; fixture boxes insufficient |
| P0-05 | Two independent observations for every required label, raw provenance | B+D | Instrument actual request inputs to prove neither reader sees peer output; enforce two configured routes per required region; retain raw envelopes/digests, parsed outputs, prompt/model/input/usage/time evidence; partial completion must not adjudicate | Not tested; live quality proof additional |
| P0-06 | Visible disagreement, adjudication preserves readings | B+F+D | Fixture with conflicting date digit and minority name; inspect non-color-only span/line diffs; adjudicate with reason; compare original raw observation hashes before/after | Not tested |
| P0-07 | Literal separate from structured/normalized | B+D+F | Preserve misspelled locality, punctuation, partial date and taxon synonym literally; parse and normalize linked candidates; reopen detail and verify all layers separately | Not tested |
| P0-08 | Typed lookup/validation outcomes | B | Adapter tests for success/no-match/ambiguity/429/timeout/auth error plus 403/empty/malformed/5xx/policy block; capture exact query/source metadata and digests; replay captured response without network; validate real approved public taxonomy response separately | Not tested |
| P0-09 | Failure resumes checkpoint without duplicates | B+D+R | Kill worker before call, after provider response before commit, after checkpoint before ack, and during human wait; restart separate process; assert logical observation/result counts and immutable IDs; unknown external effects remain explicit; test two simultaneous workers and stale lease | Not tested; SQL and engine proof required beyond SQLite |
| P0-10 | No clearance with unresolved critical gate | B+D | Parameterize each coverage/independence/disagreement/schema/provenance/hard-validation/policy/human-approval gate; mutate one at a time in otherwise valid fixture; high score and requested clear must not bypass; race correction versus finalize | Not tested |
| P0-11 | Every mandatory Insects field blocks if empty/unresolved | B+F | Parameterize all 20 keys across null/blank/unknown/unreadable/not-present/not-applicable/ambiguous/unresolved; verify explicit field reason and no Cleared; required operational lookup failure remains blocked | Not tested |
| P0-12 | Completion pressure causes abstention | B+Q | Adversarial request says fill all blanks/guess IRN/use plausible dates; provide absent source evidence and unknown D/T/S semantics; assert no invented/coerced/placeholder candidate marked supported and failed clearance gate | Not tested |
| P0-13 | Operational failure cannot become Deferred | B+F | Parameterize 429, timeout, invalid credentials, permission denial, outage, code error, exhausted capacity/budget and unconfigured runtime; exhaust retries; disposition null and actionable operational blocker/timeline | Not tested |
| P0-14 | Legitimate capability Deferred includes attempts/reason/eligibility | B+D+F | Approved fixture proves unsupported script or irrecoverable occlusion after viable configured alternatives; persist attempt versions, reason and newer-capability/profile/campaign eligibility; reject incomplete-attempt and transient-error variants | Not tested |
| P0-15 | Reviewer resolves case and dependent validation/disposition changes | F+B+D | Open review case, edit evidenced field with reason, reject stale concurrent edit with 409, rerun only dependent validation; show new outcome/history and prevent viewer-only edit | Not tested |
| P0-16 | Every final field traces through full evidence | B+D+F | Traverse each selected candidate to original pixels and model/human observation, transform and authority evidence where applicable, plus policy decision; reject dangling/cross-tenant links and digest mismatch; visually inspect crop locator | Not tested |
| P0-17 | Reconstruct every final disposition without hidden state | D+B+Q | Persist one case per queue; terminate API/worker, discard process caches, restart from persisted stores and immutable assets only; compare record versions, decisions, evidence, attempts and queue; exercise backup restore separately | Not tested |
| P0-18 | Deny unauthorized images, records, credentials and audit | D+B+F+Q | Two tenants/two collections and operator/reviewer/admin matrix; forged/missing/expired tokens, membership revocation, guessed IDs, cursor reuse, direct connector/Storage access, signed-link expiry; secret and telemetry content inspection | Not tested; IAM/production policy proof additional |
| P0-19 | Phase 0 accessibility/security/recovery/quality gates pass | F+B+D+R+M+Q | Keyboard/touch/screen reader, visible focus, contrast/scalable text/reduced motion and non-color disagreement; threat/retention review; restore drill and agreed recovery targets; representative gold-set false-clear/field/region metrics with named approvals | Blocked on approved thresholds, cohort and sign-offs |
| P0-20 | Production-like end-to-end without hidden repair | R+B+D+F+Q | Launch integrated client/API/persistence/worker, intake fixture, observe real staged processing, review correction and final reconstruction; record commands and IDs; no SQL console edits or injected final snapshots; repeat on approved configured processing plane | Not tested; synthetic journey must be labeled |

## Required test layers and handoff

1. Backend domain/adapter tests prove literal boundaries, abstention, policy,
   typed failures and idempotency. Existing tests only prove foundation behavior.
2. API tests use real HTTP and persisted repositories, exercise Firebase verifier
   boundaries and explicit local identity mode, race concurrent reviews and
   prohibit direct final-state writes. Publish executable JSON/OpenAPI and a
   Flutter-consumable synthetic response fixture from the same schema.
3. Data emulator tests compile schema/operations and exercise membership checks,
   CAS failures, duplicate receipts, immutability, cross-scope references and
   reconstruction. Verify direct unprivileged access is denied. Do not rely only
   on text matching `@auth` declarations.
4. Integrated restart tests kill processes and reopen the application from disk.
   Real selected-engine deployment/replay tests remain separate from local runner
   proof. Inspect external call counts and outcome-unknown events honestly.
5. Flutter widget tests plus browser/device journeys verify actual API calls,
   accessibility, resume/reselection behavior, expired credentials, conflicts,
   nonresponsive server and actionable blocked mode. A synthetic local UI with
   in-memory success is not API integration evidence.
6. Representative quality and institutional review supply the approval evidence
   that code cannot manufacture. No auto-generated synthetic reviewer signature.

Canonical `scripts/ci/verify.sh` is required before any push and on the integrated
candidate. It verifies repository hooks, locked Python tests, Flutter analysis,
widget tests and web release build. It does not establish production quality,
native-device acceptance, SQL safety, live inference or cloud deployment.

## Coverage beyond the numbered criteria

Section 19 is not permission to omit section 11 P0 functionality. Integration
must also explicitly inspect: image quality feedback and format limits;
configurable collection hierarchy/profile mapping; every region edit operation;
mixed-language/script handling; label/field/specimen disagreement and explainable
risk components; all seven harness phases; immutable profile publication;
search/filter fields; keyboard/touch review; reasoned critical overrides;
per-stage attempt/retry timeline; dead-letter replay. These map to P0-01/03/04,
P0-05/06, P0-08/10, P0-15/17 and P0-19/20 respectively and require concrete tests.

P1-labelled interruption recovery and later classification correction are still
mandatory where section 19 explicitly demands them. EMu export/projection/write
is deferred and is not an acceptance shortcut or first-slice requirement.

## Release evidence is additional

A release record needs exact commit, PR, green required checks, merged main SHA,
green main workflow, successful Hosting deploy job, matching public
`deployment.json`, and public application smoke. Runtime/data deployment has
separate approval and verification gates under DEPLOYMENT.md. Do not mark P0-20
Pass merely because the static Hosting shell has the right SHA and HTTP 200.

## Whole-product ownership refresh after repaired candidate 290a2a7

Coordinator reports independent B04/F04 accessibility closure and five green CI
checks on the first repair. Those scoped closures do not mark all P0 rows Pass.
This architecture refresh inspected reliability checkpoint report and current
uncommitted `3782` workflow/collection_runtime/evidence_runtime/API sources.
WIP observations below are not tested candidate evidence. The original test
specification remains authoritative; this table replaces only the stale ownership
and implementation-progress picture, not historical results.

| Criterion | Remaining demonstration / owner | Current boundary |
|---|---|---|
| P0-01 | Flutter capture/resume devices; collection+backend format/preflight implementation | Basic HTTP resume has evidence; HEIC/approved RAW and automated pre-submission feedback lack explicit completion owner until parent assigns extension |
| P0-02 | Backend/data/QA derivative/original integrity and IAM | Original integrity repairs reported; new derivatives and actual runtime IAM still need proof |
| P0-03 | Backend wires collection registry/candidates and Flutter selection with scoped invalidation | Real WIP handler exists; integrated fixture and correction journey pending; model calibration external |
| P0-04 | Flutter rotation/region controls; collection/backend transforms and coverage | Corrected-image QA closure is narrower than all segmentation edits; real SAM 3/sample acceptance external |
| P0-05 | Backend pinned independent requests; evidence owner language/script observation extension | Existing independence proof retained; metadata integration and real approved inference still outstanding |
| P0-06 | Backend artifact access + Flutter span/line/field comparisons | Disagreement artifacts exist in WIP; UI retrieval/display and long-reading unmeasured states pending |
| P0-07 | Backend/evidence phases + Flutter layered values | Typed phase implementation wired in WIP; prove actual normalized proposals and selections survive API/restart |
| P0-08 | Backend/evidence authority execution + QA outcomes | Checkpointed authority calls now WIP; required provider failure/absence semantics and UI candidate selection pending |
| P0-09 | Backend/data/QA due scans, budgets, leases and crash boundaries | Reliability subset reported tested; shared circuits/remaining deadline paths and final integrated QA outstanding |
| P0-10 | Backend/QA integrity and phase gates | First-wave clearance integrity fixes reported; new phase/profile/authority inputs must not bypass gates |
| P0-11 | Backend/QA mandatory fields with new profiles/authority plans | Re-run exhaustive absence matrix; missing source must be data unresolved, unavailable authority service operational |
| P0-12 | Evidence/backend/QA unsupported suggestions under new phases | Preserve existing abstention checks and extend to Parties/geography/unknown semantics |
| P0-13 | Backend/Flutter/QA action and blocker taxonomy | Extend existing failures to new classifier/authority adapters; avoid missing-value operational dead ends |
| P0-14 | Backend/Flutter/QA capability reason, retained attempts, retry predicates | Existing narrowly gated action; verify new profile alternatives cannot be skipped |
| P0-15 | Flutter/backend authority and classification correction journeys | authority_resolution newly WIP; fixed revision, reason, selection evidence and downstream revalidation required |
| P0-16 | Backend scoped artifact retrieval + Flutter evidence browser + QA | Phase blobs verified by WIP; authority/disagreement/raw artifact retrieval not yet established as a shared contract |
| P0-17 | Backend/data/Flutter/QA new phase/history reconstruction | B04 scoped closure reported; WIP current graph size, new phase refs and historical artifact reads need proof |
| P0-18 | Backend/data/Flutter/QA authorization on every new endpoint | Existing scoped denials retained; new artifact/profile/authority paths must be tested; production identity/IAM external |
| P0-19 | Flutter/QA component accessibility; museum/ops approved thresholds and devices | Code/semantics tests implementable; independent device/screen-reader and institutional quality/restore acceptance separate |
| P0-20 | Integration/QA actual new-handler HTTP+SQL+Flutter journey | First candidate is baseline only; second-wave integration and real processing-plane acceptance remain |

Cross-cutting EXP-001 filters require explicit backend/data projection and Flutter
ownership, beyond UI filtering an unbounded fetched list. Not all twenty rows are
blocked by external decisions: substantial listed code and local end-to-end work
can proceed now. See NEXT_WAVE.md's ownership-gap assignments and UI contract gate.

## Final bounded audit at backend 6b4b654 / Flutter 57405a1

This 2026-09-08 audit supersedes the earlier ownership-progress refresh above.
Backend worktree 3782 was clean at `6b4b654`; Flutter worktree 6b01 was at
`57405a1` with declaration UI changes uncommitted and still owner-in-progress.
Architecture independently ran `uv run pytest -q` in backend worktree 3782:
**271 passed, 24 skipped, 7 warnings in 60.10 seconds**. The final advertised
declaration-action test explains the increase from the earlier 270-test report.
SQL/optional-codec skips are not passes. Warnings concerned deprecations and
unconfigured local Logfire; no live telemetry or production evidence is inferred.

Architecture read backend HARDENING, ACTIVE_GRAPH, READING_DECLARATIONS and
RELIABILITY_NEXT reports, data DATA_CHECKSUM, and Flutter UI_P0. Actual SQL,
optional-codec, Flutter HTTP/browser and canonical results below are attributed
to those owners, not independently rerun here. Older report open-item lists may
be stale; the exact source checkpoint and findings below govern this audit.

The table states **local subcondition evidence**, not release acceptance. Section
19 requires an agreed representative dataset: no row receives final release Pass
from synthetic testing. `Pass subset` is tested local behavior; `Fail` identifies
specific missing code; `Not tested` identifies absent combined/external proof.
Backend test paths below are under `tests/`; Flutter paths under
`apps/specimen_digitization/test/`. Q must independently verify the final combined
candidate after the remaining fixes. The original twenty test specifications
above remain the acceptance contract.

| ID | Current local state and concrete evidence | Remaining owner/gate |
| --- | --- | --- |
| P0-01 | Pass subset: `test_application.py::test_http_upload_restart_transcribe_review_clear_and_reconstruct`, `test_upload_completion_http.py`; owner-reported `test_codec_runtime.py::test_real_optional_codec_intake_worker_crop_and_restart`; Flutter `live_codec_test.dart`, `capture_quality_test.dart` | F+Q real mobile/tablet camera and interruption acceptance Not tested; approved codec runtime/families external. Assisted feedback interpretation below avoids unnecessary detector scope. |
| P0-02 | Pass subset: `test_blob_publication.py`, `test_blob_limits.py`, `test_hardening_concurrency.py::test_same_source_concurrent_http_completion_is_authorized_duplicate` (SQLite rerun, SQL owner-reported) | D+B+Q final V3/Storage integration; legacy V1/V2 writers/null rows and deployed IAM remain rollout gates. |
| P0-03 | Pass correction subset: `test_collection_runtime.py::test_versioned_profile_correction_preserves_scope_source_and_history`, `test_classification.py`; Flutter `live_next_workflow_test.dart` | B production classifier adapter absent beyond injectable protocol/synthetic/unconfigured paths; M approved model/calibration separate. Manual correction is not automatic classifier proof. |
| P0-04 | Pass geometry/deadline subset: `test_collection_runtime.py::test_original_coordinate_crop_and_four_clockwise_rotations`, `test_sam3_runtime.py`; Flutter `region_editor_test.dart`, `source_geometry_test.dart`, `source_transform_test.dart` | Fail profile SAM settings runtime wiring, B. Real pinned SAM regions/masks/quality and service approval external. Mock service is not inference. |
| P0-05 | Pass independence subset: `test_application.py::test_production_transcriber_does_not_receive_peer_observations`, `test_reading_declarations_runtime.py` | Fail parsed latency/finish/parameters provenance and published language-rule wiring, B+collection owner. F declaration UI active. Approved live two-route inference/quality external. |
| P0-06 | Pass bounded evidence subset: `test_reading_evidence.py`, `test_reading_runtime.py`, `test_application.py::test_http_transcription_abstention_preserves_readings_and_blocks_clear`; Flutter `reading_alignment_test.dart` | Fail legacy workflow's unbounded SequenceMatcher; B. Q final visible minority-reading/adjudication journey. |
| P0-07 | Pass local: `test_evidence_harness.py::test_all_phases_keep_candidates_and_meaningful_failed_gates`, `test_contradictory_normalized_sources_are_never_selected`; Flutter `next_wire_test.dart`, `live_next_workflow_test.dart` | Q combined correction/restart; M approved source semantics. |
| P0-08 | Pass local: `test_application.py::test_lookup_http_failure_taxonomy`, `test_lookup_timeout_and_malformed`, `test_authority_runtime.py`, `test_parties.py`, `test_geography.py` | B+D+Q combined actual HTTP/SQL replay; live approved authority access/response validation external. |
| P0-09 | Pass local: `test_worker_recovery.py`, `test_provider_circuit.py`, `test_bounded_effect.py`, `test_sam3_runtime.py`, `test_hardening_concurrency.py`; SQL owner-reported | Q final crash/CAS matrix. Unknown remote effects remain explicit; no exactly-once remote execution claim. |
| P0-10 | Pass hard-gate subset: `test_application.py::test_mandatory_gate_every_field_and_semantics`, `test_whitespace_and_unbacked_normalization_cannot_clear`, `test_evidence_integrity.py` | B+Q rerun after profile-policy wiring; M real approval policy. |
| P0-11 | Pass local: `test_application.py::test_mandatory_gate_every_field_and_semantics`, `test_authority_runtime.py::test_missing_authority_literal_is_review_not_provider_failure` | Q final exhaustive matrix; M institution-specific semantics including unresolved D/T/S. |
| P0-12 | Pass local: `test_application.py::test_extraction_rejects_coerced_value_and_retains_supported_candidates`, `test_evidence_harness.py::test_search_snippet_without_captured_authority_response_cannot_normalize` | Q final adversarial abstention. No synthetic approval promotion. |
| P0-13 | Pass local: `test_application.py::test_deferred_requires_capability_attempts_and_never_operational`, `test_worker_recovery.py::test_unpriced_production_effect_is_not_treated_as_zero_cost`; Flutter `workflow_controls_test.dart` | Q new classifier/policy failure taxonomy and final UI actions. |
| P0-14 | Pass synthetic gate subset: `test_application.py::test_deferred_requires_capability_attempts_and_never_operational` | Q retained attempts/retry predicates after policy fixes; M legitimate capability cohort/approved alternatives. |
| P0-15 | Pass local: `test_authority_runtime.py::test_parties_requires_qualified_selection_and_persists_intent_before_tcp`, `test_source_correction_invalidates_authority_and_retains_old_revision`; declaration replay/supersession tests; Flutter `live_next_workflow_test.dart` | F declaration UI remains active; Q combined CAS/role/selective-invalidation journey. |
| P0-16 | Pass local: `test_evidence_integrity.py`, `test_active_graph.py::test_graph_reconstruction_rejects_identity_and_content_faults`; Flutter `graph_wire_test.dart`, `live_graph_test.dart` | Q full field/source/authority trace on combined candidate; actual SAM masks/source quality external. |
| P0-17 | Pass subset: `test_history_paging.py`, `test_http_process_restart.py`, `test_active_graph.py`; SQL owner-reported; Flutter `audit_history_test.dart`, `live_graph_test.dart` | Q reconstruct all three queues on final SQL candidate; D+R restore drill separate. |
| P0-18 | Pass local: `test_application.py::test_auth_scope_stale_write_and_concurrent_cas`, `test_history_paging.py::test_history_current_authorization_and_stored_snapshot_digest`, declaration role and graph scope tests; data security owner-reported | Q final surfaces/scanners; D+R deployed identity/IAM/signed links and privacy review external. |
| P0-19 | Not tested as a whole; Flutter geometry/reading/history/graph widget/browser subsets and first-candidate accessibility repairs reported | F+Q final assistive/device checks; M approved cohort/quality/privacy; D+R recovery objectives/restore. |
| P0-20 | Pass synthetic subsets: application HTTP/restart test above, `test_sqlconnect_application.py`, `test_http_process_restart.py`; Flutter live next/codec/graph owner-reported | R+Q freeze combined candidate and prove actual HTTP/SQL/UI without hidden repair after fixes. Configured plane, representative acceptance and release remain separate. |

### Remaining implementable P0 work

Coordinator has assigned the following narrow fixes: core backend owns runtime
wiring, parsed provenance and bounded legacy adjudication; collection owner owns
published language/scoring fields; evidence owner owns label risk/policy resolver.
No new delegation is requested by this audit.

- **TRN-007:** workflow adjudication still calls unbounded
  `SequenceMatcher(None, texts[0], texts[-1]).ratio()` with default autojunk.
  Use the bounded comparison contract and explicit unmeasured/review fallback;
  test repetitive long readings through the actual workflow.
- **SCR-001 / PRF-001:** `CollectionProfile.scoring_policy` is stored, while
  `refresh_review_evidence` calls default `review_risk(signals)` and emits only
  specimen risk. Resolve pinned profile weights and emit per-label components.
  Test two policy versions and restart; no calibrated accuracy claim needed.
- **TRN-006 / PRF-001:** application Profile has a default language rule but
  published CollectionProfile lacks that configuration, and selection rebuilds
  defaults. Wire immutable published handling and reject unknown policies.
- **SEG-001 / PRF-001:** published segmentation_policy is retained while the SAM
  request uses hard-coded prompt/settings. Resolve/pin profile service settings;
  test exact request and drift rejection without live inference.
- **TRN-005:** parsed Observation lacks per-call latency, finish state and
  parameters despite full raw retention. Record actual execution/provider values;
  unavailable values stay unknown/null and old observations remain readable.
- **CLS-002:** only injected protocol, SyntheticClassifier and
  UnconfiguredClassifier were found. B must distinguish runnable adapter work
  from M's approved route/calibration gate. A fail-closed adapter boundary is not
  proof that a production classifier exists. Sent to B/coordinator for ownership.

### ING-005 and EXP-001 scope interpretation

ING-005 requires feedback before submission; it does not require an automated
focus/glare detector or calibrated pass/fail algorithm. Inspected Flutter
`capture_quality.dart` provides bounded preview, exposure/detail statistics and
specific smallest-text, reflections, all-label inspection and retake guidance,
alongside readability confirmation. Accept this as **assisted feedback** code
coverage. Automated focus/glare/framing are explicitly unmeasured; do not claim
otherwise. Real mobile/tablet capture, accessible interaction and representative
usability acceptance remain Not tested. No new detector or guessed thresholds
are mandatory from this wording. This supersedes preliminary audit messages
that treated absent automated measurement as a required code gap.

EXP-001's score band can be a user-defined inclusive numeric interval:
`risk_min`/`risk_max`. Existing bounds validation, missing-score exclusion,
cursor binding and Flutter controls cover this functional dimension. No named
low/medium/high taxonomy or new `score_band` API is required. Scores remain
uncalibrated. This supersedes earlier NEXT_WAVE notes treating absence of a named
parameter as an open requirement.

Other inspected section 11 P0 groups have local paths/tests: immutable registry,
region controls, seven harness phases, evidence layers, three disposition gates,
reasoned review/CAS, timeline/dead-letter actions, scoped server search and
artifact/history retrieval. That does not certify all edge cases or a combined
product. Known verified graph/codecs/circuit work is not reopened by this audit.

### External and final-candidate gates

M supplies representative cohort, critical-field/profile/language/authority
semantics, rights/provider permissions, calibration and expert approval. D+B+R
own configured optional codecs, SAM/model services, credentials/pricing, deployed
identity/storage and V3 writer cutover/legacy audit. F+Q own real device and
assistive-technology acceptance. R+D+Q own recovery objectives/restore, frozen
combined candidate, canonical checks and independent SQL/HTTP/UI demonstration.
Production needs the separate PR/CI/deployment-marker/public-smoke evidence and
authorization; no deployment or cloud mutation occurred in this audit.
