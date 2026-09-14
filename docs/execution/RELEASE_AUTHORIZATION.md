# Approved release authority — 2026-09-08

The September 14 approved amendment below supersedes only the original budget,
worker-duration and explicitly listed IAM setup limits. The original text remains
the authority for legacy artifacts and all unchanged release boundaries.

The user submitted both approvals in release decision packet v1 in task
`01a082b2-c2c3-70d2-be90-7bfb622c9102`. This records the actual submitted
decisions, superseding earlier statements that these two approvals were pending.
It is authority for the bounded actions below, not evidence that any resource,
credential, cost estimate, backup, deployment or acceptance test is ready.

## Protected backend and data releases

Amend `AGENTS.md` and `docs/DEPLOYMENT.md`. Hosting continues only through
`.github/workflows/ci-cd.yml`. Backend and data production deployments use only
`.github/workflows/runtime-release.yml` and
`.github/workflows/data-release.yml`, respectively, after a PR merges to `main`.
Each uses a separate main-only environment and keyless identity. Require all
five successful checks on the exact merged source, independent review,
immutable build provenance, verified data readiness and public end-to-end
verification. Preserve Hosting isolation and every existing protection.

Workstation deployments, manual dispatch, weaker branch protection, broader
Hosting permissions, service-account JSON keys and AWS resources remain forbidden.
Predeployment admission and postdeployment acceptance are distinct gates;
an incomplete example packet or a source-only test cannot satisfy live readiness.

## Bounded Google Cloud setup

Use only the existing `specimen-digitization` project; proposed region
`us-east4`. Current cloud resource existence must be discovered, not assumed.

| Component | Approved maximum |
|---|---|
| API | 1 CPU / 1 GiB; minimum 0, maximum 2 instances |
| Worker | One execution; 1 CPU / 1 GiB; 30 minutes; no platform retries |
| CPU SAM | 4 CPUs / 16 GiB; minimum 0, maximum 1 instance; absolute expiry within 1 hour including startup |
| SQL and Storage | Reuse existing services; no new persistent SQL instance or capacity upgrade |
| Restore rehearsal | One isolated clone, at most 2 hours; proposed `specimen-digitization-restore-20260908-r1`; smallest compatible target after checking backup/source requirements and complete cost |

Remove only the newly created rehearsal clone by its expiry after preserving
verification evidence. Never delete the source instance or original data. Preserve
originals, object generations and history. Apply only independently reviewed,
compatible schema, connector, index and private Storage-rule changes through the
protected data workflow. Bootstrap only the previously supplied administrator
after verifying identity and collection scope; keep sensitive-data access disabled.

Create only missing APIs, image registry, secret versions and separate build,
release and runtime identities needed by these services. Permissions must be
scoped to named resources, approved connector operations and the application
object prefix. Only the worker runtime reads the pinned inference secret and
invokes SAM. No broad project Owner/Editor grants and no changes to the Hosting
identity. Verify effective access, rather than treating a role name as proof.

Configure the verified API URL and App Check registration/site key for the
existing live app. Verify authentication and denials before real data processing.
Publish public build settings only after their targets are verified.

## Execution and budget boundary

The coordinator may resolve routine resource names and configuration within
these limits after live inventory and independent review. Record an exact action
packet before execution. The user's prior scope remains exactly ten specimens
and **USD 5 total incremental test spending across all sessions and retries**,
without resets. The USD 4 ordinary-reservation target and USD 1 contingency are
planning allocations within that ceiling, not extra budget.

Stop if the complete conservative reservation cannot fit the remaining budget
or a change falls outside these limits. Do not omit specimens or regions to make
cost or acceptance pass. Stop paid processing when the test completes or its
limit is reached. An evidence-only intermediate run is not full-pipeline release
acceptance.

Google authentication is a separate owner action. The decision submission does
not establish successful sign-in, a verified UID, a frozen manifest, a cloud
quote, native SAM timing or live production readiness. Those are facts to verify,
not approvals to request again. Retain the private authority artifact and its
digest with the private execution packet; no private identity or object path
belongs in this public record.

## Approved combined amendment — 2026-09-14

The user explicitly approved the combined decision at 2026-09-14T02:03:08.382Z
in integration task `01a07f48-a57c-71b0-9642-c9430886049c` after presentation of
the exact budget, worker and Firebase IAM proposal. Its direct user-record digest
and additive evidence contracts are in [APPROVED_RELEASE_BUDGET.md](APPROVED_RELEASE_BUDGET.md).

- USD 12 cumulative and daily, preserving every previous cost and reservation.
- One worker execution, 1 CPU/1 GiB, one task, zero platform retries, at most
  3500 seconds from original dispatch. Useful work stops by 3485; cleanup by 3500.
  The original SAM one-hour expiry remains unchanged. See
  [APPROVED_WORKER_TIMING.md](APPROVED_WORKER_TIMING.md).
- One fresh ten-minute bounded Firebase setup window for exactly three effects:
  create persistent role `specimenDataOwnerBootstrap` with only
  `firebaseauth.users.get`, `firebasedataconnect.services.executeGraphql` and
  `firebasedataconnect.services.executeGraphqlRead`; grant it at project scope
  to the existing DATA release identity for at most two hours; renew only 18
  timestamps in nine existing DATA/restore-claim bindings, preserving all other
  permissions, members and resource predicates. Initializer/disposal/ordinary
  access expires after 75/115/120 minutes respectively. The role definition
  persists after the conditional grant expires. Reviewed bootstrap code binds
  the approved owner and service; sensitive access stays disabled.

This includes finishing, independently reviewing and using the bounded helpers
for those effects with at most 187 metadata/IAM requests. Prepare all source,
review, cost and private inputs before the single setup clock starts. Never
replay a completed effect or consumed fence. Protected merged-main workflows
still perform database/runtime deployments. This amendment does not itself
establish credential access, free service quotas, managed database capability,
trace delivery, actual complete region counts or live product acceptance.
