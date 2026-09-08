# Scoped filtered search projections

Status: locally implemented data contract; backend/API integration is separately
owned. No cloud DDL, schema publication, deployment, paid inference or production
validation. Branch `codex/data-search-projections` starts at clean paging handoff
`584aac728b9b8b043df7964f1d7a255973ad2db9`. Prior wave branches are preserved.
Backend and architect agreed this contract before edits.

## Result

`SearchSpecimens` filters metadata in PostgreSQL and returns at most 100 rows.
It has no offset, total-result cap, client-side filtering or full-snapshot return.
`SpecimenSearch` is an inlined SQL Connect view joining `specimen` to exactly its
current `specimen_snapshot` by organization, collection, specimen ID and revision.
No mutable projection columns, tables, or Create/Save variables are added.
Atomic snapshot/revision commits immediately become searchable. Historical
snapshots cannot create duplicate results or satisfy current filters.

## Connector contract

Use the server-only `specimen-server` connector's `SearchSpecimens` named query
through the existing Admin impersonateQuery route. `NO_ACCESS` blocks end-user
execution. Backend binds `actorUid` to verified identity; organization and
collection active membership and requested sensitive permission are checked on
every page. `includeSensitive=false` excludes sensitive records.

Required variables: `organizationId: UUID!`, `collectionId: UUID!`,
`actorUid: String!`, `cutoff: Timestamp!`, `afterId: String!`, `limit: Int!`
(1..100), `includeSensitive: Boolean!`. `afterCreatedAt: Timestamp` defaults
null. First page uses null and empty afterId; subsequent pages use the last
returned createdAt and canonical lowercase 36-character ID. Both cursor parts
must be supplied together, and neither cursor timestamp nor cutoff may be in
the future. Ordering is createdAt ASC, id ASC with C-collated canonical UUID text.
The API owns opaque cursor encoding and binding to verified scope, all filters,
cutoff and ordering. Legacy offset 0 may start a fresh search; nonzero legacy
offsets must fail explicitly in the API, never silently reinterpret them.

All optional filter variables default to null. Null/omitted means no filter;
non-null filters are ANDed. Exact strings are case-sensitive.

| API filter | Connector variable | Persisted source / semantics |
|---|---|---|
| specimen_id | specimenId: String | canonical specimen UUID text, exact |
| asset_id | assetId: String | current snapshot asset.id, exact |
| active_run_id | activeRunId: String | current snapshot run.id, exact |
| batch_id | batchId: String | current snapshot batch_id, exact |
| state | status: String | typed specimen.state, exact |
| stage | stage: String | current snapshot run.stage, exact |
| disposition | disposition: String | typed specimen.disposition, exact |
| uploader_id | uploader: String | current snapshot asset.uploader, exact |
| reason_code | reasonCode: String | exact member of current run.reasons |
| blocker | blocker: String | current run.blocker, exact |
| profile_id | profileId: String | current run.profile.id, exact |
| profile_version | profileVersion: String | current run.profile.version, exact |
| created_from | createdFrom: Timestamp | typed specimen.created_at, inclusive |
| created_before | createdBefore: Timestamp | typed specimen.created_at, exclusive |
| risk_min / risk_max | riskMin / riskMax: Float | current run.review_risk.composite, inclusive 0..100 |

The API validates UUIDs, UTC timestamps, enums, nonempty strings and unknown
filters and returns explicit 422 errors where appropriate. The connector checks
page/cursor/date/risk bounds but does not duplicate the backend's evolving stage
enum. It honors supplied exact strings; unknown strings do not become no-ops.
Reason and blocker filters remain distinct; no union issue alias, full text,
score bands, or calibrated confidence claim is implemented.

Missing, nonnumeric or out-of-range risk is null, never zero. Numeric zero remains
zero. Risk predicates exclude null scores; absent risk predicates retain them.
The numeric score is a persisted review-prioritization value, not accuracy or
calibrated confidence. JSON type checks precede casts. Malformed/non-array reason
payloads safely become an empty list; only string array members are considered.

Returns `items` with `id`, `revision`, `status`, `stage`, `disposition`,
`sensitive`, `createdAt`, `updatedAt`, `domainCreatedAt`, `assetId`, `batchId`, `filename`, `uploader`,
`activeRunId`, `blocker`, `profileId`, `profileVersion`, `reasonCodes`, `risk`,
`synthetic`. Active run and synthetic come from current snapshot run.id and
run.profile.synthetic, including initial creations whose typed activeRunId has
not yet been set. API may derive record_version_id from run ID and revision and
available actions from current authorization. No payloads or signed URLs return.

Typed specimen.createdAt is authoritative for search filtering, ordering, cutoff
and displayed creation time. Original snapshot root.created_at may differ by
milliseconds and remains immutable domain provenance; it is not rewritten.
Nullable domainCreatedAt returns this original string without full hydration;
it is not used for search filtering or cursor ordering.
Current data can change between pages. The fixed cutoff excludes later-created
records; mutable filters do not create a transactionally frozen result set. A
record becoming eligible behind the cursor appears on a fresh search. Backend
must use the same typed creation-time semantics in SQL and SQLite summaries.

## Indexes and rollout boundary

`dataconnect/sql/search-indexes.sql` adds a scoped creation-time/text-ID index
including current summary fields, and a scoped JSON expression index for batch
with specimen ID/revision. The existing snapshot key supports exact current
revision joins. These indexes avoid schema duplication; the `allRows` view field
is a constant SQL true used solely for optional-filter predicates, not storage.
Explicit fallback expressions avoid SQL Connect rejecting null timestamp
comparisons even when their optional branch is bypassed.

Index DDL is an independent reviewed data rollout, never Hosting workflow work.
Inspect definitions and validity: `IF NOT EXISTS` does not repair an invalid or
mismatched index. Local connector restart preserved all four supplemental paging
and search indexes. A local development schema reload can recreate tables and
remove indexes; apply supplemental indexes after schema stabilization. No claim
is made that a destructive schema deployment preserves them.

Not every JSON filter has an expression index. Risk/reason/profile/uploader
predicates can require database evaluation of candidates. This implementation
bounds response size and eliminates client hydration/scans; it does not promise
constant-time arbitrary filter combinations. Measure real corpus distribution
and snapshot sizes before proposing further indexes or performance guarantees.

## Verification

`SPECIMEN_TEST_PG_PORT=5609 SPECIMEN_TEST_DC_PORT=9559 scripts/data/test-postgres.sh`
runs the real PostgreSQL 18 / SQL Connect 3.2.0 connector suite. The search suite
uses 2,037 current specimens and 4,074 immutable snapshots, plus a later insert
and new current revision. Named connector operations verify exact/combined
filters, old-revision exclusion, null and omitted filters, typed timestamps,
missing/string/numeric/zero risk, and full filtered traversal across timestamp
ties using bounded pages. It checks scope rejection, sensitivity and revocation,
invalid cursor/range/page bounds, later-created exclusion and fresh-search
inclusion, and immediate membership change after a new current revision.

Measured EXPLAIN ANALYZE queries use the scoped composite cursor index and the
selective persisted batch expression index with the current-revision join. These
are equivalent SQL plan checks on synthetic local data, not a production latency
claim or an assertion that every GraphQL filter combination uses an index.

The same suite reruns first-wave CAS/receipts/security and prior paging coverage
including 10,037 due rows, restarts SQL Connect, reads immutable snapshots again,
and checks all four supplemental indexes remain valid. `scripts/ci/verify.sh`
also passes Python tests, pre-commit checks, Flutter analysis/widget tests and
release web build. Backend HTTP cursor, SQLite equivalence, Flutter wiring and
end-to-end API behavior remain the owning tasks' integration evidence.

Final local evidence: canonical CI gates passed; final PostgreSQL suite retained
logs at `/var/folders/nq/t4rvrkyx2dx2293cx4bn8gfm0000gn/T/specimen-data-test.2O9KHW`.
The temporary server on 5599/9549 was stopped, and both its ports and final test
ports 5609/9559 were verified closed. No active backend lease was interrupted.
