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
