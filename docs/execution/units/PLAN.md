# Program plan: reading units and the specimen ontology

Owner's mandate, 2026-10-26: "build it once and for all, properly test it and run it and get it
working. It's not about adding more and creating more dead code. It's about building it right in a
maintainable way replacing, upgrading, adding, removing where needed. [...] once you spec it out
we'll decide the models, what they work on, split it all up and execute. [...] Plan it well and
iterate and get to final steady state."

Spec: [`docs/product-requirements/FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md`](../../product-requirements/FIRST_PASS_UNITS_AND_SPECIMEN_ONTOLOGY.md).

## 1. The goal and the steady state

The pipeline becomes: readers (N) -> first pass (reading units, never settles) -> field experts
(settle from the units, the lookups and the ontology) -> review for what remains. Measured on a
fixed reference set, the steady state is reached when, against today's pipeline:

- more fields settle right, no more settle wrong, fewer go to review;
- adding a reader never lowers the settled-right count (the design's own test);
- every settled value carries its basis (as written, matched by a source, derived by a named rule)
  and the app shows it;
- nothing dead remains: the removals in section 5 are done, not deferred.

Reference set: the 12 pilot labels already measured (`~/specimen-golive/runs/three-readers-20261025/
cases.json`, with reader C in `c_readings.jsonl`), plus 20 further specimens from the 1,000 real
slides chosen for multi-label specimens, so cross-label assembly is measured. The 2026-10-25 scores
are the baseline (`~/specimen-golive/runs/free-harness-20261025/score_full.md`).

## 2. Phases and work packages

Each work package is one branch, one pull request, one independent review on its exact head (G51),
merged and released on green per the owner's standing instruction, then pruned. Models: Fable
(this session) owns the design, the hard reviews and acceptance; Opus coordinates one phase lane at
a time and nothing else; Sonnet implements; Haiku writes documentation and bounded summaries.

### Phase 1: reading units

| WP | Scope | Files | Model | Acceptance |
|---|---|---|---|---|
| 1.1 Unit model and storage | `ReadingUnit`/`ReadingUnits` Pydantic models; stored with the run as a first-pass artifact; wire contract documented; the pinned contracts untouched or changed through their gates | `application/reading_units.py` (new), `application/first_pass.py`, `DATA_CONTRACT.md` | Sonnet; Fable designs the schema | Round-trips through the run record; contract tests pass |
| 1.2 First pass v2 | Prompt and output schema produce units; the model's unit texts are validated against the readers' texts and positions (the alignment `reading_differences_among` supplies the candidate breaks and the check); `selected_reader` and per-difference verdicts removed; retry text updated | `application/first_pass.py`, `prompts.py` (`_DISAGREEMENT_ADJUDICATION_DEFAULT` replaced), `integrity.py` | Sonnet; Fable reviews the prompt | On the 12 labels, every unit's reader texts are exact substrings at consistent offsets; `image` never names a text no reader wrote; cost per call within 1.5x today's |
| 1.3 Experts take units | Expert request carries units for the field (and all raw readings); `FirstPassAdvice` replaced; common.txt rule 4 and the five tool-less briefs rewritten; settlement basis `BY_IMAGE` (a literal that lies in units whose `image` names a reader) added; `BY_FIRST_PASS` whole-reader basis and the unanimity rule removed; `several_possibilities` when `image` is uncertain and no source settles | `field_research/contracts.py`, `experts.py`, `agreement.py`, `step.py`, `prompts/common.txt`, five briefs | Sonnet; Fable reviews `agreement.py` | Fail-first tests for each basis; `tests/field_research` green; no reference to the removed bases remains |
| 1.4 Organiser | Units' `fields` replace the organiser's candidates; `apply_candidates` unanimity rule removed; the organiser call removed if 1.5 shows units assign fields as well as it did, else kept as a check only | `application/harness.py`, `application/production.py` | Sonnet | Measured in 1.5 |
| 1.5 Measurement | Rig: live first pass per repeat (no replayed rows), pair and three-reader arms, two repeats, reference set; scored against the baseline | `~/specimen-golive/runs/units-<date>/` (off-repo), `scripts/lab/` if reusable | Sonnet runs; Haiku summarises; Fable accepts | Steady-state criteria 1 and 2 met or the gap explained |
| 1.6 App | Review screen shows the units per label (readers' texts, what the image names, the meaning, the field) in place of "the first pass preferred reader X"; finding codes named | `apps/specimen_digitization/lib/src/...` (review, blockers.dart), goldens | Sonnet, under the design docs; Fable reviews | Widget tests and size-class goldens; copy passes `design/02-ux-writing-guidelines.md` |
| 1.7 Docs | `FIELD_RESEARCH.md`, `HARNESS.md`, `DATA_CONTRACT.md`, closeout entry | docs | Haiku, reviewed by Fable | Every sentence backed by code or a test |

### Phase 2: the ontology

| WP | Scope | Files | Model | Acceptance |
|---|---|---|---|---|
| 2.1 The ontology file | One file: things, relations, constraints, derivations, each with an id, a plain statement, how it is checked (code, model, or not yet), its sources, and the Darwin Core term; drafted from the spec, the pilot labels, the existing briefs and `application/harness_knowledge/insects` | `src/specimen_digitization/ontology/specimen.yaml` (new) + loader | Opus drafts; Fable reviews; the owner reads the rules once | Loader validates every rule; the file renders to prompt text |
| 2.2 Baked in | The rendered ontology enters every model's instructions: readers, first pass, organiser if kept, every expert | `prompts.py`, `field_research/prompts/common.txt`, reader prompts | Sonnet | Prompt tests pin the rendered text; cost per call within budget |
| 2.3 Code-checked rules | Place chain (exists; keep), elevation range for the settled place (new source: a free elevation API, named in the file), date order (collect before determine), code dates agree with the collecting date, label types place units, institution and era conventions (unit of elevation by era and country) | `field_research/ontology_checks.py` (new), `derive.py` rewritten to read rules from the file | Sonnet; Fable reviews | Fail-first tests per rule; each derived value names its rule |
| 2.4 Cross-label assembly | One field from units on different labels when the ontology says they belong together (genus + species; day + year); conflicts between labels go to review with both | `agreement.py`, `step.py` | Sonnet; Fable reviews | Tests on multi-label specimens; measured in 2.5 |
| 2.5 Measurement | Same rig on the reference set including the 20 multi-label specimens | off-repo | Sonnet runs; Haiku summarises; Fable accepts | Criteria 1-3 met |
| 2.6 Docs | Ontology documented for curators; closeout | docs | Haiku | As 1.7 |

### Phase 3: people and conventions

| WP | Scope | Model | Acceptance |
|---|---|---|---|
| 3.1 People lookups | Wikidata persons for collectors and identifiers (active years, names); Bionomia only if Wikidata leaves gaps, put to the owner first | Sonnet | Collector matches on the reference set; no wrong settles |
| 3.2 Conventions table | Institution names and dates, slide-code formats, unit conventions, in the ontology file | Opus drafts; owner reads once | Rules validated and tested |
| 3.3 Steady-state run | Reference set, two repeats, both arms; the report that closes the program | Sonnet runs; Haiku summarises; Fable accepts | All four criteria met |

## 3. Order and gates

1.1 -> 1.2 -> 1.3 -> 1.4 -> 1.5 (gate: criteria 1 and 2) -> 1.6 and 1.7 in parallel.
2.1 starts when 1.3 is merged (it needs the units' shape); 2.2 -> 2.3 -> 2.4 -> 2.5 (gate) -> 2.6.
3.1 and 3.2 after 2.5; 3.3 closes.

One phase lane runs at a time; inside a lane, work packages that touch different files run in
parallel sessions in their own worktrees. The strict-main delta check applies to every merge.

## 4. Measurement budget

Each measurement run is costed at list before it starts and reported after. Program cap: USD 15 at
list across all runs (the 2026-10-25 program used USD 2.93 of its USD 3). A run that would pass the
cap waits for the owner.

## 5. Removals (not deferred)

- `FirstPassOutput.selected_reader`, `DifferenceVerdict`, `FirstPassAdvice`, `confirmed_against_image`, `BY_FIRST_PASS`, the unanimity-only `BY_AGREEMENT`, `_deciding`-era remnants, `first_pass_*` finding codes replaced by unit-based ones.
- `harness.apply_candidates`'s unanimity rule; the organiser call itself if 1.5 allows.
- `prompt__field_harness` (registered, read by no agent) and its Logfire mirror.
- The six-specialist research harness (`research_harness/`, `SPECIMEN_RESEARCH_HARNESS=on`) if the owner confirms production stays on field experts; its six Logfire mirrors with it.
- `_FIELD_HARNESS_DEFAULT` and any prompt text that describes the whole-reader pick.

## 6. What the owner does

Reads the ontology's rules once when 2.1 is drafted (they are statements about the collection), and
confirms or corrects them. Everything else is handled in the lanes and reported.
