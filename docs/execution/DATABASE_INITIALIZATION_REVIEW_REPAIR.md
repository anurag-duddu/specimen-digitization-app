# Independent-review repair evidence

This follow-up repairs two findings in initial candidate `07b9a4d5597000ea0eace3775e5daffbc14d8a50`.
The initial candidate's full-suite counts and file hashes are historical; final
canonical verification belongs to the coordinator after integration.

- Both initializer cleanup and ordinary disposal check complete named-instance
  user-operation history since signed absence before each destructive effect.
  Any other create/delete, or update without exact retained request/response
  proof, prevents adoption of the current same-named principal. History reads
  use only the existing two named targets and are bounded by the cleanup clock.
- Complete application-role memberships now compare all recipients, grantors
  and ADMIN/INHERIT/SET options, preserving actual PostgreSQL18 bootstrap
  ADMIN-only rows and the permanent managed self-grants.
- Four initial lifecycle probes reproduced the ownership failure. The final
  suite also covers same-actor updates, late same-actor creation, deletion
  between absence and creation, and replacement between revoke and delete.
- Six real PostgreSQL18 failures reproduced unknown recipients, altered managed
  self-grant options and extra bootstrap-grantor edges to ordinary recipients.
  An early fixture assumed a bootstrap username; the corrected red run uses the
  actual local bootstrap principal and the managed role explicitly.
- Focused final initialization suite: **144 passed in 30.80 seconds**, including
  PostgreSQL18, actual Node guards, encryption and orchestration. The later
  named-history transport assertion also passed. No new full-suite run, push,
  merge, cloud execution or managed-service readiness claim was made here.

## Frozen repair inputs and test evidence

The file/log hashes below identify the consumed source and evidence. Public
checksums are identifiers, not credentials.

| Resource | SHA256 |
| --- | --- |
| `scripts/ci/release_initialize.py` | `cb2f1b4f097a6ee78c6d875be11e2ae10cf8953a26f79fc2e9559c0de9c972a9` |
| `scripts/ci/initialize_postconditions.sql` | `ebbce67687c4cf1b43675c6b5c833235a9aa0547414870348e3e83b223513e4f` |
| `scripts/ci/test_data_initialization.py` | `e62e1253624c0ce037f4ea40aa5cc3cd6ba36a1dc37197cc5dcc7d51b7bc4361` |
| `scripts/ci/test_initializer_disposal.py` | `014bedb881b70852e5321225d9ffbd1f01927d381e4e5230640ab3755ed17c1c` |
| `scripts/ci/test_initialization_acl_postgres.py` | `f5a52e3b0716f367b5b54f2a3052f6362b7c772ecb592dd94d530f23aa2142b9` |
| `/tmp/specimen-initialize-lifecycle-red-20260909.log` | `f4ffef024c312403ac096cd0bcadeb4ce6b0ccec3ea96f5c48753885099403e5` |
| `/tmp/specimen-initialize-memberships-corrected-red-20260909.log` | `332fa559b2a8f8f281faea8163b7055a3162548c9db294ead89daad3d363d182` |
| `/tmp/specimen-initialize-final-review-repair-green-20260909.log` | `2c939dfd0537dab5a2642746242bcb74146589bd5d7a436fc05e4bfe7bb7cd24` |
| `/tmp/specimen-initialize-lifecycle-transport-green-20260909.log` | `e5ae89c15236c4684c4748d86776127551478997e0886c5d18ff2e964dbd68c1` |
