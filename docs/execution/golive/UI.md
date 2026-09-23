# Go-live UI workstream (S6): spec deltas

Owner: the session "Build the record thread UI". Scope: `apps/specimen_digitization/`.
Authority: `docs/execution/golive/PLAN.md` sections 2.1 (G1 to G12), 3 (the client
row) and 4.7, and the workstream brief `briefs/S6-record-thread-ui.md`. Nothing
here adds product behaviour (G5); each delta implements a specification that
already exists, and names it.

## T1. Client defects

Every defect below is visible on the ten pilot records today (PLAN section 3,
"Client"). Each fix reads data the backend already sends; no backend change.

### T1.1 The record status comes from the field the backend sends

The summary and workspace responses carry the run's operational state as
`status` (`api.py` `summary()`), one of `running`, `processing_blocked`,
`retry_scheduled`, `paused`, `cancelled` and `completed`, and the queue as
`disposition`. The status strip read `operational_state`, which no response
carries, so every record without a disposition, all ten pilot records
included, said "State unknown".

- A record's chip is its disposition when it has one, otherwise its
  operational state. Both the queue row and the status strip use one mapping,
  so they cannot disagree.
- An absent or unrecognised value is still "State unknown", and a field state
  (`unknown`, `supported`, ...) is never drawn as a record's state.

### T1.2 Every operational state has its own word

PRD 10.1 names the operational states: "Any processing stage may enter
`Retry scheduled`, `Paused`, `Cancelled`, or `Processing blocked`. Those are
operational states, not final data-quality queues." `CONTRACTS.md` 209-210
lists the same run statuses. The client drew the first three as "State
unknown".

| Wire value | Chip word (PRD 10.1) | Colour triple | Glyph (registry meaning) |
|---|---|---|---|
| `retry_scheduled` | Retry scheduled | `state.blocked` | `UiIcons.time`, "Waiting time and timestamps" |
| `paused` | Paused | `state.blocked` | `UiIcons.blocked`, "Processing blocked" |
| `cancelled` | Cancelled | `state.blocked` | `UiIcons.stop`, "Cancel processing" |

No new colour or glyph is introduced. The three stopped states use the one
operational triple the design system defines (03 section 3.4, `state.blocked`:
"Operational, not evidentiary"), because PRD QUE-005 makes them operational
blocks and never a queue, and 02 section 2.4 gives operational state one colour
role. Each draws an existing registry glyph whose documented meaning matches.

`completed` is deliberately not a chip. The backend sends it only together
with a disposition (`api.py` `summary()`, `production.py` `_commit`,
`search.py`), and the chip shows the disposition, which is the queue. A
completed run with no disposition has no queue, so its chip stays "State
unknown", which is the truth about it.

### T1.3 Readings are said to differ only when they differ

`Transcript.alternatives` is the set of distinct reading texts for a region
(`workflow.py` adjudicate step, `evidence_pilot.py` pilot review). The client
treated every unresolved transcription as a disagreement, and the pilot leaves
every transcription unresolved, so identical readings were labelled as
differing, twice (a synthesised disagreement row and a transcription row).

- "N readings differ for Label K" appears only when a region's transcription
  is unresolved and carries two or more distinct alternatives (02 section 2.3,
  data ambiguity pattern).
- An unresolved region whose readings agree says "Transcription not resolved
  for Label K". It still blocks clearance (PRD QUE-002: completed
  adjudication), with the same instruction to resolve it.
- The Readings segment draws one row per region: resolved, the readings
  differ, or unresolved.

### T1.4 Each reason blocks clearance once

The workspace response publishes each run reason twice: in `reason_codes` and
as a `validations` entry whose `reason_code` is the same string (`api.py`
`workspace()`). The blockers list counted both. A reason code already stated by
a validation finding is not listed again.
