# All-ten reading admission: local candidate evidence

Date: 2026-09-09 UTC. Task: `01a082b4-a9bd-7392-a73b-57ca45532fb7`.
Coordinator: `01a082b2-c2c3-70d2-be90-7bfb622c9102`.
Worktree: `/Users/anuragduddu/.codex/worktrees/7471/specimen-digitization-app`.
Branch: `codex/initialize-missing-database`; base: `1d24d6401e2899b87851532a939a99361e8d0e89`.
This candidate is the commit containing this document. No new PR, push, merge,
deployment, native cloud worker execution, paid inference or original specimen
image inspection was performed by this task. Initializer source is unchanged.

## Resulting behavior

Within the existing evidence-only worker execution, all exact ten authorized
specimens finish retained segmentation before any reading. A terminal failed
segmentation leaves the cohort incomplete; the worker finishes any remaining
eligible segmentation and exits once no segmentation can proceed. No discovery,
eleventh specimen, smaller region set, substitute route, extra execution or
clearance is introduced.

The stable existing `pilot_launch` auxiliary document is the cumulative ledger.
Admission validates every binding, run, pinned evidence marker, profile,
segmentation provenance and retained region. It calculates, for each specimen:

`number of retained regions * (Qwen invocation reservation + Muse invocation reservation) * maximum workflow attempts`

Each invocation reservation already covers its allowed underlying schema retry;
it is not multiplied by two again for cost. Calls reserve two and tokens reserve
16,000 per invocation, matching the existing bounded reader contract. Admission
also requires the complete remaining step and worst-case active-time capacity.
The comparison includes previously reserved segmentation cost, including retries.

One existing compare-and-swap document write publishes the entire `reading_cohort`
reservation or a durable blocked decision. This subdivides existing `runs`
allocations: their sum remains unchanged, preventing a double debit. Full holds
are never released or credited on success, known failure, unknown failure, or
restart. The ledger kind, connector transaction, schema, identity and sensitivity
contract are unchanged.

Immediately before the production reader boundary, the workflow revalidates the
whole retained cohort and writes a per-region, per-route attempt claim into that
same ledger by compare-and-swap. Claims survive a lost response and are checked
against retained attempt, call, token and cost counters. Direct adapter calls
without a matching active workflow dispatch fail. The existing external intent
and durable worker dispatch fences continue to block uncertain replay.

## Validation actually run

All images and adapter responses in these tests are generated local fixtures.
Fixture prices 17 / 59 / 89 microdollars are arbitrary test values, not provider
prices or an approved live cost plan. The single-worker success test segments
ten generated assets, retains two regions each, verifies the complete hold and
claim at every provider boundary, records exactly 40 unique readings, and stops
with ten `pilot_evidence_review_required` results.

The final focused command was:

```sh
uv run pytest -q tests/test_cohort_reading_barrier.py tests/test_evidence*.py tests/test_pilot*.py tests/test_reading*.py tests/test_worker*.py tests/test_stage_cost_reservations.py tests/test_sqlconnect_stage_cost_roundtrip.py
```

Result: **213 passed, 5 skipped, 3 warnings in 22.18 seconds**. The skips retain
existing opt-in requirements, including the isolated SQL Connect emulator.
The new barrier suite contains 29 tests. It exercises late/terminal tenth
segmentation, missing records/regions/provenance, multiple regions, insufficient
whole-cohort cost and capacity, pinned-input drift, same-ledger CAS contention,
known retries, unknown outcomes, consumed counter resets, unreconciled prior
reader work, lost hold/claim responses, restart and real protobuf Struct numeric
serialization. A Struct round trip is not a live connector qualification.

The original eight regressions failed before the barrier existed. Three further
liability regressions failed before durable claims were added. A corrected
non-retryable segmentation probe reproduced the terminal worker loop. Six
provenance/capacity probes failed before cohort-wide validation was tightened.
The earlier terminal probe used a retryable default failure; it was corrected to
an explicitly malformed non-retryable response before accepting red evidence.
Four old single-specimen reading tests required generated segmentation of the
other nine first; the old partial-reading budget expectation now correctly
requires zero reader calls when the whole work cannot fit.

## Limits and follow-ups

Independent review, canonical full verification and release gates remain the
coordinator's work. New nested-ledger payloads were verified in real SQLite CAS
and protobuf serialization, not a live SQL Connect service. This task does not
confirm native cloud readiness, actual model pricing, actual segmentation counts,
paid reader behavior or the real-ten outcome. The one-execution constraint and
frozen launch remain required. A stored earlier launch/reader liability is a
reconciliation gate, never authorization to reset or enlarge the budget.

Metadata snapshots are read and checked before admission and again at each
reader boundary; the ledger allocation itself uses a single CAS. This does not
add a cross-record SQL transaction around ten specimen metadata reads. Existing
repository revisions and dispatch fences remain necessary; this local evidence
does not claim isolation against arbitrary privileged concurrent metadata edits.

## Source fingerprints

| File | SHA256 |
| --- | --- |
| `src/specimen_digitization/application/worker_launch.py` | `06f28c4e21d46f43055214448f5082849f6c0ba9ba2a8d200e29384f84d2ee59` |
| `src/specimen_digitization/application/worker.py` | `907063e902793436341b52e070c90c7a2a0b3bfb5f51b12dae21add19e4fbfb3` |
| `src/specimen_digitization/application/evidence_pilot.py` | `899848565e068b1a73e1df7072223d4a335250dd44a6e43c2b119c88b0a6d355` |
| `tests/test_cohort_reading_barrier.py` | `24ec8a83462bd7b13641be9277dcc86ce85165199fc55524e0e90071b30ceefc` |
| `tests/test_evidence_pilot.py` | `2d98c7810695b0e3eab500a2d39b9d7c7638ee05f3b6d2763827c529dacd76b7` |
| `tests/test_stage_cost_reservations.py` | `dab85742d257fc45dfb194c00934bdd9397444ddc8ccd7c622708a43a19fa2b0` |

## Local test-log fingerprints

The outcomes above remain in this repository even if temporary logs expire.

| Local log | Observed result | SHA256 |
| --- | --- | --- |
| `/tmp/specimen-cohort-barrier-red-20260909.log` | 8 failing initial regressions | `ae2f4e31505090424b84827381c9728aaa5b79f7e88c40e6a763254a161dbeee` |
| `/tmp/specimen-cohort-barrier-first-green-20260909.log` | 8 passed | `f8582e2f1c487f917022426cd1aa4e58de7ec2faae5ef7a7ef38ec5326cc860e` |
| `/tmp/specimen-cohort-reader-liability-red-20260909.log` | 3 failed, 8 deselected | `1eb2cc92c5b279e55bff79156b8bc8c4b0814442e1d95232a911fb2806d8795a` |
| `/tmp/specimen-cohort-barrier-liability-green-20260909.log` | 11 passed | `68404bb22303c1714c872448e31e1130122e210c8b92878cd8fac86766ffb301` |
| `/tmp/specimen-cohort-terminal-corrected-red-20260909.log` | 1 failed, 18 deselected; explicitly non-retryable segmentation | `4818e8571d66f1c576f5dd2807d9bff0769fa2d83b49eb86df395d6ebfec4ef2` |
| `/tmp/specimen-cohort-integrity-red-20260909.log` | 6 failed, 2 passed, 19 deselected | `51f07512a243ac8f5d4a0114f7502a1a2584a5dfd862a13bb7fc9dafadf1e655` |
| `/tmp/specimen-cohort-integrity-green-20260909.log` | 120 passed, 1 skipped | `b4bfc57bc5ec6225b35c25d0bcd038dc8e1fde6433f04ae79f13187aef20c7d6` |
| `/tmp/specimen-cohort-final-focused-20260909.log` | 213 passed, 5 skipped, 3 warnings; 22.18 seconds | `a02a6d7ce7395ca651ac09f3f50a933e94672bf3aed2468abae0016b78cc94b6` |
| `/tmp/specimen-cohort-hooks-20260909.log` | Focused file hooks passed before final two test additions | `14fec5fb4ff883b8286d24a1dc3efd537d0ddfc57265d21c4d20bbb76a78fb76` |
| `/tmp/specimen-cohort-all-hooks-20260909.log` | All-file repository hooks passed, including secret checks, actionlint and shellcheck | `24ad6f263ac507f9228945447915e673989705f65c8f85e15c41417e72f7ab7a` |
