# NVIDIA Nemotron option

Status: built behind a switch that is off. Production keeps today's models
until the owner turns the option on, after the conversation with NVIDIA's
Nemotron team. The owner asked for it on 2026-10-18, typed in the
coordinator session: "We have to enable Nvidia across the pipeline as
another option also see how this impacts the UI and backend".

This document covers what the option is, how it is switched, what it
changes in the backend and the app, and what was measured. The plain-language
story for NVIDIA is [`docs/outreach/NEMOTRON_STORY.md`](../outreach/NEMOTRON_STORY.md).

## 1. What runs where today, and the NVIDIA alternative

Every model call goes through `HuggingFaceModelGateway`
(`src/specimen_digitization/model_gateway.py`). It uses Hugging Face
Inference Providers, each route pinned to one provider, and it never uses
automatic provider routing.

| Stage | Today | NVIDIA option |
|---|---|---|
| Readers (two independent readings of each label) | `handwriting-qwen`: Qwen3-VL-30B-A3B on Novita; `handwriting-muse`: Muse-Glimmer-30B on DeepInfra | `handwriting-nemotron` takes reader A's place; Muse stays reader B |
| Parse (turns reader A's text into field candidates) | runs on reader A's route (`harness.py` uses `run.profile.routes[0]`) | follows reader A, so it runs on Nemotron when the readers stage is on |
| First pass (compares the two readings with the image) | `first-pass-glm`: GLM-5.3-Flash on Novita | `first-pass-nemotron` |
| Field research (20 field experts with lookups) | `harness-deepseek`: DeepSeek-V4.1-Flash on DeepInfra | `harness-nemotron` |
| Label finding (SAM 3) | not a language model | unchanged |

All three NVIDIA routes use one model,
`nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4` (120B parameters, 12B
active, image and text input, 1,048,576-token context, OpenMDW-1.1 licence,
published 2026-10-12), served by Baseten through Hugging Face.

### Why this model and this provider

Checked 2026-10-18 (full research: section 9).

- It is the only NVIDIA model that reads images and has a Hugging Face
  provider. Baseten is that provider, at USD 0.20 per million input tokens,
  0.04 cached and 0.50 output (Hugging Face router catalog and Baseten's
  price page).
- The text-only Nemotron models are served on Hugging Face by Fireworks
  (Nemotron 3.5 Lightning, Nemotron 3 Ultra NVFP4), DeepInfra (Ultra BF16,
  USD 1.00 / 5.00) and Featherless (Nemotron 3 Super, no listed price).
  Through the production token Fireworks answers HTTP 402 ("Pay-as-you go
  is not enabled for provider fireworks-ai yet"), as Together and Fireworks
  did on 2026-10-18 for GLM. Ultra on DeepInfra answers, at five times
  DeepSeek's list price. One model across the pipeline is also the simpler
  story for NVIDIA.
- NVIDIA's own API (build.nvidia.com) hosts all of them, but its trial terms
  allow internal testing only, not production, forbid personal data, and let
  NVIDIA use submitted content. Production NVIDIA serving is NIM under an AI
  Enterprise licence or a partner host such as Baseten. If NVIDIA offers
  credits on its own API, section 8 says what that path needs.
- No second NVIDIA vision model has a Hugging Face provider, so the option
  cannot supply two independent NVIDIA readers. Two readings from one model
  fail together, which defeats the reason for two readers. Nemotron
  therefore takes one reader slot. Section 7 shows why reader A: Muse plus
  Nemotron covered slightly more facts than Muse plus Qwen.

## 2. The switch

`SPECIMEN_NVIDIA_STAGES` is a comma-separated subset of `readers`,
`first_pass` and `field_research`. Unset or empty means off. Any other
value stops the process at start-up with an error that names the setting.

Examples:

- unset: today's pipeline, unchanged;
- `first_pass`: Nemotron compares the readings, everything else unchanged;
- `readers,first_pass,field_research`: Nemotron everywhere it can be.

The switch is read where the published collection profiles are loaded
(`published_registry()`). With any stage on, the loaded profile is a
variant of the published one:

- the stage's route fields change (`model_routes` becomes
  `("handwriting-nemotron", "handwriting-muse")`, `first_pass_route`
  becomes `first-pass-nemotron`, `harness_route` becomes
  `harness-nemotron`);
- its version gains semantic-versioning build metadata naming the stages,
  for example `1.0.0+nvidia.readers.first-pass.field-research`, and the
  collection mapping points at that version.

So every run records which option it ran under: its `profile_snapshot`
carries the variant's version and routes, and its pins carry each route's
model and provider. A run never changes option mid-way: it keeps the
profile it was classified under.

Rules that depend on the label rather than the models read the base
version. The field-research "not on the label" list
(`field_research/contracts.py`, keyed by profile id and version) is looked
up with the build metadata removed, so a variant clears the same fields as
the published profile.

The API and the worker each load the profiles. Both must carry the same
value, and `scripts/ci/test_runtime_settings.py` checks that.

### Turning it on

Production runs with the switch unset. Turning it on is a pull request that
adds `SPECIMEN_NVIDIA_STAGES` with the same value to the API and worker
environments in `scripts/ci/runtime_settings.py`. The runtime release
deploys it. Runs already in progress keep their routes. A new run or a
reprocess picks up the new option.

Turning it off is the same change reversed. A run that failed on an NVIDIA
route is reprocessed and takes today's routes.

## 3. Prices, reservations and actual cost

The owner's rule (2026-10-17): "remember I want actual costs attributed
properly."

- The published price list gains a row for each NVIDIA route at Baseten's
  list price, USD 0.20 in and 0.50 out per million tokens, context
  1,048,576. Its version becomes `pilot-prices-2026-10-18`. Extra rows are
  allowed: a profile must price every route it uses, and may price more. So
  the API, which copies the price list into a run when it queues it, never
  hands the worker a run whose NVIDIA routes are unpriced.
- The reader row carries Nemotron's image rule: one token per 32 by 32
  pixels (16-pixel patches merged 2 by 2), at most 3,328 tokens an image
  (`max_num_patches` 13,312 / 4), from the model's `preprocessor_config.json`.
  Reservations then size a reading by its crop, as for Qwen and Muse.
- The first-pass row carries GLM's request bounds: `max_input_tokens`
  32,768 and `max_output_tokens` 4,096.
- Stage costs gain `transcribe:handwriting-nemotron` at the same floor as
  the other readers.
- The cost meter (PR #378) settles each paid call from the tokens the
  provider reports, at the price list the run carries. Nothing else
  changes: the NVIDIA rows are ordinary rows.
- Cached input: Baseten lists USD 0.04 per million cached input tokens.
  The price list has no cached-input column, so reservations and the
  meter use the uncached price, the upper bound. The bill is lower when
  Baseten's cache hits.
- Parse runs on reader A's route, so with the readers stage on it is
  reserved and charged at Nemotron's row. Its reservation is two whole
  requests at the route's context, as today.
- What a call reserves before it is sent, in micro-dollars (pinned in
  `tests/test_nvidia_option.py`): a Nemotron reading 20,000 (the stage
  floor; a pilot crop's worst case is lower), parse 423,528, first pass
  423,528 (GLM's is 318,670), one field-research expert request 10,727. Two
  first-pass calls whose outcome stays unknown hold 847,056 of the USD 1 run
  limit, so a third waits; with GLM a third fits.
- The research harness's older "on" mode pins DeepSeek's tokenizer files
  for its request bound, so it refuses `harness-nemotron`
  (`research_committed_tokenizer_unpinned`) before any paid call until
  Nemotron's own files are pinned. Production's field research ("fields"
  mode) does not use those pins.

## 4. Secrets and release configuration

No new secret. Baseten is billed through Hugging Face's pay-as-you-go on the
same `HF_TOKEN` (`huggingface-runtime-token`, version 2) the worker already
mounts; a call on 2026-10-18 answered without HTTP 402.

The installed `huggingface_hub` (1.18.0) has no Baseten helper; Baseten
first appears in 1.26.1. Upgrading a library every route uses is a larger
change, so the NVIDIA routes use the gateway's `transport="router"`
instead: the client calls `https://router.huggingface.co/v1` with the model
name `model_id:baseten`. That name pins one concrete provider, exactly as
the provider client does, and keeps the token and the bill-to header
(tested in `tests/test_model_gateway.py`).

Preflight (`specimen-huggingface-preflight`) checks the routes of the
active option only, so the NVIDIA routes cannot block a release while the
option is off.

## 5. Failures and fallbacks

There is no automatic fallback between routes or providers, as for every
route today (`HUGGINGFACE_ROUTING.md`): a run never silently moves to
different infrastructure. With a stage on:

- a failed call retries on the same route up to the step's attempts, then
  the step gives up as today: a reader leaves the label one reading short,
  the first pass leaves the label undecided, field research marks the field
  as timed out, and the record goes to human review;
- Baseten gets its own provider circuit (keyed by provider), so its
  failures do not trip Novita's or DeepInfra's;
- the operational fallback is the switch: turn the stage off and reprocess
  the failed records;
- an HTTP 402 is not treated as a refusal, so a provider that stops
  accepting pay-as-you-go would hold each attempt's reservation until the
  run settles. Baseten answered on 2026-10-18; preflight would catch a
  catalog change.

Baseten is the only provider of this model on Hugging Face. That is the
main operational risk of the option, and a reason to keep Muse as reader B.

## 6. Provenance, audit and the app

### What is recorded

Nothing new is needed; the NVIDIA routes fill the same records:

- each reading and first-pass call: `route_id`, `model_id`, `provider`
  (`baseten`), the provider's reported model, prompt version, tokens,
  latency and the request settings, including a route's request options;
- each run: the profile snapshot (with the variant version), the pinned
  routes, and one `paid_calls` entry per paid call with the price list
  version;
- Logfire: the route, model and provider attributes on every span. With
  `transport="router"` Pydantic AI reports the model as
  `nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4:baseten`, so the
  `chat <model>` spans that the billed-cost workbook joins on carry that
  suffix.

### What a reviewer sees

The app shows only what each reading records. With the readers stage on, a
reading card names `nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4` and
the provider `baseten`, in the same place Qwen's name appears today. The
reader brand marks exist for Qwen and Muse only, and "unknown families
receive no mark" (`assets/reader-brands/README.md`), so the card shows the
name as text. Adding NVIDIA's mark would need NVIDIA's brand permission.

The app does not show the first-pass model, the field-research model, the
active option or any cost, today or with the option. Nothing in the app
needs to change for the option to work.

If the owner wants reviewers to see the option, the smallest useful change
is one "Models" row in Review details > Processing that lists each stage's
model and provider from the run's pins and profile snapshot. It is
read-only. The option should not be a reviewer setting: models are chosen
per deployment, so that cost and provenance stay controlled. That row is a
separate front-end change with its own design review (`design/` documents
and the UX writing checklist), not part of this option.

## 7. Measured on real labels

Measured on 2026-10-18, stage by stage, through the app's own code, with
only the stage's model changed. Spend: USD 2.43 at list price, of a USD 5
cap. The inputs, scripts and raw results are saved outside the repository
in `~/specimen-golive/runs/nvidia-nemotron-20261018/` (README there).

The labels are the ten pilot slides: handwritten 1946 labels from Mindanao
(Philippines) and 1948 labels from Yepocapa (Guatemala). No human-checked
transcript of them exists. The references are earlier sessions' readings of
the full-resolution images: S8's table of what each label says, S4's verdict
on each disagreement between the readers, and the field values in
`tests/fixtures/field_model_pilot_rows.json`. Each reference was checked
against the crop at every difference. The sample is small, so a difference
of a few points is noise; the large differences are not.

### Verdict per stage

| Stage | Nemotron compared with today | Recommendation |
|---|---|---|
| Readers | Weaker alone, never failed, 4x faster, same cost; with Muse it covers as many facts as today's pair | Ready: the best NVIDIA stage |
| Parse | About as accurate as Qwen, fewer wrongly filled fields, 20x faster, cheaper, less repeatable | Ready; it follows the readers stage |
| First pass | Wrong picks as rare as GLM's, but a third of labels left undecided and 3x the cost | Not yet: keep GLM |
| Field research | Half of its field experts fail the answer checks; dearer than DeepSeek | Not yet: keep DeepSeek |

### Readers

15 label crops (the ten left labels, plus the right-hand locality label of
slides 324-328), 3 readings each, the app's literal-transcription prompt and
agent. Each reading was scored against 98 reference facts, 75 of them the
facts the field experts rely on (dates, codes, collectors, places,
elevations).

| Reader | Calls | Failed | Facts right | Key facts right | Median s | List USD a reading |
|---|---|---|---|---|---|---|
| Muse (today's reader B) | 45 | 0 | 91.5% | 92.9% | 9.3 | 0.00150 |
| Qwen (today's reader A) | 45 | 12 | 69.0% (91.4% of answered) | 69.8% | 9.7 | 0.00029 |
| Nemotron | 45 | 0 | 76.2% | 76.4% | 2.2 | 0.00033 |

How often at least one of the two readers had a fact right, which is what
the first pass can choose from: Muse with Nemotron 94.9%, Muse with Qwen
94.6%, Nemotron with Qwen 89.8%. So Nemotron takes reader A's place, not
Muse's.

Nemotron reads places well (87 of 96) and is weakest on handwritten digits:
it read the writer's "2" as "a" or "D" in codes and dates (`IV- a9-68-4`,
`IV-D3-48`), dropped the foot mark from elevations, and of the 8 readings in which it
copied the printed catalog number beside a label, 2 had it one digit off
(slide 326, 4486778 for 4486779). Qwen's 12 failures were its output failing validation
twice, always on the same five labels; that is a finding about today's
reader, outside this option.

### First pass

PR #382's scored set: 12 labels with a reference (6 calls each) and 6 labels
where a reader wrote "[unreadable]" (3 calls each), through
`first_pass_direct`. GLM's rows are PR #382's "medium" calls from the same
day and code.

| First pass | Calls | Pick precision | Wrong picks | No answer | Fluent traps caught | Median s | List USD a call |
|---|---|---|---|---|---|---|---|
| GLM, reasoning "medium" (today) | 91 | 76% | 15% | 0% | 16 of 19 | 15.8 | 0.00055 |
| Nemotron, no reasoning (Baseten's default) | 90 | 34% | 38% | 22% | 1 of 14 | 1.1 | 0.00054 |
| Nemotron, reasoning "low" | 180 | 66% | 15% | 35% | 17 of 24 | 6.8 | 0.00173 |

- Baseten skips Nemotron's reasoning whenever a tool call is forced, and
  structured output forces one: 0-1 reasoning tokens against 1,516 with
  tool choice "auto". The route's `forced_tool_choice_disables_thinking`
  sends "auto", so the option's first-pass route reasons ("low"; "medium" was
  no better at 58% precision).
- With reasoning, 56 of 180 calls ran out of room at the 4,096-token answer
  cap that `reliability.run_agent_bounded` puts on every request (about 2,800
  output tokens a call on average). A label with no answer is left undecided
  and goes to review, which is safe but does no work. Raising that global
  cap is a separate decision, not made here.
- Without reasoning, 20 answers were malformed: notes for each reader written
  as one string, then keyed "Reader A", and "None" written as text.

### Parse

The ten slides, 3 calls each, same reader texts for both arms, through
`harness.extract_with_agent`.

| Parse | Failed | Main fields right / partial / wrong / missing (of 180) | Wrongly filled | Same result on repeat | Median s | List USD a call |
|---|---|---|---|---|---|---|
| Qwen (today) | 0 | 117 / 16 / 15 / 32 | 14 | 96.7% | 23.5 | 0.00085 |
| Nemotron | 0 | 112 / 15 / 9 / 44 | 4 | 67.5% | 1.2 | 0.00069 |

Nemotron took a slide-preparation code for a date in 3 calls; Qwen put
those codes into the collection code or catalog number in 24 calls and
Nemotron in 13. Qwen silently corrected the label's misspelling
"Chimaltenago" in all 9 calls, so the verbatim check dropped those
candidates. Nemotron kept the label's spelling, but filed the department as
the county 4 times of 9.

### Field research

The ten slides once each, and four of them twice, per model, through the
production step (`field_research.step.production_step()`), with GBIF,
Catalogue of Life and Global Names live and geography switched off.

| Field research | Runs failed | Experts whose answer failed the checks | Label fields right / wrong / review (of 41) | Derived fields right / wrong / review (of 50) | Collection date right | Median s | List USD a slide |
|---|---|---|---|---|---|---|---|
| DeepSeek (today) | 0 | 0 of 266 | 32 / 3 / 6 | 37 / 9 / 4 | 13 of 14 | 10.4 | 0.0433 |
| Nemotron | 0 | 132 of 266 | 14 / 2 / 25 | 3 / 28 / 19 | 0 of 14 | 4.0 | 0.0745 |

- Nemotron wrote the text "None" into empty fields (206 of 559 answers) and
  made up authority identifiers such as `wikidata:Q123456`, which the
  evidence checks rightly refuse. 18 answers were malformed. Turning its
  reasoning on made it worse (16 of 19 experts failed on one slide).
- Hugging Face bills DeepSeek at about 12% of list here, because the 20
  experts share a cached prompt: about USD 0.005 a slide. Nemotron at
  Baseten's cached rate would be about USD 0.03.
- Not measured: place fields (geography was off) and the effect of a first
  pass (both stages saw two raw readings).
- Nemotron's prompt tokens never exceeded the request's bytes (at most 0.28
  tokens a byte), so the field-research budget's byte-level assumption
  holds for it.

### Cost per specimen

From the measured per-call costs, for a slide with two labels (two readings
and one first pass per label, one parse, one field research), at list price
except field research, which uses Hugging Face's billed rate for DeepSeek
and Baseten's cached rate for Nemotron:

| Pipeline | AI cost a specimen (estimate) |
|---|---|
| Today | about 1.1 cents |
| Nemotron readers and parse (recommended) | about 1.1 cents |
| Nemotron in every stage | about 4.0 cents |

The billed-cost workbook of 2026-10-18 measured today's actual cost at about
2.9 cents a specimen, 1.7 of it AI and 1.2 machines; the estimate above is
lower because it leaves out retries, failed calls and slides with more
labels. The comparison between rows is what the estimate is for.

## 8. If NVIDIA offers credits on its own API

Credits on build.nvidia.com would need a direct transport: the
OpenAI-compatible endpoint `https://integrate.api.nvidia.com/v1` with an
`NVIDIA_API_KEY` secret (Secret Manager, a pinned version, the worker's
`secret_env`, an owner-run grant in `scripts/ops/owner_setup.sh`, and the
API's forbidden-secret list in `runtime_config.py`). `huggingface_hub`
1.18 already has an `nvidia` helper that calls that endpoint directly when
the key is not a Hugging Face token. NVIDIA's trial terms rule out
production use and personal data, so production would need NVIDIA's
written terms for the credits first. Credits on Hugging Face or Baseten
need no code change.

## 9. Sources

- Research notes (2026-10-18): candidates, providers, prices, terms
  (`nemotron-research.md` in the measurement folder of section 7).
- Route surface map (2026-10-18): every file the option touches
  (`route-surface-map.md`, same folder).
- Model card: https://huggingface.co/nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4
- Provider mapping: https://huggingface.co/api/models/nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B-NVFP4?expand[]=inferenceProviderMapping
- Router catalog and prices: https://router.huggingface.co/v1/models
- Baseten reasoning and pricing: https://docs.baseten.co/development/model-apis/overview
- NVIDIA API trial terms: https://assets.ngc.nvidia.com/products/api-catalog/legal/NVIDIA%20API%20Trial%20Terms%20of%20Service.pdf
