# Scoped checksum precheck and atomic uniqueness

Branch `codex/data-checksum-precheck`, worktree
`/Users/anuragduddu/.codex/worktrees/39c2/specimen-digitization-app`, starts at
clean search handoff `9df195575f0fab5ffcefcf85c14326d184464ab4`. This is local
code/schema/test work only. No cloud change, migration, backfill, deployment or
paid inference occurred. Coordinator approved the expanded V3 scope after the
schema discrepancy below was verified; backend agreed the exact contract.

## Corrected premise and implementation

The clean search schema had no Specimen checksum field or scoped byte uniqueness.
SourceAsset.sha256 was nonunique; its constraint protected only bucket/object/
generation and its append was separate from atomic specimen creation. Existing
receipt tests proved duplicate request handling, not concurrent same-byte creates
with different item IDs. SQLite uniqueness must not be claimed as SQL evidence.

The added nullable `Specimen.sourceChecksum: String` has unique constraint/index
`specimen_scope_checksum` on organizationId, collectionId, sourceChecksum. Null
supports existing rows during an explicitly gated transition, not verified
checksum coverage. Same bytes in different collections are allowed. The digest
is server-computed/verified by the backend; connector validation checks format
and consistency with the snapshot, not access to original bytes.

`FindSpecimenByChecksum` uses required variables `organizationId: UUID!`,
`collectionId: UUID!`, `actorUid: String!`, `checksum: String!`, and
`includeSensitive: Boolean!`. It accepts only lowercase 64-character hex, checks
current active organization and collection membership, checks sensitive access
when requested, and returns `specimens[{id,revision}]` with fixed limit 2. Normal
SQL Connect UUID output may be 32 hex characters; backend canonicalizes IDs.
No full snapshot, arbitrary API checksum search, or new general search filter is
introduced. Null legacy checksums are deliberately absent from this lookup.

`CreateSpecimenV3` has the existing V2 variables plus required
`sourceChecksum: String!`. It checks canonical hex and equality to
`snapshot.asset.sha256`, then atomically writes the typed digest with specimen,
snapshot, receipt, audit and outbox. The scoped database unique constraint is the
final race guard. An empty precheck does not authorize two concurrent inserts.
Backend handles a uniqueness conflict by re-querying within verified scope and
returning the authorized duplicate result; it must not turn the conflict into a
successful second specimen or leak a sensitive match.

`SaveSpecimenV3` uses exactly the V2 save variables, with no new checksum variable.
It checks that the current typed checksum is nonnull and equals the next
snapshot.asset.sha256, alongside current revision/sensitivity checks and CAS.
It never updates the typed checksum. Missing/changed digests and null legacy rows
fail closed. The source digest cannot be changed through this named operation,
even if a caller constructs an inconsistent snapshot.

All operations are `NO_ACCESS` server-only. The server binds actorUid to verified
identity. Existing V1/V2 operations remain for compatibility with the prior test
and handoff contract; they do not provide the V3 checksum guarantee. Backend must
switch BOTH create and save to V3. Running legacy writers or unaudited null rows
is an explicit rollout gate, not production-ready checksum protection.

## Read-only audit and incremental rollout proposal

`dataconnect/sql/checksum-audit.sql` runs in a repeatable-read, read-only transaction.
It reports null/invalid typed checksum counts, missing current snapshots,
invalid or mismatched snapshot hashes, scoped duplicate groups, and unique index
validity/definition. It returns IDs, digests and states, never snapshot payloads.
It performs no updates, deduplication, deletion, history rewrite or backfill.

A separately authorized data rollout must:

1. Inspect current schema and obtain backup/restore evidence under deployment
   rules. Plan additive nullable column and scoped uniqueness independently of
   Hosting. Review table size, locking and an appropriate concurrent index /
   constraint installation sequence; this branch does not execute that plan.
2. Audit legacy candidates and compare their stored digest to verified immutable
   original bytes/provenance. Review duplicate groups and decide canonical links
   without silently deleting or merging specimens or rewriting history. A JSON
   digest alone is not proof that the underlying bytes were verified.
3. Perform a separately reviewed, bounded, resumable backfill after resolving
   duplicates. Recheck revisions/provenance while updating and let the unique
   constraint reject races. Do not auto-fill on a read or V3 save.
4. Coordinate writer quiescence/cutover: backfill completion cannot be declared
   while V1/V2 writers can insert further null rows. Deploy/verify V3 backend
   create+save, retire legacy writer access through a reviewed connector change,
   and prove no null/mismatched rows remain. Preserve fail-closed handling during
   transition instead of falling back from V3 to V2.
5. Re-run audit and actual concurrent intake/API tests, inspect unique index
   validity and the deployed connector/runtime versions. Only then claim enforced
   collection checksum deduplication. No production rollout was performed here.

## Verification and handoff limits

The real PostgreSQL 18 / SQL Connect 3.2.0 suite verifies malformed/mismatched
create digests, server-only lookup, current membership and sensitivity,
organization/collection revocation, same checksum allowed in a different
collection, and exact metadata without payloads. Two concurrent requests use
identical source digests but different specimen IDs and idempotency keys: exactly
one commits, the loser reports uniqueness failure, and total specimen/snapshot/
receipt/audit/outbox counts remain one each. Invalid saves leave revision
unchanged; a valid save advances revision and retains the source checksum.
Legacy V2 creation is intentionally absent from the typed lookup and blocked
from V3 save, proving the documented transition limitation.

A further 10,037 persisted typed checksums prove the bounded lookup and measured
EXPLAIN ANALYZE use of `specimen_scope_checksum`. The read-only audit is executed
against synthetic legacy data. Existing data CAS/security, due paging, filtered
search and restart/index tests also pass. `scripts/ci/verify.sh` passes Python,
hooks, Flutter analysis/widget and release web build. These are local results;
backend SQLite/intake conflict mapping and HTTP behavior remain its owner's
integration proof. No production performance or legacy readiness is inferred.

Code commit: `3daf6c7753601e9db14390bb79845d4cbed24459`.
Reproduce the complete suite with
`SPECIMEN_TEST_PG_PORT=5609 SPECIMEN_TEST_DC_PORT=9559 scripts/data/test-postgres.sh`,
and canonical gates with `scripts/ci/verify.sh`. Full suite logs were retained at
`/var/folders/nq/t4rvrkyx2dx2293cx4bn8gfm0000gn/T/specimen-data-test.09SsWp`.
The final standalone checksum/audit smoke used the same ports and
`FIREBASE_DATACONNECT_EMULATOR_HOST=127.0.0.1:9559 PSQL_BIN=/opt/homebrew/opt/postgresql@18/bin/psql SPECIMEN_TEST_PG_PORT=5609 node scripts/data/checksum-test.mjs`.
That disposable cluster is retained at
`/var/folders/nq/t4rvrkyx2dx2293cx4bn8gfm0000gn/T/specimen-data-serve.oQmCtW`.
Both local processes were stopped and ports 5609/9559 verified closed. No active
backend lease was interrupted. Commits are local for coordinator integration.
