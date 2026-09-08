# Live product rollout

Coordinator task: `01a07f48-a57c-71b0-9642-c9430886049c`.
Shared live plan: `/Users/anuragduddu/.codex/worktrees/80e6/specimen-digitization-app/docs/execution/LIVE_ROLLOUT_PLAN.md`.
Baseline: `a53f855e963b457c3ee2065f387609a193bb6f32` (PR 3, all six CI/CD jobs passed).
Coordinator branch: `codex/live-rollout-coordination`. Date: 2026-09-08.

## Objective and authorization

Deliver a functioning hosted specimen application: verified user signs in,
receives assigned collection access, uploads an approved image, observes actual
processing, reviews retained evidence, saves a correction and sees that record
survive runtime restart. A setup page, synthetic result, or deployment marker
alone does not meet this objective.

The user requested parallel tasks, isolated branches/worktrees, complete
documentation, PRs and continuous CI/CD. Work now on feature branches; submit
PRs when complete and keep their checks green. The user said we will merge later:
no task may merge to main or deploy independently. Coordinator stages integration
and presents the concrete release candidate before the later merge phase.

The user supplied one initial admin email (kept in private coordinator state) and
authorizes only the first 10 specimens already in cloud object storage. Freeze
the exact specimen/object generation/hash manifest before use; no expansion until
the user reviews and approves end-to-end results. Cloud infrastructure budget is
still unspecified. Implement and verify locally, inspect cloud metadata read-only,
and prepare exact resource/IAM/migration plans while the cost proposal is reviewed.
Do not create billable resources, enable paid inference, change production IAM,
deploy schemas/rules/runtime, or guess an administrator identity. This does not
block implementation or PR submission. Existing local review services on ports
3000/8000 and their private state must remain running and untouched.

Read AGENTS.md and docs/DEPLOYMENT.md completely before release-sensitive work.
The existing Hosting workflow stays Hosting-only; no workstation firebase/gcloud
deployment, no AWS, no weakening checks/WIF/environment/scanners. Define new data
and runtime delivery in a separately reviewed contract and PR. No secret values
in Git, logs, PRs, task messages or browser URLs.

## Workstreams and ownership

| Workstream | Effort | Owned scope | Required handoff |
|---|---|---|---|
| API runtime and auth | high | API entrypoint, API Dockerfile, api.py/cli.py and API-specific tests | Immutable runnable container; PORT binding; liveness/readiness/version; Firebase/App Check/CORS denial tests; exact runtime configuration |
| Data and platform | high | dataconnect, storage rules, scripts/data, infra/live data/IAM manifests; repository adapter sections in production.py/storage.py by explicit coordination | Live metadata inventory; reversible migration/backup/restore plan; first-user membership bootstrap; least-privilege identity manifest; real emulator evidence |
| Processing and inference | high | worker/workflow/reliability/model adapters and worker container; production.py provider adapter sections by explicit coordination | Bounded durable worker; hosting/engine decision backed by failure tests; pinned HF/SAM config and cost gates; no synthetic fallback |
| Flutter live connection | medium | apps/specimen_digitization only | Production sign-in/onboarding/access/error recovery; App Check configuration contract; real API integration; web/mobile gates |
| Delivery and integration | high | .github, scripts/ci, docs/DEPLOYMENT.md and LIVE_DELIVERY.md, release-only infra | Separate guarded runtime/data delivery contract; PR CI coverage; immutable provenance and rollback; integration branch and all-green combined PR |
| Independent live QA | high | docs/execution/LIVE_QA.md and qa-evidence/live-rollout; independent test harnesses under scripts/qa/live | Threat/acceptance matrix, independent deployed-stack tests, exact scope and blockers; final release verdict |

Use the configured Codex model for new tasks; select reasoning effort per scope.
Complex security, data-loss, orchestration and integration work uses high effort;
bounded client implementation starts at medium. Escalate based on concrete
unresolved complexity. Model availability/settings are not performance proof.

Coordinator owns this plan and LIVE_ROLLOUT_STATUS.md only. Each owner maintains
docs/execution/LIVE_<WORKSTREAM>.md in their own worktree. Shared-file changes need
an explicit owner handshake, especially production.py, storage.py, pyproject.toml
and uv.lock. Do not overwrite another worktree or edit main. Claim isolated ports
in status before starting fixtures. Coordinate shared Docker engine resources.

## Sequence and integration

1. Inventory and publish interfaces immediately: API/worker image targets,
   configuration keys, runtime version/readiness contract, data schema revisions,
   access bootstrap and release workflow inputs. Resolve conflicts centrally.
2. Build each workstream and meaningful local failure tests in parallel. Use
   official current docs for cloud/SDK decisions. Existing reports are history,
   not proof of live resource state. Record exact unknowns.
3. Each owner runs scripts/ci/verify.sh before pushing, opens a scoped PR to main,
   watches every required job and repairs failures. No self-merges. Report branch,
   full SHA, PR, CI run, touched paths, dependencies and remaining launch gates.
4. Delivery task integrates reviewed owner commits on codex/live-integration,
   preserving owner branches/PRs. Run canonical gates and independent QA against
   one frozen combined candidate. Update each PR's dependency/base notes to avoid
   ambiguous competing source trees. Keep all five platform checks intact.
5. With concrete budget/access/resource decisions, prepare a staged launch packet:
   reviewed data backup/restore and rollout; API and durable worker revisions;
   App Check and public client build values; auth/membership and provider policies.
   The later merge/deployment phase must follow the approved separate contracts.
6. Record deployed commit/image/connector revisions and actual authenticated
   browser workflow, denial tests, idempotency/restart recovery and observability.
   Publish final main CI/Hosting marker proof separately from runtime/data proof.

## Documentation and active management

Every workstream report must contain: objective, scope, baseline, branch/worktree,
current SHA, decisions and alternatives, configuration/ownership contracts,
commands and exact outcomes, artifact paths, known limitations, PR/CI URLs,
rollback/recovery steps, and next action with owner. Use Confirmed, Not confirmed,
Blocked, and Not run accurately. Never count skipped tests as passes or fixture
outputs as paid/live inference. Preserve evidence and failed experiments.

Send coordinator milestones promptly and maintain your report as work proceeds.
Coordinator tracks dependencies and concrete blockers, relays approved contracts,
reviews PRs, and resumes useful work when owners finish. A heartbeat checks for
meaningful progress without repetitive notifications. Pause it only after the
objective is achieved, the user stops it, or no actionable work remains without
required user input; state exact outstanding gates.

## Launch acceptance

- Exact authorized user can sign in through production Firebase/App Check and
  see only assigned collections. Unauthorized/revoked/cross-tenant requests fail.
- Actual cloud upload, immutable storage and SQL reconstruction pass; backups and
  restore are proven before valuable records enter the system.
- Approved worker/provider routes perform actual bounded inference with retained
  independent raw observations/provenance; unknown external outcomes are not replayed.
- Review/correction/history persist across API and worker restarts. Missing model,
  authority or institutional policy remains visibly blocked, never fabricated.
- Web is the first live acceptance target. Android/iOS compile continuously;
  signing, physical devices and store distribution remain separately evidenced.
- Spending controls, shutdown/rollback and operational documentation are concrete.
- All required PR/main checks, deployment jobs, public marker and authenticated
  product smoke agree on the released source/runtime/schema revisions.
