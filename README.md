# Specimen Digitization

A Flutter and Firebase application for converting natural-history specimen
images into evidence-backed, reviewable digital records. The first pilot targets
the Field Museum Insects subcollection. Firebase SQL Connect, backed by Cloud SQL
for PostgreSQL, is the application database; Cloud Storage holds images and
immutable evidence.

## Current implementation

The repository contains a Flutter web/Android/iOS client, a scoped FastAPI
service, a checkpointed Python processing worker, SQL Connect schemas and named
operations, and separate Hosting, data, and runtime release workflows. Pydantic
AI agents, field research, and SAM 3 serving are implemented.

The processing path accepts camera captures or selected files, identifies label
regions, retains independent readings, compares them, organises fields,
researches their supporting evidence, and applies collection policy. The client
shows saved processing milestones and retry or attention states. Reviewers can
inspect the source and evidence, save reasoned decisions, and work with records
in the Cleared, Needs Human, and Deferred queues. A processing block is separate
from a final queue decision.

These are implementation descriptions, not a report of current production
health or museum quality acceptance. A synthetic demo uses declared fixtures;
it does not establish real-model accuracy, physical-device behavior, or
institutional acceptance. See [Release rules](#release-rules) for deployment
verification.

## Architecture and processing

| Component | Location | Responsibility |
|---|---|---|
| Flutter client | `apps/specimen_digitization/` | Sign-in, collection access, intake, source/evidence review, and queue decisions |
| Scoped API | `src/specimen_digitization/application/api.py` | Authorization, uploads, record reads and writes, and worker dispatch |
| Processing worker | `src/specimen_digitization/application/worker.py` | Advance persisted runs through bounded steps and recovery |
| Field research | `src/specimen_digitization/field_research/` | Research individual fields and retain their supporting evidence |
| Research harness | `src/specimen_digitization/research_harness/` | Research contracts, persistence, publication, and workflow integration |
| SQL Connect | `dataconnect/` | Application schema, named server operations, and supplemental indexes |
| Runtime definitions | `scripts/ci/runtime_settings.py`, `containers/` | API, worker, SAM, pinned configuration, and secret references |

Firebase Authentication and App Check supply identity and app attestation. The
API checks collection membership. Flutter sends photographs and record changes
through that API; it has no Storage or SQL Connect client dependency and never
connects directly to PostgreSQL. The local synthetic adapter uses SQLite and
local blobs; the production adapters use SQL Connect and Cloud Storage.

The current worker uses an application-owned workflow with persisted progress,
leases, bounded retries, and cost reservations. The committed worker settings
select `SPECIMEN_RESEARCH_HARNESS=fields`: research runs one expert per field at
the post-parse handover for profiles with a harness route. `on` selects the
six-specialist research harness instead; `off` retains the ordinary processing
chain. See the [field research design](docs/execution/golive/FIELD_RESEARCH.md)
and [mode selection](src/specimen_digitization/research_harness/enablement.py).

Temporal and Google Cloud Workflows are comparison proposals, not the engine
running this worker. The [workflow options document](docs/product-requirements/HARNESS_OPTIONS.md)
records the comparative spike and the restriction on provisioning Temporal
Cloud before its decision gates pass. Its description of Pydantic AI as a
candidate predates the implemented agents.

## Local development

Use Python 3.11 or newer (CI uses 3.12), uv **0.12.5**, and Flutter **3.38.5**
with Dart **3.10.4**. The full local gate also requires Firebase CLI **15.8.0**.
Keep the committed lockfiles and the Flutter dependency overrides. See
[the tool and command catalog](docs/DEPLOYMENT.md#required-local-tools) for
platform prerequisites. Android builds need a JDK; iOS builds need
Xcode/CocoaPods and target iOS 15.0 or newer.

From the repository root:

```bash
uv sync --frozen
uvx --from pre-commit==4.5.1 pre-commit install \
  --hook-type pre-commit --hook-type pre-push
```

### Run the synthetic API and demo

This path needs no Firebase credentials, provider keys, paid inference, or
museum images. It creates a generated label and exercises HTTP upload,
processing, review, and fixture-policy clearance.

Use a free port 8000. In one terminal, start the API in the background so the
demo command can inherit the same private local bearer:

```bash
export SPECIMEN_SYNTHETIC_TOKEN="$(openssl rand -hex 24)"
demo_state="$(mktemp -d "${TMPDIR:-/tmp}/specimen-demo.XXXXXX")"
uv run specimen-api --mode synthetic --state-dir "$demo_state" --port 8000 &
demo_api_pid=$!
```

Wait for readiness, then run the CLI in that same terminal:

```bash
curl --fail --silent --show-error --retry 30 --retry-connrefused \
  --retry-delay 1 --max-time 2 http://127.0.0.1:8000/health/ready
uv run specimen-demo --url http://127.0.0.1:8000
```

The demo prints its synthetic mode, specimen ID, disposition, and revision.
Keep the API running to inspect that record in Flutter. Use the value of
`SPECIMEN_SYNTHETIC_TOKEN` privately in the client's **Fixture token** field;
any test email is a local display label. Do not use a production token.

When finished, stop the API started in this terminal:

```bash
kill "$demo_api_pid"
wait "$demo_api_pid"
unset SPECIMEN_SYNTHETIC_TOKEN
```

The temporary state directory remains available for inspection. To resume
pending synthetic work after stopping the API, set the same local bearer and
run `uv run specimen-worker --mode synthetic --state-dir "$demo_state"`.
For the optional PostgreSQL-backed SQL Connect emulator, see
[`scripts/data/serve-local.sh`](scripts/data/serve-local.sh); emulator success
is separate from production migration or acceptance evidence.

### Connect Flutter to the local API

In a second terminal, preserve any existing generated Firebase configuration
and create a credential-free placeholder only when it is absent:

```bash
cd apps/specimen_digitization
test -f lib/firebase_options.dart || cp lib/firebase_options.ci.dart lib/firebase_options.dart
flutter pub get --enforce-lockfile
flutter run -d web-server --web-port 3000 \
  --dart-define=SPECIMEN_API_BASE_URL=http://127.0.0.1:8000 \
  --dart-define=SPECIMEN_LOCAL_SYNTHETIC=true
```

Open `http://localhost:3000`. The synthetic API allows this local origin. The
client restricts synthetic access to a local API and labels the fixture mode.
Remove only a placeholder you created when finished; preserve a pre-existing
real configuration.

A plain `flutter run` does not configure collection access. Production mode
requires real FlutterFire configuration, `SPECIMEN_API_BASE_URL`, and, on web,
`SPECIMEN_RECAPTCHA_SITE_KEY`. Missing configuration can show the setup screen.
`lib/firebase_options.dart` is ignored and must never be committed. Firebase
configuration maintenance and production web build inputs are documented in
[the deployment runbook](docs/DEPLOYMENT.md).

### The design system

The client uses the in-repo
[`specimen_ui` package](apps/specimen_digitization/packages/specimen_ui/README.md)
for tokens, primitives, and controls. It is built on Flutter widgets, with
Material retained for framework infrastructure rather than screen components.
The [brand direction](apps/specimen_digitization/design/09-brand-direction.md)
and [component specification](apps/specimen_digitization/design/10-component-library.md)
describe the design.

Visit `/gallery` in a non-release local build to browse tokens and controls.
It needs no session and is absent from release builds. The
[client README](apps/specimen_digitization/README.md) covers layering,
accessibility, reduced motion, and the macOS golden-comparison policy.

## Verification

Run the canonical gate from the repository root before pushing:

```bash
scripts/ci/verify.sh
```

It runs repository and secret checks, frozen Python installation and test
shards, UI writing checks, both Flutter packages' analysis and tests, Dart
formatting, a release web build, and a loopback route smoke. It creates and
removes a CI Firebase placeholder only if the ignored configuration is absent.
It does not deploy or run paid model requests.

For focused client checks, run these commands separately from
`apps/specimen_digitization`:

```bash
flutter analyze --fatal-infos
flutter test
dart format --output=none --set-exit-if-changed \
  lib test packages/specimen_ui/lib packages/specimen_ui/test
```

Run `flutter pub get`, `flutter analyze --fatal-infos`, and `flutter test`
separately inside `apps/specimen_digitization/packages/specimen_ui` as well.
Avoid concurrent Flutter verification in one worktree. Native compile checks
are `scripts/ci/build_mobile.sh android` and `scripts/ci/build_mobile.sh ios`;
they prove compilation, not device operation, signing, or store distribution.

## Release rules

Production changes go through a pull request with the required checks and
review, then merge to `main`. Each merge starts three workflows:

| Workflow | Production changes |
|---|---|
| [CI/CD](.github/workflows/ci-cd.yml) | Deploy the tested static Flutter artifact to Firebase Hosting |
| [Data release](.github/workflows/data-release.yml) | Initialize missing database state, apply additive schema changes, publish schema/connector, indexes, Storage rules, bootstrap rows, and pinned georeferencing datasets |
| [Runtime release](.github/workflows/runtime-release.yml) | Build and publish API/worker/SAM images, deploy by digest, and verify the runtime definitions |

Data and runtime workflows also accept manual dispatch on `main`; manual
Hosting dispatch runs checks without deploying. Runtime deployment waits for a
successful data release of the same commit. An ordinary runtime release defines
the worker job without executing it; optional manual `process_queued` processing
is a separate action.

A release is complete only when all three workflows succeed on the merged
commit, the public `/deployment.json` marker and API `/version` source SHA
match it, and Hosting/API/runtime smoke checks pass. Processing success and
scientific acceptance remain separate checks.

Never deploy from a workstation or agent shell, weaken required checks or
branch protection, or use the Hosting workflow to deploy data or runtime
resources. The authoritative contract is [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).
Read it and [AGENTS.md](AGENTS.md) before release-sensitive work. Owner setup,
when needed, follows that runbook; it is not part of local development.

## Model access

The [model gateway](src/specimen_digitization/model_gateway.py) registers
explicit provider routes rather than automatic provider selection:

| Route | Model | Provider | Role |
|---|---|---|---|
| `handwriting-qwen` | Qwen3-VL-30B-A3B-Instruct | Novita | Independent image reading |
| `handwriting-muse` | Muse-Glimmer-30B | DeepInfra | Independent image reading |
| `first-pass-glm` | GLM-5.3-Flash | Novita | Compare readings |
| `harness-deepseek` | DeepSeek-V4.1-Flash | DeepInfra | Field organisation and research |

Runs retain their pinned route/profile configuration. The source gateway is
the authority for exact model IDs. `HF_TOKEN` is server-only; the committed
worker configuration references the `huggingface-runtime-token` Secret Manager
secret by numbered version. Provider credentials do not belong in Flutter or
SQL Connect records.

SAM 3 is implemented as a private segmentation service called by the worker,
with a revision-pinned `facebook/sam3` asset and checkpoint validation. The
runtime release deploys it separately from the API and worker. Nemotron remains
a pinned self-hosted evaluation candidate, not one of the configured HF routes.
See [Hub assets](src/specimen_digitization/hub_models.py) and
[runtime settings](scripts/ci/runtime_settings.py).

For optional real-service development, copy `.env.example` to `.env` only if
needed and fill the settings used by that task. The file includes proposal
settings, such as Temporal, that do not enable an implemented integration.
Commands load it explicitly with `uv run --env-file .env`; the synthetic demo
does not need it. Never commit `.env`, credentials, museum images, transcripts,
or production exports.

The preflight checks credentials, route availability, and SAM asset access
without paid inference by default; it still contacts Hugging Face:

```bash
uv run --env-file .env specimen-huggingface-preflight
```

`--live-route` makes a paid request; image routes also require an approved
image through `--image`, while text-only routes reject images. Run live calls
only with spending and data approval. See the [model routing notes](docs/product-requirements/HUGGINGFACE_MODEL_ROUTING.md)
for background; committed source determines the current routes.

## Observability and evaluation

Logfire instrumentation and Pydantic Evals are implemented. To exercise their
synthetic contracts locally without exporting telemetry or calling a model
provider:

```bash
uv run specimen-logfire-smoke --no-send
uv run specimen-eval-smoke --no-send
```

Omit `--no-send` only when the intended Logfire destination is configured.
Local Logfire credentials are ignored under `.logfire/`. The local default
capture mode is `metadata`, which excludes prompt/output text. The committed
production runtime settings select `approved-content`, which permits text
under the recorded data policy; binary image content remains excluded in both
modes. Production credentials are pinned Secret Manager references. See the
[observability architecture](docs/OBSERVABILITY_AND_EVALUATION.md) and current
[runtime settings](scripts/ci/runtime_settings.py).

## Documentation

Start with source and current implementation references:

- [Production deployment contract](docs/DEPLOYMENT.md)
- [Field research implementation](docs/execution/golive/FIELD_RESEARCH.md) and [harness contracts](docs/execution/golive/HARNESS.md)
- [Product requirements](docs/product-requirements/PRD.md) and [collection hierarchy](docs/product-requirements/COLLECTION_HIERARCHY.md)
- [GBIF integration](docs/GBIF.md)
- [Front-end design foundation](apps/specimen_digitization/design/README.md) and [design system](apps/specimen_digitization/packages/specimen_ui/README.md)
- [Append-only session learnings](docs/SESSION_LEARNINGS.md)

These documents retain decisions, proposals, or dated evidence rather than a
current production status report. Check their dates and superseding notes:

- [Historical runnable handoff and evidence index](docs/execution/HANDOFF.md)
- Historical records only (retired; do not follow their commands): [2026-09-22 go-live readiness assessment](docs/execution/GO_LIVE_READINESS.md) and [first-ten runbook](docs/execution/GO_LIVE_RUNBOOK.md)
- [Architecture decision record](docs/execution/ARCHITECTURE.md)
- [Workflow-engine comparison](docs/product-requirements/HARNESS_OPTIONS.md)
- [Front-end refactor plan](docs/execution/FRONT_END_REFACTOR.md) and [lessons](docs/LESSONS_FRONT_END_REFACTOR.md)
- [Field Museum EMu Parties and IRN research](docs/product-requirements/EMU_PARTIES_IRN_RESEARCH.md)
