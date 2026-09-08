# Live coordination status

Baseline: 82fd60e. Initial workstreams dispatched 2026-09-07 evening America/Chicago.

| Workstream | Task | Worktree / branch | State |
|---|---|---|---|
| Coordinator | 01a07f44-7d89-7052-b968-5e96753493ad | /Users/anuragduddu/code-projects/fieldmuseum/specimen-digitization-coordination / codex/product-coordination | Plan written; coordination only |
| Architecture | 01a07f47-c8a6-7983-9d45-adfccf0971a9 | /Users/anuragduddu/.codex/worktrees/969e/specimen-digitization-app / codex/architecture-contracts | Full audit and early shared contracts underway |
| Backend | 01a07f47-f5cc-7c10-bc1f-571b086e9cd2 | /Users/anuragduddu/.codex/worktrees/3782/specimen-digitization-app / codex/insects-backend | Domain/gate tests; coordinating API |
| Flutter | 01a07f48-2c8e-72b1-99bc-d81f2729c429 | /Users/anuragduddu/.codex/worktrees/6b01/specimen-digitization-app / codex/flutter-product | UI/repository boundaries; coordinating API |
| Data | 01a07f48-6017-7af2-930d-ac2edda9ad9e | /Users/anuragduddu/.codex/worktrees/39c2/specimen-digitization-app / codex/data-platform-foundation | Existing cloud metadata verified; schemas/contracts underway |
| CI/CD integration | 01a07f48-a57c-71b0-9642-c9430886049c | /Users/anuragduddu/.codex/worktrees/80e6/specimen-digitization-app / codex/product-integration | Live protections and public baseline verified; canonical tests underway |
| Independent QA | 01a07f4a-f674-7243-a6c8-f91cd82c1d27 | /Users/anuragduddu/.codex/worktrees/14dd/specimen-digitization-app / codex/independent-acceptance-review | Acceptance procedure underway; integrated candidate required for final review |

## Decisions and communications

- User confirms configured access and authorizes use of local CLIs, computer and browser. Tasks should inspect existing resources before claiming missing access.
- Spending cap, provisioning and production merge question remains pending; proceed with implementation, read-only existing resource inspection and local/emulator verification.
- Architecture/backend/Flutter task IDs and preliminary API requirements distributed directly among owners.
- Architect published v0.1 contract at /Users/anuragduddu/.codex/worktrees/969e/specimen-digitization-app/docs/execution/CONTRACTS.md; distributed to all implementation owners. Backend remains executable schema owner; deviations must be reconciled before integration.
- Production database remains SQL Connect. Any SQLite adapter is explicitly local/synthetic, not a production substitution.
- Critical environment finding: default gcloud project is fm-specimen-pipeline, not this project. Every cloud request must explicitly target specimen-digitization; relayed to data/backend/release.
- Data owner verified existing PostgreSQL 18 instance/service in us-east4, no listed SQL Connect connectors, Storage bucket in US-EAST1, and Hugging Face Secret Manager metadata. No secret values inspected.
- Release owner found JDK17 through Android toolchain; connected data owner for emulator setup.
- Heartbeat coordinate-specimen-product-build created every 15 minutes for continued coordination; quiet unless meaningful change/action. Pause when completed or only user-dependent work remains.

## Evidence

- Initial working tree clean; origin fetched; no open PRs.
- Latest baseline main workflow 34185255766 was completed/success. Public marker independently pending release task.
- Release task subsequently verified all four jobs green, public marker/title smoke matching full SHA 82fd60eff90684d2c630a37c59e1250604ad1cae, strict branch checks/admin protections/main-only environment/exact WIF/least-privilege Hosting identity. Baseline 33 Python tests and 1 widget test pass; web build in progress at report.
- No new product completion, production deployment, real inference, or cross-platform verification claimed yet.
