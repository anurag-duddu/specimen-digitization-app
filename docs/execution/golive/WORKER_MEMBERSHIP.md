# Worker membership bootstrap

Status: spec, 2026-09-23. Owner: the data workstream (S5). It is applied once,
with readback, by one path only: T3e, the protected data release's bootstrap
job. Never by hand, and never from an agent shell against production
(`AGENTS.md`; PLAN section 7.7).

The coordinator ruled on 2026-09-23 that the processing worker acts as its own
account, as `LIVE_PROCESSING.md` 62-63, `BACKEND.md` 170 and `OWNER_INPUTS.md` 288
already require: a separate, nonsensitive operator, "no administrator inferred or
hardcoded". Automation is marked by that uid; no new audit action is added.

## The worker's account

The API admits any enabled account with a verified museum email and App Check
(`runtime_auth.py` 45-55), so the worker's Firebase account must be one nobody
can sign in with: it is disabled, and it has no email, password, phone or
sign-in provider. "Disabled or provider-less" is not enough: production's
email-link sign-in allows sign-up and reaches any enabled account that ever
held an address (`MAGIC_LINK_SIGN_IN.md` 3-5, 43-44). The worker never signs
in: it acts through its service account (`production.py` 117-121). Its uid is
private: the owner holds it in the secret
`specimen-worker-actor-uid`, and the data release receives it only for the
bootstrap run.

Before T3e writes the membership, its bootstrap run looks the uid up read-only
with Identity Toolkit `accounts:lookup`, as `bootstrap_release.py` 396-405
already does for the administrator. It refuses unless the account exists, is
disabled (`disabled: true`), and has no email, password, phone or sign-in
provider (coordinator ruling, 2026-09-23, tightened after #96's security
review; #104). A wrong uid therefore cannot give a
person's enabled account the membership. The check runs exactly when the membership is written, uses a
lookup the bootstrap identity already makes, and catches any later change to
the account. The owner-side evidence is recorded in `OWNER_INPUTS.md` 288.

## Rows

One transaction, written with the existing member tables and no schema change:

- `OrganizationMember {organizationId, uid, active: true}`;
- for each allow-listed collection, `CollectionMember {organizationId,
  collectionId, uid, active: true, role: "operator", canViewSensitive: false}`.

The allow-list is committed: `WORKER_COLLECTION_KEYS = ("insects",)` in
`scripts/data/bootstrap_admin.py`. Membership does not inherit down the
collection tree (`COLLECTION_HIERARCHY.md`), so the list names every collection
the lane processes specimens in; for the pilot that is Insects alone. Any
further collection needs a coordinator ruling.

## Where the values come from

There is no organization or collection identifier input.
`worker_membership_request(artifact=..., approved_sha256=..., uid=...,
collection_keys=["insects"])` resolves both from the hash-approved hierarchy
artifact the administrator's bootstrap uses (`first-scope-hierarchy-bootstrap/v1`,
`FIRST_COLLECTION_BOOTSTRAP.md` "Hierarchy mode"):

1. It refuses any key outside the allow-list, such as `["insects", "other"]`,
   and an empty or repeated list.
2. It regenerates the artifact from its own values, as the release's
   `validate_prepared` does (`scripts/ci/bootstrap_release.py` 91-124): the
   reviewed tree is read at its fixed path in this checkout and must hash to the
   bound digest, and the regenerated artifact must equal the given one and the
   approved hash exactly. The approved hash is an owner-held value kept apart
   from the artifact. The release job never computes it from the artifact it
   approves: a self-consistent artifact with the Insects and Mammals ids swapped
   would otherwise pass. S2 builds T3e to this rule.
   - T3e runs from a commit whose collection tree matches the artifact's
     `tree_sha256`, so any edit to the tree waits until after T3e. It fails
     safe either way: a changed tree refuses the run.
3. It refuses the administrator's uid from that artifact.
4. It takes `organizationId` from the artifact's request and each collection
   identifier from the artifact's collection with that key.

So the document can make the worker an operator only in the allow-listed
collections of the one bootstrapped organization. No uid or UUID is committed
or logged.

## The document

`worker_membership_mutation(count)` renders it. Its variables are
`$organizationId`, `$uid` and one `$c{i}` per collection, because Data Connect
takes no list of table inputs. Its body, in order, is the organization member
insert, a redacted precondition that the uid has no collection membership in
the organization, and one aliased `m{i}` operator insert per collection, each
with its own `$c{i}`. The same count always yields the same bytes, so a reviewer
regenerates the document without the private values. `PrepareWorkerMembership`
is never published in the runtime connector.

## Guarantees

- All rows commit or none do.
- A replay stops on the organization member's primary key.
- A uid that is already a member of the organization, such as the
  administrator, is refused the same way, so the operation never adopts, demotes
  or elevates an existing member.
- A uid that already has any collection membership in the organization is
  refused by the redacted precondition, the check the administrator's document
  makes (`bootstrap_admin.py` 46-47). `CollectionMember` has no foreign key to
  `OrganizationMember`, so without it a leftover row, possibly `admin` or with
  sensitive access, would become live under the new organization row.
- An unknown collection is refused by the composite foreign key, and the whole
  transaction rolls back.
- The mutation writes only `role: "operator"` and `canViewSensitive: false`;
  neither is a variable.

## Application and readback

- It is applied once, with readback, by T3e alone, never by hand or from an
  agent shell against production.
- The release path regenerates the request with `worker_membership_request`,
  and so the query from `worker_membership_mutation(count)`, rather than
  trusting a supplied one, as `validate_prepared` does.
- The readback reads the uid's rows in the organization. It passes only with
  exactly one organization row, which is active, plus exactly one collection
  row per listed collection, each active, `role: "operator"` and
  `canViewSensitive: false`, and nothing else. It runs after the transaction,
  and it alone decides whether rows found by a later run count as applied.
- A replay and the administrator's uid get the same refusal from the
  transaction, so a refusal is never read as "already applied". A run on the
  administrator's uid fails the readback, because the rows it finds are an
  administrator's.
- Runtime activation's own check accepts `admin`, `manager`, `reviewer` or
  `operator` for the worker (`scripts/ci/deploy_runtime.py` 461), so it does not
  prove this membership; the readback does.

## What the membership allows

- New uploads default to Sensitive (`CONTRACTS.md` "Explicit intake
  sensitivity"), and this membership cannot see sensitive records, so the
  worker processes only uploads declared not sensitive. G2 and DoD-6 hold for
  those. The ten pilot slides qualify because the owner classified them not
  sensitive on 2026-09-23 (G31).
- `ListDueWork` on `main` requires `canViewSensitive` (`paging.gql` 60, called
  at `production.py` 309). With this membership the worker lists no due work
  until it uses #88's `ListDueWorkV2` with `includeSensitive: false` (S3's T2).
  Writing the rows does not need #88; the worker finding work does.
- As an operator, the worker cannot approve (`api.py` 325, 341).

## Tests

`scripts/data/worker-membership-test.mjs`, run by `scripts/data/test-postgres.sh`
against real PostgreSQL and the Data Connect emulator, first bootstraps a
synthetic hierarchy artifact prepared from the committed tree. Then: the
worker's rows land exactly, in that organization's Insects collection; a
replay, the administrator's uid on another collection, an organization member
without collection rows, a uid with a leftover collection row and an unknown
collection are refused, with nothing written; and the new worker passes
`CreateSpecimenV3` for a non-sensitive specimen and is refused for a sensitive
one. `tests/test_worker_membership.py`: the exact document for two collections,
the allow-list, resolution from the approved artifact and refusal of a changed
or unapproved one, the uid rules, and that the operation is not published in
the connector.
