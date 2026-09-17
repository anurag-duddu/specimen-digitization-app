# North star

## The goal in one sentence

Build the specimen review client that a Field Museum entomologist would choose to
spend four hours a day in: every pixel of evidence one glance away, every decision
recorded with its reason, nothing hidden and nothing invented, on whatever screen
is in their hands.

## The product we are building

Specimen Digitization turns a photograph of a pinned insect and its labels into a
record the museum can trust. Models do the first reading; people make the
decisions. The client exists to make those decisions fast, correct and
accountable.

It runs on Android phones and tablets, iPhones and iPads, and desktop browsers. The
phone is for capture and status. The tablet in landscape and the desktop browser
are the review desk. All three are first class: the same tokens, the same
vocabulary, the same components, adapted to the window rather than rebuilt per
platform.

## What it feels like to use

An operator at a copy stand opens Intake on a tablet, frames a specimen inside the
guides, and sees the shutter confirm. A thumbnail lands in the upload list with a
quiet progress ring. They shoot the next one. When they look up ten minutes later
the list says twelve accepted, one duplicate, none failed, and the phone in their
pocket said nothing because nothing needed them.

A reviewer opens the queue on an iPad. Needs human review is first, sorted by age.
Each row shows the specimen, the reason it is here in plain words, and how long it
has waited. They tap one. The photograph fills the left two thirds of the screen;
the two model readings sit on the right, each character that differs marked with
an underline and a symbol, never color alone. They tap a label region; the image
glides to it and the readings scroll to match. One field is unresolved. They pick
the supported reading, type a reason, and the disposition chip changes from amber
to green with a short settle. The next specimen is one keystroke or one swipe away.

A collection manager on a laptop sees the queue by disposition, the oldest blocked
run, and which stage it is blocked at. Nothing on the screen claims more certainty
than the data has: unmeasured says unmeasured, uncalibrated says uncalibrated, and
a score is always shown beside the components that produced it.

## The bar

"Top one percent" is a measurable standard, not a feeling. The redesign is done
when all of the following are true.

| Dimension | Standard | How we check |
|---|---|---|
| Usability | All ten Nielsen Norman Group heuristics pass the criteria in [01-usability-heuristics-audit.md](01-usability-heuristics-audit.md) with no finding above severity 1 | Heuristic re-audit by someone who did not build it |
| Writing | Every user-facing string passes the checklist in [02-ux-writing-guidelines.md](02-ux-writing-guidelines.md); no string exceeds its length budget; zero em-dashes | Automated string lint plus editorial review |
| Visual system | Zero literal colors, sizes or durations in widgets; light and dark both ship; every text pair meets WCAG 2.2 AA contrast | Grep gate in CI, contrast unit test on the token table |
| Motion | Every animation is in the catalog in [04-motion-and-microinteractions.md](04-motion-and-microinteractions.md) with a one-sentence reason; all collapse correctly under reduced motion | Widget tests with animations disabled |
| Adaptation | Every screen has a verified layout at compact, medium, expanded and large widths, in both orientations, on iOS, Android and web | Golden tests per size class and a device matrix run |
| Accessibility | WCAG 2.2 AA; VoiceOver and TalkBack scripts for the review flow complete without a sighted helper; keyboard-only review on web | Manual scripts in [06-accessibility.md](06-accessibility.md), guideline matchers in tests |
| Honesty | No measurement ever renders as zero when missing; no score without components; no action the server forbids appears enabled | Existing wire tests remain green |
| Speed of review | A reviewer can move from one specimen to the next, including one correction with a reason, without leaving the keyboard on desktop or lifting more than one hand on a tablet | Timed task walkthrough |

## Principles that decide arguments

1. **Evidence before interpretation.** The photograph is the largest thing on the
   review screen. Readings, fields and authority results are arranged around it,
   never instead of it.
2. **Say what we know, exactly.** Unknown, unreadable, not present, unmeasured and
   uncalibrated are first-class states with their own label and icon. We never
   round them to a number or a reassuring color.
3. **One reason per decision.** Anything that changes a record asks for a reason in
   the same surface, shows what will change, and can be cancelled. The reason is
   visible afterwards in history.
4. **Calm by default.** No motion, sound or color that does not carry state. The
   interface is quiet so that a difference between two readings is loud.
5. **The window decides the layout.** Size classes, not device names. A phone in
   landscape and an iPad in split view get the layout their width earns.
6. **Internal words stay internal.** Revision, digest, artifact and lease exist for
   audit. They live in a details layer that is one tap away, not in the first
   sentence a reviewer reads.
7. **Nothing new to learn twice.** One status chip, one reason sheet, one evidence
   disclosure, one diff view, reused everywhere. A reviewer who learns the queue
   already knows the history.

## What changes from today

Today the client is a correct, honest, fully tested vertical slice whose interface
is a stack of Material cards, expansion tiles and long paragraphs. The redesign
keeps every invariant the backend enforces and every honest state the client
already models, and replaces the presentation layer.

- The theme becomes a token system with light and dark modes and a product
  `ThemeExtension` (see [03-design-system.md](03-design-system.md)).
- Every string is rewritten to the writing guidelines; caveats become a short
  label plus a "Why" disclosure.
- Raw JSON leaves the primary interface. Evidence is rendered as typed components
  (reading cards, diff text, field rows with literal, parsed and normalized
  layers, authority candidate cards) with an `EvidenceDrawer` escape hatch for the raw JSON.
- The queue becomes list-detail on medium and wider windows; the workbench gets a
  stable image pane, a sticky action bar and a supporting pane for history.
- Dialogs become bottom sheets on compact windows and constrained dialogs on
  wider ones; the region editor becomes a direct-manipulation editor on touch.
- Navigation gains real routes (a specimen has a URL) and keyboard shortcuts.
- Motion is added only where it carries state, with reduced-motion parity.

## Sequencing

Work lands on the `design/frontend-foundation` branch in this order. Each step is
independently shippable and keeps `flutter analyze` and `flutter test` green.

1. **Foundation.** Tokens, theme, typography, component primitives (status chip,
   evidence disclosure, reason sheet, skeleton row, environment banner). No screen
   changes yet; the app looks the same but reads from tokens.
2. **Writing pass.** Every string rewritten against the guidelines and the length
   budgets, with the string lint in CI.
3. **Shell and queue.** Adaptive scaffold, routes, list-detail queue, filters
   sheet, empty and loading states.
4. **Workbench.** Image pane, readings and diff, fields with layers, evidence
   components, sticky actions, reason sheet, history pane, keyboard map.
5. **Intake and capture.** Upload list redesign, then the first-class camera flow.
6. **Motion and polish.** The catalog, reduced motion, haptics, dark mode QA.
7. **Verification.** Heuristic re-audit, accessibility scripts, device matrix,
   golden tests.

Parallel branches are acceptable for steps 3, 4 and 5 once step 1 has merged,
because they touch different files. Steps 1 and 2 are sequential and come first.

### Refactor, 2026-09-16

The rebuild above reached `main` and was judged to read as stock Material 3:
the fonts were never bundled, the icons were Material Symbols, and every
control kept Material anatomy. A second pass replaces the presentation layer
with an owned component library on `flutter/widgets.dart`. The direction is
[09-brand-direction.md](09-brand-direction.md), the library is
[10-component-library.md](10-component-library.md), and the build plan with
waves, ownership and gates is
[docs/execution/FRONT_END_REFACTOR.md](../../../docs/execution/FRONT_END_REFACTOR.md).
Work lands on the `front-end-refactor` branch. Everything in this document
other than the sequencing list stands; the bar in "The bar" is re-measured in
`12-verification-report-v2.md` when the refactor completes.

## Out of scope for this foundation

Backend contracts, new endpoints, offline capture with later sync, multi-specimen
photographs, and dashboards beyond the queue summary. Where a design calls for
data the API does not return yet, the document says so and the interface shows an
honest absence rather than a placeholder.
