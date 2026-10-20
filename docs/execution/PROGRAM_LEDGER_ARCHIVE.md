# Program ledger archive

The program allowance ledger (`application/lane_allowance.py`, G9, G30) no
longer keeps every charge in one document. This note says why, what changed,
and what is left for the owner.

## What grew

Measured read-only on 2026-10-20. Payload sizes come from the storage footprint
review of that day (sections 3 and 8), a session note kept outside the
repository (`storage-footprint-2026-10-20.md`, in the side-session notes of
session local_e3ae4073). The counts and the disk figures were re-read the same day
with `executeGraphqlRead` aggregates and Cloud Monitoring:

- The ledger is one `worker_cursor` document in the Data Connect table
  `AuxiliaryDocument`. Every charge saved it through `SaveDocumentV2`, and that
  mutation also inserts the whole saved payload into `AuxiliaryVersion`.
- The ledger document was at revision 2,003 with 2,003 version rows. Its payload
  had grown from 58 B to 214,678 B (913 ordinary and 99 research effects), so
  the versions held 197 MB of JSON: about half the final size times the number
  of saves. Saves grow with paid steps, so those bytes grew with their square.
- Cloud SQL `disk/bytes_used` went from 234.7 MB (daily maximum at the start of
  the 30-day window, 2026-09-20 to 09-21) to 393.4 MB (2026-10-20). The disk is
  10 GiB, `PD_SSD`, with automatic storage increase off.

Nothing reads those versions. The compare-and-set uses the document's
`revision`; a resend is recognized by its `AuxiliaryReceipt`;
`GetDocumentVersionV2` has no caller in the application.

## What changed

The ledger document is now a head: the total, the last charge, and only the
effects it has not archived. A charge still checks and changes the total and
its effect in one compare-and-set save of the head, as before. After an
ordinary reservation or settlement leaves more than `HEAD_EFFECTS` (16) effects
in the head, the worker writes up to `ARCHIVE_BATCH` (64) of them, ordinary and
research alike, to one archive document each (kind `worker_cursor`, id derived
from the ledger id, the effect family and its key, `sensitive: false`), then
saves the head without the effects whose archive holds the same state. A
research charge does not archive: it runs inside its send's lease, which should
not wait on up to 64 writes.

Why the invariants hold:

- An effect has two states, held then settled. Its archive is created with the
  state the head had and can only move from held to settled of the same charge.
- An effect leaves the head only after its archive holds exactly that state,
  and only if the head still holds it unchanged.
- `ProgramLedger.effect` reads the head first and the archive second. A key the
  head does not hold is therefore either never charged, or archived with a
  state at least as new as that head. A later change of the effect's state goes
  through a head save, which moves the head revision, so the charge's own save
  conflicts and is retried on a fresh read.
- So a reservation is still made once, a settlement still applies once, and the
  total still changes only in the save that changes an effect. Archiving never
  changes the total. If archiving fails, the effects stay in the head and the
  charge stands.

The existing head drains on its own: each save past the threshold archives up
to 64 effects, so the 1,012 effects of 2026-10-20 leave the head over about 16
charges. The head document is updated as before; no existing version row is
changed or deleted. This needs no schema, connector
or data release change: archives go through the existing `CreateDocumentV2` and
`SaveDocumentV2`, which already accept `worker_cursor` documents from the
worker's actor.

`tests/test_lane_allowance_archive.py` records the bytes each save would store
as a version row. On `origin/main` at `ba007d4c`, with one head keeping every
effect, 400 paid steps stored 28,021,053 bytes against 1,810,024 for 100 (15.5
times); with the archive the
test asserts under 5 times and no single save over 8,000 bytes. In a local run
on 2026-10-20 the same harness stored about 4 KB per paid step at 100, 400 and
1,600 steps.

## Left for the owner

**Pruning the old versions: not needed.** The 2,003 existing version rows stay.
They are about 197 MB of JSON; on disk they take less, not measured (the review
found 35.8 MB after zlib, and 2.3 times compression for the database's JSON
overall, which would be about 85 MB), against a 10 GiB disk. They no longer
grow. Deleting them might not lower the disk figure either: PostgreSQL mostly
keeps freed space for new rows of the same table rather than handing it back
without a table rewrite. If the owner ever wants them gone, it is a one-off SQL
statement on the production database, run by the owner and never by a release:
delete the rows of `public.auxiliary_version` with `kind = 'worker_cursor'` and
the ledger's `document_id` whose `revision` is below the document's current
`revision`. Take a backup first; it cannot be undone.

**A disk safety net: recommended, not urgent.** After this change the database
still grows with every specimen, mostly through `SpecimenSnapshot` (one full
copy per revision, about 6 MB of JSON per specimen on 2026-10-20). By the
review's arithmetic that is a few gigabytes at 1,000 specimens, inside the
10 GiB disk, but it is a projection, not a measurement. A full disk would stop
every write. Turning on automatic storage increase with a limit is cheap
insurance: Cloud SQL bills the provisioned size, so it costs nothing until the
disk actually grows. It is a production setting, changed only through
`scripts/ops/owner_setup.sh` (which has no step for it yet) or the release
workflows, never from an agent shell. If the disk ever grows past 10 GiB, the
restore-clone cost inputs that assume 10 GiB (`infra/live/data-resources.json`
`observed_storage_gib`, `infra/release/OWNER_INPUTS.md` `source_disk_gb`) need
updating too.
