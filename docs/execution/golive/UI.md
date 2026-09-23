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
- The repository's synthesised `disagreements` list holds only the regions
  whose readings differ and are unresolved, so the key means what it says.

### T1.4 Each reason blocks clearance once

The workspace response publishes each run reason twice: in `reason_codes` and
as a `validations` entry whose `reason_code` is the same string (`api.py`
`workspace()`). The blockers list counted both. A reason code already stated by
a validation finding is not listed again.

### T1.5 The photograph is fetched once per checksum

The queue's 20 second poll reloads the open record, and each reload downloaded
the whole original again (up to 25 MB). The repository keeps the bytes of the
last few images it fetched, keyed by collection, asset id, the original's
SHA-256 and, for a view derivative, the derivative's SHA-256. A reload whose
asset has the same identity reuses the bytes without a request. The cache
belongs to one verified session: a new access check or another account starts
it empty. Reusing the same bytes also keeps the decoded image, so the
photograph no longer re-decodes every 20 seconds.

### T1.6 Queue search sends only an identifier the API can match

The search field is "Specimen ID, exact match" (07 section 3, controls row).
The API coerces `specimen_id`, `asset_id`, `active_run_id` and `batch_id` to a
UUID and answers anything else with 422 (`search.py` `SearchFilters.bounds`),
so a partial ID, or any text, showed an error banner while the reviewer typed.
A value that is not a UUID cannot name a record, so the repository answers an
empty page without a request, and the queue shows its existing filtered empty
state ("No records match these filters", with "Clear all"). A UUID is sent in
canonical form, accepting the spellings the API accepts.

## T2. The record's thread

Sources: PLAN 4.7; brief T2; the thread response in
`docs/execution/golive/DATA_CONTRACT.md` section 8 (S5, PR #88); the owner's
decisions G15 (automatic coverage check), G16 (`identified_by_irn` optional),
G19 (the harness runs on each raw reading when the first pass selects none)
and G20 (a lookup-confirmed raw literal keeps `raw_reading` as its source).

### T2.1 One typed thread per run

The client reads the thread response into a typed `SpecimenThread`
(`lib/src/thread/thread.dart`), unlike the workspace's untyped `Specimen`
map, so every part the record screen draws has a type and an absent part is
a null the screen names.

- Parsing is lenient in one direction only: a missing or malformed value is
  absent, and absent never becomes a value. An unmeasured ratio stays null,
  never zero. An unknown decision kind, group or input source stays unknown,
  never a guess. A field with no group is kept apart from both groups rather
  than filed into one.
- The trace link is kept only when it is an absolute `https` URL, because it
  opens in the reviewer's browser.
- A synthetic two-label fixture (`test/fixtures/thread-two-label-slide.json`)
  stands in for the endpoint until S5's T3 serves it, then gives way to S5's
  canonical fixture so the client and the server test one file. The fetch
  itself, and its entry in the wire contract test, arrive with the route: the
  contract test admits a route only with the backend line that declares it.
- The model lands in two parts: the envelope, the regions, the readings and
  their comparison first; the first pass with its handoffs, the harness's
  calls, the fields and the queue decision second.
- A date field carries its precision (day, month or year, as written) and
  the century rule that set a two-digit year (G24) beside its parsed text,
  as S5 pins them for the thread; the stored object form is read too.
- A field keeps what was written as a list, one entry for the decided
  transcript or one per reader when the first pass chose none, each
  attributed (G27, G28), and what was settled: the standardized value and
  the authority record (a Google place ID, never a Google name, G26; GBIF's
  accepted name may be shown, G28). Its evidence names each source's
  relation to the value: decides, supports or contradicts (G23). The
  decision carries its findings, hard, warning or info (#88 at `6b97508`).

### T2.2 Readings: one section per label region

The Readings segment draws one section per label region, in the order the
regions are numbered, so a two-label slide (324 to 328 among the pilot ten)
has two. A reading whose region the record does not list goes into a last
section, "Unassigned label". A region no reader read says so in its section.
Each section, in order:

1. The region's name, "Label K", as a heading at the weight the region's name
   had in each card, so on a phone the first reading stays on the first
   screen under the photograph and the strip (13 sections 0 and 2.5).
2. Its reading cards: model and provider as today, and beneath them the
   route and the prompt version when the reading records them. The card no
   longer repeats the region's name the heading states.

Part two adds, from the thread, to each section:

3. The comparison: "Difference 0.03" beside its components ("1 edit over 33
   characters") and the "Not calibrated" chip, a measured zero as "No edits
   over 23 characters", or "Difference not measured" with the server's reason
   behind "Why" (02 section 4.15; north star: a score is shown beside the
   components that produced it).
4. The decision: "The readings match", "The first pass chose <reader>", "The
   first pass chose no reading", "Decided by a reviewer", or "No decision
   recorded" with where the run stands. A decision the thread marks
   `unresolved` says "Transcription not resolved" under its title
   (DATA_CONTRACT.md section 4.2: no reading selected, a material difference
   still `neither` or `uncertain`, or a reviewer who left it unresolved). The
   workspace's `resolved` flag means only that a reading was selected, so it
   cannot say this, and no title claims a resolution. Then the decided
   transcript, the rationale, the first pass's model and prompt, and "Handed
   to the harness": each reader, whether it handed the decided transcript or
   its own raw reading, and the text it handed.

The declarations and the "Differences and resolution" list stay below the
sections. Where the thread gives a region's comparison, that region's row
no longer repeats the ratio, so the score appears once.
