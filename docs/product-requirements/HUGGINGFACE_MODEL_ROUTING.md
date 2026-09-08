# Hugging Face Model Routing

| Document field | Value |
|---|---|
| Status | Initial implementation; representative handwriting benchmark pending |
| Date | 2026-09-07 |
| Pilot | Field Museum Insects |
| Credential | `HF_TOKEN`, server-side only |
| Google Secret Manager resource | `projects/specimen-digitization/secrets/huggingface-runtime-token` |

## Decision

Use Hugging Face as the initial platform model gateway. One Hugging Face token
replaces separate model-provider credentials for routed inference, while the
application still owns model selection, provider policy, validation, audit
records, and fallback decisions.

This is an implementation of the existing `ModelGateway` boundary, not a
replacement for it. Collection profiles continue to reference logical
capabilities. A published profile resolves those capabilities to exact,
reviewed routes, and every run records that resolution.

## Initial transcription routes

| Route | Model | Provider | Intended use |
|---|---|---|---|
| `handwriting-qwen` | `Qwen/Qwen3-VL-30B-A3B-Instruct` | `novita` | Independent literal handwriting transcription |
| `handwriting-muse` | `meta-models/Muse-Glimmer-30B` | `deepinfra` | Independent literal handwriting transcription |

Both routes require text and image input and structured-output support. They
use different model families and infrastructure providers. They are candidates,
not approved production models, until the representative Field Museum
handwriting benchmark and data-policy review pass.

Automatic provider policies such as `auto`, `fastest`, `cheapest`, and
`preferred` are rejected by the gateway. A provider outage must produce a typed
operational failure or an explicit, recorded application fallback; it must not
silently move a run to different infrastructure.

## SAM 3

`facebook/sam3` is a gated Hub model and is not currently served through the
Inference Providers router. It remains a deterministic segmentation activity
on a separately provisioned GPU worker.

The model reference is pinned to revision
`3c879f39826c281e95690f02c7821c4de09afae7`. The runtime uses the same
`HF_TOKEN` to download that approved revision. The preflight downloads only
`config.json` to confirm gated access; it does not download the multi-gigabyte
checkpoint or provision GPU infrastructure.

## Nemotron

The initial self-hosted candidate is
`nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-FP8`, pinned to revision
`e9550fdec09682d12e8c3e41548b2e05b16db7c1`. Hugging Face currently lists the
model for local/vLLM use but does not advertise an Inference Provider for it.

Keep Nemotron behind the self-hosted OpenAI-compatible adapter until one of the
following is explicitly approved:

1. A compatible Hugging Face Inference Provider becomes live and passes the
   same route checks and handwriting benchmark.
2. A dedicated Hugging Face Inference Endpoint is provisioned with an approved
   region, hardware size, scaling policy, budget, and data terms.
3. The project deploys a vLLM/SGLang GPU worker in its own processing plane.

Do not provision an always-on paid endpoint from repository defaults.

## Credential and billing policy

Local development reads `HF_TOKEN` from the gitignored `.env`. Deployed workers
must receive the token from Google Secret Manager; it must never be stored in
Flutter configuration, SQL Connect/Cloud SQL, logs, traces, prompts, or checked
in files.

The current development token works for routed inference and gated SAM 3 access,
but it has permissions beyond runtime needs. Rotate it before production to a
fine-grained token containing only:

- `inference.serverless.write`;
- `repo.content.read`, scoped to the exact gated/private model repositories;
- `inference.endpoints.infer.write` only if the runtime calls a dedicated
  Hugging Face endpoint.

Endpoint creation/deletion, repository writes, jobs, webhooks, collections, and
billing administration belong on separate operator credentials. If inference
should bill a Hugging Face organization or resource group, set `HF_BILL_TO`;
this is configuration, not a secret.

## Verification

The safe default preflight performs four checks without sending a model prompt:

```bash
uv run --env-file .env specimen-huggingface-preflight
```

It verifies authentication and required permission names without displaying
identity or token material, validates each route against the live router model
catalog, and confirms access to the pinned SAM 3 `config.json`.

An explicit live smoke uses only an approved synthetic or public image:

```bash
uv run --env-file .env specimen-huggingface-preflight \
  --live-route handwriting-qwen \
  --approved-content \
  --image apps/specimen_digitization/web/icons/Icon-192.png
```

The smoke validates image input and typed Pydantic output. The optional
`--approved-content` flag records prompt/output text in the Logfire trace while
still excluding binary image bytes. It does not establish transcription quality.
Quality approval requires a versioned, representative, expert-reviewed
handwriting set and field-level error analysis.
