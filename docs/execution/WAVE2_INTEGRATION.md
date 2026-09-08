# Second-wave integration checkpoint

Branch: codex/product-wave2. Worktree: /Users/anuragduddu/.codex/worktrees/80e6/specimen-digitization-app.
The first repair remains on codex/product-integration at published a11724a (PR3).
No second-wave push, merge, cloud change, paid inference or complete-P0 claim.

## Exact provenance

Application assembly source026d0b9 is integrated as e963811. The Python source,
Python tests, dataconnect, scripts/data, pyproject.toml and uv.lock trees match
026d0b9 exactly, verified with an empty Git diff after assembly. Reviewed Flutter
16826ac is integrated as a398583, the combined application checkpoint.

| Original owner commit | Integrated commit | Scope |
|---|---|---|
| bbf536a | bbf536a | Audited exact next-fixture scanner metadata |
| 5023f235 | c966bbe | Collection profile/classifier/quality modules |
| 0da144d | 98cc285 | Evidence phases and authority modules |
| 305a133 | 9f87bdc | Due-work/history metadata queries and indexes |
| 584aac7 | a3f228a | Paging evidence/cleanup report |
| a63ab1a | 215c1ef | Reliability checkpoint |
| 17a585a | c9833a4 | Bounded Unicode reading evidence |
| eef106f | 291223f | Optional codecs and preflight |
| 12bd103 | 2ff6f33 | Current-snapshot metadata search |
| 9df1955 | c3ffc0d | Original domain timestamp projection |
| cb968490 | 53b52ea | Actionable unavailable memory-enforcement hint |
| 026d0b9 | e963811 | Backend application assembly and frozen fixture |
| 16826ac | a398583 | Flutter workflow, evidence, geometry and metadata paging |

Existing first-wave data and B01–B04/F04/history-checksum repairs were not picked
again. Reliability conflicted with the already integrated c99d1b2 retained-hash
repair in API, SQLite and SQL adapter files. Resolution uses the owner's tested
4cd3595 file contents, combining metadata paging with version_info/raw stored
hashes; 4cd3595 was not separately cherry-picked. Final exact tree parity above
checks this resolution. Architecture docs through27d7778 and coordinator status
95bdfc1 are included as planning/progress history, not additional execution proof.

## Independently executed here

- Canonical scripts/ci/verify.sh passed on assembled application e963811: 206
  Python tests, 13 explicitly optional SQL/codec skips; existing first-repair
  Flutter analysis, 26 tests (two live skips), web release and repository scanners
  passed. Log: /tmp/specimen-wave2-checkpoint-canonical.log. The new Flutter
  workflow has not yet been integrated, so this does not establish its behavior.
- SPECIMEN_TEST_PG_PORT=5589 SPECIMEN_TEST_DC_PORT=9539 scripts/data/test-postgres.sh
  passed against disposable PostgreSQL/SQL Connect, including legacy atomic CAS,
  authorization, due paging, scoped search, typed date/risk filters, index plans
  and connector restart. Log: /tmp/specimen-wave2-data.log; retained cluster/logs
  /var/folders/nq/t4rvrkyx2dx2293cx4bn8gfm0000gn/T/specimen-data-test.Whukjx.
  The logged connector SIGTERM is the deliberate restart step, not a failed suite.
- A fresh serve-local.sh on the same owned ports seeded the canonical synthetic
  scope. SPECIMEN_TEST_SQL_EMULATOR=true and SPECIMEN_SQL_EMULATOR_HOST=127.0.0.1:9539
  enabled test_authority_runtime.py, test_worker_recovery.py, test_history_paging.py,
  test_upload_completion_http.py, test_sqlconnect_application.py and
  test_http_process_restart.py: all26 passed in27.13s. This includes actual API
  TCP plus local TCP Parties plus SQL, worker discovery, review/recovery/history,
  receipt/CAS and process restart. Log: /tmp/specimen-wave2-sql-http.log.
- Combined a398583 canonical scripts/ci/verify.sh passed: 206 Python tests,
  13 optional SQL/codec skips; 47 Flutter tests, three opt-in live skips;
  analysis, web release and repository scanners passed. Log:
  /tmp/specimen-wave2-combined-canonical.log.
- The opt-in Flutter live_next_workflow_test.dart then passed against a fresh
  actual local HTTP API, SQLite and TCP mock Parties on loopback port8123.
  It exercised preflight, upload/completion, retained phase/authority/raw reading
  artifacts, alignment, explicit authority selection, stale CAS rejection,
  separate approval, pinned prior evidence and scoped metadata search. Specimen
  02fe30c0-5777-5b24-b4b2-39a92722a67a moved from revision24 to26, cleared.
  Log: /tmp/specimen-wave2-combined-live.log; retained synthetic state:
  /tmp/specimen-wave2-combined-a398583-local. This is repository HTTP evidence;
  independent additive GUI verification remains pending.

Frozen next response fixture SHA256:
6d1bf6bf4eab1b47defdafcc8c99c10dd51dc15dc28f46a18c65782b3dfbb07f.
Both owner copies and24 retained blobs were independently verified in the scanner
review. This is actual synthetic API/local-authority output, not institutional
Parties access or live-model output. Optional codec successes from owner reports
remain separate from this default-environment run and production runtime approval.

## Still open

Independent combined QA remains required after Flutter workflow integration.
The source checkpoint explicitly leaves current active-graph size, bounded raw
blob download, actual optional-codec intake, shared circuits, total SAM/auth
deadlines, metadata propagation and SQL checksum race correctness incomplete.
The subsequent data V3 checksum commits3daf6c7/5f15bc1 are a separate follow-up
pending backend wiring; this checkpoint still has the documented SQL uniqueness
gap. Do not label a metadata precheck concurrent-race proof. Later data rollout
needs legacy-writer/null-row reconciliation and authorization, never Hosting.
Institutional semantics/quality/provider/device/production gates remain separate.

## Additive ROI follow-up

After independent GUI execution finished on frozen a398583, reviewed Flutter
1e18d14 was integrated as b53a9ec. It clears obsolete selected ROI/rotation/zoom
when the active run changes or the selected region disappears. Additional tests
cover that regression, explicit preflight transmission and multilingual offsets.
Canonical scripts/ci/verify.sh passed on b53a9ec:206 Python/13 optional skips,
50 Flutter/three opt-in live skips, analysis, web release and scanners.
Log: /tmp/specimen-wave2-roi-canonical.log. Prior a398583 GUI evidence remains
attributed to that exact application version; backend source is unchanged.
The codec scanner dependency5868705 is included, but codec application/client
follow-ups are not yet integrated. No second-wave push or deployment occurred.

## Backend hardening checkpoint

Reviewed core d6be7a0 is integrated as1901ce7. Empty Git diff verifies exact
src/tests/dataconnect/scripts-data/pyproject.toml/uv.lock tree parity with that
owner checkpoint. Ordered unique provenance:

| Owner | Integrated | Scope |
|---|---|---|
| 3daf6c7 | c908fc1 | V3 checksum operations and scoped uniqueness |
| 5f15bc1 | 8984fb4 | Checksum test report |
| e0dd0aa | 6194707 | Bounded isolated trusted effects |
| 19997c7 | 9f4d182 | Persisted provider circuits |
| effb708 | 5a7109f | Explicit HEIC/DNG profile policy |
| 681d1e0 | 7a86fa9 | Probe lease/execution bound alignment |
| 5868705 | 5868705 | Already integrated exact codec fixture scanner metadata |
| d6be7a0 | 1901ce7 | Actual codec intake, bounded reads, SQL and provider bindings |

Independent verification on1901ce7:

- Canonical scripts/ci/verify.sh passed243 Python/23 explicit SQL/codec skips,
  50 Flutter/three opt-in live skips, analysis, scanners and web release.
  Log: /tmp/specimen-wave2-hardening-canonical.log.
- Fresh owned PostgreSQL/SQL Connect5589/9539 plus actual HTTP ran hardening
  concurrency, authority, worker recovery, history paging, upload completion,
  SQL application and process restart suites:30 passed in29.19s. Includes both
  SQLite/SQL same-source completion race and shared circuit admission.
  Log: /tmp/specimen-wave2-hardening-sql-http.log. Services stopped; state/logs
  retained at /var/folders/nq/t4rvrkyx2dx2293cx4bn8gfm0000gn/T/specimen-data-serve.vQmnin.
- Optional pinned HEIC/raw extras and test-only tifffile2026.3.3 enabled
  test_codec_runtime.py: nine passed in8.35s for actual HEIC/DNG intake,
  orientations, retained source/crop basis, restart and approval.
  Log: /tmp/specimen-wave2-hardening-codecs.log. Tests explicitly opt out of
  unavailable local memory enforcement; production codec isolation is unproven.

The client codec followup and independent combined hardening QA are pending.
Active graph externalization and language/script propagation remain unimplemented
at this checkpoint. Legacy V1/V2/null checksum rollout, institutional semantics,
provider/device and production approvals remain separate gates. GCS byte reads
are bounded; total GCS authentication/stream wall-clock time is not established.
No push, deployment, cloud mutation or paid inference occurred.

## Frozen combined codec checkpoint

Flutter f10eb79 is integrated as906e1348e71a0e800bfb260fa1125d67239b0e0e.
Empty diffs confirm backend tree parity withd6be7a0 and complete Flutter tree
parity withf10eb79. Existing scanner5868705 was not duplicated. Both codec
fixture copies remain SHA2568dc736071fc530260097279cee0a09fab35a7c67420ef2b3dcf7271fee673e7d.
Canonical passed243 Python/23 optional skips and54 Flutter/four opt-in live
skips, plus analysis/scanners/web. Log: /tmp/specimen-wave2-codec-combined-canonical.log.

The actual Flutter live_codec_test.dart passed against a fresh local codec API
with pinned optional extras and the explicit local memory-enforcement exception.
Specimen cc3502a9-fedc-5ea1-b893-4f73532034c4 reached review at revision20;
ROI correction returned revision23 with the same bounds, quarter-turn1 and exact
source digest. Test verified original bytes,64x96 decoded HEIF primary basis,
derivative SHA and a fresh authenticated repository reopening retained evidence.
Log: /tmp/specimen-wave2-combined-codec-live.log. State retained at
/tmp/specimen-combined-codec-906e134; own8123 server stopped.

Independent QA received this exact frozen combined SHA for hardening and actual
HEIC browser verification. Subsequent graph/TRN work is excluded. This checkpoint
is local and unpushed; production memory isolation and rollout gates remain open.

## Graph follow-up and open verification failures

Graph core0fc9cd0 integrated asa13ba6c with exact backend source/test/data tree
parity; frozen response fixture/generator d78a45e integrated asf1a87b8. Scanner
d77038b was already present and not duplicated. This is separate from codec
QA's frozen906e134. Canonical passed253 Python/24 optional skips,54 Flutter/four
live skips, analysis/scanners/web; /tmp/specimen-wave2-graph-core-canonical.log.
Client large-workspace recovery is not yet integrated.

The combined SQL graph/history/application/restart run FAILED:17 passed, one
failed at test_real_sql_adapter_workflow_cas_and_reconstruction. Its unconfigured
fresh repository list traversed a graph row retained by another test in their
shared synthetic scope; graph_blobs was None, so integrity failed closed. Owner
is repairing test scope/store configuration, not suppressing integrity. Preserve
/tmp/specimen-wave2-graph-sql-http.log. Owned5589/9539 stopped; retained cluster
/var/folders/nq/t4rvrkyx2dx2293cx4bn8gfm0000gn/T/specimen-data-serve.dTg9if.

Independently, QA found and deterministically reproduced a real LocalBlobs.put
publication race on frozen906e134: an identical concurrent put can see the newly
created final pathname before bytes are written and return409 Immutable blob
content mismatch. Prior passing concurrency runs do not close this intermittent
failure. QA log /tmp/specimen-qa-906e134-sql.log and deterministic harness
/tmp/specimen-hardening-blob-race.py are retained. Backend owns a minimal atomic
publication repair and repeated multiprocess/HTTP SQL verification. Same-key
completion replay passed; changed-key409 was intentional and is not a defect.
No hardening acceptance or push is authorized while the real race remains open.

## Atomic publication and graph fixture repairs

38fa32f integrated as8416892; independent integration found duplicate empty
blob regression, fixed by ownerc8001bb integrated as96caa27. Both use private
fully synced temporary files and atomic create-only hardlinks; hash checks stay
strict. Graph SQL fixture isolation3aca16f integrated asb23a9d0. Its initial
canonical run attempted SQL seeding before the opt-in guard; owner3bd7f64,
integrated ascd90ade, restores the guard before any setup network call.

Fresh SQL combined graph/publication/limits/concurrency/authority/worker/history/
upload/reconstruction/restart suite passed48 tests in45.20s, resolving the prior
combined graph fixture failure. Log:/tmp/specimen-wave2-graph-atomic-sql.log.
Owned5589/9539 services stopped; cluster retained at
/var/folders/nq/t4rvrkyx2dx2293cx4bn8gfm0000gn/T/specimen-data-serve.GRJDIp.
Canonical oncd90ade passed258 Python/24 optional skips,54 Flutter/four live skips,
analysis/scanners/web. Log:/tmp/specimen-wave2-graph-atomic-final-canonical.log.
Backend src/tests/data/dependency tree exactly matches owner3bd7f64.

QA is independently verifying the minimal906e134+38fa32f+c8001bb repair candidate;
this local combined pass alone does not close its publication-race finding.
Client large-graph fallback remains pending, as does TRN declaration work.
