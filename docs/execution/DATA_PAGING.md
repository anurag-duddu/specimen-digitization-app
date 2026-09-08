# Due-work paging and bounded history

Status: local implementation and PostgreSQL verification; no cloud mutation,
schema publication, production deployment or paid inference. First-wave handoff
remains on `codex/data-platform-foundation` at `1a9bce8`.

This wave: `codex/data-work-paging`, same isolated worktree
`/Users/anuragduddu/.codex/worktrees/39c2/specimen-digitization-app`, from clean
`1a9bce8dcfcc69d9a4a08b12609104335ef28752`. Read shared PLAN and architect
NEXT_WAVE.md. Data owns schema/operations/index SQL and local data tests; backend
owns worker, persistence adapter, HTTP cursor encoding, history compaction and all
Python changes. No Python modules or dependencies changed here.

## Problem and result

The prior worker repeatedly fetched whole snapshots through offset pages capped
at 10,000. Mutable ordering could omit or repeat work, and large queues beyond
the cap could never be reached. The new operations return bounded due summaries,
use a stable ID cursor with a fixed creation-time cutoff, and impose no total cap.
Only attempted work needs a full snapshot. Scoped listing/history projections
avoid embedding raw history in each page.

## Exact operation contract

All operations use the existing server-only `specimen-server` connector, admin
REST impersonateQuery/impersonateMutation endpoints and verified actorUid. Both
organization and collection membership are checked on every page. Lists are
bounded to 1..100 items and return no signed URLs, raw image/model payloads or
snapshot JSON. No end-user SQL operation is exposed.

`ListDueWork` variables:

| Variable | Type and meaning |
|---|---|
| organizationId, collectionId | UUID, verified authorized scope |
| actorUid | String, bound by backend identity verification |
| cutoff | Timestamp, fixed at sweep start; must not be in the future |
| afterId | String, empty for first page; thereafter last returned canonical lowercase UUID text |
| limit | Int, 1..100 |

Returns `items[{id, revision, state, activeRunId, workAvailableAt, createdAt}]`.
IDs from this projection have canonical hyphens, unlike normal SQL Connect UUID
output. Filter is same scope, createdAt<=cutoff, state in pending/running/
retry_scheduled, and workAvailableAt null or <=cutoff. Null is legacy/immediate
runnable scheduling, not a claim that a blocked or terminal record is eligible.
Other states never enter the due page. Active lease/retry timestamps must be
projected by the backend; the workflow still rechecks the current revision,
lease and completed-step state before any effect.

`CreateSpecimenV2` and `SaveSpecimenV2` have all original variables plus nullable
`workAvailableAt: Timestamp`. Backend supplies it on every V2 commit: due now,
future retry, lease expiry, or null for unscheduled nonrunnable state. GraphQL
nullable variables cannot distinguish omitted from explicit null, so the backend
must honor this contract; omitted/null on a runnable row is conservatively due.
Scheduling updates are atomic with revision, snapshot, receipt, audit and outbox.
Original CreateSpecimen/SaveSpecimen operations remain unchanged for first-wave
compatibility. Old rows with null scheduling remain discoverable in runnable states.
Do not mix old/new worker writers after activating scheduling without validating
projection semantics: a V1 save does not update an existing schedule timestamp.

Additional projections in `paging.gql`:

- `ListSpecimenPage(scope, actorUid, cutoff, afterId, limit, includeSensitive)`
  returns `specimens` summary fields, ID ascending. Current sensitive access is
  checked, and non-sensitive listing excludes restricted records.
- `ListDocumentPage(scope, actorUid, kind, cutoff, afterId, limit)` returns
  `auxiliaryDocuments` metadata without payload. Kinds upload/batch only; callers
  load selected documents explicitly. Requires sensitive permission, consistent
  with existing auxiliary operations.
- `ListSnapshotHistory(scope, actorUid, id, afterRevision, throughRevision, limit)`
  returns `specimenSnapshots[{revision, sha256, contractVersion, createdAt}]`.
  Revisions ascend; 0 begins traversal, throughRevision is fixed at the current
  summary revision and cannot exceed it. GetSnapshot fetches a chosen immutable
  payload. Current record sensitivity protects historical metadata too.

The API owns opaque cursor encoding and must bind scope, operation/filter, cutoff
and last ID/revision; never accept an unvalidated cursor from another collection.
A page is exhausted when fewer than limit rows are returned (or a final empty
page); a full page always permits continuation. There is no 10k break condition.
All ID cursors accept only empty or canonical lowercase UUID text.

## Fair traversal and restart

Freeze cutoff for each collection sweep, advance afterId to the last returned
item after processing the page, and rotate bounded pages across collections.
Continue the existing sweep across polling ticks; do not restart at its first
page each second. Persist a cursor when backend restart fairness requires it.

A record becoming due behind the current cursor, or an insert after cutoff,
can legitimately be absent from that sweep. Reset cutoff and cursor after
exhaustion; it is then eligible in the next sweep. This is eventual traversal,
not a promise of a transactionally frozen queue. Updating early items cannot
move their immutable IDs ahead of the cursor, and new post-cutoff inserts cannot
extend the sweep indefinitely. No row is permanently discarded merely because
it was not returned this time. An intentionally cancelled/rescheduled row is
re-evaluated from current state. Concurrent consumers still need revision CAS.

`worker_cursor` is added to auxiliary Create/Save/Get operations. Active
operator/reviewer/manager/admin with sensitive permission can create and update
its own cursor; GetDocument/SaveDocument/GetDocumentVersion reject a different
creator even in the same collection. General document listing forbids this kind.
Backend uses a stable scope/actor-specific ID and stores a bounded
`{cutoff, after_id, revision}` payload, CAS after a completed page. A crash before
cursor commit safely replays that page; repeated crashes need backend backoff
and supervision. Data paging alone does not guarantee timely progress under an
endlessly failing worker. No new broker/outbox consumer is introduced.

## Schema and indexes

Specimen gains nullable workAvailableAt and native composite due-work index.
SQL Connect's UUID_Filter does not implement gt/le operators (compiler verified),
so two narrow SQL @view projections cast the existing immutable UUID to canonical
text with C collation. They do not copy IDs into a separately maintained scan key.
SQL Connect inlines these view definitions; do not assume physical PostgreSQL
views exist or try to query a fabricated specimen_listing table directly.

A native UUID index cannot efficiently serve text-cast ordering. Additive
`dataconnect/sql/paging-indexes.sql` supplies concurrent expression indexes for
scoped specimen and auxiliary text cursors. Local runners install them only into
their disposable PostgreSQL clusters. The local equivalent late-page relational
query used specimen_text_cursor in EXPLAIN ANALYZE after ANALYZE; this is not a
measurement of every generated SQL shape or a production latency guarantee.

Production index execution requires the separate authorized data rollout, never
Hosting CI. Retain these supplementary indexes during COMPATIBLE schema
migrations and inspect the actual diff; do not assume STRICT mode preserves them.
Concurrent index creation can leave invalid indexes after interruption: inspect
pg_index.indisvalid and resolve invalid definitions before retry. IF NOT EXISTS
does not repair an invalid or differently defined existing index. Confirm the
actual index definition, permissions, load and query plans in staging before
production. This task did not run index DDL against any cloud database.

## Verification

`scripts/data/test-postgres.sh` creates a unique PostgreSQL18.6 cluster, compiles
SQL Connect3.2.0, runs the original regression suite, applies supplemental indexes,
runs `paging-test.mjs`, restarts SQL Connect, reconstructs old/current snapshots
and verifies both supplemental indexes are still valid. Owned processes stop on
exit; synthetic data/logs remain in the printed temporary directory.

New real-PostgreSQL tests cover:

- 10,037 due rows over 102 bounded requests, including retry and legacy-null states;
- continuous early-item requeue without starving the tail or duplicating a page;
- due updates behind the cursor and new post-cutoff inserts recovered next sweep;
- future retry/lease-style timestamp exclusion and atomic schedule changes;
- two racing V2 saves, exactly one winner with no inconsistent revision/schedule;
- outsider/cross-scope denial, page limits, malformed/future cursor rejection,
  revoked membership mid-scan, sensitive record/history denial;
- snapshot metadata pages bounded by a retained revision while new snapshots append;
- worker cursor creator isolation and operator compatibility;
- specimen/document metadata keysets and absence of large payload fields;
- equivalent late-page SQL index selection and index survival across restart.

The original PGlite concurrency limitation remains; these tests require real
PostgreSQL. The full first-wave connector tests still run against additive changes.
Canonical `scripts/ci/verify.sh` is required before pushing; final result is sent
with the commit handoff. Storage behavior is unchanged by this wave.

## Integration and limits

Backend accepted the operation signatures and owns replacing capped/full-snapshot
loops, computing retry/lease schedules, cursor persistence/rotation, control-plane
backoff, and bounded current-history representation. These operations do not
alone remove the previous_runs/audit arrays or prove the backend's complete worker
failure matrix. History compaction must retain exact old snapshots/digests and
must not truncate evidence to pass a size bound.

A V2 rollout is additive but still requires tested old/new adapter compatibility,
explicit scheduling projection migration, and reviewed schema/index publication.
First-wave artifacts remain frozen independently. No institutional acceptance,
production provisioning, availability claim, deployment or paid effect is implied.

Final verification: implementation commit
`305a133ff3daf2422e16060ffb4e19666a6df24c` passed canonical verify.sh (repository
hooks, 33 baseline Python tests, Flutter analysis/widget test/release web build)
and the real PostgreSQL suite described above. The first canonical attempt only
normalized an EOF blank line; the subsequent full run passed. Backend accepted
signatures but is prioritizing first-candidate QA repairs; full new worker
integration is not yet verified by this data task.

Backend confirmed it was not consuming the new local server. Stopped the owned
serve-local process/cluster and confirmed loopback5579/9529 closed; preserved
synthetic logs/data at the printed temporary directory. No idle service is leased.
