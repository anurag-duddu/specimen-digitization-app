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
- The thread API, S5's #171 at `a73b323`, adds to section 8, and the model
  reads each part:
  - a region's `reviewer_decision` (its decided text, whether it left the
    region unresolved, its rationale), beside the model's own first pass,
    which a later layer never erases (G38);
  - a field's `layer` (verbatim, settled or derived; unknown keeps the
    server's word), `derived_from`, `authority_identity` (name, source,
    record id, credit; a Google value has no name, G26) and its own
    `findings`, such as G45's value-shape check;
  - the `review` input source, with a call's `review_decision_id`; where a
    source is named, its words are "reviewer's text", the contract's own;
  - an evidence entry's `observation_ids`, the readings it quotes;
  - a Google call's result as `place_ids` only (G26).
  S5's `thread-example.json` from #171 is now the canonical fixture
  (`test/fixtures/thread-example.json`, byte for byte), so the client and
  the server test one file. The synthetic two-label fixture stays for the
  screen tests that change its values.

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
5. A reviewer's decision (#171's `reviewer_decision`), after "Handed to the
   harness", in the order the thread ran. It reads "Decided by a reviewer",
   then "Transcription not resolved" when the reviewer left the region
   unresolved, then the transcript the reviewer decided on and the
   reviewer's reason, all as one announcement. The model's first pass stays
   above it: a later layer never erases an earlier one (G38). When a
   reviewer decided a region the model did not, the reviewer's decision
   stands alone. "No decision recorded" is for a region with neither.

The declarations and the "Differences and resolution" list stay below the
sections. Where the thread gives a region's comparison, that region's row
no longer repeats the ratio, so the score appears once.

### T2.3 Fields: required and optional

The Fields segment lists the required fields under "Required fields" and
the rest under "Optional fields" (PLAN 4.7: the thread shows "mandatory and
optional fields"; G16: `identified_by_irn` is optional).

- The groups follow the record's own `required` flag, the one each row's
  "(required)" marker already reads, so a heading and its rows never
  disagree, and the groups are there before the thread is. A field the
  run's profile does not classify counts as required, as its marker does.
- Within a group the fields keep the record's order. A group with no fields
  is left out, and a record with no fields keeps its one caveat.
- A group heading has the weight and treatment of a Readings region
  heading, from one shared `GroupHeading`: a label, not a title, set without
  leading, whose node is the size of its words.

Part two adds, from the thread, what was written, by whom, and what settled
it. It applies only while the record's field stands exactly as the run left
it: no pending correction, and the same state, text, reading, standardized
value and authority record. A saved correction changes one of them, and the
row then shows the record alone, so the run's account never sits beside a
value it does not describe.

1. Each reader's text. When the first pass chose no reading, the thread
   gives one text per reader (G27, G28), and the "As written" layer lists
   each under its reader: "<reader> · raw reading". A single text the
   harness took from one reader's raw reading (G20) names that reader the
   same way. The decided transcript's text names no reader, because the
   Readings segment shows how the transcript was decided.
2. Each source's relation to the value (G23): "GBIF decides this value",
   "Global Names Verifier supports this value", "Catalogue of Life
   contradicts this value", followed by the source's locator. A Google
   record is named only by its place ID (G26): "Google Maps supports this
   value · place ID …". These lines take the place of the single authority
   line. The thread lists only linked evidence, so a lookup that failed or
   was retried appears in the lookups timeline, not here.
3. A century a rule set (G24; the coordinator's wording, 2026-09-23): one
   line under "Read as", "Century from the profile's rule: 1900s". A
   four-digit year, or a field that is not a date, has none. The precision
   needs no line, because the parsed form shows it.

The sources go by the names the services use, from the ids the thread
carries (S5, 2026-09-23): `google-maps-geocoding` is Google Maps, `gbif` is
GBIF, `gnv` is Global Names Verifier, `col` is Catalogue of Life, and
`label-coverage-check` is the label coverage check. An id the client does
not know shows in the server's own word. Corrections are unchanged: every
layer, the text and the standardized value alike, opens the same editor
(G27: corrections on both).

Part three marks which readings settled the value. The owner's G32: a
field found on two labels is settled per label on its own evidence and
clears when every label settles to the same value; otherwise it goes to
review with each label's reading kept, and every verbatim stays as written
(G27). The thread gives `settled_observation_ids` and one verbatim entry
per label's source reading (#88 at `4f9997a`).

1. When a field's texts come from more than one label, each entry names
   its label first: "Label 2 · <reader> · decided transcript". In a
   per-label map a decided-transcript entry names its label's selected
   reading (S5, 2026-09-24); a single decided transcript still names no
   reader.
2. An entry whose reading is in `settled_observation_ids` ends "· settled
   the value". A field that went to review settled nothing, so no entry is
   marked, and each label's reading stays in view.
3. A single decided transcript whose value a fallback lookup settled from
   another reader's raw reading (G20) says so under the text: "<reader> ·
   raw reading · settled the value".

The guard of part two is unchanged. A field with a verbatim map has no
record literal, so it matches the record on the settled value (S5 and S4,
2026-09-24).

### T2.4 The coverage check and the decision's findings

The thread explains what the record states; it never adds a blocker the
record does not have. A reviewer can confirm label coverage after the run,
so the thread's failed check is shown only while the record still carries
the check's reason, `label_coverage_unconfirmed` (G15: show the reason and
the evidence with the queue decision; the coordinator placed it in the
status strip's blockers).

- A failed coverage check is one entry in the blockers list, "Label
  coverage not confirmed". Its detail says what each failed check measured,
  from the detail S5 pins for the thread (#88 section 8 at `4f9997a`,
  re-confirmed by S6 on #88):
  - the region count: "Found 3 label regions; the profile allows 1 to 2",
    "Found no label regions", or "A label region lies outside the
    photograph";
  - the full-image cross-check: "1 of 4 label-like detections lies outside
    the label regions".
  A range the check does not record is not guessed ("Found 3 label
  regions"), and a check this client does not know is named ("Failed: …").
  The entry takes the place of the workspace's generic finding and reason
  code for the check, so the check is stated once, and "Go to" opens
  Readings, beside the label regions the check judged. Without the thread,
  the reason reads "Label coverage not confirmed" too.
- The decision's warning and info findings attach to their fields, "Worth
  checking" and "For information", in the caution and secondary tones
  rather than the error role, because they never change the disposition.
  They follow the Fields segment's rule: shown while the field stands as
  the run left it. Hard findings keep coming from the workspace, in the
  blockers list and on their fields, so none is stated twice.

### T2.5 Processing: the run and its trace

The Processing disclosure, in the Fields segment at every width (13
section 3.2), adds from the thread where the record's run came from. The
coordinator placed the run, the version and "Open trace" here under G5,
and brief T2 asks for "a link built from the Logfire project configuration
and the trace id".

- The run, the profile with its version, and the policy the queue decided
  under, as labelled values: "Run", "Profile" and "Policy".
- The trace: its id, with a control that copies it, and "Open trace", a
  link to the run's trace in Logfire. The thread gives the address, and the
  client keeps it only when it is an absolute https URL (T2.1). A trace id
  without an address is still named, and a run with neither says "No trace
  recorded".
- A run blocked because the program's model allowance is spent
  (`program_allowance_exhausted`, G30) says so in plain words, with the
  amount when the thread records it: "The USD 5.00 model allowance for this
  program is spent. Processing resumes when the owner raises it." Without
  the thread the sentence names no amount. Cost appears nowhere else (the
  coordinator, 2026-09-23).

"Open trace" is `url_launcher`'s `Link`. The coordinator approved the
dependency for it on 2026-09-23 (22:07 UTC, in the message confirming the
four placements: "Adding `url_launcher` as a dependency for the real 'Open
trace' link is fine"). On the web it is a real link that opens in a new
tab, and elsewhere it opens the system browser.

## T3 Queue and processing

Brief T3. The coordinator ruled on two T3 questions on 2026-09-24, and a
later part of T3 builds both. The reasons to filter the review queue by
come from the collection configuration's `reason_codes`, which S3 publishes
from S4's policy. Today's status chips stay, and the filter sheet picks any
one run state.

### T3.1 A Sensitive upload is not processed

PLAN section 2.2: an upload declared Sensitive, the intake default, is never
processed by the lane's worker, whose membership cannot see sensitive data,
and a Sensitive upload is never reclassified (`CONTRACTS.md` 137, 161). The
app says so where an upload's sensitivity is chosen and on the record (brief
T3; the coordinator's correction of 2026-09-23: it is not processed, never
"waiting").

- Where sensitivity is chosen, the options keep their names, "Sensitive"
  and "Not sensitive", and Sensitive stays preselected. Named by their
  consequence ("Sensitive: not processed"), they no longer fit the
  control's track in the capture card's column: the control fell to its
  icon-only rung, and the regenerated goldens showed two padlocks with no
  words. So the consequence is the line directly under the control, where
  the operator reads it with the choice (`design/01` H2.6's aim: an
  operator no longer guesses).
- That line says what the choice does before anything is sent (`design/03`
  section 1.7), in the coordinator's words: "Applies to photographs you add
  next. Sensitive photographs are not processed." It stays that short so
  the capture card keeps its place above the fold on a phone at 200 percent
  text (13 section 2.5); a longer first draft pushed it 1 dp below.
- The caveat beside the upload action keeps "Sensitivity cannot be changed
  after an upload starts", and its "Why" ends with the way round it, in
  neutral words (`design/02` section 1.8): "To have a sensitive photograph
  processed, upload it again as not sensitive."
- On the record, a run the lane stops with `sensitive_record_not_processed`
  (S3's blocker, status `processing_blocked`) reads "Blocked: sensitive
  record not processed" wherever a blocker is named. The Processing
  disclosure explains it: "This record was uploaded as sensitive, so it is
  not processed. To have it processed, upload the photograph again as not
  sensitive."

### T3.2 The review queue's reasons in words

The lane policy's reason codes read as words that pass `design/02`
wherever a reason is shown: the queue's rows, the blockers list, and the
filter sheet's "Issue" picker. The picker fills from the collection
configuration's `reason_codes` once S3 publishes it (the coordinator's
ruling of 2026-09-24). The codes are S3's list of 2026-09-24, generated
from S4's `policy.py`:

| Code | Reads |
| --- | --- |
| `institutional_policy_unapproved` | Institutional policy not approved |
| `mandatory_semantics_unconfirmed` | Required field meanings not confirmed |
| `label_coverage_unconfirmed` | Label coverage not confirmed |
| `independent_observations_missing` | Two independent readings needed |
| `raw_provenance_missing` | Raw reading not stored |
| `unresolved_transcription` | Transcription not resolved |
| `evidence_lineage_invalid` | Evidence not traced to a label region |
| `mandatory_unresolved` | Required field has no supported value |
| `evidence_missing` | Required field cites no evidence |
| `evidence_does_not_support_value` | Evidence does not contain the value |
| `pixel_lineage_missing` | Evidence not from a label region |
| `unsupported_parsed` | Read as not supported by evidence |
| `unsupported_normalized` | Standardized value not supported by evidence |
| `unsupported_authority_id` | Authority match not supported by evidence |
| `elevation_range` | Elevation range reversed |
| `elevation_invalid` | Elevation is not a number |
| `elevation_units_conflict` | Meters and feet disagree |
| `date_order` | Dates out of order |
| `date_precision_requires_review` | Date is not a full calendar date |
| `identifier_format` | Catalog number format not recognized |
| `human_approval_required` | Reviewer approval needed |
| `taxonomy_lookup_missing` | No taxonomy lookup ran |
| `taxonomy_unresolved` | Taxonomy not resolved to one accepted name |

- The words use the product's own terms: "required", not "mandatory", and
  "Read as", "Standardized" and "Authority match" for the three layers.
- A code stored with a suffix reads as its words and the field or unit it
  names: `mandatory_unresolved:country` reads "Required field has no
  supported value: country". A suffix that is an identifier, a region's or
  a piece of evidence's, is left out, because it means nothing to a
  reviewer and the record shows where the problem is.
- A code this client does not know still reads as its own words.
- Until S5's T5 search lands, the search API matches a code exactly, so a
  picked code finds only the records whose code is stored without a suffix
  (S5, 2026-09-24). The "Issue" picker therefore offers only the codes
  stored without one: the institutional policy, required field meanings,
  label coverage, the two date codes, the catalog number, reviewer approval
  and the two taxonomy codes. The fourteen codes stored with a suffix, from
  `independent_observations_missing` to `elevation_units_conflict` (S3,
  2026-09-24), come back when T5 lands. A filter that silently returns
  nothing is worse than a shorter list (the coordinator's ruling (b),
  2026-09-24).

### T3.3 Run states in the filter sheet

Today's status chips stay: All, Needs review, Cleared, Deferred, Blocked
and Processing. Each row already shows its record's state (T1.2). The
filter sheet's new "Run state" picker chooses any one state the search
API filters, in the rows' words: Processing, Completed, Processing
blocked, Retry scheduled, Paused and Cancelled (the coordinator's ruling
(c), 2026-09-24). The rows' chips say "Processing blocked", where the
segment chip, with less room, says "Blocked". Waiting (`pending`, G13) joins once #85 adds it to the
search API, so the picker never offers a value the server refuses.

- The Blocked and Processing chips choose a run state too, so whichever
  was chosen last wins. Applying a state from the sheet returns a state
  chip to All, and tapping Blocked or Processing clears the sheet's state.
  A queue chip (Needs review, Cleared, Deferred) combines with the sheet's
  state, as the API intends.
- An active filter's chip names its value in words: "Run state: Retry
  scheduled", "Issue: Reviewer approval needed". It no longer shows the
  wire value (`retry_scheduled`, `human_approval_required`). An
  identifier, a date or a number stays as typed.

## T4 Region boxes on the lane's records

Brief T4. The client draws label regions only over a verified oriented
view (`SourceOrientationCaveat.unverified` in `source_pane.dart`). The
backend strips that view for the evidence pilot (`api.py` 369-370,
1686-1689 and 1705-1706).

S3 confirmed on 2026-09-23 that a lane run never carries `evidence_pilot`,
intake keeps the oriented view (`view_derivative`) with its checksums, and
SAM 3 keeps the original's pixel edges. So a lane record's view verifies
and its boxes are drawn with no change to the gate, while the pilot's
frozen originals keep the caveat. T4 is therefore a client test, not a
gate change:

- A lane-shaped record's view verifies through the repository (its
  checksums match), and the gate allows its label regions.
- A pilot-shaped record, whose view the server strips, keeps "This
  photograph has no verified orientation, so label regions are not drawn."
