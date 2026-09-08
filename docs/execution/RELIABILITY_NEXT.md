# Reliability wave: bounded polling checkpoint

Branch: codex/backend-reliability. Worktree: /Users/anuragduddu/.codex/worktrees/3782/specimen-digitization-app.
This checkpoint is a tested subset of NEXT_WAVE, not completion of the full wave or production readiness.

## Carried dependencies and repairs

Collection modules: original5023f235 as7a39834. Evidence modules: original0da144de asa68a0bb. Data base790a9f9/1a9bce8 as8923541/bf0dbd8, paging305a133/584aac7 as16ad098/ff74e50. Frozen-candidate QA repairs7a47b10/df73e35/f0d8ede/4bea6c9 are carried as5551f70/4597443/7c7ad85/a8e5ea9. Integration should retain its equivalent dependency commits and select only subsequent core commits; do not duplicate these dependencies.

## Implemented behavior

SQL Connect writes now use V2 Create/Save to persist workAvailableAt atomically with snapshots and receipts. The worker reads ListDueWork metadata with a fixed cutoff and canonical ID keyset. SQLite has the same due metadata and index. Cursor state is persisted as the authorized, owner-scoped worker_cursor document. Fixed-cutoff sweeps wrap so inserts or renewed eligibility behind the cursor are revisited. Legacy API list helpers no longer silently stop at 10,000, though they still hydrate results and are not the worker discovery path.

Polling rotates up to eight scopes per tick with bounded steps per scope, independent record/scope/membership failure handling, bounded control-plane backoff, record cooldown, conflict accounting and stop-event signal handling. Health captures actual attempts, errors, last success and oldest due item considered in the current tick.

Each run retains step, external-call, token-reservation, active-time and approved-cost budgets. Reservations precede the external intent checkpoint. Unpriced production effects block rather than becoming zero-cost calls. Agent invocations reserve their permitted two requests. Policy requires at least a 30-second lease margin beyond its external deadline. PydanticAI calls have an async total deadline and bounded usage. Late results are discarded, active leases reject concurrent retry/resume/reprocess and correction restarts, and late CAS cannot overwrite cancellation. A crashed pending effect becomes outcome-unknown and never automatically repeats.

Resolved prompt text, model/provider routes and execution policy are retained before effects. Production transcription and extraction read pinned prompts; route drift fails closed. Retry delays include jitter and honor numeric or HTTP-date Retry-After, without reducing a provider minimum.

The B04 audit compaction and authorized immutable-history behavior remain intact. History listing now uses the new metadata-only SQL query, with unchanged fixed-revision API pagination and verified exact-version readers. Original fixture bytes are unchanged.

## Evidence

The large discovery test reads actual SQLite metadata for 10,037 due records, restarts the worker halfway through, and proves every ID is considered once without hydrating discovery snapshots. Other tests exercise poison record isolation, membership cooldown, exhausted budgets before effects, unknown production pricing, concurrent lease/CAS cancellation, process death after intent, late-result rejection, and HTTP active-lease guards.

Separately enabled tests against disposable PostgreSQL18.6 + SQL Connect9589 exercise actual V2 writes, workflow CAS/reconstruction, real TCP process restart, 110 repeated HTTP reviews with history/replay, and the complete PollingWorker SQL due-page/cursor path through independent observations and final review. The worker observed four synthetic external stages with no scope or record errors. These are synthetic fixtures and real persistence/HTTP execution, not live inference or museum clearance evidence.

Canonical scripts/ci/verify.sh is the required checkpoint gate; see the handoff message for its final count. Ruff F checks and diff checks also pass. No push, merge, cloud provisioning, paid inference or deployment.

## Still required in this wave

- Wire the carried collection profile/classifier/image-quality modules and authority/harness/risk modules into application paths, with verified source literals, immutable phase outputs and explicit unavailable authority states.
- Add provider-wide persistent circuit-breaker behavior and complete the remaining crash-boundary/scoped-failure matrix. Current cooldown is worker-local, not a shared provider circuit.
- Bound/configure all production adapter wall-clock effects, including the unconfigured SAM3/authentication path, and prove those constraints with controlled service tests. Current async model deadline and elapsed-result rejection must not be described as live SAM3 timeout validation.
- Move remaining API discovery/search paths onto useful bounded projections; removal of a silent cap does not make full-list hydration a scalable API.
- Continue preserving immutable historical evidence if a single current evidence graph itself grows beyond the current payload bound; the B04 repair specifically addresses repeated historical audit/run duplication.
- Run the final integrated SQL/HTTP/profile/harness acceptance and independent QA. This checkpoint does not select a broker or managed durable engine.
