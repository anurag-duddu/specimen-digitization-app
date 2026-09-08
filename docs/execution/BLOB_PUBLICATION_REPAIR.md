# Atomic local blob publication repair

Isolated branch `codex/blob-publication-fix`, base `906e134`, worktree `/tmp/specimen-blob-publication-repair`. Independent QA reproduced a duplicate-upload 409: exclusive creation exposed an empty digest filename before the first writer wrote its bytes. A second identical writer then correctly rejected the incomplete object.

LocalBlobs now writes a private same-directory temporary inode, flushes/fsyncs complete bytes, and atomically hardlinks it to the digest filename without overwriting any existing object. An existing object is read with a size bound and its digest/content verified. The directory is synced before success. Each process removes only its own temporary file; a killed process can leave a non-addressable temporary file, which neither blocks future publication nor becomes a source reference. No sleep, retry loop, or weakened integrity check masks publication failures.

Tests exercise two spawned processes with forty synchronized same-byte publications while a separate reader hashes visible objects; a killed pre-publication writer and subsequent retry; owned-temp cleanup on fsync failure; existing corruption preserved and rejected; and the GCS adapter's existing generation-zero create precondition and duplicate-content validation. The GCS check uses a contract fake and is not live-cloud verification. No GCS code or cloud resources changed. SQL/SQLite HTTP concurrency tests verify authorized duplicate responses and provider circuit behavior against actual local persistence.

Logs: `/tmp/specimen-blob-publication-final.log` (four tests passed), `/tmp/specimen-blob-publication-sql-final.log` (combined publication, bounded reads and actual SQL/SQLite concurrency). Earlier logs contain a corrected test assertion expecting ValueError where the adapter correctly raised Conflict; there was no integrity bypass.

No push, production merge, deployment, or paid inference. The caller's last successful bytes remain immutable. Filesystems must support same-directory hardlinks and directory fsync; unsupported operations fail rather than publishing partially written data.
