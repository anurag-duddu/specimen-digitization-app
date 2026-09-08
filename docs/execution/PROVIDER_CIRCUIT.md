# Persisted provider circuit

Worktree `/Users/anuragduddu/.codex/worktrees/5178/specimen-digitization-app`;
branch `codex/provider-circuit`; base
`17a585a4943bc04af334af33a379f9c5cb177355`. Only the new provider_circuit.py,
matching test_provider_circuit.py and this report change. The reviewed commit is
sent to the coordinator/backend owner after canonical verification. No existing
workflow, worker, storage, dependency or deployment file is edited.

## Persistence and integration contract

`CircuitStore.load(key: str) -> tuple[int, dict] | None` returns the current
revision and complete serialized state, or None when missing.
`compare_and_swap(key, expected_revision: int | None, state: dict) -> int` commits
atomically and returns its new revision, raising `CircuitConflict` on conflict.
Backend maps its existing storage.Conflict and missing-document revision zero to
this port. Admission/result updates attempt CAS at most four times, reloading
state each time. Other persistence failures return explicit blockers without
exception text, credentials or raw provider data.

`CircuitKey` includes organization, collection, provider identifier and a
config_sha256 fingerprint. The digest must describe sanitized versioned provider
configuration, not credentials. Its `storage_key` property is an opaque,
deterministic UUIDv5 under the dedicated `specimen:provider-circuit:v1` namespace,
compatible with the existing worker_cursor key type. Raw scope/provider values
are not persisted in keys or circuit state. Backend owns the port binding and
must retain its worker_cursor namespace separation and authorization.

`ProviderCircuit(store, clock, policy=CircuitPolicy())` takes an injected UTC
clock. `admit(configkey, probelease_seconds)` returns Admission with permitted,
open, busy or blocked status, reason and optional retry_at. Only permitted has a
PermitToken. `record_success(token)` and
`record_failure(token, transientclass, retry_after=None)` return CircuitOutcome
with recorded, stale or blocked status. Retry-After input is relative seconds;
the adapter/worker parses an HTTP date before calling this module.

Default policy is three transient failures, local cooldown 30 seconds doubling
on repeated openings to a 300-second cap, four CAS attempts, 128 maximum in-flight
permits, and at most 300 seconds per permit lease. All durations and counts are
validated; malformed policy construction fails explicitly. Persisted policy
fingerprints must match. A policy change belongs under a new sanitized config
fingerprint, not a reinterpretation of existing circuit history.

The complete serialized state includes schema version, config/policy fingerprints,
CLOSED/OPEN/HALF_OPEN, epoch, failure count, opening count, open-until deadline,
last persisted UTC clock, current permits, last reason and last failure class.
Permits contain unique IDs, epochs and expiry timestamps. Tokens are internal
fences, not authentication credentials; API/model input must not supply them.

## State and failure semantics

CLOSED admission persists a permit before returning it. A valid success consumes
that permit and resets consecutive transient failures. Timeout, rate_limited and
provider_error increment the counter. Authentication, authorization, policy and
malformed-response outcomes consume a CLOSED permit without incrementing the
transient counter; the worker must retain their actual operational blocker.
Valid biological no-match/ambiguity/empty-result responses are service availability
successes, never evidence that a record is clear. The worker maps these separately.

On the threshold, the circuit opens, increments its epoch and invalidates all
older permits. A positive provider Retry-After on a transient outcome opens
immediately even before the threshold: continuing calls would violate the stated
minimum. Its minimum is not shortened by the local 300-second exponential cap.
The result uses max(local backoff, provider delay). Delays over one day, negative,
nonfinite, boolean or malformed values block for explicit review rather than being
silently capped into an earlier provider call.

After cooldown, a CAS transition admits exactly one HALF_OPEN probe. Other workers
receive busy with the probe lease deadline. Probe success closes the circuit and
advances the epoch. Any probe failure reopens it; nontransient failures remain the
worker's responsibility, not an automatic retry policy. An expired probe is
outcome-unknown: the next admission persists OPEN with a new epoch and cooldown,
and does not reuse its token. Old outcomes, expired leases and repeated outcomes
are fenced and cannot reset a newer circuit or increment it twice.

Expired CLOSED permits may be pruned during a later admission so capacity is not
permanently consumed. This is only circuit bookkeeping. It does not reconcile,
clear or retry an expired workflow effect. The outer workflow's durable intent,
lease and explicit outcome-unknown recovery remain authoritative. Likewise a
lost CAS acknowledgement never returns a permit: the call remains blocked even
if its internal permit was persisted. Success/failure CAS retries report outcome
only; they never invoke the provider again.

A naive/non-UTC/invalid clock or regression behind the last persisted state time
blocks. Clock observation is compared to persisted transitions; read-only denials
do not write timestamps. Malformed stored state, fingerprint mismatch, storage
outage, unknown failure classification and exhausted CAS contention each have a
specific safe reason. No raw exception is exposed. The module never sleeps,
performs a provider call, allocates infrastructure, schedules a retry or changes
a specimen queue.

## Verification

The test adapter uses actual SQLite transactions with BEGIN IMMEDIATE and revision
comparison, using separate database connections. Tests cover CLOSED threshold,
duplicate/late outcomes, OPEN epoch fencing, restart, probe success/failure and
expiry, transient versus nontransient mapping, Retry-After 600 seconds, backoff
30/60/120/240/300/300, scope/provider/config isolation, malformed policy/state,
UTC/regressed clock, invalid arguments, in-flight limits and storage errors.

Two independent clients synchronize reads to force a real CAS race for HALF_OPEN:
exactly one wins and the other reloads busy. A separate concurrent test preserves
both CLOSED failure increments. A Python subprocess admits a probe and exits;
another interpreter reopens the same SQLite file and is denied a duplicate probe.
The original token can still be completed by the authorized outer owner. Fault
seams additionally prove exactly four CAS attempts and lost-ack non-admission.
No mock provider success is presented as a live service validation.

Validation performed:

- `uv run pytest tests/test_provider_circuit.py -q`: 15 passed, including
  malformed extreme UTC timestamps that cannot safely represent future deadlines.
- `scripts/ci/verify.sh`: 133 Python tests passed, two existing emulator-only
  tests skipped; repository hooks, both secret scanners, Flutter analyze/widget
  test and release web build passed.
- Ruff undefined/unused-name checks and `git diff --check`: passed.

Existing Starlette deprecation and unconfigured Logfire warnings remain; the new
circuit itself emits no network calls or telemetry. Backend integration
must bind the real persistence port, execute circuit admission before provider
work, checkpoint the existing workflow intent, and record results while preserving
all original effect fences. Its shared HTTP/SQL worker regression tests are a
separate required gate. This module provides HAR-009/OPS-002 component behavior;
it does not replace workflow retries, claim exactly-once external effects, select
a durable engine or complete production acceptance. No private data, provider,
paid, cloud, provisioning, push, merge or deployment action occurs in this task.
