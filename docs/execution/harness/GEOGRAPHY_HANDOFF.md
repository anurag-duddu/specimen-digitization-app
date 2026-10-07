# Geography harness local implementation — 2026-10-07

Task/chat: Geography harness, `01a11840-3eb6-7831-874a-1cbf46b3ee67`.
Branch: `codex/harness-geography`.
Worktree: `/Users/anuragduddu/.codex/worktrees/6fc3/specimen-digitization-app`.
Verified clean base and remote default branch at start: `7890de551c75fe3b06836c7fb224f85dd2a2423a`.

This is an implemented, locally tested geography slice and shared extension interface. Lane P retains integration, canonical verification, PR review/merge, paid canaries and release. No production, billing, owned runner, human decision, budget hold or original dirty checkout was changed.

## Connected geography behavior

- New geography jobs pin coherent v9 instructions. Historical v1-v8 prompt files remain byte-identical. Old numeric model queries are locally refused; the separate worker-only locked-anchor command proof still permits geometry.
- Model GEOLocate queries contain place text, without guessed latitude, longitude or radius. Names and country/admin context require immutable readings, previous scoped deciding validation, or an exact query proposed from captured typed hierarchy. Actual returned coordinates remain captured metadata, never record fields.
- `geography_hierarchy()` proposes target-specific GEOLocate queries from captured hierarchy; it never promotes a historical candidate to a settled field. NGA's typed country/admin links are supported; generic TGN/Wikidata parent links do not silently become administrative levels. Unanimous parents can supply country/admin hypotheses while separate town/municipality identities remain explicit.
- `geography_progress(field_key)` tracks retained effects and distinct semantic strategies. A relevant completed alternative is enough; no fixed all-provider sequence. Unrelated place searches or cached original queries cannot close research. Novel canonical names need validation; country/admin hypotheses need the exact verified hierarchy interpretation. Scientific ambiguous hierarchy can create structured review after its names are covered; missing type/date proof remains an explicit prerequisite.
- Validator v4 excludes nonsettling historical/computed proposals from deciding authority and permits valid literal locality assemblies beside historical context. v1-v3 validator identities remain readable; evidence is revalidated under the current boundary. The evidence source SHA is pinned in `accepted_output.py`.
- Default v9 geography recovery restores a failed, complete native frontier with exact scope/input/prompt/serialization checks, canonical source rehydration and spent request/tool/helper counts. Unknown send/cost, open tools, active/unrecorded runs and changed pins fail closed. Spent helpers return a contained limit result with production zero tool retries, so valid retained work can finish. Authorized field retries use their admitted command identity in a separate conversation and retain the same financial ledger.

## Field outcomes demonstrated offline

| Field | Demonstrated behavior |
| --- | --- |
| country | A label naming only Yepocapa newly publishes Guatemala after captured NGA hierarchy and field-specific GEOLocate validation. Country was absent from every input reading. |
| province_state | The same composed run newly publishes Chimaltenango from its verified hierarchy and deciding validation; the admin name was absent from the label. |
| city | Publishes Yepocapa from the exact captured deciding candidate; raw/locality provenance remains attached. |
| precise_location | Publishes the accepted written locality without replacing it by a modern administrative interpretation. Valid verbatim assemblies survive nonsettling historical context. |
| county | Guatemala remains unresolved `waiting_policy` under the existing unqualified county contract; no municipality-to-county mapping is invented. |

Normal deciding success may settle despite an earlier refusal, with all history retained. Any unresolved refused, failed, timed-out or unreceipted strategy remains a source hold. Legitimate completed absence/ambiguity yields structured Needs Human work. Missing declared unit policy uses the existing policy path. No new product queue or automatic outage-to-Deferred policy was added; final product queues remain Cleared, Needs Human, Deferred.

## Shared interfaces and ownership

`shared_capabilities.py` supplies `SharedResearchAdapters` and `SharedResearchCapability` using the pinned AI 2.51.0 capability/toolset API and the existing durable effect broker. Browser capture, isolated-code execution, verified role/collection lessons and exact reviewed procedures share scope, field revision/human lock, registration, effect, budget, size and timeout gates. Pages and code outputs are untrusted data; catalog entries are reusable context, not field authority. No model memory writes or model-weight training occur.

Providers are injected protocols: browser navigation is source-policy checked and original bytes are captured; code requires a declared isolated executor, never host subprocess execution. v1 accepts explicitly offline providers and refuses live execution until pricing is qualified. Memory/procedures require a pinned curator-verified catalog. The actual SpecialistHarness factory hook is tested on main and helper agents, including one captured memory effect reused across both.

`recovery.py` exposes `load_specialist_recovery`, `RecoveryContext` and `ResumeDelegationBudget`. Other domains can use these interfaces without duplicating a scheduler, writer, journal, source capture runtime or shell.

Exact existing-file integration hunks:

- `agents.py`: additive optional extra-capability/collecting-context/source-verifier inputs; root step-store retention; query/result attempt tracking; geography-v9 progress/hierarchy tools and review validation; default geography recovery plus usage/helper preservation; retry conversation identity. Other role policies are unchanged.
- `sources.py`: GEOLocate optional all-or-none worker placement parsing; model placement refusal; immutable-reading/captured-hierarchy grounding; optional host collecting context; coordinate-free match/ambiguity handling.
- `source_capture_v2.py`: only optional collecting-context forwarding to the existing SourceBroker.
- `evidence.py` and `accepted_output.py`: geography nonsettling-context selection and v4 boundary pin/older identity compatibility.
- `prompts/__init__.py`, new geography v9 file and `committed_pins.py`: active geography prompt and explicit geography-only deterministic tool roster/version pin.
- Tests: existing GEOLocate numeric verdict fixtures explicitly identify their host-only synthetic entry; model capture fixtures are coordinate-free. Frozen v8 feedback tests remain pinned to their original contract. Composed offline fixture queries now omit placement.

No engine, scheduler, writer, journal, source capture semantics, CI or release workflow was redesigned.

## Verification and evidence scope

The declared lane environment was built from the frozen lock, using cached packages. Package qualification confirms AI/evals/graph 2.51.0, harness 0.36.0 and Logfire 5.0.0. Pinned package source and its official v0.36.0 exports were inspected. BrowserUse requires the absent optional browser-use dependency; CodeMode requires the absent optional Monty runtime. The adapters above are explicit application integrations, not a claim that those optional packages are running.

Focused verification commands, run with `.venv/bin/python -m pytest -q`:

```
tests/research_harness/test_geography_context.py
tests/research_harness/test_geography_strategy.py
tests/research_harness/test_geolocate_placement_provenance.py
tests/research_harness/test_geolocate_capture.py
tests/research_harness/test_geolocate_validator.py
tests/research_harness/test_geolocate_record_fields.py
tests/research_harness/test_geography_prompt_v2.py
tests/research_harness/test_geography_prompt_v6.py
tests/research_harness/test_geography_prompt_v7.py
tests/research_harness/test_geography_prompt_v8.py
tests/research_harness/test_source_history_feedback.py
tests/research_harness/test_shared_capabilities.py
tests/research_harness/test_specialist_recovery.py
tests/research_harness/test_source_capture_v2.py
tests/research_harness/test_unqualified_label_policy.py
tests/research_harness/test_taxon_input_reconciliation.py
tests/test_research_harness_agents.py
tests/test_historical_gazetteers.py
```

Publication verification uses `tests/research_harness/test_geography_hierarchy_publication.py` and `tests/research_harness/test_production_e2e.py::test_the_run_reaches_its_final_queue`. These exercise the production composer, captured source effects, native step/acceptance journal and automatic canonical writer against a scripted FunctionModel and the existing in-memory connector. Recorded NGA and GEOLocate bytes are served by offline source providers; network HTTP is refused. They are composed offline evidence, not authenticated or live production evidence.

The focused final counts and local commit are recorded in the session closeout. `git diff --check` and Python compile checks passed. Canonical `scripts/ci/verify.sh`, push, PR, CI, live canary and production release are Not confirmed and remain with Lane P.

## Remaining integration prerequisites

- Production composer must supply/pin qualified browser and isolated executor providers, live pricing, a verified catalog loader and admission for durable knowledge contributions. The current composer does not forward the optional extra-capability factory; live shared adapters fail closed.
- `accepted_collecting_context` provides an explicit host interface over actual accepted checkpoint proofs and exact dependency pins, and tests reject stale/forged/date-range context. Production initial requests still do not populate those cross-domain dependencies; the host must load the proofs and provide the same verified context to the harness and source broker.
- Generic TGN/Wikidata admin-level mappings and non-USA county contracts need reviewed source/type rules. No county inference was added outside the USA.
- Recovery intentionally refuses active/unrecorded process crashes and unresolved effects until ownership/effect reconciliation. The common engine's whole-output rejection and sibling salvage were not redesigned by this lane.

Dosu: no knowledge MCP tools were listed. CLI v0.66.1 showed expired authentication; deployment inspection could not save refreshed credentials under the restricted config. The coordinator had already reported monthly credit exhaustion. No knowledge query retry, billing/auth mutation, knowledge write or receipt finalization occurred.
