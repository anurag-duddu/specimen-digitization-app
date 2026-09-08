# Live candidate integration

Status: local implementation candidate; no runtime release or spend authorization.
Delivery owns `codex/live-integration` in worktree `live-integration-20260908`.
All owner histories are retained with conflict-free merge commits. Owner branches
remain independent. Final combined source/check/build evidence is recorded in the
combined PR body to avoid changing the commit being verified.

## Reviewed source mapping

| Owner | Frozen owner source | Review state |
|---|---|---|
| Coordination PR4 | 5d44ca61cf1bf11decb61b2476c64b4f7a2287fa | All five CI checks passed, run34261808343 |
| Delivery PR6 | 5a17bc163a3cbc936afb6c22cf96327c61bec6da | Independent QA86 tests and12 architecture/provenance cases passed; all five CI34262763154 passed |
| Client repair PR11 | 3bc8c4d7f237424443bbcd67c611398470ec5a98 | All five CI34262652657 passed; independent QA47 passed; both access findings closed |
| API PR10 | 1c04fe7d8bc0007efb0778f44fe88aecac46c2d7 | All five CI checks passed, run34262161948; independent QA41 passed; list-action finding closed |
| Data PR8 | 3d60a1b87027c7321d409be8617a73401cc82b3b | All five CI checks passed, run34260978476; independently reproduced SQL rehearsal |
| Processing PR9 | c8b10eba77877ecf425ac74552157eaa3e49f647 | Corrective provenance/lock source frozen; independent review and CI pending |
| QA PR7 | e9f75d4e035007e552baf439b823b8664cbc9e15 | All five CI checks passed, run34260268109 |

Committed coordination documents are handoff snapshots. The active authority is
coordinator-owned in worktree80e6. No private identity, approval configuration,
source inventory or specimen data is included in this branch.

## Verified local evidence

At initial assembly7c745a79c149f99703742b48472c27fec60f5dec,209 bounded
API/worker/SAM/pilot/delivery-policy tests and the data proposal validator passed.
This is preliminary evidence, superseded by final combined verification.

The real local PostgreSQL/DataConnect harness passed on isolated ports5579/9529.
The first attempt stopped for missing fresh-worktree .venv; `uv sync --frozen`
resolved the prerequisite. The second run restored27 tables/26,315 synthetic rows,
including22,139 specimen rows. Restore equality, connector-restart equality,
writer quiescence and refreshed planner statistics were all verified. It exercised
two connector restart rounds and four index repair/idempotence passes. All owned
fixture processes stopped; user services on3000/8000 were preserved.

Evidence: `/tmp/specimen-live-integration-data-verify-2.log`; retained proof
`/var/folders/nq/t4rvrkyx2dx2293cx4bn8gfm0000gn/T/specimen-data-test.FXkDFz/backup-restore-proof.json`,
SHA256 `87373c95298c576d5ae9e448c310fb2a0bf354195c1f2ae80c708c29866fa66c`.
Local synthetic restore evidence does not prove production backup or restore.

DataConnect3.2.0 COMPATIBLE reconstruction removes four supplemental nonunique
indexes. Explicit repair of paging/search indexes and post-restore ANALYZE remain
required. Core schema-managed uniqueness is separately checked; no unsupported
claim of lost uniqueness is made.

## Runtime build and mounted-input gates

All three images must build from a whitelist `git archive` of the exact combined
commit, assert LinuxAMD64 architecture and embedded source SHA, and smoke without
network access, credentials, checkpoint downloads or paid inference. Preliminary
ARM64 API/worker smoke does not establish the required runtime ABI. Preliminary
SAM ARM64 hash rejection was preserved; the supported AMD64 build passed.
See [Cloud Run's runtime contract](https://docs.cloud.google.com/run/docs/container-contract).
Final source-level and actual-container evidence remains required after repairs.

Startup materialization copies independently digest-pinned approved read-only
mounts into fresh runtime-owned0700 directories with0600 files, bounded reads,
exclusive creation and cleanup. Existing strict manifest/launch/profile readers
remain the authority. Both worker and SAM require explicit opt-in to this copy
step. A root-owned0444 synthetic mount must be tested inside the actual AMD64
UID10001 images; helper unit tests alone are insufficient. The copy step grants
no cloud, data-policy, inference or budget authorization.

## External static release

PR5 was externally merged as `1d297db520a6e31021e7bfa5e5f81b77e90cf618`
while client corrections were pending. It is reconciled into this branch without
reverting or cancelling the user's release. Main workflow
[34260264888](https://github.com/anurag-duddu/specimen-digitization-app/actions/runs/34260264888)
passed all six jobs including Hosting. Independent public deployment marker and
`smoke_hosting.sh` matched that exact SHA. Browser smoke rendered the collection
connection/setup screen because the API is not configured. This proves only the
static release; corrected client acceptance comes from PR11 and combined checks.

## Completion and launch boundaries

The combined PR requires canonical verification, all five platform checks,
additive runtime candidate checks, all three real AMD64 builds and independent
combined QA. Candidate structure CI reports NOT READY; strict readiness requires
an independently trusted exact source and complete evidence. Neither validator
creates approval or verifies live services. Leave the combined and owner PRs
unmerged for consolidated user review.

Runtime/data release configuration remains a proposal. Existing Hosting-only
commands, production environment, WIF conditions, pinned actions and original
policy tests remain intact. No workstation deployment or cloud mutation occurs.

Launch still needs refreshed cloud authentication and metadata, the exact frozen
ten-specimen manifest, actual resources/IAM and token/App Check acceptance,
approved model artifacts/rates/total budget, a reviewed separate runtime/data
release contract, production restore evidence and authenticated browser workflow
verification. See [the consolidated resource/cost proposal](LIVE_PILOT_COST.md).
No ready packet, completed cloud cohort or live product is claimed.
