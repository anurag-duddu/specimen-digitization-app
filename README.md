# Specimen Digitization

A Flutter and Firebase application for converting natural-history specimen images into evidence-backed, reviewable digital records. Firebase SQL Connect backed by Cloud SQL for PostgreSQL is the application database. The first pilot targets the Field Museum Insects subcollection.

Firebase remains the product and data platform. Phase 0 will compare Temporal with Google Cloud Workflows as an additive durable workflow layer; Pydantic AI is the first typed, collection-specific agent-harness candidate. No Temporal Cloud resources should be provisioned until the bounded comparative failure-injection spike passes its decision gates.

## Current status

Product definition, architecture setup, initial Python observability scaffolding, and a Firebase-configured Flutter shell for Web, iOS, and Android. SQL Connect schema and connector implementation are the next database milestone.

## Workflow-engine status

Firebase Authentication, App Check, SQL Connect/Cloud SQL, Cloud Storage, and short event handlers remain responsible for identity, authorization, product records, large artifacts, and request handling. A durable workflow engine would coordinate the multi-stage specimen-processing lifecycle across worker crashes, provider retries, parallel model calls, deployments, cancellation, and human-review waits; it would not replace Firebase or store specimen business data.

Temporal is the fine-grained recovery candidate because Pydantic AI supports it directly. Google Cloud Workflows is the simpler GCP-native comparator when agent runs can stay short and every meaningful step can be externalized. The final choice must be based on the same failure-injection scenario, including a worker termination, provider `429`, human pause/resume, replay, and duplicate-side-effect checks. See [Agent harness and durable workflow options](docs/product-requirements/HARNESS_OPTIONS.md).

## Flutter client

The client is in `apps/specimen_digitization` and initializes the registered Firebase Web, iOS, and Android apps from the generated FlutterFire configuration. Authentication, Storage, and SQL Connect packages are installed. The iOS deployment target is 15.0 because the current Firebase Data Connect dependency chain requires it.

```bash
cd apps/specimen_digitization
flutter analyze
flutter test
flutter run
```

The SQL Connect service exists in Firebase, but it does not yet have a connector. Define and review the schema, operations, and connector before running `firebase dataconnect:sdk:generate`; do not make the Flutter client connect directly to PostgreSQL.

## Documentation

- [Product requirements](docs/product-requirements/PRD.md)
- [Agent harness decision and alternatives](docs/product-requirements/HARNESS_OPTIONS.md)
- [Validated GBIF integration strategy](docs/GBIF.md)
- [Observability, prompt, and evaluation architecture](docs/OBSERVABILITY_AND_EVALUATION.md)
- [Hugging Face model routing](docs/product-requirements/HUGGINGFACE_MODEL_ROUTING.md)
- [CI/CD and Firebase Hosting](docs/DEPLOYMENT.md)
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
