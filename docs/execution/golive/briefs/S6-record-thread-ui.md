# S6 brief: record thread UI

Session title: **Build the record thread UI**. Recommended model Opus 5.5 at
high effort.

## Mission

The live web app shows each specimen's whole processing thread (PLAN section
4.7), the queue and live processing status, at the bar the design documents set.

## Read first

1. `CLAUDE.md` front-end rules; they are mandatory.
2. `apps/specimen_digitization/design/00-north-star.md`, then the documents your
   change touches: `02-ux-writing-guidelines.md` (every string passes its
   checklist), `03` tokens, `07-screen-blueprints.md`, `13-screen-composition.md`.
3. `docs/execution/golive/PLAN.md`, `~/specimen-golive/research/05-flutter-client.md`
   (all) and `03-data-model-and-persistence.md` section 4.

## Pull requests, in order

**T1. Client defects (small and visible).**
- The status strip reads `operational_state`, which the backend never sends; the
  summary uses `status` (`status_strip.dart` 141-143; `api.py` 293-315). Every
  record without a disposition shows "State unknown".
- Identical readings are labelled as differing, and reason codes are counted
  twice as blockers (`api_repository.dart` 945-951; `blockers.dart` 55-97;
  `readings_panel.dart` 340-358).
- The 20-second poll re-downloads the full original image; cache it by its
  SHA-256 (`workspace.dart` 285-294; `api_repository.dart` 857-871).
- Free-text queue search is sent as `specimen_id` and returns 422 for anything
  that is not a UUID (`workspace.dart` 251; `search.py` 72-77).
- The completed, retry-scheduled, paused and cancelled states render as
  "State unknown" (`specimen_status.dart` 133-157).

**T2. The thread view.** Build against the thread API contract from the data
workstream (S5), with a fixture until the endpoint lands: regions with the
readings grouped under each region (several per specimen: five pilot slides
carry two labels); each reader's identity (route, model,
provider, prompt version); the disagreement score labelled uncalibrated; the
first pass's decision and what each reader handed to the harness; the harness's
lookups as a timeline with their typed outcomes (a geography lookup shows the
place ID and its outcome only, G26); fields grouped mandatory and
optional with state and evidence, a place or taxon field showing its verbatim
text and its settled final value, each labelled, with each reader's reading
attributed when the first pass picked none (G27, G28), and a date the harness
could not settle showing its candidate readings (G29); the queue decision with its reasons,
including a failed automatic coverage check (G15); and
"Open trace", a link built from the Logfire project configuration and the trace
id. Use `specimen_ui` components; there is no timeline component yet, so add one
to the package with its own tests.

**G38 (owner decision, 2026-09-24; coordinator reading).** The thread marks
each value's layer, verbatim,
settled or derived, with a derived value's evidence one step away. In review,
after a reviewer fills a field, "Fill the rest" derives the remaining fields
through S5's route; the filled values show as derived and stay editable before
approval, and the result is announced once. The action enqueues a job and
shows its progress; the server refuses it for a Sensitive record (PLAN section
4.8). Coordinator rulings, 2026-09-24: the new run states are picked in the
filter sheet, with no new status chips; the trace link opens through
`url_launcher`, flutter.dev's first-party plugin (#122).

**T3. Queue and processing.** Needs human review (filterable by reason; until
S5's T5, only the codes stored without a suffix, coordinator ruling),
deferred, cleared, processing and blocked; a record declared Sensitive shows
that it is not processed, because automated reading never runs on sensitive
records, and the upload screen says so before submission, with the Sensitive
default left preselected (`design/03` §1.7, `design/01` H2.6, in `design/02`
§1.8's neutral wording; PLAN section 2.2); a Process action
(`POST /specimens/{id}/process`); intake that starts processing and shows live
status; upload rows linked to the specimen they created (`api.py` 1283 already
returns `specimen_id`).

**T4. Region boxes on the pilot originals.** The client hides them unless the
preview is a verified derivative (`source_pane.dart` 800-801), and the backend
strips the derivative for the pilot (`api.py` 369-370, 1704-1706). Agree with S3
and S5 how the backend proves orientation or serves an oriented view, then
relax the gate.

## Rules

- A widget test for every new component and a golden or size-class test for
  every new screen layout.
- You are the only session that regenerates goldens; parallel regenerations
  silently revert each other.
- 48 dp targets, semantic labels, visible focus, announcements once; honour
  `MediaQuery.disableAnimationsOf`; colours, type and spacing from theme tokens.
- `flutter analyze --fatal-infos` clean and `flutter test` green before a push;
  copy `firebase_options.ci.dart` to `lib/firebase_options.dart` for builds and
  remove it afterwards; never commit it.
- Hot reload through the Dart MCP server when an app instance is running.
- Where the specification or the design documents are silent or contradictory,
  stop and ask the coordinator; do not decide (G5).

## Done

For a processed specimen, the live app shows its whole thread, its queue
placement and a working trace link; the queue and intake reflect processing live.
