# Review hierarchy and navigation

Owner direction, 2026-10-25: improve the complete, brand-relevant UI. Earlier
interaction decisions are requirements, not a request to restore old styling.

## Design and implementation

- Keep the specimen queue as a working list. The selected view names itself
  beside a Phosphor icon; inactive views retain accessible names and tooltips.
  Primary web navigation keeps every destination label visible. The compact
  mobile navigation retains its selected-label behavior.
  Remove the redundant queue heading.
- Use a visible Select action and an explicit selected-count/action state.
  Selection must preserve scope, eligibility, pending work and pagination.
  The count and Done control lead a compact footer. Shared decision controls
  keep the primary action visible; selection scope, secondary actions and
  eligibility details use a named menu when space is constrained.
- Make specimen references primary, with truthful review and missing counts
  as secondary information. Do not repeat the queue disposition in a badge or
  replace counts with an arbitrary blocker sentence.
- Separate IDs, Collection, Date and Taxa with responsive 32/48 dp group gaps.
  Keep the section name and counts together. A field is counted once even when
  several findings target it.
- Settled, present supported values use readable secondary ink and a check.
  Actionable fields use primary ink. Pending corrections never claim to be
  settled. Explicit absence and not-applicable decisions retain their meaning.
- Show compact provenance beside each field label. As written, Derived,
  Inferred and recorded Settled layers describe the actual source, not a
  guessed confidence score. Detailed blockers, evidence and editing belong
  in the disclosure.
- Keep neutral Paper/Obsidian/Mist surfaces and restrained Iris selection and
  focus. The Amber–Iris gradient remains a brand expression, not field status
  decoration. No acid yellow, decorative left stripes or new icon family.

Shared primitives live in specimen_ui, their interactive examples in
Widgetbook, and product previews render the actual application. This avoids a
parallel catalog implementation drifting away from the shipped UI.

## Adaptive queue companion

Owner clarification, 2026-10-25: the selected-only label behavior applies to
Queue views, not the expanded primary navigation on web. The primary sidebar
keeps both Specimens and Intake visible. Compact mobile navigation retains
its existing treatment.

`UiSidePanel` owns the common retained panel, motion, focus and modal behavior.
The app supplies the queue and record; Widgetbook renders this same primitive
and the actual product composition. No screen-specific visual copy is needed.

- Dock only when the remaining workbench still supports the photograph and
  inspector side by side. Otherwise open over the existing record allocation.
  Every docked-window record retains a queue toggle, including tablet widths.
- Reveal a panel at a stable inner width using the standard motion token.
  Reduced motion changes state immediately. Keep the background scrim fixed
  to the viewport while the panel moves; never slide a dimming edge across it.
- Keep queue search, selection and scroll, record state and unfinished field
  editor text/caret across collapse and responsive arrangement changes.
- Overlay dismissal precedes record navigation: Close, Escape, framework Back
  and scrim dismissal close the queue first. Record selection keeps the normal
  unsaved-change guard. A docked companion remains open after selection.
- Overlay focus stays inside the panel and returns to the opener. Opening on
  a touch tablet focuses its close control instead of summoning a search
  keyboard. Covered content is inert until the exit transition completes.

The reference review inspected Untitled UI's
[labelled primary sidebar](https://www.figma.com/design/fIfKyBB3UUanoV9lZoTBx9?node-id=1161-8593),
[separate slim rail](https://www.figma.com/design/fIfKyBB3UUanoV9lZoTBx9?node-id=1165-2049),
[desktop slideout](https://www.figma.com/design/fIfKyBB3UUanoV9lZoTBx9?node-id=1240-175083)
and [mobile slideout](https://www.figma.com/design/fIfKyBB3UUanoV9lZoTBx9?node-id=1251-10038).
Figma design-context extraction failed; actual screenshots and metadata were
available and are treated as references, not extracted implementation specs.
Mobbin examples inspected were
[Asana](https://mobbin.com/screens/95d319c8-e44a-48e0-bb32-83937d98ba96),
[Plain](https://mobbin.com/screens/150cc4a9-6311-444b-9902-01e491c25a5f) and
[Lightfield](https://mobbin.com/screens/c1322cfa-763a-4f21-8b49-0062d3c40ed1).
The tablet query returned phone examples, so tablet adaptation follows measured
content constraints, not an assertion that a tablet reference was verified.

## Count contract

`review_summary: {review: int, missing: int}` is nullable. Unknown/unmaterialized
fields never become an invented zero. Counts describe unique current fields,
not the total queue, labels, processing failures or final human approval.
Missing and review may overlap: a policy-approved absent value can be missing
without needing review. Not applicable is excluded from missing.

The bounded search query projects state and value presence from only the
current scoped immutable snapshot. New graph-backed snapshots retain a
versioned compact projection alongside their graph identity. Existing packed
snapshots need a compatible, verified graph read because their inline fields
were intentionally omitted. This recovery is limited to queue-count requests,
with bounded page work and a small positive-result cache; unrelated metadata
lookups remain metadata-only. Fresh scope and sensitivity authorization precede
every result, including cache hits. Failed or budget-exhausted recovery remains
unknown, never zero.

Python derives counts with the same rules as section presentation. The list
response contains neither graph references nor field content, and recovery
does not add per-record database queries or rewrite existing snapshots.
Pending edits affect local section counts only. Acceptance must compare a
real graph-backed record's queue counts with the sum of its field sections,
as well as cover inline records and the real SQL engine transport.

## Reference evidence

Untitled UI supplied proportion and hierarchy references, inspected through
Figma metadata and screenshots: [tabs](https://www.figma.com/design/fIfKyBB3UUanoV9lZoTBx9?node-id=1119-263),
[compact metadata](https://www.figma.com/design/fIfKyBB3UUanoV9lZoTBx9?node-id=4825-411483)
and [section headings](https://www.figma.com/design/fIfKyBB3UUanoV9lZoTBx9?node-id=1214-66).
Design-context extraction failed, so these are visual references, not extracted
implementation specifications.

Mobbin references inspected: [GitHub iOS selection](https://mobbin.com/screens/5edb4b50-e0ce-4571-ac92-dc6af0f05cea),
[ClickUp desktop selection](https://mobbin.com/screens/a032e768-e08b-442b-8b4b-16a67f6033c9),
[Linear property metadata](https://mobbin.com/screens/cef36326-d8ec-4c6f-acd4-a9f1e1060d33)
and [Juicebox view navigation](https://mobbin.com/screens/808fa0ce-b071-4040-9608-8b9ee8b3ab08).
They inform behavior and emphasis; the product keeps its own brand and queue.

## Acceptance

Independently review full queue and mixed-state field screens, not just isolated
controls. Cover light/dark, narrow mobile and wide desktop, 200% text, keyboard
and touch, selection/cancellation, source disclosure, count parity and preserved
record navigation. Review changed golden pixels before accepting baselines.
Run canonical repository checks and exact-head independent review, release only
through protected main workflows, then inspect live web and installed Android.
Keep iPhone acceptance deferred per the owner.
