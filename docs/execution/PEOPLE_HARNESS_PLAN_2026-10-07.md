# People harness implementation plan

Task: People harness; branch `codex/harness-parties`; worktree
`/Users/anuragduddu/.codex/worktrees/0ff0/specimen-digitization-app`.
Local and remote `main` were verified at `7890de551c75fe3b06836c7fb224f85dd2a2423a`.

1. Qualify collector evidence against its exact retained reading and line. Reject
   explicit determiner, preparer and locality roles, incomplete lists and initials
   that do not name a person. Keep all raw alternatives and original spelling.
2. Recover omitted explicit collector lines using exact observation/span lineage,
   a decided reading or agreeing retained readers, and existing native literal
   evidence. Recovery cannot invent an evidence row or an identity.
3. Verify normal, ambiguous, absent, wrong-role, invalid and resumed outcomes with
   focused offline tests, including native automatic publication where supported.
4. Preserve `identified_by_irn` as null Unknown under G43/G16 until qualified
   read-only eparties identity and the correct specimen determination row exist.
   Record authority and shared browser/code/memory/recovery prerequisites.

Geography owns shared capability adapters. This lane changes only people policy,
helpers, the people prompt, narrow graph/validator integration and required pin
bookkeeping. It does not release, push, run the canonical suite or change holds.
Dosu CLI v0.66.1 reported expired authentication and could not persist refreshed
credentials in the sandbox. No server knowledge tools are listed. The coordinator
also reported monthly credit exhaustion; no query or billing change was retried.

## Implemented domain slice

`research_harness/people.py` provides exact role/span checks, omitted explicit
collector recovery, preserved multiple-person spelling, and collector settlement.
The graph factory uses it after the organiser pass; the application validator
also applies it, so a falsely accepted collecting event cannot bypass the checks.
The existing scoped `invoke_utility` now admits `settle_collectors` for parties
only, with `field_key=collectors` and an existing accepted `event_id`. Local
publication replay recomputes the exact result. No external effect receipt is
invented for this pure utility.

| Evidence condition | Collector outcome / stop rule |
| --- | --- |
| Qualified exact collecting assembly, full list | Supported spelling with native quote and observation/span/event lineage; automatic native publication |
| Explicit omitted collector line, decided reading or unanimous readers, existing covering native quote | One recovered accepted assembly; original alternatives remain retained |
| Determiner, preparer or locality assigned as collector | Located or rejected; no collector clearance |
| Different readings, initials-only, missing quote or role | Located alternatives; structured missing-policy Needs Human work |
| Incomplete list or explicit next-line continuation | No partial collector settlement; qualified relation needed |
| No admitted eparties identity / determination row | Null Unknown IRN, unchanged nonblocking owner exception |
| Interrupted known-complete checkpoint | Resume publication without repeating people model or Save |
| Unknown external send | Existing durable hold remains; never reissue or clear it |

The parties v6 prompt replaces only the active people prompt; old bytes remain.
Validator v4 preserves historical v1-v3 proof pairs and revalidates under current
semantics. Its source hash also binds the imported people policy bytes. The
integrator must recompute this hash after composing other lanes' evidence.py
hunks; it cannot copy this lane's final hash onto a combined validator.

## Shared integration and authority requirements

This is independently tested domain work, not a claim of six connected full
browser/terminal agents. Geography retains ownership of additive shared adapters.

- Browser capture must expose admitted supporting-source reads with exact
  source/version/query/observation/effect lineage. Public biographies may support
  research context; they cannot identify eparties rows or decide a person IRN.
- Isolated code must operate on captured inputs through the same scoped effect
  broker, without production credentials or a second canonical writer.
- Shared Memory and Skills can load
  `research_harness/skills/people-label-research/SKILL.md`. Memory needs an
  organization/collection/people procedural namespace, verified reusable entries
  and capture/replay. It supplies procedures, not identity evidence or retraining.
- The qualified Python environment is AI 2.51.0 / Harness 0.36.0. Memory, Skills
  and Shell signatures were inspected in that installed source. BrowserUse and
  CodeMode are exported but optional `browser_use` and `pydantic_monty` dependencies
  are absent. This lane did not install extras or connect unrestricted tools.
- Recovering an omitted name without any native covering quote still needs a
  shared immutable evidence-capture operation bound to the original observation
  and asset. This lane emits a located lead and never fabricates a native row.
- Multiline names and separate collector lists need explicit qualified
  continuation/event relationships. Proximity and surname similarity do not
  provide those relationships.
- eparties needs admitted read-only authority, exact specimen determination row
  and explicit determiner relationship. IPT joins and EMu qualification remain
  unconnected; no IRN-producing adapter was added.
- The shared engine still does not restore agent message history or salvage a
  newly valid sibling after two invalid final outputs. This lane tests successful
  correction retaining valid collector evidence, and preservation of an already
  accepted collector when a pending IRN sibling fails. It does not claim the
  broader new-sibling salvage gap is fixed.

## Integration hunks

Additive people module, people procedure and v6 prompt are this lane's files.
Shared files contain only these bounded hooks: `initial_requests._build_graph`
recovery and `_organiser_candidate` / `_validator_refuses` people qualification;
`evidence.validate_resolution` collector guard and helper source hash;
`sources.local_settlement_result` / `SourceBroker.invoke_utility` parties utility;
`local_utility_proof_v2` roster and exact replay dispatch; `agents.utility_model_view`
compact view; parties prompt mapping; accepted-output v4/hash/history qualification.
No engine, writer, journal, scheduler, contract or source-capture redesign.

Reviewable commit and final focused validation are recorded in the append-only
session log. No push, PR, canonical full verify, paid canary, deployment or live
native/EMu acceptance occurred in this lane.
