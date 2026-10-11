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

### How a reader's answer is read

A reader answers with one tool call whose arguments are a
`LiteralTranscription` (`src/specimen_digitization/transcription.py`): the
transcription whole, as `verbatim_text`, and split into `lines`. The schema
asks for `verbatim_text` to be the lines joined with newlines, and an answer
whose two forms disagree is refused.

Novita's server for `Qwen/Qwen3-VL-30B-A3B-Instruct` has also answered with
`lines` split at each break and each break in `verbatim_text` written as a
space (three answers on 2026-10-03; 16 of the 18 answers of run 0c7f52e1 on
2026-10-11) or as the newline symbol `↵`, U+21B5 (the other two). The exact
rule refused all 18 of 2026-10-11, so every handwriting-qwen reading of that
run failed as `model_malformed_response`. Such an answer is now read as its
lines joined with newlines. The rule is exact: `verbatim_text` must be the lines
in order with exactly one character between each two lines, that character a
newline, a space or `↵`, and every other character the same as in the lines.
Two spaces are therefore accepted only where the lines have two breaks, around
an empty line (lines `["a", "", "b"]` with "a  b" read `"a\n\nb"`). Anything
else is still refused: a word that differs (a recorded 2026-10-05 answer read
"tap" in its text and "trap" in its lines), two characters at one break, a break
the lines do not have, text added or dropped, lines out of order. A refused
answer gets Pydantic AI's one output retry and then fails as
`model_malformed_response`, which the workflow retries as a reader's failure
(`docs/execution/golive/HARNESS.md` section 3).

The schema the readers are sent is unchanged, and the raw response stored with
an observation keeps the provider's answer as it was sent; the observation's
text and its declaration evidence hold the newline form. Nothing on the
observation records that a break was rewritten: reading the stored raw answer
again with `LiteralTranscription` gives the observation's text. The human-review
release checker (`scripts/qa/live/human_review.py`, `literal_output`) compares a
retained raw answer with its observation that way, so it applies the same rule
as the reader. The recorded answers are in
`tests/fixtures/qwen_reader_answers.json`, replayed by
`tests/test_reader_line_breaks.py` and `scripts/qa/live/test_human_review.py`.

## First-pass and harness routes

| Route | Model | Provider | Intended use |
|---|---|---|---|
| `first-pass-glm` | `zai-org/GLM-5.3-Flash` | `deepinfra` | The LLM first pass: which reader's raw transcript the harness runs on (text and image) |
| `harness-deepseek` | `deepseek-ai/DeepSeek-V4.1-Flash` | `deepinfra` | The agentic harness's tool calling (text); provisional until the acceptance lab re-measures it with the real harness and G29's prompt |

Chosen on 2026-09-23 from measurements on the ten pilot slides, recorded in
`docs/execution/golive/HARNESS.md` section 5, and approved by the coordinator on
2026-09-23 (coordinator.md:58); G7 requires only that the first pass and the
harness run on a Hugging Face model through the existing gateway and token. They
share the `handwriting-muse` reader's provider and no reader's model family.
Each is pinned by model id and provider, as the readers are, and a reader or
first-pass call refuses a route outside its role (HARNESS.md section 5).

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
