# Cohort time admission repair

Date: 2026-09-09 UTC. Task `01a082b4-a9bd-7392-a73b-57ca45532fb7`.
Branch `codex/initialize-missing-database`; base `3bb8d172e81a1204631f064a9d9131ebd1c7ed22`.
Candidate is the commit containing this report.

This corrects the time-capacity claim in `COHORT_READING_ADMISSION.md` for
3bb8d17. Independent review demonstrated that per-specimen active-time checks
could admit readers when the whole serial cohort could not fit either launch
expiry or the existing effective 1500-second worker maximum. The earlier source
fingerprints and 213-test pass are historical, not validation of this repair.

The existing pilot ledger now retains one execution start/deadline. It is first
bound before effects and can only become earlier, including after restart.
Missing deadline evidence after previous effects fails closed. The worker also
supplies its actual remaining monotonic execution time. This introduces no new
execution and increases no workflow, cloud, resource or time limit.

Before the first reader, and again at every reader boundary, the whole remaining
serial work must fit the minimum of launch expiry, the retained deadline, and
actual remaining worker time. The calculation includes every remaining allowed
reader attempt at the existing per-invocation timeout, maximum local retry
jitter, known pending provider wait, scheduling intervals, final review ticks and
the existing five-second margin. A later provider Retry-After is checked against
the same deadline; this does not claim to predict unbounded future provider
waits. A failure retains existing cost holds/claims and stops incomplete.

Validation: three initial probes reproduced the late-launch, effective-worker
maximum and restart-window gaps. Final focused evidence/pilot/reading/worker/cost
suite passed **218 tests, 5 existing skips, 3 warnings in 24.07 seconds**. Five new
time regressions cover launch lifetime, whole work exceeding the unchanged 1500
seconds, restart without deadline refresh, missing historical execution window,
and monotonic depletion with a stalled wall clock. The cohort fixture retains a
120-second default so independent negative probes remain meaningful. Feasible
success tests explicitly select generated 1-second invocation timeouts; no live
price, throughput or model behavior is implied.

Independent final re-review and canonical verification remain coordinator gates.
No paid call, cloud action, source-image read, initializer change or budget-ledger
v2 implementation is part of this commit.

| Source/test file | SHA256 |
| --- | --- |
| `src/specimen_digitization/application/worker_launch.py` | `bf6e3f26b9e94e1d26da44c83001141be9599f3d06df9fd79914656da1345980` |
| `src/specimen_digitization/application/worker.py` | `510fda233e92ae96bb373dab5d222cbe51a9da98d01fcdc6c449941b5896b85b` |
| `src/specimen_digitization/application/evidence_pilot.py` | `80ef231ab9b523adce0a34c5cf52c178cf8deb1229c0943f204c4a1b472fd51e` |
| `tests/test_cohort_reading_barrier.py` | `1fd9be8f41eccb48f07b8a2aec60ef757470810fca48f8f5d43977bb5d23a106` |
| `tests/test_evidence_pilot.py` | `0d364514169de516e112987752444d032da77ec0b11cf505234a6aa8dfafb94c` |

| Local log | SHA256 |
| --- | --- |
| `/tmp/specimen-cohort-time-red-20260909.log` | `8f29218d7591d0f35b1f32ebdd8c33fd63f1524ec4d6ed84300173709917899b` |
| `/tmp/specimen-cohort-time-green-20260909.log` | `147386a2537ef0de4bde6c650e947067505e00cebacc366c5e88801f33acc241` |
| `/tmp/specimen-cohort-time-final-20260909.log` | `0c9714e3d12f4ca0310a2f253ddc730b74ebfd551807522f4d177bd4139434b7` |

## Follow-up correction after independent review of 73f5885

The preceding source fingerprints describe 73f5885. Independent review found
that an existing false-valued execution_window could be treated as absent and
recreated. This follow-up distinguishes key absence from all existing values,
rejects wrong types or shapes before writing, and never replaces the malformed
window. The existing cost allocations and claims remain untouched.

Seven generated variants reproduced five failures and two already-safe denials;
all seven now fail closed. The related cohort/evidence/cost/worker suite passed
99 tests with 3 warnings in 19.81 seconds. No resource, timeout or execution
limit changed. Accounting v2 is separate from this correction.

| Follow-up source or log | SHA256 |
| --- | --- |
| `src/specimen_digitization/application/worker_launch.py` | `9a6c8ef183c7192cb86ae4bed58958fa4eaa50de8c309245af7d4b4bf7ac342f` |
| `tests/test_cohort_reading_barrier.py` | `6b882d99d8f9de9f9ee14f59ba4cd4e35b1bf817abd36577608e863c8f2c5641` |
| `/tmp/specimen-cohort-falsey-window-red-20260909.log` | `5eeda78c4431c8cf6596681180b5ebcb5fef514ee04938ba9e8e1ce321ba77c0` |
| `/tmp/specimen-cohort-falsey-window-green-20260909.log` | `bfc6905badac0961455a757465a10e99974c7f5a3579ded1141734b019759f02` |
