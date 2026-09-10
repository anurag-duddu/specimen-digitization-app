# Protected first application database initialization

This is a separate `data-initialize-missing/v1` phase of the protected
`data-release.yml` main-push workflow. It is not `initialize_empty`, inventory
evidence, live permission setup or a workstation execution path. Existing
inventory, ordinary apply and bootstrap phases retain their meanings.

First collect the missing native evidence through the credential-bound,
read-only `data-initialization-inventory/v1` phase. Its plan has only `version`,
`source_sha`, observed `database_etag`, `initialization_files`, and
`catalog_recipient`. It connects to
`postgres` as the already registered no-role data maintenance principal and
collects the complete role/membership/catalog metadata. The public signed receipt
contains only its canonical hash, fixed provenance, session count, false
readiness flags and the encrypted evidence filename/digest.
It does not require the application database, expected application roles, or SQL
Connect principal to exist, and reports no readiness. No password fields or
specimen rows are queried. Review unknown facts before using its hash in an
initialization plan.

Both new plans require `catalog_recipient` with exactly `public_key_pem` and
`public_key_sha256`, bound to the reviewed coordinator public key. The private
key is never included in runner inputs. The locked cryptography library encrypts
the exact native observation bytes using random AES256-GCM with a key wrapped
using RSA-OAEP-SHA256. Repository, source, run and attempt provenance are
authenticated along with the envelope metadata. The public workflow publishes
only these encrypted envelopes, including facts retained before rejected native
checks. Successful encryption removes the local plaintext file; no plaintext
catalog filename or wildcard is an upload source, even if encryption fails.
Capability and absence checks use this same controlled transport.

The coordinator must verify the signed public receipt against its exact source,
run and attempt, match the downloaded envelope SHA256, and use the local-only
`release_catalog_envelope.decrypt_catalog` with the privately retained key,
expected public-key hash and expected provenance. That helper authenticates the
envelope and checks the exact plaintext digest/length. Independently recompute
the canonical `catalog` hash from the decrypted native JSON and compare it to the
receipt before review. A failed-run envelope is diagnostic evidence only and
cannot establish successful inventory or authorize initialization. Publishing a
raw catalog or assuming public Actions artifacts are private is forbidden.

The maintenance IAM SQL user is an upstream setup prerequisite. If the observed
SQL Connect service agent has no IAM SQL registration, the coordinator's
separately reviewed setup path must register that exact observed principal with
no database roles, then collect a fresh catalog. This initializer neither guesses
the principal nor registers it with elevated roles. Source absence/capability
checks require those two ordinary principals to be present and narrow before
backup/clone creation. Native API/worker SQL logins are outside this first
release's scope and must be absent; their runtimes use SQL Connect operations.

The otherwise empty source/clone may also contain the native managed database
`cloudsqladmin`, only when its observed owner is exactly `cloudsqladmin`. The
allowed database lists are exactly `postgres`, or `cloudsqladmin` plus `postgres`;
missing/wrong owners, duplicates and any other database block absence/capability
qualification. The managed database and every observed field remain in the full
private catalog, encryption and source/restore parity hash. This exception does
not change namespace, object, role, writer-session, connection-context or
application-database absence checks.

The ordinary data identity observes native `postgres` catalog facts, requires
the application database and three application roles to be absent, rejects user
objects and other user databases, and compares the complete catalog hash with
the privately reviewed input. It checks API/worker absence and native client
sessions, takes or verifies the one approved recent source backup, creates only
the named owned clone, restores it, and compares the clone and freshly reread
source catalogs. Backup success alone cannot authorize initialization.

The signed recovery artifact binds source, run, attempt, plan hash, exact
initializer file bytes, native restoration and parity time. Only then can a
separate `data-initialization-production` job obtain the
`specimen-data-initialize` keyless identity. The job checks the live GitHub
environment for exactly one custom branch policy, `main`; an automatically
created default environment fails. It rechecks all existing source/PR/five-CI,
independent review, authority and cumulative-budget gates before credentials.
Its reviewed packet uses plane `data-initialization`, the same plan, and the
separately observed `specimen-data-initialize` WIF provider.

The initialization plan extends the ordinary plan with `catalog_recipient`,
`schema_mode` set to
`initialize_missing`, absent schema/connector revisions, no bootstrap, a PG18
restore recipe, and an `initialization` object containing:

- `files`: exact SHA256 values for the committed Python helper, Node helper,
  catalog SQL, role transaction, executable postconditions and encryption helper;
- `catalog_sha256`: the independently reviewed complete native source catalog;
- `authority_sha256` and `review_sha256`: the same private artifacts already
  bound into the admitted packet, explicitly reviewed for this privilege;
- `privilege_window_seconds`: an integer between 120 and 600, measured from
  actual native restoration parity, capped by packet and clone expiry;
- `identity`, `service_agent`, `permissions`, and
  `conditional_binding_sha256`: observed exact initializer provider/project,
  SQL Connect principal, fixed minimum permission set and reviewed conditional
  source/clone binding evidence. These are admission inputs, not instructions to
  create IAM bindings, identities, environments or privilege policy.
- `disposal_permissions` and `disposal_binding_sha256`: separately reviewed
  ordinary data-identity cleanup binding; exact Cloud SQL users get/list/update/
  delete additions scoped to the named targets. This does not add create-role,
  create-user, IAM-policy or instance-capacity authority, and the code creates no
  binding. Actual effective cleanup permissions remain a live admission gate.

The initializer may address only the fixed source and clone. Its transport
allows exact database creation and the newly created temporary principal's
lifecycle, plus bounded metadata/operation reads. It cannot alter IAM, source
instance capacity, passwords, backup settings, original data, Hosting or runtime
resources. Ordinary identities do not receive initializer capabilities.

On the clone, it creates the absent temporary IAM SQL principal with the one
reviewed managed role, observes native role attributes and actual `SET LOCAL
ROLE`/`CREATEROLE` capability, creates the exact absent application database once,
and runs the fixed transaction. Database owner is observed natively; the API
request does not invent an owner field. Unsupported managed behavior stops.
Every write records exclusive intent before submission and retains a native
response when available. Propagation waits repeat only reads. Unknown results,
preexisting users/databases/roles and existing intents block replay or adoption.
Every operation poll preserves original operation name, target, project, actor,
type and insertion time. Read timeouts use the remaining window; a response
arriving after the original deadline cannot qualify completion.

Before any backup or restore-clone creation, ordinary recovery must win the
[fixed-key held Storage claim](CLONE_ALLOWANCE.md) in the same invocation as
those effects. Its original signed intent is published before the claim; the
current native response alone unlocks one backup/create/restore sequence. Failed
or lost claims cannot be read, adopted, retried or refunded. This replaces only
the absent-clone history admission check. Existing-instance ownership and native
operation-history requirements above still apply.

Before any CREATE_USER, a separate step rereads both targets' absence and creates
two immutable intent documents bound to source/run/attempt, signed recovery and
the original privilege window. The workflow attests and publishes both documents
before the effect step. The effect step verifies those exact signed bytes and
keeps later operation outcomes in separate local records. Failed publication
prevents all creation; losing the later runner does not erase the published
ownership evidence. This is distinct from an always-run upload after effects.

Before commit, executable SQL assertions verify narrow roles, membership paths
and grant options, schema ownership, effective removal of temporary database
CREATE, exact owner-scoped default privileges, and absence of initializer
ownership or grant dependencies. PG18 may have multiple grantor rows; the checks
inspect every row instead of assuming uniqueness by role/member. System schema
tests use literal `pg_` prefixes. Standalone enum/domain types and other catalog
objects are included in absence checks. Writer defaults are SELECT/INSERT/UPDATE/
DELETE and sequence USAGE; no TRUNCATE grant is added.
Complete schema, database, default and relation ACL sets are compared in both
directions, including PUBLIC, grantors, grant options and global additive
defaults. Reader SELECT must be present; unknown grantees or column grants are
rejected. Each effective CRUD privilege is checked separately. Source database
encoding, collation, locale, ownership and privileges must match the clone's
native result before source COMMIT; only the naturally different database OID
is excluded from that comparison.
The complete application-role membership set is also compared in both
directions: every recipient, grantor and ADMIN/INHERIT/SET option must match.
Only the native PG18 bootstrap ADMIN-only edges, the permanent managed-role
self-grants and the two reviewed ordinary assignments are allowed. An unrelated
recipient or extra bootstrap grantor on an ordinary assignment is rejected.

The initializer closes its SQL connection, replaces database roles with an empty
set through `users.update` query parameters (`revokeExistingRoles=true`), verifies
native role removal and denied managed-role SET, and deletes only its positively
owned temporary principal. There is no `DROP OWNED` or `CASCADE`. Clone capability
and cleanup must both succeed before the identical fixed source operation starts.
A partial source initialization is retained, not deleted or automatically retried.
The absolute deadline is checked again after slow admission, immediately before
HTTP mutation, and before native work; the last minute is reserved for cleanup.
Revocation/deletion are the only disposal exceptions after authority expiry.
Failure to verify cleanup prevents a success artifact and requires reconciliation.
Every issued CREATE_USER intent gets a durable cleanup-state record, including
unacknowledged responses, rejected operation ownership, native verification
failure and expiry. Unknown ownership never authorizes adopting or deleting an
observed principal. Records distinguish observed empty API roles, verified native
removal and principal deletion. The cleanup path retains the original privilege
deadline; an expired native check cannot be relabeled complete. The workflow
preserves these blocked records for immediate protected reconciliation and never
uses them to replay CREATE_USER or proceed to source initialization.

A separate always-run `dispose-initializer` job uses the ordinary data identity
and the shared mutation lock. It verifies the original signed recovery and
prepublished intents, even when later outcome files were lost. A complete native
operations listing must identify exactly one initializer CREATE_USER with the
named target/project/actor and original window. A matching principal alone is
insufficient. Both cleanup paths reread complete user-operation history since
the signed absence immediately before revocation and deletion. Any other
CREATE_USER or DELETE_USER makes current ownership ambiguous, including changes
by the same actor or after the original window. UPDATE_USER requires the exact
retained fixed-request/native-response proof from this cleanup invocation; an
actor match alone is insufficient. Missing history, intervening replacement or
an unproven update stops disposal. Native operation metadata identifies an
instance, not a SQL username, so historical creation is never treated as a
stable user identity.
For a positively owned principal, only empty-role replacement and deletion are
available. An ordinary read-only SQL connection first proves no elevated role
attributes, memberships, dependencies or initializer sessions, then verifies
native principal absence after deletion. It never uses an expired initializer
login, extends its privilege window, retries CREATE_USER, or drops owned objects.
The disposal job has its own bounded observation period and explicitly records
late cleanup; it cannot make failed initialization release-ready. The compatible
apply and clone cleanup jobs wait for this disposal attempt. Missing artifacts,
revoked cleanup permissions or cancellation of the entire workflow remain exact
reconciliation gates; no claim of unconditional cleanup is made.

The ordinary data identity consumes the signed result, rereads native ownership,
privileges and source configuration, and continues compatible schema/connector/
index/rules apply using the same original recovery receipt and owned clone. It
does not take another backup or create another clone. Application table ownership
and effective permissions are checked after schema apply: inherited owner-role
membership alone does not make later DDL execute as that owner. A SQL Connect
migration-actor mismatch stops; no service-agent elevation is a fallback.
The established always-run owned-clone cleanup covers both phase paths.

Live admission remains incomplete until the coordinator verifies actual global
roles, native source catalog, identities, effective conditional permissions and
environment policy; reconciles the exact temporary privilege with the recorded
authority/review; reserves all costs within the existing shared USD5 ceiling;
and proves Cloud SQL PG18 creation, owner, SET/CREATEROLE, empty role replacement,
principal disposal and ordinary migration behavior on the single clone. Local
PostgreSQL tests prove SQL semantics, not these managed-service capabilities.
Existing sessions and external authorization propagation must be accounted for
in the independently reviewed privilege-expiry/cleanup mechanism. A process kill
or unacknowledged creation can leave an unknown liability; neither is a success
or permission to replay a write.

Primary API clarification: [users.update](https://docs.cloud.google.com/sql/docs/postgres/admin-api/rest/v1beta4/users/update)
uses PUT with role/revocation query parameters and ignores role changes in the
body. [PostgreSQL18 role membership](https://www.postgresql.org/docs/18/role-membership.html)
distinguishes membership, inherited privileges and SET capability. Native tests
and the clone qualification are separate evidence from these documentation claims.

IAM service accounts also retain the system authentication membership
`cloudsqliamserviceaccount`; an empty API `databaseRoles` value is not an empty
`pg_auth_members` graph. The signed ordinary-account catalog established a
narrow, non-login marker without parent roles and an exact `cloudsqladmin`
grant with ADMIN false and INHERIT/SET true. Qualification requires that same
shape for each named IAM principal. Capability permits only that marker plus
the one reviewed temporary `cloudsqlsuperuser` membership. Ordinary postconditions
permit only the marker and intended application role. Cleanup and disposal
require the marker alone, denied elevated SET, narrow actor flags, no sessions
or dependencies, and then removal of the owned principal. No role is revoked
merely to make a membership count zero.
[Google's role-update contract](https://docs.cloud.google.com/sql/docs/postgres/reference/mcp/postgres/mcp/tools_list/update_user)
documents preservation of IAM authentication system roles during role replacement.
These checks change no grant or API request. Actual future initializer creation,
API assigned-role readback, privilege removal and deletion must still qualify
on the owned clone; local PostgreSQL tests do not emulate that managed behavior.

Historical local validation for the initial candidate `07b9a4d` is recorded in
[`DATABASE_INITIALIZATION_LOCAL_VALIDATION.json`](DATABASE_INITIALIZATION_LOCAL_VALIDATION.json):
1,275 Python passed / 50 skipped; 129 Flutter passed / 7 skipped; all canonical
lint, security, analysis and web-build gates passed. The separate opt-in suite
passed 128 checks, including real isolated PostgreSQL18, actual Node guard and
connection-closure tests, and standard-primitive encryption interoperability.
These counts do not validate later repairs. Focused follow-up evidence is in
`DATABASE_INITIALIZATION_REVIEW_REPAIR.md`; the coordinator must run final
integrated canonical verification and qualify actual managed-service behavior.
