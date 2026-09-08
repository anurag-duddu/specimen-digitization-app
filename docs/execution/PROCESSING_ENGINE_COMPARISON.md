# Bounded processing engine decision

Assessment date: 2026-09-08. Baseline:
`a53f855e963b457c3ee2065f387609a193bb6f32`, branch `codex/live-processing`.
Owner: processing workstream; coordinator accepts the combined launch contract.
Scope: exactly the ten specimens frozen by the data owner, with no expansion.

## Recommendation and status

**Decision proposed for this launch:** retain the application's SQL-backed
checkpoint engine and host one bounded CPU worker as a Cloud Run Job. Do not
introduce Temporal or Google Cloud Workflows for the ten-specimen run. The
application already owns step selection, effects, authorization, retries,
budgets, cancellation, and compare-and-swap fencing. Local failure injection
shows why that ledger remains necessary with an external engine.

**Confirmed locally:** application process-death recovery and fencing tests;
Temporal worker/server crash recovery with and without a durable effect guard.
**Not confirmed:** live Cloud Run behavior, production SQL durability, Workflows
execution, production Temporal deployment, provider idempotency, GPU/SAM service,
or successful inference on any of the ten specimens. This is an engineering
choice with explicit cloud acceptance gates, not a completed live comparison or
proof of production readiness.

**Blocked:** cloud mutations and live tests await the concrete budget, frozen
ten-object generation/hash manifest, and coordinator authorization. No cloud
resources, IAM, deployment workflows, dependencies, or user services were changed
by this assessment. Tests used generated local fixtures only.

## Comparison against the required failure behavior

| Requirement | Temporal | Google Cloud Workflows | Existing checkpoint worker |
|---|---|---|---|
| Recover orchestration after worker death | Tested locally: persisted dev-server history survives worker and server SIGKILL, activity retries | Documented managed orchestration and Cloud Run Jobs connector; no live test | Tested: fresh process/repository reads retained intent and cursor |
| Prevent duplicate unknown paid effect | Engine retry alone repeated the fixture effect; application guard required | Retry policy must distinguish idempotent and non-idempotent calls; application guard still required (inference) | Tested: intent committed before effect; unknown outcome blocks after lease expiry |
| Reject late result after cancellation | Requires application revision/lease fence at external persistence boundary (inference) | Same application fence required (inference) | Tested: late completion loses CAS and cancelled state remains |
| Preserve cost/call/deadline reservations | Application-owned budget ledger still required | Application-owned budget ledger still required | Tested: exhausted budgets stop before adapter; unknown/late effect keeps reservation |
| Bound operation for ten specimens | Adds a Temporal service plus worker and workflow/SDK lifecycle | Adds a workflow revision, invoker identity and job invocation/error contract | Reuses SQL data service and one finite worker execution |
| Production hosting proof | Not run; local dev server is not a production service | Not run | Not run; Cloud Run Job is the proposed host |

Temporal Activities may execute again following failure; retry limits do not
establish downstream exactly-once effects. The relevant official contracts are
[Activity execution](https://docs.temporal.io/activity-execution) and
[Python failure handling](https://docs.temporal.io/develop/python/best-practices/error-handling).
Workflows distinguishes retry predicates for idempotent and non-idempotent steps;
its documented [retry syntax](https://docs.cloud.google.com/workflows/docs/reference/syntax/retrying)
does not replace a provider receipt or application reservation. Workflows can
[execute a Cloud Run Job](https://docs.cloud.google.com/workflows/docs/tutorials/execute-cloud-run-jobs),
but adding that invocation layer does not remove the existing worker's safety
responsibilities. These are documentation-based conclusions for Workflows.

## Failure evidence

Command executed in the processing worktree:

```bash
uv run pytest -q tests/test_processing_engine_comparison.py tests/test_worker_recovery.py -k 'not real_sql'
```

Result: **13 passed, 1 deselected, 2 warnings in 6.46 seconds**. The deselected
test requires seeded SQL Connect/PostgreSQL and is not counted as a pass.
Warnings were Starlette's AnyIO deprecation and unconfigured local Logfire.

The two new process tests run the actual application `Workflow` against a local
SQLite database in a child process. They wait until durable intent is committed,
then send SIGKILL either before a downstream fixture receipt or after that receipt
is fsynced. A fresh repository and workflow, after lease expiry, retain one call
reservation, reject any adapter replay, preserve the unknown outcome and enter
`processing_blocked`. Neither test treats a missing receipt as proof of failure.

Existing tests cover a competing attempt during an active lease; a cancellation
revision fencing a late result; late external-deadline completion; exhausted
step/call/token/time budgets; unpriced production calls; membership failure and
poison-record isolation; and persisted keyset discovery after worker recreation.
The 10,037-record discovery test uses local metadata fixtures. It does not expand
the authorized cloud sample or claim inference throughput.

### Actual Temporal experiment

CLI `1.8.3`, embedded server `1.31.2`, Python SDK `1.24.0` in an isolated temporary
virtual environment. No repository dependency or global executable was changed.
The first standard-library download attempt failed certificate verification;
system `curl` succeeded with normal TLS verification enabled. The downloaded
archive SHA-256 is recorded in the evidence manifest. File-specific pre-commit
initially flagged benign high-entropy runtime/build IDs and base64 fixture results
in the raw histories, plus JSON checksum fields. Raw files were retained locally;
decoded summaries and a Markdown hash manifest avoid that scanner noise without
changing scanners, baselines, or adding allowlists.

The dev server used a persistent SQLite file, loopback ports `17333`, `17334`,
`17335`, and no UI. Each activity committed a local fixture effect, then waited.
The harness SIGKILLed its worker and dev server, reopened the same server file,
and started a fresh worker. Activity policy allowed two attempts with a four
second start-to-close timeout and one second initial retry delay.

| Probe | Worker/server death | Effects after restart | Final result |
|---|---|---|---|
| Unguarded activity | Both SIGKILLed | 2 | `completed` |
| Activity with persisted intent guard | Both SIGKILLed | 1 | `blocked:external_outcome_unknown` |

Both saved histories contain 11 events. The retry attempt is part of Activity
execution and must not be equated with a separate scheduled Activity in history.
The harness uses an unsandboxed pure workflow definition to isolate recovery;
it does not validate production sandbox imports, version compatibility, mTLS,
Cloud namespaces, HA, or the production SQL adapter. Its tiny intent guard is a
fixture; the separate process tests exercise the real application's ledger.

Evidence is retained under
[`qa-evidence/processing-engine/`](qa-evidence/processing-engine/manifest.md):
`experiment.py`, `result.json`, both decoded event summaries, and a SHA-256
manifest. Full raw histories remain at the isolated local path in the manifest.
The event summaries omit runtime identity/build IDs and decode result payloads. The script makes no provider requests and contains no specimen data.
All experiment-owned worker/server processes were terminated on completion.

To repeat without adding repository dependencies, create a new temporary
directory, copy `experiment.py` into it, place the reviewed Temporal CLI named
`temporal` beside it, create a virtual environment there, and install
`temporalio==1.24.0` in that environment. Run its Python against the copied script.
It refuses occupied ports. Use a new directory on every run because retained
workflow IDs and marker files intentionally persist. The dev server is for this
local test only and must never become the production runtime.

### Workflows experiment not run

No workflow was created or executed. A managed Workflows execution and worker
hosting trial would cross the current cloud mutation/budget gate. No local Python
simulation is offered as equivalent evidence. After authorization, a meaningful
trial would interrupt an actual Cloud Run task after persisted intent and again
after a receipt, lose the invocation response, run the approved recovery path,
and assert the same single-effect/unknown-outcome behavior and cancellation CAS
fence against production-like SQL. Record exact workflow revision, job image,
execution IDs, database revision, and receipts. Comparison remains asymmetric
until that experiment occurs.

## Concrete bounded hosting contract for delivery

Use one job task, parallelism one, no platform task retries, no scheduler and no
automatic batch expansion. A provisional worker shape is one CPU and 1 GiB RAM;
it makes approved remote calls and is not a GPU model host. Resource adequacy and
cost are unbenchmarked; delivery must price and validate this shape before launch.
Require a finite worker wall deadline below a configured job timeout, exact
manifest hash, maximum ten authorized specimen IDs, durable per-run cost/call/
token limits and an aggregate approved batch ceiling. Unknown prices fail closed.
Use immutable image and secret version pins; never floating provider routing.

Cloud Run defaults include task retries and a ten-minute task timeout, so delivery
must set explicit values. A provisional 30-minute job cap may bound an initial
run; it is not a promise that ten specimens finish within it. Work can stop and
resume from SQL after reconciliation. [Task retries](https://docs.cloud.google.com/run/docs/configuring/max-retries)
and [task timeouts](https://docs.cloud.google.com/run/docs/configuring/task-timeout)
are configurable; timeout applies per attempt, so retry count affects the bound.

SIGTERM must stop discovery immediately. An interrupted in-flight call retains
its intent and reservation; shutdown must not mark an uncertain effect safe to
retry. The job's forced termination is an expected recovery case. Cloud Run's
[container contract](https://docs.cloud.google.com/run/docs/container-contract)
defines termination signaling; application deadlines and SDK timeouts must fit
that contract. The tested SIGKILL path proves the application cannot depend on
cleanup handlers alone.

The finite job ends with a retained summary distinguishing complete, review,
blocked, pending and failed outcomes. It does not wait indefinitely for a human
review. Human corrections remain in SQL. Another job execution requires the
coordinator's bounded launch/recovery decision, the same authorized manifest,
and durable budget accounting across executions. Re-running a process must not
reset a paid-call allowance. A single-task setting alone does not prevent two
separate job executions; application CAS/intent fencing and launch admission
must cover that case.

## Reconsideration and launch gates

Revisit Workflows when the batch needs managed multi-service orchestration or
connector operations beyond the checkpoint worker. Revisit Temporal when tested
requirements need durable signals, timers and multiple independently versioned
worker queues that outweigh the added service. Neither is justified merely to
retry non-idempotent paid requests. If broader multi-tenant Temporal processing is
later adopted, evaluate its task queue fairness alongside the existing bounded
scope rotation; this ten-specimen launch needs no additional fairness subsystem.

Delivery owns the separate reviewed runtime workflow and resource revision; data
owns live SQL/GCS durability and the ten-object manifest; processing owns bounded
entrypoint, actual provider/SAM routes, intent persistence and receipts. No Hosting
workflow change or hand deployment is authorized by this recommendation.

Before launch, verify aggregate spending admission across concurrent executions,
exact membership/manifest filters, real SQL kill/restart and CAS behavior,
actual provider output retention, pinned working SAM service, and public/API
integration. On failure stop new admission, retain evidence and reconcile unknown
effects; use the prior compatible immutable image only after reviewing schema
compatibility. Do not clear intent, refund unknown reservations, or re-run an
unknown paid effect merely to make the batch appear complete.

PR/CI: this assessment is part of the processing owner's PR, recorded in
`LIVE_PROCESSING.md`; no separate PR or deployment was performed by this subtask.
