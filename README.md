# Specimen Digitization

A Flutter and Firebase application for converting natural-history specimen images into evidence-backed, reviewable digital records. Firebase SQL Connect backed by Cloud SQL for PostgreSQL is the application database. The first pilot targets the Field Museum Insects subcollection.

Firebase remains the product and data platform. Phase 0 will compare Temporal with Google Cloud Workflows as an additive durable workflow layer; Pydantic AI is the first typed, collection-specific agent-harness candidate. No Temporal Cloud resources should be provisioned until the bounded comparative failure-injection spike passes its decision gates.

## Current status

A connected Flutter intake/review client, scoped Python API and worker, immutable
evidence storage, and SQL Connect schema/operations are implemented and tested
locally. Synthetic demonstrations use declared fixtures; production processing,
institutional quality acceptance and deployment remain gated. Start with the
[reviewer handoff and runnable demo](docs/execution/HANDOFF.md).

## Workflow-engine status

Firebase Authentication, App Check, SQL Connect/Cloud SQL, Cloud Storage, and short event handlers remain responsible for identity, authorization, product records, large artifacts, and request handling. A durable workflow engine would coordinate the multi-stage specimen-processing lifecycle across worker crashes, provider retries, parallel model calls, deployments, cancellation, and human-review waits; it would not replace Firebase or store specimen business data.

Temporal is the fine-grained recovery candidate because Pydantic AI supports it directly. Google Cloud Workflows is the simpler GCP-native comparator when agent runs can stay short and every meaningful step can be externalized. The final choice must be based on the same failure-injection scenario, including a worker termination, provider `429`, human pause/resume, replay, and duplicate-side-effect checks. See [Agent harness and durable workflow options](docs/product-requirements/HARNESS_OPTIONS.md).

## Flutter client

The client is in `apps/specimen_digitization`. It is what a collections
reviewer works in: photographs come in through intake, a record is reviewed
against its own evidence, and a decision is recorded with a reason. One
codebase serves the web, Android and iOS. It initializes the registered
Firebase Web, iOS and Android apps from the generated FlutterFire
configuration; the Authentication and App Check packages are installed, and
nothing else. Photographs and records travel over the scoped API, so the
Storage and SQL Connect client packages are not in the bundle: they were
declared and never imported, and were removed. The iOS deployment target is
15.0 because the Firebase iOS SDK these packages resolve to requires it.

```bash
cd apps/specimen_digitization
flutter pub get --enforce-lockfile
flutter run -d chrome
```

The committed SQL Connect schema and named server operations are exercised with
an isolated PostgreSQL-backed emulator. Their production rollout is separate
from Hosting and is not performed by this PR. Flutter calls the scoped API;
it does not connect directly to PostgreSQL.

[`apps/specimen_digitization/README.md`](apps/specimen_digitization/README.md)
has the layers, the gates, the golden policy and the text scale and reduced
motion behaviour.

### The design system

The client's presentation layer is an in-repo package,
[`specimen_ui`](apps/specimen_digitization/packages/specimen_ui), built on
`package:flutter/widgets.dart` rather than on Material. Tokens, primitives and
thirty controls live there; no screen in the application constructs a Material
component, and a test holds that line. The direction is
[`design/09-brand-direction.md`](apps/specimen_digitization/design/09-brand-direction.md)
and the library is specified in
[`design/10-component-library.md`](apps/specimen_digitization/design/10-component-library.md).

Every token and every control, in every variant, state, size, density and mode,
is on one browsable page:

```bash
cd apps/specimen_digitization
flutter run -d chrome
# then visit /gallery
```

The gallery needs no session and is absent from release builds, so it is what a
reviewer looks at and not what a museum sees.

### Running the client's gates

Every rule the client is held to is a test. Run each on its own and read its
own exit code; the two suites contend for one machine, so a single chained
command can be reaped without either having failed.

```bash
cd apps/specimen_digitization
flutter analyze --fatal-infos
flutter test
(cd packages/specimen_ui && flutter analyze --fatal-infos && flutter test)
dart format --set-exit-if-changed lib test
```

The full local gate for the whole repository, which is what CI runs, is
`scripts/ci/verify.sh`.

## Release rules

1. A merge to `main` is the only production trigger; a pull request cannot
   deploy.
2. No `firebase deploy`, Hosting channel deploy or `gcloud ... deploy` command
   is ever run from a workstation or an agent shell.
3. A release is complete only when the public `/deployment.json` marker reports
   the exact merged commit SHA and the smoke check passes.

The authoritative runbook, with the required checks, the identities and the
failure handling, is [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md). Read it before
changing CI, release configuration, Firebase Hosting, Google Cloud IAM, GitHub
environments or production.

## Documentation

- [Go-live readiness assessment](docs/execution/GO_LIVE_READINESS.md) and the [owner runbook](docs/execution/GO_LIVE_RUNBOOK.md)
- [Runnable handoff, architecture and evidence index](docs/execution/HANDOFF.md)
- [Product requirements](docs/product-requirements/PRD.md) and the [collection hierarchy](docs/product-requirements/COLLECTION_HIERARCHY.md)
- [Agent harness decision and alternatives](docs/product-requirements/HARNESS_OPTIONS.md)
- [Validated GBIF integration strategy](docs/GBIF.md)
- [Observability, prompt, and evaluation architecture](docs/OBSERVABILITY_AND_EVALUATION.md)
- [Hugging Face model routing](docs/product-requirements/HUGGINGFACE_MODEL_ROUTING.md)
- [CI/CD and Firebase Hosting](docs/DEPLOYMENT.md)
- [Front-end design foundation, 00 to 13](apps/specimen_digitization/design/README.md)
- [The `specimen_ui` design system](apps/specimen_digitization/packages/specimen_ui/README.md)
- [Front-end refactor plan](docs/execution/FRONT_END_REFACTOR.md) and [what it taught](docs/LESSONS_FRONT_END_REFACTOR.md)
- [Field Museum EMu Parties and IRN availability check](docs/product-requirements/EMU_PARTIES_IRN_RESEARCH.md)

## Safe local setup

1. Copy `.env.example` to `.env` and fill only the backend services used for the current development task. Blank optional values are not setup failures.
2. Install the official FlutterFire CLI with `dart pub global activate flutterfire_cli`.
3. The Flutter client lives in `apps/specimen_digitization`. Rerun `flutterfire configure` there when its Firebase app configuration changes; do not duplicate client configuration in `.env`.
4. Keep SQL Connect schemas, connectors, operations, and generated-SDK configuration in source control. Do not make the Flutter client connect directly to PostgreSQL.
5. Java is not required by FlutterFire or hosted SQL Connect. Android builds need a JDK (Android Studio normally supplies one), and Java-based Firebase emulators such as Storage need a local JDK.
6. Never commit `.env`, cloud credential files, museum images, raw transcripts, or production exports.
7. Read the mandatory [CI/CD and production deployment contract](docs/DEPLOYMENT.md).
8. Install both Git hooks:

   ```bash
   pre-commit install --hook-type pre-commit --hook-type pre-push
   ```

9. Run the complete local CI suite before a commit or push:

   ```bash
   scripts/ci/verify.sh
   ```

Use short-lived, least-privilege development credentials. Tenant BYOK is provider-neutral runtime configuration: the administrator supplies the supported provider or compatible endpoint, model metadata, and credential. Production BYOK credentials will live in a cloud secret manager and will be referenced by identifier rather than stored in SQL Connect/Cloud SQL or local configuration.

## Logfire observability

Local Logfire credentials live in the gitignored `.logfire/` directory. After
selecting the intended Logfire project, install the Python environment and send
one synthetic Pydantic AI run:

```bash
uv sync
uv run specimen-logfire-smoke
```

The smoke run uses Pydantic AI's deterministic test model, so it does not need a
model-provider key or send specimen data. Run the synthetic Pydantic Evals
contract experiment with:

```bash
uv run specimen-eval-smoke
```

`LOGFIRE_CAPTURE_MODE=metadata` is the safe default. It records the complete
trace structure and operational metadata without prompt/output content.
`approved-content` additionally records text for approved evaluation fixtures;
binary image bytes are always excluded. See the observability architecture for
the trace attributes, managed prompt names, dataset strategy, and promotion
gates.

## Hugging Face model access

The initial model gateway uses one `HF_TOKEN` for two explicitly pinned
Inference Providers routes: Qwen through Novita and Muse through DeepInfra. It
does not use Hugging Face's automatic provider selection, so a provider cannot
change silently during a versioned specimen run.

The same token can read the gated, revision-pinned `facebook/sam3` asset for a
future GPU segmentation worker. Nemotron remains a pinned self-hosted candidate
because its vision model is not currently served by Inference Providers. The
token is server-only: local development reads `.env`, and deployed workers will
receive it from the `huggingface-runtime-token` secret in the
`specimen-digitization` Google Cloud project.

Run the non-paid credential, route-catalog, and SAM 3 access checks with:

```bash
uv run --env-file .env specimen-huggingface-preflight
```

Add `--live-route handwriting-qwen` or `--live-route handwriting-muse` plus an
approved PNG or JPEG through `--image` to make a paid image request and verify
Pydantic structured output. Add `--approved-content` only when prompt and output
text may be retained in Logfire; image bytes remain excluded. Never use an
unapproved specimen image for this smoke test.
