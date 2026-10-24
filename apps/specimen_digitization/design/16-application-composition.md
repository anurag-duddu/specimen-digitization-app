# Applying the design system to the application

The application and Widgetbook consume the same `specimen_ui` package. A
catalog component is not complete evidence of a usable screen: inspect its
actual application composition, including the shell, data state and available
space. Changes to source take effect in both on rebuild; production and native
installations still require their normal release.

## Brand and hierarchy

- Use the owned ribbon mark in the workspace navigation. Phosphor supplies
  interface icons, never a substitute product logo.
- The Amber-Iris gradient belongs to the identity and deliberate brand
  introductions. A routine queue or import task does not need a promotional
  panel. Paper, Mist and Obsidian support working surfaces; Iris identifies
  secondary selection. Do not reintroduce acid yellow or decorative status
  colours.
- A specimen photograph remains evidence. Do not place gradients over it or
  sacrifice its working area for introductory content.

## Screen responsibilities

| Surface | Composition | Preserved behaviour |
| --- | --- | --- |
| Navigation | Owned mark, collection selector, two named destinations and account footer; flat surfaces and a quiet selected fill | Keyboard focus, current destination semantics, mobile bottom navigation and state across resizing |
| Queue | Main working column with named view controls and readable record reasons; the list becomes an optional companion only after opening a record | Retained list position, selection, keyboard traversal, filters and direct record routing |
| Intake | Camera and file actions, named disclosure for other sources; batch save status once above a lazy photo grid; persistent submission | Private drafts, provider browsing, original-file recovery, inspection, retake, retry and explicit submission |
| Workbench | Dominant source canvas with a bounded Paper inspector; fields lead with values or problems and disclose provenance and requirements | Source transforms, region selection, editing, review guard, record navigation and decision actions |

Counts describe the response actually loaded. Missing scores, thumbnails and
timestamps remain missing; a page layout must not invent them. Existing roles,
errors, loading and recovery states remain visible and actionable.

## Pattern correction and source evidence

The independent audit on 2026-10-24 rejected the first application composition:
the queue was compressed beside an introduction, wide navigation remained
icon-only, selected rows had a heavy left stripe, and review state was repeated
at multiple levels. Empty Intake stacked an introduction, explanations and
nested source cards; saved batches repeated their baseline on every photo.

The correction is implemented in shared controls before application consumers:

| Pattern | Shared contract | Application decision |
| --- | --- | --- |
| Sidebar | Labels, proportional inline icons, 48 dp targets, distinct selection and focus | Use available desktop space for two real destinations; keep account controls at the bottom when height permits |
| List row | Body-size primary line, secondary line with breathing room, quiet selected fill | Identifier plus useful issue; omit ordinary review badges within the review queue; retain exceptions and accessible update time |
| Disclosure | Value-first summary option; details remain reachable and named | Show the field value or problem before provenance, requirements and editing detail |
| Photo tile | Host can suppress a settled caption while keeping accessible status; exclusions remain visible | Report saved once per batch; show pending, failure and sensitivity per photo |
| Button | Visual glyph follows the adjacent text role and scaler; measured slots match painted contents | Preserve 48 dp targets and centered idle/busy states without oversized glyphs |

Observed Mobbin references:

- [Todoist desktop navigation](https://mobbin.com/screens/fedfc0e2-73d1-42b6-853c-fb41ec5919f7)
  uses named destinations with small supporting icons and a quiet selected fill.
- [Todoist working list](https://mobbin.com/screens/a2aac87b-a8a7-40c7-8592-2a8f1357c5b9)
  keeps the task list primary and supporting descriptors subordinate.
- [Things mobile task detail](https://mobbin.com/screens/bc8c7688-15a0-44d3-9f57-15531c3f5f7a)
  discloses task detail while surrounding rows remain concise.
- [HubSpot source selection](https://mobbin.com/screens/8df9af3f-d761-462f-aa21-59d93c854288)
  presents each source as one named action, without nested buttons inside cards.
- [Docusign mobile capture](https://mobbin.com/screens/1551d31d-09e7-4754-9787-30c187d5c6ae)
  keeps capture primary and supporting commands secondary.

These observations inform our compositions; they are not evidence of museum
task frequency or accessibility. Camera/files remain the current initial
actions; other source names remain visible in the disclosure summary. This is
an implementation choice to validate with usage, not a claim that connected
sources are rarely used. [NN/G's progressive disclosure guidance](https://www.nngroup.com/articles/progressive-disclosure/)
requires a clear path to secondary choices and a task-appropriate split.
[Android's adaptive layout guidance](https://developer.android.com/develop/ui/views/layout/use-window-size-classes)
uses available window space, including height, rather than device identity.
Mobbin supplied web and iOS references; Android requires its own rendered and
physical-device verification.

The independent reviewer checks the combined result after parallel navigation,
content and Intake work. Acceptance includes 320/390 dp phones, 768 dp tablet,
1180/1440 dp desktop, light/dark, 100/200% text, long content, loading/error,
selected/focused states and preserved drafts. Updated screenshots alone do not
establish acceptance: retained queue state, explicit submission, source
recovery, unknown values, role restrictions and unsaved edits must still work.

## Review loop

Use the production screen widgets in Widgetbook with deterministic synthetic
repositories. Mock transport and device acquisition, not page layout. Keep
preview navigation and dialogs inside the selected viewport and keep production
configuration and museum data out of catalog assets.

For every composition change, inspect phone and desktop, light and dark, and
200% text. Verify the constraints in `13-screen-composition.md`: one vertical
scroll owner per content region, reachable actions, visible primary work,
bounded chrome and no nested surface clutter. Review changed golden pixels and
semantics before updating the expected files. Required automated checks and an
independent review precede the protected web release; a physical Android check
then verifies the installed build and retained user state.
