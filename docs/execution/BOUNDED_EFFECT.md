# Bounded trusted effects

Worktree `/Users/anuragduddu/.codex/worktrees/23ec/specimen-digitization-app`;
branch `codex/bounded-effects`, base
`cb9684904fb58d0a7621282ec4c9820f5c5ec476`. Only the new
`application/bounded_effect.py`, `tests/test_bounded_effect.py`, and this report
change. Backend owns `production.py` and all workflow/API wiring. No cloud,
credential fetch, paid inference, provisioning, push or deployment occurred.

## Handler contract

```python
run_isolated(
    trusted_callable,       # hardcoded, importable top-level synchronous function
    payload,                # JSON primitives/dicts/lists only
    timeout_seconds,
    max_result_bytes,
    *, max_input_bytes=1024 * 1024,
) -> IsolatedResult
```

The frozen dataclass result contains `status` (`completed`, `deadline_exceeded`,
`worker_failed`, `output_limit`), `value: bytes | None`, `elapsed_seconds`,
`input_bytes`, `result_bytes`, safe `reason`, `worker_pid`, `cleanup_complete`.
Backend requested exact response bytes: the child helper returns **bytes**, not a
parsed provider object. Only `completed` carries a value. `completed` means the
helper returned within its deadline; it does not prove provider success, valid
SAM output or a correct specimen. Backend must validate those exact raw bytes.

Callable references are derived from an already imported Python function object.
Lambdas, closures, bound methods, strings, non-exported functions, coroutine and
generator functions are rejected. The production integration must hardcode its
helper; an API/user must never supply a module, function or import search path.
Importability is checked at the parent boundary and resolved again in the fresh
child; import failures produce worker failure. Application/test import paths are
propagated as trusted runtime metadata, never accepted in payload.

The entire Google `fetch_id_token` plus SAM HTTP request must occur **inside** the
same helper. The parent must not perform token discovery first and only wrap the
POST. Backend's helper should stream the response with its own byte cap, and pass
only safe structured input; this wrapper does not read credentials or know Google
or SAM semantics. Auth environment/ADC access is inherited intentionally by the
trusted application process. stdout/stderr are discarded and exception strings,
tracebacks and payload contents are not returned as errors. Actual raw success
bytes must remain private provenance, not be logged as a result summary.

## Deadline and process semantics

A single monotonic budget starts before input validation/serialization and covers
private IPC setup, interpreter creation/startup, module import, helper auth, HTTP,
response transport and parent receipt. The deadline is checked before invoking the
helper, after its return and before the parent accepts bytes. A child exiting late
cannot publish an accepted result. The wrapper uses a fresh interpreter subprocess,
not a thread or a timed-out future that keeps running. It does not fork an already
initialized native model/provider thread pool. On expiry, it sends TERM, waits up
to one second, sends KILL if needed, and waits/reaps for up to two seconds. Success
and failure paths also reap the child. It never retries automatically.

`elapsed_seconds` includes normal cleanup time. `cleanup_complete=False` means the
OS did not confirm reaping after bounded termination; backend must retain an
operational block, not permit a new effect or describe cancellation as confirmed.
Production helpers must remain synchronous and must not spawn detached subprocesses;
this wrapper owns/reaps its direct child, not arbitrary independently daemonized
processes. The runtime must supervise parent process failure as well.

The lease must be at least **overall deadline + 30 seconds** for cleanup/scheduling
margin, and result commits must retain the existing revision/lease fencing. A
local kill cannot cancel an HTTP request already accepted by a remote service.
Deadline, process failure or oversized output after dispatch can therefore leave
an unknown external outcome; backend persists that state and requires authorized
reconciliation rather than blindly retrying or classifying it as Deferred.

One platform caveat is explicit: Python/OS process-creation calls and filesystem
syscalls cannot universally be interrupted mid-call. Startup is charged to the
budget; if creation returns after the deadline, the child is immediately terminated
and its output rejected. The tested delayed-start case proves this behavior. A
hung kernel/system call may still delay wall-clock return beyond the budget plus
cleanup allowance. This is not a claim of hard real-time OS scheduling.
[Python documents the process-creation limitation](https://docs.python.org/3/library/subprocess.html).

## Serialization, transport and bounds

Inputs are strict JSON values: no pickle, custom classes, encoder callbacks,
non-string keys, cycles, NaN or infinity. Traversal is bounded to depth 64 and
100,000 values, uses depth-sized iterator state, checks the monotonic deadline and
rejects size excess before serializing whole input. Incremental UTF-8 JSON encoding
checks the byte cap. Temporary encoder chunks are bounded by admitted string size,
not an unlimited source stream. Input and response caps must each be 1–16 MiB;
input defaults to 1 MiB. The backend must choose an explicit adequate cap for its
payload (including any base64 expansion) or pass an approved immutable reference
resolved inside the helper. Oversized input fails before any child/effect.

Input and result travel through a private temporary directory, removed after normal
completion, failure or timeout. No input credential/body is put in command-line
arguments; arguments contain only fixed worker dispatch and the private directory.
Trusted startup metadata has a 64 KiB bound and control output a 4 KiB bound.
The helper's exact bytes are checked before writing response IPC; the parent checks
file size before reading and also limits its read to cap+1. Oversized output returns
`output_limit` with an observed byte count and no value. Provider output is never
unpickled or parsed as JSON by the parent wrapper. The response filename is an
internal transport detail, not a claim all returned bytes are JSON.

This caps IPC/parent result allocation, not the helper's peak heap, response buffer,
CPU use or external requests. The helper must stream/cap HTTP and the deployment
must set an OS/container memory ceiling if hard memory bounds are required. A
trusted helper could allocate memory before returning; this wrapper cannot undo
that allocation. No memory-limit enforcement or complete security sandbox is
claimed. The wrapper also cannot prevent external telemetry explicitly emitted by
an incorrectly instrumented helper; backend must retain its no-credential-log policy.

## Verification

`uv run pytest tests/test_bounded_effect.py -q` exercises actual spawned interpreters
and a test-owned loopback HTTP server. The server thread is only the test peer; the
effect itself always runs in a separate process. No Google credential acquisition
or remote service is called.

Cases include exact UTF-8 input/output boundaries, simulated slow auth before HTTP,
continuous TCP body drip, a 4 KiB real HTTP response rejected at a 32-byte IPC cap,
process death, TERM-resistant child requiring KILL, no surviving PID, no accepted
late result, no leaked exception/stdout text, malformed/non-JSON/cyclic/deep input,
non-importable callables, input deadline before spawn, non-byte response, delayed
spawn charged to the original deadline, private IPC cleanup and observed oversized
byte count. The slow-auth fixture proves auth is inside the same child/budget; it
is not a live Google authentication benchmark.

Canonical gate/counts and reviewed commit are handed to backend/coordinator below.
No shared workflow or production helper was edited. Backend remains responsible
for actual Google-auth/SAM composition tests, streamed HTTP caps, durable intent,
unknown outcome handling, leases, fencing and production runtime validation.

Final verification: **12 focused tests passed** in 5.61 seconds. Staged-code
`scripts/ci/verify.sh` passed repository/secret checks, **104 Python tests passed,
10 explicit skips** (optional codec/SQL suites), Flutter analysis/widget tests and
release web build. Ruff F and staged diff checks passed. Canonical log:
`/tmp/bounded-effect-verify.log`. This final report paragraph is a documentation
addition after the staged-code gate and is checked by commit hooks. No push or
production changes; integration must retain its own exact-candidate verification.
