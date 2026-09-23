# Approved review worker timing

> 2026-09-23: The owner's decisions in [`docs/execution/golive/PLAN.md`
> section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> supersede parts of this document for the go-live program. Each superseded
> clause keeps its original text and carries a dated note naming the
> decision. [`golive/RELEASE.md`](golive/RELEASE.md) lists the code that
> still enforces a superseded clause until a later go-live pull request
> changes it.

> 2026-09-23: Superseded for the go-live program by [`docs/execution/golive/PLAN.md`
> section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G2 and G11. Specimens are processed one at a time, on demand, instead of
> the single bounded worker execution, timing clock T and SAM life reserve
> this document defines; the ten pilot specimens remain the acceptance
> cohort, processed in order, and SAM 3 scales to zero instead of expiring
> after an hour. Release envelopes, cost ledgers and reservations, including
> the reservation budget and approval digest this document requires, are
> retired; data and runtime releases now deploy automatically on merge.

The combined approval recorded on 2026-09-14 adds one explicit timing dialect.
It does not change legacy launches. This document describes source behavior and
required native qualification; it is not an operational launch packet or evidence
of native completion.

An approved runtime plan retains its existing `runtime-prepare/v1` or
`runtime-activate/v1` phase and adds
`worker.timing_version: approved-worker-timing/v1`. It requires the approved
`shared-release-reservations/v2` budget and matching approval digest. Its pinned
launch has `timing` with exactly `version`, `approval_sha256`,
`dispatch_started_at_unix` and `sam_expires_at_unix`. For native qualification,
root must durably record the original timestamp T when issuing the bounded
original authorization, before any API-first effects or image preparation, and
retain it in the later launch and dispatch intent. DATA initialization,
restore/clone cleanup and owner bootstrap
can finish before the original API start Sa. When T=Sa, both image preparations,
input setup, reviews, public build if needed and startup consume that unchanged
interval. The launch expiry must be T+3500, within the original release packet.
The packet's `issued_at_unix` retains the actual original authorization issue
time; later construction, materialization and review retain their actual later
timestamps separately. Never backdate or recreate the origin, claim a later
packet already existed at T, or add future receipt hashes to the original record.

Before granting or writing the exact launch inputs, and again before protected
activation installation/dispatch, native qualification requires an independently
reviewed guard over the actual launch, original timing-origin receipt and
effective policy readbacks. The guard must parse the launch through its qualified
source consumer, join its T to the original source/cohort/API scope and verify
T+3500 < G, where G is the earliest expiry of every needed runtime permission or
dependency. With completion expiry Ec and API expiry Ea, require G <= Ec <= Ea;
Ec=Ea=Sa+3600 is permitted only when the actual scopes and effective policies
substantiate it. Retain the original SAM expiry Es <= Ec and the independent
Es-D >=2135 check immediately before dispatch. A true input flag or a valid
digest alone does not prove these temporal or effective-permission joins.

The actual protected job start, worker cleanup, bounded final Google observations
and publication/closeout must also fit the job's 55-minute deadline and their own
remaining bounds. The 100-second arithmetic gap between T+3500 and Sa+3600 does
not prove cloud finalization fits. Record actual ordered phase durations, remaining
bounds and cost at each transition; both three-image preparations consume the
original clock. A late path stops with spent/unknown evidence, without a new
clock, third image triplet, extra secret version, refund or permission extension.

Before the sole job request, activation exclusively creates and fsyncs
`worker-dispatch.intent.json`, retaining the original timing, launch/source pins,
fixed execution token and request digest. An existing intent is never replaced.
A final guard rechecks the exact request and at least 2135 seconds of remaining
original SAM lifetime after fresh release admission and before SDK dispatch.
The 2135 seconds comprise 240 platform startup, 60 application startup, 1200 SAM,
30 polling, 600 shared parent work and a five-second margin. These are admission
reserves, not extra execution time or a cloud latency guarantee.

The job remains one task, parallelism one, zero platform retries, 1 CPU and 1 GiB.
Its timeout is at most the remaining time to T+3500. The same timing object is
passed as `SPECIMEN_WORKER_TIMING`; the supervisor reads it before materializing
configuration and verifies it against the pinned launch. Useful work ends by
T+3485. Owned-group hard stop/reaping shares the absolute T+3500 limit; the
existing two-second reaping bound is also retained. Startup, imports, SDK calls,
polling and final summary never start a new execution clock. A retained earlier
deadline can only shorten enforcement. Wall-clock corrections cannot restore
elapsed time inside an admission instance.

Approved evidence operations require one attempt per model stage. Before each
SAM boundary, remaining SAM/poll work and the shared parent reserve must fit the
unchanged SAM expiry; known regions and a lower bound for still-unknown region
counts must also fit the original worker window. This pre-SAM lower bound never
authorizes readers. Reader admission requires every actual region of all ten
persisted, successful SAM results, exact bindings and the existing atomic
cohort reservation. Its retained time bound includes 600 seconds of parent work
and 30 seconds of finalization, in addition to the existing reader/poll margin.
The safety margin is counted once in the complete worker envelope.

The all-region CAS also records the reader-phase identity. Only an acknowledgement
received before the original SAM expiry authorizes the in-process transition.
An unknown/late acknowledgement remains fenced: a restarted process cannot adopt
the stored phase as proof of timely completion. Admitted readers may then continue
until the original useful-work cutoff, even after SAM expires. They cannot return
to segmentation, extend SAM, drop a specimen/region, or create another job.

Slow work stops with blocked/unknown evidence instead of a completion claim.
The illustrative 25-region schedule does not guarantee native completion: actual
startup and parent I/O may consume its remaining room. Tests include a feasible
50-second startup with ten full 120-second SAM bounds and fifty 30-second reader
bounds, plus late-start and unknown-transition rejection. No test spends money,
loads museum pixels or proves native trace/data/UI acceptance.

Legacy launches without this timing discriminator retain their original
1500-second internal / 1800-second platform limits and existing budget dialect.
The original SAM activation lifetime remains at most one hour in both dialects.

## Worker trace delivery

> 2026-09-23: Superseded for the go-live program by [`docs/execution/golive/PLAN.md`
> section 2.1](golive/PLAN.md#21-owner-decisions-2026-09-23-chat-with-the-coordinator)
> G3 and G11. System prompts and text inputs and outputs at every VLM, LLM
> and SAM 3 level, SAM 3 parameters and the harness's tool calls with
> arguments and results (geocoding keeps only what G26 allows) are recorded
> in Logfire, one trace per run linked
> from the specimen record, not the metadata-only, worker-only scope this
> section fixes; the amended scope is in
> [APPROVED_LOGFIRE_TRACING.md](APPROVED_LOGFIRE_TRACING.md). The
> independent transport/privacy/completion review this section keeps as a
> release gate is retired along with other independent-review gates.

Approved native tracing requires `worker_trace` with version `worker-trace/v2`,
the reviewed existing `project_id`, the distinct immutable worker writer
`token_secret`, reviewed `service_name`, `identity_receipt_sha256`, and
`approval_sha256`. The approval is the original bounded tracing authorization
`06af8483b7b190a5b0f2549475681a60483f2aff98a714472baad28376703b48`;
the secret must use the exact `specimen-worker-logfire` parent and an acknowledged
positive numeric version. Legacy `worker-trace/v1` keeps its five-field template
compatibility but does not activate the newly approved native transport. The
private plan pin binds those metadata fields together. The coordinator must
verify the receipt and actual destination/access; a well-formed digest alone is
not that evidence. No token value belongs in the plan or launch.

Only the worker receives the `LOGFIRE_TOKEN` secret reference. Its fixed settings
select `SPECIMEN_TRACE_EXPORT_MODE=bounded-v1`, copy the exact
`identity_receipt_sha256` into `SPECIMEN_TRACE_SCOPE_SHA256`, and set
`LOGFIRE_SEND_TO_LOGFIRE=false` to disable the SDK's default native exporter.
Version 2 also copies its distinct `approval_sha256` into
`SPECIMEN_TRACE_APPROVAL_SHA256`; it never substitutes that approval for the
actual writer identity receipt.
Metadata capture, production environment, full head sampling and disabled
incoming distributed tracing remain fixed. The worker creates its shared
accounting ledger inside the existing supervisor-owned workspace; deployment
must not set `SPECIMEN_TRACE_LEDGER_PATH`. No endpoint override is allowed.
API and SAM templates receive neither writer reference nor trace settings.

The [additive bounded tracing approval](APPROVED_LOGFIRE_TRACING.md) authorizes
the reviewed native transport and distinct fifth writer-secret setup. Its approval
digest is separate from the budget authority and native writer identity receipt.
Existing four-slot setup history alone still authorizes neither another secret
version nor an unverified destination. Explicit writer use and bounded transport
initialization require the exact approval, verified identity scope and original
supervised deadline. Imports may read local SDK environment settings; that is
distinct from initializing an exporter or sending a request. Source implementation
and independent transport/privacy/completion review remain release gates.
Actual identity, owned setup, cost admission and delivery evidence remain
coordinator-owned gates even after the final source is reviewed.
