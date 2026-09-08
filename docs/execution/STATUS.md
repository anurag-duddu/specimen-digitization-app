# Live coordination status

Baseline: 82fd60e. Initial workstreams dispatched 2026-09-07 evening America/Chicago.

| Workstream | Task | Worktree / branch | State |
|---|---|---|---|
| Coordinator | 01a07f44-7d89-7052-b968-5e96753493ad | /Users/anuragduddu/code-projects/fieldmuseum/specimen-digitization-coordination / codex/product-coordination | Plan written; coordination only |
| Architecture | 01a07f47-c8a6-7983-9d45-adfccf0971a9 | /Users/anuragduddu/.codex/worktrees/969e/specimen-digitization-app / codex/architecture-contracts | Full audit and early shared contracts underway |
| Backend | 01a07f47-f5cc-7c10-bc1f-571b086e9cd2 | /Users/anuragduddu/.codex/worktrees/3782/specimen-digitization-app / codex/insects-backend | Domain/gate tests; coordinating API |
| Flutter | 01a07f48-2c8e-72b1-99bc-d81f2729c429 | /Users/anuragduddu/.codex/worktrees/6b01/specimen-digitization-app / codex/flutter-product | UI/repository boundaries; coordinating API |
| Data | 01a07f48-6017-7af2-930d-ac2edda9ad9e | /Users/anuragduddu/.codex/worktrees/39c2/specimen-digitization-app / codex/data-platform-foundation | Existing cloud metadata verified; schemas/contracts underway |
| CI/CD integration | 01a07f48-a57c-71b0-9642-c9430886049c | /Users/anuragduddu/.codex/worktrees/80e6/specimen-digitization-app / codex/product-integration | Live protections and public baseline verified; canonical tests underway |
| Independent QA | 01a07f4a-f674-7243-a6c8-f91cd82c1d27 | /Users/anuragduddu/.codex/worktrees/14dd/specimen-digitization-app / codex/independent-acceptance-review | Acceptance procedure underway; integrated candidate required for final review |

## Decisions and communications

- User confirms configured access and authorizes use of local CLIs, computer and browser. Tasks should inspect existing resources before claiming missing access.
- Spending cap, provisioning and production merge question remains pending; proceed with implementation, read-only existing resource inspection and local/emulator verification.
- Architecture/backend/Flutter task IDs and preliminary API requirements distributed directly among owners.
- Architect published v0.1 contract at /Users/anuragduddu/.codex/worktrees/969e/specimen-digitization-app/docs/execution/CONTRACTS.md; distributed to all implementation owners. Backend remains executable schema owner; deviations must be reconciled before integration.
- Production database remains SQL Connect. Any SQLite adapter is explicitly local/synthetic, not a production substitution.
- Critical environment finding: default gcloud project is fm-specimen-pipeline, not this project. Every cloud request must explicitly target specimen-digitization; relayed to data/backend/release.
- Data owner verified existing PostgreSQL 18 instance/service in us-east4, no listed SQL Connect connectors, Storage bucket in US-EAST1, and Hugging Face Secret Manager metadata. No secret values inspected.
- Release owner found JDK17 through Android toolchain; connected data owner for emulator setup.
- Heartbeat coordinate-specimen-product-build created every 15 minutes for continued coordination; quiet unless meaningful change/action. Pause when completed or only user-dependent work remains.

## Evidence

- Initial working tree clean; origin fetched; no open PRs.
- Latest baseline main workflow 34185255766 was completed/success. Public marker independently pending release task.
- Release task subsequently verified all four jobs green, public marker/title smoke matching full SHA 82fd60eff90684d2c630a37c59e1250604ad1cae, strict branch checks/admin protections/main-only environment/exact WIF/least-privilege Hosting identity. Baseline 33 Python tests and 1 widget test pass; web build in progress at report.
- No new product completion, production deployment, real inference, or cross-platform verification claimed yet.
- Integration baseline report committed as 84d80e8 on codex/product-integration. Canonical scripts/ci/verify.sh fully passed, including release web build. Integration awaits reviewed component commits; native CI preparation depends on Flutter credential-free configuration strategy. Report: /Users/anuragduddu/.codex/worktrees/80e6/specimen-digitization-app/docs/execution/INTEGRATION.md.
- Native preparation: integration reports Android debug APK build and temporary-config preservation tests pass. Local unsigned iOS blocked by missing iOS 26.5 platform/generic destination; CI runner compatibility must be verified. No signed/device acceptance claimed.
- QA procedure published at /Users/anuragduddu/.codex/worktrees/14dd/specimen-digitization-app/docs/execution/QA.md, all 20 P0 criteria mapped. Reviewer identified baseline echo-evaluation/title-widget/mock-route false-positive risks and was asked to send them to owners. Final acceptance awaits immutable integrated candidate.
- Architect completed whole-codebase/requirements audit and published ARCHITECTURE.md and ACCEPTANCE.md beside CONTRACTS.md in architecture worktree. Includes all 20 section-19 criteria plus section-11 P0 obligations. Documentation verification/commit pending; wire transport agreement still needs owner confirmation.
- Native CI preparation committed locally as 7e168b6 on integration branch; canonical verification passes, Android build/cleanup fault tests pass. Integration verified exact macos-15 architecture mapping against official runner reference. Actual PR native CI remains untested until candidate push; no deployment or merge.
- Architecture documentation verified commit 41e8f29 ready; integration notified. Flutter/backend agreed offset-based authenticated upload PUT /v1/organizations/{org}/uploads/{id}/content, GET offset and versioned complete. Data compiled seven named CRUD/membership/receipt operations. Follow-up delta ledger pending; backend exact serialized session/workspace/mutation fixtures still required.
- Architecture final HEAD 6a19fa9 integrated through integration HEAD bcdb81c. Naming/projection settled; real HTTP workspace/upload response fixtures and identical-file Flutter parsing remain executable acceptance gates. QA notified about valid-empty outcomes, unresolved values and bounded snapshots.
- Data reports 25+ compiled operations and emulator checks passing CAS/stale rollback/history/isolation/sensitivity/revocation/client denial/upload shape/outbox/audit. Concurrent writers exposed bundled PGlite connection failure; owner retaining regression and preparing isolated local PostgreSQL18 test cluster. Storage rules test Java21 acquired locally with vendor checksum. These are component reports, not integrated or deployed acceptance.
- Backend reports 14 new behavioral tests pass, full synthetic HTTP intake/two readings/review/clearance/restart/chunks; initial Python SQL Connect adapter operations pass on PostgreSQL18-backed emulator. Full SQL journey, production adapters and final canonical check still pending.
- Flutter reports analysis and 9 offline tests including actual backend fixture pass, real HTTP test and browser login/queue/source/review pass in explicit synthetic mode. UI polish/canonical commit pending; production API/App Check setup is a distinct gate.
- Latest QA addenda 71f5af7 and 5ac3798 specify exact UTF8 size boundaries, actual shared fixtures, fresh-process SQL recovery and synthetic/production clearance separation. Integration notified; independent execution awaits immutable integrated candidate.
- Data final790a9f936299de9770d66dc79563fb530625f9cf integrated as14e7361. Integration independently reran PG18.6 connector race/restart and Storage denial suites exit0 on isolated5589/9539. Runtime provisioning proposal prepared in integration docs/execution/RUNTIME_PROPOSAL.md; approval/spend still pending.
- Backend reports real TCP SQL HTTP complete synthetic journey and API kill/restart with identical workspace/original bytes. Worker uses persisted5min external-call leases/revision fencing, three safe lookup retries/deadletter and snapshot polling; no outbox consumer or selected managed engine. Final canonical rerun/commit pending and QA notified to independently verify.
- Production config inspection found empty repo/environment build variables and SERVICE_DISABLED for AppCheck and CloudRun APIs. Alternative runtime not ruled out. Missing API/AppCheck setup must produce actionable production UI state, never synthetic fallback.
- Backend final implementation80b432eab35e97c04b6776373563a3128bf4b702/report034d806c30b21e2b1d031ac6c84b6c80637088e8 ready and relayed integration. Canonical54Python and baselineFlutter pass;2opt-in SQL/TCP restart tests pass. F01 typed abstention/F03 role actions fixed with HTTP regression. Full production gaps remain in BACKEND.md.
- Exact generated fixture digest scanner findings resolved by integration30d6f99 with individually audited values and credential-canary rejection; defaults preserved. Flutter canonical/native handoff pending.
- Architecture task resumed for NEXT_WAVE.md planning: prioritize remaining implementable P0 work versus externally gated production/model/institutional validation; propose2-3 bounded tasks. Parent continues coordination, no product implementation.
- Flutter final31120e7d88ce053c465e890718d5fc21fc898322/report57a070cf4c6dd835cf2ae9be0ced442dc9187bd1 integrated through63ecf8c; exact fixture parity verified integration.16Flutter regressions and realHTTP pass owner; Android debug passes, local iOS SDK missing. QA-F01/F02/F03 fixes included. Mutable3000/8000/8001 task services stopped.
- Backend isolation patch03eaefcd950de7f0994614355021e4c91465dec0 canonical62Python passes; first branch frozen, next branch codex/backend-reliability active3782. Data first services stopped and report1a9bce8 ready; codex/data-work-paging active39c2. First integrated canonical+SQL verification underway before QA freeze.

## Second wave active

- Collection profiles, classification and image quality: task01a07f6f-fd00-7011-827b-c03257df69bf, worktree /Users/anuragduddu/.codex/worktrees/23ec/specimen-digitization-app, codex/collection-quality at backend034d806 baseline. Own new collection_profiles.py/classification.py/image_quality.py plus matching tests/report only.
- Evidence/authority harness: task01a07f70-854b-7b50-be5a-9d19ab8747c0, worktree /Users/anuragduddu/.codex/worktrees/5178/specimen-digitization-app, codex/evidence-authorities at034d806. Own new evidence_harness.py/authority_registry.py/parties.py/geography.py/review_risk.py plus matching tests/report only.
- Backend remains sole core workflow/domain/API/shared harness integrator; data owns due-work pagination/history SQL ops/indexes. Exact handler contracts exchanged directly. No managed engine/broker selection required for local reliability fixes.
- Independent QA evaluates frozen first-wave candidate; unfinished second-wave code excluded. Later integrate reviewed second-wave changes and repeat impacted QA. Externally blocked production/institutional/model acceptance remains separate.
