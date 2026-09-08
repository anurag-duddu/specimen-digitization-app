# Independent review of a local data-owner artifact

Classification: **owner-report artifact, independently checked for consistency**.
This QA task did not reproduce PostgreSQL or emulator execution. Data owner's
frozen commit was not yet supplied at review time. No live cloud acceptance.

Artifact: `specimen-data-test.QyrfUm/backup-restore-proof.json`, supplied by data
owner from a private temporary local test directory. SHA-256:
`eb5cd641144342014d7ff529cf8eac6165cca68369e1e1d7e722aad2e927d6e7`.

Independent JSON comparisons established:

- `kind` is `local-synthetic-only`; recorded PostgreSQL version is 18.6.
- Exactly 27 tables, 26,315 synthetic rows, including 22,139 specimens.
- Complete before/after restore and final repaired inventories are equal.
- Both connector reconciliation rounds retain table hashes/counts and the core
  `specimen_scope_checksum` catalog entry: unique and valid, exact expected
  definition on organization, collection and source checksum.
- Both rounds remove the same four nonunique supplemental query indexes.
- All four DDL repair/idempotence inventory snapshots equal the initial full
  inventory. All repaired checksum reads return the expected specimen ID and
  revision. The query intentionally returns only those two columns; comparing
  it to the five-column input object would be an incorrect QA assertion.
- The recorded post-restore EXPLAIN uses `specimen_scope_checksum` Index Scan
  and returns one row. Statistics refresh and writers-quiesced flags are true.

These are comparisons of retained owner observations, not independent proof
that writers were quiesced, a dump was restored or the emulator binary executed.
Reproduce against the frozen data candidate and review actual quiescence,
schema/restart, supplemental DDL, ANALYZE and read/write reopening order before
closing the migration gate. The previous 16,251-row rehearsal is a different
historical dataset and must not be conflated with this artifact.
