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
  operational state. The queue row, the status strip and the history view's
  version line use one mapping, so they cannot disagree.
- A disposition that is present decides: an unrecognised one is "State
  unknown", never hidden behind the run state. An absent or unrecognised
  value is "State unknown", and a field state (`unknown`, `supported`, ...) is
  never drawn as a record's state.
- The strip shows the live state, so a change the poll brings (processing to
  blocked, paused or cancelled) is announced once, in the chip's words; a
  decision is still announced as "Saved" (CLAUDE.md, 02 section 4.16).

### T1.2 Every operational state has its own word

PRD 10.1 names the operational states: "Any processing stage may enter
`Retry scheduled`, `Paused`, `Cancelled`, or `Processing blocked`. Those are
operational states, not final data-quality queues." `CONTRACTS.md` 209-210
lists the same run statuses. The client drew the first three as "State
unknown".

| Wire value | Chip word (PRD 10.1) | Colour triple | Glyph (registry entry) |
|---|---|---|---|
| `retry_scheduled` | Retry scheduled | `state.blocked` | `UiIcons.time`, "Waiting time and timestamps" |
| `paused` | Paused | `state.blocked` | `UiIcons.blocked`, shared with Processing blocked |
| `cancelled` | Cancelled | `state.blocked` | `UiIcons.stop`, the "Cancel processing" action's glyph |

No new colour or glyph is introduced. The three stopped states use the one
operational triple the design system defines (03 section 3.4, `state.blocked`:
"Operational, not evidentiary"), because PRD QUE-005 makes them operational
blocks and never a queue, and 02 section 2.4 gives operational state one colour
role. Retry scheduled draws the registry's waiting glyph. Paused shares the
glyph and the colours of Processing blocked, because in both processing has
stopped until someone acts; the word tells them apart. Cancelled draws the
glyph of the action that caused it. 03 section 3.5 and 09 section 7 carry the
three rows. A screen reader hears each as the run's state ("Run: paused"),
never as a queue, and so are Processing and Processing blocked.

Decided 2026-09-23: the coordinator confirmed this mapping under G5 (message
to S6, 2026-09-23). The confirmation covers exactly the three PRD 10.1 words,
the `state.blocked` colours and the clock, prohibit and stop circle glyphs, and
extends to the G13 waiting state (`pending`) when S3 names it, with existing
tokens only.

`completed` is deliberately not a chip. The backend sends it only together
with a disposition (`api.py` `summary()`, `production.py` `_commit`,
`search.py`), and the chip shows the disposition, which is the queue. A
completed run with no disposition has no queue, so its chip stays "State
unknown", which is the truth about it. This departs on purpose from the
wording of brief T1's last bullet, which lists `completed` among the states
drawn as "State unknown".

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
  for Label K". It still blocks clearance (CONTRACTS.md 239-240: completed
  adjudication), with the same instruction to resolve it.
- Distinct means exactly distinct, as the server counts it: readings that
  differ only in case or spacing differ. A transcription without a list of
  alternatives is judged by its region's own readings.
- The Readings segment draws one row per region, older records' difference
  rows included, by the same rule: resolved, the readings differ, or
  unresolved. A resolved region whose readings differed keeps them in view.

### T1.4 Each reason blocks clearance once

The workspace response publishes each run reason twice: in `reason_codes` and
as a `validations` entry whose `reason_code` is the same string (`api.py`
`workspace()`). The blockers list counted both. A reason code already stated by
a validation finding is not listed again.
