# Live delivery and integration

Status: proposed contract for separate review; no runtime/data deployment is
implemented or authorized. Updated 2026-09-08. Owner: delivery task.

## Scope and baseline

Worktree: `/Users/anuragduddu/.codex/worktrees/f88c/specimen-digitization-app`.
Branch: `codex/live-delivery`. Baseline SHA:
`a53f855e963b457c3ee2065f387609a193bb6f32`.
Own `.github/`, `scripts/ci/`, `docs/DEPLOYMENT.md`, this report and release-only
infrastructure. Integration is a later isolated `codex/live-integration` branch;
owner PRs remain intact and no merge to main is authorized.

Objective: independently review the data/runtime release boundary, preserve all
five CI checks and Hosting isolation, then assemble one tested candidate with
source, image, data revision and real application evidence.

## Bootstrap blockers: first handoff

1. **Blocked:** current AGENTS.md permits production only through `ci-cd.yml`;
   DEPLOYMENT.md and `test_no_other_automation_can_issue_a_deploy` permit only
   the guarded Hosting command. Separate runtime/data executable workflows
   therefore require an explicitly reviewed contract amendment before code.
   This proposal does not silently create that exception.
2. **Blocked:** no approved budget supplied. Initial administrator identity was supplied privately.
   Provisioning, IAM/environment changes, API enablement, paid calls and
   membership bootstrap require coordinator authorization of concrete actions.
3. **Blocked:** data owner must freeze exactly the first ten existing cloud
   specimens with object generation and cryptographic integrity evidence.
   Source download is authorized only after metadata/generation freeze. No paid inference, eleventh specimen or inferred replacement.
4. **Not confirmed:** new runtime/data environments, WIF providers, registry,
   runnable image/config contracts, backup/restore and worker hosting choice.
5. **Blocked for CLI metadata:** Google credentials require interactive
   reauthentication; no account/config change was performed. GitHub metadata
   inspection works. Prior RUNTIME_PROPOSAL cloud observations remain historical.

## Candidate release contract v1 (awaiting review)

Existing `ci-cd.yml`, `production` environment, Hosting identity/provider,
`deploy_hosting.sh`, artifact/marker checks and all original deployment tests
remain authoritative and unchanged. No deploy commands are added in this phase.

After separate contract approval, propose **independent main-push workflows**
`data-release.yml` and `runtime-release.yml`, with `data-production` and
`runtime-production` main-only environments. This requires an explicit narrow
AGENTS.md/runbook amendment. Manual dispatch, PRs, tags, workflow_run and
workstation commands cannot release. Each deploy job must verify all five
successful checks on the exact merged main SHA, check PR merge provenance and
reject a superseded candidate before obtaining credentials. A check result from
another commit is insufficient. Use immutable checkout/action references;
repository default token remains read-only. PR image compilation may be added
without cloud credentials and without changing the five existing check names.

### Separate identities and authorization

| Plane | Candidate identity | Allowed boundary | Prohibited |
|---|---|---|---|
| Hosting | Existing github-firebase-hosting | Existing tested static artifact only | Runtime, data, secrets, IAM |
| Runtime build | New identity, exact name pending review | Push immutable images to named Artifact Registry repository | Runtime update, secret values, data, IAM |
| Runtime release | specimen-runtime-release | Read approved digests; update named existing API/worker resources; actAs only approved runtime identities | Registry overwrite/delete, secret values, schema, Hosting, IAM |
| Data release | specimen-data-release | Exact named connector/schema/rules operations justified by reviewed diff | Runtime release, provider secrets, Hosting, IAM |
| Bootstrap operator | Separately authorized administrative session | Only itemized APIs/resources/IAM/environment/configuration changes | Implicit recurring deployment authority |

Candidate WIF conditions must bind numeric repository ID `1360732425`, owner
ID `140138196`, `push`, `refs/heads/main`, exact environment and exact workflow
ref. Runtime and data get separate providers and service-account bindings;
never broaden Hosting's provider. Bind environment through verified OIDC claims
including exact `sub` as appropriate; validate actual token claims without
logging the token. No JSON keys. Grant only reviewed resource-scoped permissions;
role names alone do not prove effective least privilege. Wrong repo, fork, PR,
manual event, branch, environment and workflow must each fail authentication.

[Google WIF guidance](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines)
supports claim-based restrictions. Exact provider policy and effective allow/deny
behavior remain to be tested after administrative authorization.

### Immutable release packet

A release packet is review evidence, never an authorization token. Retain:

- exact source SHA, merged PR, successful five-check run/job URLs and build run;
- API and worker image references ending `@sha256:<64 lowercase hex>`, source
  labels, pinned base-image/dependency versions, build provenance and verified
  attestation binding each image digest to the same source/build identity;
- data schema/connector/Storage-rules content hashes and deployed revision IDs,
  compatibility range, reviewed migration diff, preflight/backup/restore evidence;
- hash and immutable location of the data owner's exact ten-specimen manifest;
  keep private object names and user identities out of public CI artifacts;
- approved public API URL/App Check key configuration digest, runtime config
  digest with secret references/version numbers only, approved runtime identity;
- explicit bounded resources, budget/data/provider authorization references,
  rollout/rollback revision map and independent acceptance evidence locations.

Tags such as latest, branch or SHA tags are not deployment inputs. Build once for
merged source; promote and inspect the exact digest. A digest without trusted
provenance is insufficient. PR images never become production images merely by
retagging. API `/version`, Cloud Run revision imageDigest, image source label and
release packet must agree; marker success alone does not prove runtime delivery.

### Ordering and rollback

1. Freeze approvals and ten-object manifest; inspect resources/IAM read-only.
2. Authorized bootstrap creates only reviewed missing resources/identities and
   records metadata. Data owner proves backup and isolated restore before writes.
3. Data workflow applies reviewed additive compatible schema/connector/rules
   revisions. Reject destructive migration or unsupported rollback; preserve raw
   evidence and require current-runtime compatibility tests. Data owner observed
   SQL Connect emulator 3.2.0 removes all four supplemental paging/search indexes
   on restart even under COMPATIBLE. Quiesce API/worker writers if uniqueness
   protection can be absent; apply the exact reviewed paging-indexes.sql and
   search-indexes.sql after schema/connector changes, then verify four valid
   indexes, indexed constraints, catalog, row/query/invariant reconstruction
   before resuming writers. Backup row counts or schema hashes alone do not meet
   this gate; production behavior and repair proof remain pending.
4. Runtime workflow validates exact data attestation for its source/candidate,
   builds/verifies images, creates a no-traffic API revision and paused worker,
   checks readiness, auth denial, immutable-object and SQL reconstruction gates.
   No paid processing is enabled by image deployment.
5. Promote API traffic only after independent checks; enable bounded worker only
   with explicit provider/spend approval for the frozen ten. Persist/reconstruct
   review records and prove ambiguous external effects are not replayed.
6. Publish actual public API/App Check values through reviewed configuration,
   release Flutter through existing Hosting CI and verify marker plus end-to-end
   authenticated product flow. Do not fabricate a runtime URL before creation.

Cross-workflow ordering must use verified, immutable data attestation and one
release promotion lock; timing or workflow completion alone is insufficient.
No workflow may cancel a production transition in progress. Runtime rollback
uses the recorded previous digest/config and compatible data revision through a
reviewed main PR; quiesce workers first and preserve ambiguous effects. Never
reverse evidence by deleting rows/objects. An incompatible data change blocks
application rollback until a reviewed recovery plan is proved. Emergency action
requires separately explicit authorization, not a new manual workflow trigger.

[Cloud Run image behavior](https://docs.cloud.google.com/run/docs/deploying) and
[traffic rollback guidance](https://docs.cloud.google.com/run/docs/rollouts-rollbacks-traffic-migration)
support immutable revisions and testing a revision before traffic promotion.
Worker hosting is not selected by these API service capabilities.

### Owner interfaces requested

| Owner | Required before executable workflow review |
|---|---|
| API | Dockerfile path/build context/entrypoint, PORT, liveness/readiness/version response, exact config and secret exclusions |
| Worker | Dockerfile/entrypoint and hosting mode, durable stop/drain/restart contract, paid-call gates and pinned provider policy |
| Data | Exact ten-object manifest contract/hash, schema/connector/rules hashes, bootstrap membership and backup/restore evidence |
| Client | Public build variable names, production absence behavior, Firebase/App Check/CORS integration contract |
| QA | Independent no-secret acceptance harness, denial/restart/effect tests and release verdict |

## Verification and metadata inventory

Confirmed 2026-09-08 via read-only GitHub API:

- main strict protection has Repository checks, Python tests and Flutter checks
  and web build; admins enforced, stale reviews dismissed, no force/delete.
- production is the only environment returned and has custom branch policy.
  Allowed deployment branch is exactly main (confirmed by branch-policy API).
- zero open PRs at initial inventory. Both mobile checks remain mandatory release
  criteria even though only the three historical checks are in branch protection.

Commands: `gh api .../branches/main/protection`, `gh api .../environments`,
`gh pr list --json ...`: success. Cloud enabled-services, WIF provider and IAM
metadata queries: failed token refresh with noninteractive reauthentication
error. No cloud state inferred from those failures. No private images read.

Local canonical verification: initial run passed 419 Python tests (26 skipped), Flutter analysis, 76 Flutter tests (7 skipped) and release web build. Final gate: 423 Python passed (26 skipped), Flutter analysis clean, 76 Flutter passed (7 skipped), release web build passed. Original deploy-only policy tests:
unchanged. PR/CI URLs: pending scoped PR creation after successful local gate. No deployed change.

## Next action

Coordinator reviews contract v1 and resolves owner interfaces/administrative
prerequisites. Delivery adds non-deploying candidate validation and CI checks,
runs canonical verification, submits scoped PR and observes all five checks.
After owner handoffs, reconcile reviewed commits in isolated integration worktree,
run canonical verification and all five CI entries, submit combined PR with
explicit dependency mapping, and leave every PR unmerged.

## Candidate policy amendment for the executable release PR

Coordinator reviewed contract v1 as the implementation design basis. This is
not approval to merge or execute cloud changes. Proposed exact replacement for
AGENTS.md's production-workflow bullet when executable paths are reviewed:

> Hosting production deployments MUST use `.github/workflows/ci-cd.yml` after
> a pull request is merged to main. Runtime and data production changes MUST
> use only `.github/workflows/runtime-release.yml` and
> `.github/workflows/data-release.yml`, respectively, after a pull request is
> merged to main and the separately reviewed LIVE_DELIVERY contract is met.
> These workflows must enforce distinct main-only environments/WIF identities,
> all five checks on the exact source, an exact authorized source SHA and a
> complete independently verified release packet. They may never inherit or
> broaden the Hosting identity. Workstation and manual-dispatch releases remain
> forbidden. Missing resources, authorization or evidence fail closed.

Do not interpret this quoted proposal as an active rule. Current AGENTS.md and
original deployment tests still prohibit all additional deploy commands. Concrete
runtime/data scripts and exceptions must arrive together with negative tests;
this first scoped PR introduces offline guard primitives and credential-free
builds while owner migration/runtime inputs are still being implemented.

## Implemented candidate checks

- `runtime-ci.yml`: read-only token, pinned checkout, no environment/OIDC/registry
  access; API/worker Docker build with exact SOURCE_SHA and network-disabled
  CLI smoke. An absent owner Dockerfile is explicitly **Not run** on scoped
  branches. Both images must actually build in the integrated candidate.
- `validate_release_packet.py`: strict public structure, exact ten count,
  immutable role/project image references, matching source/check SHA, all five
  check names, data/provenance/approval/rollback evidence fingerprints. The
  example intentionally fails `--require-ready`. Hash presence is not trusted
  evidence verification and the output explicitly grants no authorization.
- `release_context.py`: separate candidate runtime/data workflow, environment,
  numeric repository/owner, main push/protection, source/authorized-source,
  project and service-account checks. Offline predicates cannot replace WIF.
- `build_web.sh` and `validate_public_settings.py`: main-push-only approved
  public API URL/App Check variables. Both absent retain the current setup
  screen; partial/unsafe URL/development config fails. PR/native builds remain
  credential-free. No repository variable was created or changed.

Initial targeted tests: 68 passed (packet/public/context plus original Hosting
policy). First canonical run stopped on a synthetic negative-test URL flagged
by the secret scanner; fixture changed to credential-free username-only URL,
retaining the rejection test with scanners unchanged. Canonical rerun passed; final added checks are being reverified.

Independent staged review: 68 targeted tests passed; no new deploy path, OIDC
permission or Hosting regression. Two acceptance gaps identified and addressed:
main/integration now fail for absent Dockerfiles, while scoped branches explicitly
report Not run; API image validation now reads embedded `_build.json` independently
of OCI labels. Worker embedded provenance and real HTTP `/version` remain owner
handoff/integration gates. Build context is now a whitelist Git archive at the
exact source SHA, excluding ignored credentials, specimens and uncommitted files.

## Minimal resource and cost proposal (not spend authorization)

Propose one existing-project API service (1 vCPU/1 GiB, minimum 0, maximum 2,
concurrency 8, 60-second request timeout), one worker Job execution (1 vCPU/1
GiB, one task, parallelism 1, retries 0, 1,800-second platform timeout and
1,500-second application deadline), and CPU SAM only if owner tests validate
4 vCPU/8 GiB, minimum 0/maximum 1 and ten-image completion. GPU remains excluded
from this initial proposal. Budget and live region/resource approval are pending.

Illustrative compute arithmetic using the pricing page's displayed default USD
rates before free tiers: 1,800 seconds of worker CPU/RAM at 0.000018/vCPU-second
and 0.000002/GiB-second = $0.036. Assuming API 600 active seconds and SAM ten bounded 120-second requests, API at
0.000024/vCPU-second + 0.0000025/GiB-second = $0.0159; CPU SAM at the same
request-billed rates for 1,200 seconds = $0.1392. This ~$0.191 subtotal is **not** a pilot quote or
spend ceiling: actual us-east4 SKUs, model startup time, provider tokens, existing
SQL, backup/restore, registry/build/storage, networking, logging and App Check
must be priced separately. No free-tier availability assumed. See [Cloud Run
pricing](https://cloud.google.com/run/pricing), checked 2026-09-08. Runtime
instance limits do not cap overall account or provider spend.

Data index clarification: inspected paging/search SQL contains four non-unique
indexes. Their disappearance proves a performance/query-contract gap, not
uniqueness or data loss. Migration writer ordering must follow data owner's
actual schema-change analysis; no uniqueness-loss claim is made for these four.

Confirmed coordinator naming decision for candidate contracts: services are
`specimen-api` and `specimen-worker`; attached identities are exactly
`specimen-api-runtime@specimen-digitization.iam.gserviceaccount.com` and
`specimen-worker-runtime@specimen-digitization.iam.gserviceaccount.com`.
Release identities remain separate. These names supersede historical runtime
identity proposals, do not imply resource existence and authorize no bindings.
Data owns concrete IAM manifests; no compatibility aliases grant both identities.

Final canonical command `scripts/ci/verify.sh`: passed. Evidence logs:
`/tmp/specimen-live-delivery-verify-final.log` (423 Python passed, 26 skipped;
76 Flutter passed, 7 skipped; analysis and web build passed), and
`/tmp/specimen-live-delivery-final-hooks.log` (all final workflow/security/shell
hooks passed). No skip counted as a pass. Mobile compilation awaits GitHub CI.
No local demo ports or shared Docker resources were modified by this task.

## Scoped PR checkpoint

Implementation SHA: `60d80a6d56f53dfd0992e84393762679feea5611`.
PR: <https://github.com/anurag-duddu/specimen-digitization-app/pull/6>.
Initial CI/CD: <https://github.com/anurag-duddu/specimen-digitization-app/actions/runs/34259749692>
(in progress at checkpoint). Initial candidate CI:
<https://github.com/anurag-duddu/specimen-digitization-app/actions/runs/34259749728>
completed; packet example structurally valid but incomplete, owner image builds
and data-plan validation explicitly **Not run** because inputs are absent on
this scoped branch. Green wrapper jobs do not prove image builds. The PR API is
the authority for the latest documentation checkpoint SHA and checks.

Dependencies currently PR4 coordinator, PR5 client; API/data/processing/QA PRs
pending. Keep all PRs unmerged. Delivery watches exact latest heads, not superseded
runs. Integration worktree creation waits for reviewed owner handoffs.

Confirmed owner contracts received after implementation freeze:

- API requires textual `SPECIMEN_FIREBASE_PROJECT=specimen-digitization` for
  Firebase Auth and numeric `SPECIMEN_FIREBASE_PROJECT_NUMBER=716045864126` for
  the separate App Check verification context. Every allowed Firebase app ID
  must match the numeric project. Reverify cloud metadata before launch. Owner
  local RSA/JWKS fixtures prove SDK audience handling, not live Google tokens.
- Data reports a local rehearsal with two connector restart cycles, exact four
  non-unique index reconstruction, writer quiescence, the schema-managed
  `specimen_scope_checksum` uniqueness constraint valid throughout, and required
  `ANALYZE` after restore before query-plan acceptance. Never force planner flags
  to simulate an indexed plan. Exact private artifact path remains with data/QA;
  independent artifact review and actual cloud restore are separate gates.
- Data public plan is `infra/live/data-resources.json`; offline validator is
  `uv run python scripts/data/validate_live_plan.py`. Candidate CI runs it when
  integrated and rejects its absence on main/integration. Plan's explicit
  proposal/unknown states cannot be promoted to observed resource facts.
