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
response and readback are retained privately. A successful result must return all
four exact inserted keys and reread precisely the named scope and two expected
memberships, with the sensitive permission still false. The existing signed
`data-ready.json` gains `bootstrap_receipt` only for this new mode, binding the
artifact hash, complete scope/membership readback hash, source and original
run/attempt. It continues to report `data_ready: false` and
`release_accepted: false`; bootstrap is not whole-product acceptance.

Failed or unknown dispatch, partial response, incorrect readback, or interrupted
runner does not permit automatic retry, replacement IDs, existing-row adoption
or hidden cleanup. Keep the original intent, responses and costs. The local
intent prevents redispatch in that attempt; the stable organization's database
key prevents a second committed bootstrap across runners. A new runner is not a
durable record of the previous runner's uncommitted/unknown request: the
coordinator must reconcile original evidence before admitting any subsequent
attempt. No new packet or execution window is created by this implementation.

Qualification uses synthetic identities and IDs: focused Python artifact/dispatch
tests plus the exact mutation and `executeGraphqlRead` readback on a disposable
local PostgreSQL 18/SQL Connect emulator. The local transaction tests start without manual scope
seeds, verify all four rows, inject failures after each later insert, and race two
owners on one fixed pair. Local success does not prove production executeGraphql
permissions or native creation; protected execution and authenticated app access
remain release acceptance steps.
