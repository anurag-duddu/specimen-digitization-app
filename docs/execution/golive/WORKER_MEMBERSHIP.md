# Worker membership bootstrap

Status: spec, 2026-09-23. Owner: the data workstream (S5). Applied by the release
workstream (S2) in its one-time bootstrap step.

The coordinator ruled on 2026-09-23 that the processing worker acts as its own
account, as `LIVE_PROCESSING.md` 62-63, `BACKEND.md` 170 and `OWNER_INPUTS.md` 288
already require: a separate, nonsensitive operator, "no administrator inferred or
hardcoded". Automation is marked by that uid; no new audit action is added.

## Rows

One transaction, written with the existing member tables and no schema change:

- `OrganizationMember {organizationId, uid, active: true}`;
- for each processing collection, `CollectionMember {organizationId,
  collectionId, uid, active: true, role: "operator", canViewSensitive: false}`.

Membership does not inherit down the collection tree
(`COLLECTION_HIERARCHY.md`), so the list names every collection the lane
processes specimens in. For the pilot that is `insects`.

## Guarantees

- All rows commit or none do.
- A replay stops on the organization member's primary key.
- A uid that is already a member of the organization, such as an administrator,
  is refused the same way, so the operation never adopts, demotes or elevates
  an existing member.
- An unknown collection is refused by the composite foreign key, and the whole
  transaction rolls back.
- The mutation writes only `role: "operator"` and `canViewSensitive: false`;
  neither is a variable.

## Inputs and where the document lives

`scripts/data/bootstrap_admin.py` renders the document with
`worker_membership_mutation(count)` and builds the request with
`worker_membership_request(organization_id=..., uid=..., collection_ids=[...])`.
Variables are `$organizationId`, `$uid` and one `$c{i}` per collection, because
Data Connect takes no list of table inputs. The same count always yields the same
bytes, so a reviewer regenerates the document without the private values. The
release job supplies the uid from its one-run secret and resolves each committed
collection key to its UUID from the private bootstrap artifact, so no uid or
UUID is committed or logged. `PrepareWorkerMembership` is never published in the
runtime connector.

## Tests

`scripts/data/worker-membership-test.mjs`, run by `scripts/data/test-postgres.sh`
against real PostgreSQL and the Data Connect emulator: the rows land exactly; a
replay, an existing member's uid and an unknown collection are refused, with
nothing written; and the new worker passes `CreateSpecimenV3` for a
non-sensitive specimen and is refused for a sensitive one.
`tests/test_worker_membership.py`: the document's shape and determinism, input
validation, and that the operation is not published in the connector.
