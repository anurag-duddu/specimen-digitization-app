# Approved release authority — 2026-09-08

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
