# First organization, collection and owner

This is an additive source contract for the existing protected DATA bootstrap
lane. It does not establish current native row absence, select production IDs,
  grant institutional clearance, or issue operational approval. The release still
requires the exact merged source, independent packet/artifact review, cumulative
budget, separate keyless DATA identity and main-only environment in
[DEPLOYMENT.md](../DEPLOYMENT.md).

`data-bootstrap/v1` first verifies the signed compatible schema, original native
restore and completed owned-clone cleanup receipts, then rechecks deployed
schema/connector revisions and Storage rules. It can carry either of these
private `bootstrap.payload` artifacts with its approved `bootstrap.sha256`:

- `first-admin-bootstrap/v1`: unchanged legacy mode, requiring the exact existing
  organization and collection before inserting the first administrator's two
  memberships. Its original transaction and receipt semantics are retained.
- `first-scope-owner-bootstrap/v1`: explicitly selected empty-scope mode, prepared
  by `prepare_first_scope` or the private preparation CLI's `--first-scope` flag.
  Its request contains the already selected canonical organization/collection
  UUID pair, exact organization/collection names (nonempty, trimmed, no control
  characters, at most 256 UTF-8 bytes each), and the already approved owner's
  UID/email. No IDs or names are generated. Preparation is not application.

For first-scope mode only, the private plan's `bootstrap` object also requires
`evidence_recipient: {public_key_pem, public_key_sha256}`. The complete reviewed
plan binds this canonical RSA3072-or-stronger public key and its SHA256 before
credentials or native effects. The prepared bootstrap artifact remains unchanged;
legacy bootstrap still accepts only `payload` and `sha256`. No private key enters
CI, and existing first-scope plans without the recipient must be reviewed again
before use. This source change does not supply or approve an operational key.

Before choosing the operational mode, the coordinator reconciles current native
scope state and freezes the routine UUID pair and names in the private artifact.
The prepared owner must match an existing verified, enabled Firebase account.
Immediately before applying, DATA rereads that same account in the fixed project,
rejects a different UID/email, tenant, disabled account or unverified email, and
reads the target scope. The new mode requires no target organization, collections,
organization memberships or collection memberships, and no already-used collection
ID under another organization. Partial state is a stop, never permission to adopt,
rename, reactivate or elevate rows. Existing scopes use the legacy mode after
its independent exact-scope review.

The new maintenance mutation is one `@transaction` with exactly four inserts:
the organization, its root collection (`parentId: null`), the active organization
membership, and the active collection `admin` membership with
`canViewSensitive: false`. The first organization insert contends on its pinned
primary key, so competing owners for the same pair cannot both succeed. A later
failure rolls back the whole transaction. There is no upsert, generic SQL,
runtime connector operation, client creation API, IAM change or initializer grant.

The prepared query and complete artifact are regenerated and compared to the
reviewed hash before Auth lookup. An exclusive, fsynced
`first-scope-owner.intent.json` in the original protected attempt's private input
directory is consumed before its single mutation dispatch. The original returned
response and readback are retained privately, including rejected GraphQL results.
Each captured record also receives an exclusive, fsynced `.encrypted.json`
sibling using the existing RSA-OAEP/AES-GCM envelope and original repository,
source, run and attempt provenance. The intent is encrypted before mutation;
encryption failure leaves its local fence consumed and prevents dispatch.
A successful result must return all
four exact inserted keys and reread precisely the named scope and two expected
memberships, with the sensitive permission still false. The existing signed
`data-ready.json` gains `bootstrap_receipt` only for this new mode, binding the
artifact hash, complete scope/membership readback hash, source and original
run/attempt. It continues to report `data_ready: false` and
`release_accepted: false`; bootstrap is not whole-product acceptance.

The protected release job attests available encrypted bootstrap records and
preserves them in its existing `encrypted-initialization-catalog` artifact on an
`always()` path after authentication, including ordinary failed apply steps.
Raw intent/response/readback files never match an upload path. Before using an
envelope for reconciliation, the coordinator must verify the exact protected
workflow producer, source/run/attempt and attested ciphertext digest, then decrypt
with the originally reviewed recipient and compare its plaintext hash. Envelope
encryption and self-reported provenance alone do not authenticate the producer.

Failed or unknown dispatch, partial response, incorrect readback, or interrupted
runner does not permit automatic retry, replacement IDs, existing-row adoption
or hidden cleanup. Keep the original intent, responses and costs. The local
intent prevents redispatch in that attempt; the stable organization's database
key prevents a second committed bootstrap across runners. A new runner is not a
durable record of the previous runner's uncommitted/unknown request: the
coordinator must reconcile original evidence before admitting any subsequent
attempt. Abrupt runner loss before attestation/upload can still lose evidence;
missing or unauthenticated artifacts remain an unknown outcome and never license
retry or a replacement scope. No new packet or execution window is created by
this implementation.

Qualification uses synthetic identities and IDs: focused Python artifact/dispatch
tests plus the exact mutation and `executeGraphqlRead` readback on a disposable
local PostgreSQL 18/SQL Connect emulator. The local transaction tests start without manual scope
seeds, verify all four rows, inject failures after each later insert, and race two
owners on one fixed pair. Local success does not prove production executeGraphql
permissions or native creation; protected execution and authenticated app access
remain release acceptance steps.

## Hierarchy mode (owner decision of 2026-09-22)

Everything above remains the contract for the two modes it names. This section
adds a third, `first-scope-hierarchy-bootstrap/v1`, selected by the owner so the
first data release creates the museum's whole collection tree at once and nothing
has to be re-parented afterwards. It weakens no gate: every check the four-insert
mode applies to its one collection, this mode applies to every collection.

The reviewed tree is public and lives in the repository at
[`infra/reference/fieldmuseum-collection-tree.json`](../../infra/reference/fieldmuseum-collection-tree.json),
recorded from [`COLLECTION_HIERARCHY.md`](../product-requirements/COLLECTION_HIERARCHY.md).
It carries only a stable key, a display name and a parent key per entry, parents
before children, and no identifier at all. The canonical UUIDs are the owner's
and stay private: `scripts/data/prepare_hierarchy_request.py` mints one per entry
offline into a mode0600 request skeleton outside Git, and
`scripts/data/bootstrap_admin.py --hierarchy` turns that skeleton plus the
separately exported Admin user record into the prepared artifact. Neither makes a
cloud call. The preparer refuses, without echoing a private value, unless the
private list repeats the reviewed (key, name, parent) triples in the reviewed
order, every parent appears earlier, keys and identifiers are unique, identifiers
are canonical UUIDs, no parent holds two collections with the same name, there
are 1 to 64 entries, every name is the same bounded text the existing mode
requires, `admin_collection_key` names one of the keys, and sensitive access is
exactly false. Identity is validated by the same `prepare_bootstrap` path.

The maintenance mutation is one `@transaction` rendered deterministically from
the reviewed tree's shape, so a reviewer regenerates it without the private
values. It declares `$organizationId`, `$organizationName`, `$uid`,
`$canViewSensitive`, `$collectionId` and a `$c{i}Id`/`$c{i}Name` pair per entry,
and its body is, in order: the organization insert, the redacted precondition
that none of the N identifiers already exists, one aliased `c{i}` collection
insert per entry in tree order with `parentId` null or its parent's variable,
and then the same two membership inserts as the four-insert mode. The
administrator's collection keeps the existing `$collectionId` variable, so every
existing reader of the membership rows is unchanged. The organization insert
still contends on its pinned primary key, and a later failure still rolls the
whole tree back. There is no upsert, no re-parenting and no generic SQL.

The artifact is the four-insert artifact plus one `hierarchy` object: the fixed
`tree_path`, the SHA256 of the reviewed file's exact bytes, the private ordered
collections, and `admin_collection_key`. `artifact_sha256` covers all of it. The
release regenerates the artifact before the Auth lookup exactly as before, and
additionally reads the reviewed tree from its own source checkout at the fixed
path, never at a path the artifact supplies, and requires the committed bytes to
hash to the bound digest. Editing the tree without re-minting the identifiers and
re-preparing therefore fails in CI and then fails the release.

Application mirrors the four-insert path. The before-state must be entirely
empty: no organization, no collection under it, no collection carrying any
reviewed identifier, and no memberships. An exclusive, fsynced
`first-scope-hierarchy.intent.json` is consumed before the single dispatch, and
the response, readback and receipt are retained beside it under the same names
with the same `.encrypted.json` siblings and the same envelope provenance. The
workflow's attestation glob is now `first-scope-*.encrypted.json` so it covers
both modes; the upload path was already `*.encrypted.json`, and raw records still
match no upload path. A successful result must return every pinned inserted key:
the organization, each `c{i}` alias with its organization and its own identifier,
and both memberships. The readback query reads N+1 collections, so an extra row
is visible rather than truncated, and must show exactly N collections in both the
organization-scoped and identifier-scoped lists, each matching one reviewed entry
by identifier with its exact organization, name and parent (null or the parent's
UUID, compared as UUIDs because SQL Connect returns them without hyphens), plus
exactly one organization member and one collection member on the administrator's
collection, active, `admin`, and not sensitive.

The receipt is `first-scope-hierarchy-applied/v1` with the same provenance and
membership hash, `scope_verified`, `membership_verified`, `collections_verified`
set to N, the bound `tree_sha256`, `sensitive_access: false` and
`release_accepted: false`. It reaches `data-ready.json` as `bootstrap_receipt`
exactly as the four-insert receipt does, and the private plan still requires the
reviewed `evidence_recipient`. Bootstrap is still not whole-product acceptance.

Qualification adds hierarchy cases alongside the existing ones and changes none
of them: Python tests for the exact artifact, the refusals above, the release's
empty-state, inserted-key, readback and tree-digest gates, the durable intent and
the encrypted evidence; and, on the same disposable local PostgreSQL 18/SQL
Connect emulator, a synthetic three-node tree that is prepared, applied, read
back with its parents through the protected readback query, and then refused on
replay, on a second owner, on a reused identifier and on an unknown parent.
