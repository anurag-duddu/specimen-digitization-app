# Specimen design system: brand restoration and component standard

Status: expanded component inventory implemented; the direct-render continuation
has passed shared-package, catalog and application suites and native simulator
and emulator checks. Independent source and representative visual review cleared
the reported findings. Owner direction: 2026-10-22.

The owner requested equivalent component coverage from the supplied Untitled UI
library, adapted to the Specimen brand and managed in Widgetbook.
`coverage/reference-pages.json` records all 95 actual Figma pages; family audits
identify required capabilities, implementations, catalog examples, evidence and
remaining gaps. Page registration and passing local checks do not establish
exhaustive visual parity, physical-device acceptance or production approval.

## Exhaustive expansion and integration status

The reconciled inventory now maps all 95 actual reference pages: 83 component or
example pages and 12 setup, section-label or separator pages. Widgetbook owns
157 public controls across 193 catalog groups and 911 examples.
`coverage/reference-coverage.json` connects every content page to its family audit
and reachable stories; a test rejects missing pages, unknown implementations,
broken paths and omitted pending validation.

Shared forms/actions, data visualizations and table cells, navigation/feedback,
61 modal/slideout recipes, marketing sections, shared assets, page templates and
design annotations have been implemented. Source variants are adapted to the
Specimen brand, with explicit mappings rather than copied purple palettes or
third-party logo artwork. Registration proves availability, not exhaustive
visual approval. Each audit retains its validation limits.

Independent adversarial checks found and reproduced crop bounds, short drawers,
upload identity, radar labels, asynchronous message delivery and incomplete modal
anatomy. Those findings are repaired and their probes pass. Subsequent full
integration checks identified tooltip metadata/placement and default tab-layout
regressions; the original contracts and visual placement have been restored.
All four findings from the initial final independent review have also been fixed and
independently cleared. The full package suite was rerun after those repairs.

The continuation directly inspected 31 selected marketing/reference-page frames.
It added missing announcement, benefit, byline, featured/sidebar, grouped-career,
search, sorting and recovery slots; complete Blog, Article and Team compositions;
and an explicit host-owned remembered-session preference. Additional adversarial
and actual browser checks repaired focus return, long-list selection, disabled
navigation, large-text values, carousel behavior, stale story callbacks and
truncated disclosure questions. Counts and registration alone did not reveal
these issues. The new tests exercise the actual behaviors and visible text.

| Current local validation | Result |
| --- | --- |
| Shared package | 1,656 tests passed, including exact golden comparisons |
| Widgetbook | 38 checks passed, including all 911 examples at default knobs across five environments |
| Application | 3,657 tests passed; seven existing opt-in live-backend tests skipped; 13 focused cases passed including two additional large-text scroll regressions |
| Application visual and accessibility references | Six compact 200% text images reviewed independently for complete disclosure titles; other images and semantics fixtures unchanged |
| Release artifacts | Both web builds pass; current application artifact passes all 11 declared routes and five security headers locally |

Final application testing exposed the intended disclosure-wrap change in six
compact workbench images. Coordinator and independent reviewer inspected all six
baseline/current/difference triples. The full title adds 40 px of scrollable
content height; the upper interface and fixed footer are pixel-identical. Only
those six images were adopted. Exact comparison, assertions and tolerances remain
unchanged; this does not waive an unexplained visual mismatch. Two new interaction
regressions confirm Fields and History content moves fully into view through
actual swipes at 390 dp/200% text and that the fixed approval action still opens
its confirmation sheet.

Before this continuation, the catalog was built and launched in an isolated iPad simulator. Light
and dark rendering, a paired-calendar range from 15 September to 10 October, and
successful application of that range were inspected; the Dart MCP reported no
runtime errors. The expanded catalog also built and passed isolated Flutter Driver
smoke checks in an iPhone simulator and Android emulator: the brand hero rendered,
a real tap produced its callback receipt, and the resulting screenshots were
reviewed. These are simulator/emulator observations, not physical-device or
manual screen-reader acceptance. These native checks precede the final Mon to Sun
weekday-label refinement; all 12 affected header images were subsequently
reviewed independently and the package/catalog suites passed.

The current continuation additionally passed the same seven interactive checks
on isolated iPhone/iPad simulators and an Android emulator: hero action, FAQ
filter/expand/no-results/reset, remembered and session-only synthetic submissions,
and dark header navigation. All 21 screenshots were retained and reviewed, runtime
errors were absent, and all 182 copied runtime files matched the frozen source.
Catalog viewports were 320 dp on phones and 768 dp on the tablet. Temporary apps
and devices were stopped; the installed product app and physical phone were
untouched. This qualifies those local flows, not physical-device or manual
assistive-technology acceptance.

The baseline implementation passed the gates in `scripts/ci/verify.sh`. Verification ran in
segments: the script passed security/policy, all 19,295 collected Python tests
(19,245 passed, 50 skipped), UI writing and the package suite, then stopped at
Widgetbook formatting. After standard formatting, its unchanged remaining gates
passed catalog analysis/tests/build, application analysis/tests and the actual
browser OAuth contract. The app formatting gate found eight additional files;
standard formatting followed by the unchanged final gates passed both formatting
and the app release build, plus all 11 declared routes and five security headers.
This is completed gate coverage, not a claim of one uninterrupted script run.

Scanner findings on public reference metadata, digest fields, UI-label names and
synthetic data were repaired without exclusions or weaker coverage. Standard
formatting changes preserve behavior. No merge, production deployment or release
acceptance is claimed.

## Authority and scope

The owner's `SD_brand.png` is the visual authority. It replaces conflicting
colour, atmosphere and identity guidance in 03, 09 and 14. Untitled UI is the
quality and coverage reference, not the Specimen visual identity. Phosphor
remains the icon family. The rejected yellow direction must be removed from
active code, assets and guidance, with an executable regression guard.

This work builds the design-system foundations, component slots, examples and
quality checks, then integrates them throughout the existing app. Widgetbook is
the component management, documentation and testing surface. Existing data,
authentication, upload, Queue and release semantics must stay intact. Web, mobile
and tablet need platform-appropriate behaviour as well as responsive layouts.
The current request authorizes this implementation and catalog work; it does not
authorize merging or deploying it. Release work requires a subsequent instruction
and follows `docs/DEPLOYMENT.md`.

Reference library inspected through the Figma MCP:
[Untitled UI PRO v3.2](https://www.figma.com/design/fIfKyBB3UUanoV9lZoTBx9/?node-id=1480-0).
Page inventory was read directly, not inferred from the current commercial
website. Button and input variant metadata and the table/card-header design
context and screenshots were inspected. Direct context extraction for two
component masters failed; their metadata alone is not visual acceptance.

## Brand contract

| Role | Source | Application |
| --- | --- | --- |
| Obsidian | `#0E0E11` | Principal ink, high-contrast commands, dark canvas |
| Paper | `#FAF9F6` | Warm light canvas |
| Amber | `#F5A45B` | First end of the brand gradient |
| Iris | `#7B61FF` | Second end of the gradient and secondary brand colour |
| Mist | `#E6E6EA` | Quiet neutral separation and surfaces |
| Hero | Amber to Iris | Deliberate hero/brand regions, never behind evidence |

These are brand seeds, not five arbitrary text colours. Derive accessible
foreground, edge, fill and selected roles for each mode. Preserve neutral white
photo mattes. Never put normal text on a gradient without a separate solid
surface. Success, warning and error remain functional accessibility roles;
provenance and process categories do not each earn another decorative hue.
Labels and Phosphor icons retain distinctions when hues are consolidated.

The reference names Söhne. No Söhne font was found in the package, the user's
font directory or the system font directory during the initial audit. Keep
bundled Geist/Geist Mono as the explicit implementation fallback; do not silently
pretend that Geist is Söhne or add an unlicensed font dependency.

## What the comparison found

The existing `specimen_ui` package has a good architectural base: owned Flutter
components, semantic tokens, light/dark modes, 48 dp targets, keyboard behaviour,
reduced motion and fit tests. At the starting commit its catalog was a custom `/gallery`; Widgetbook now manages
the components and preserves the gallery as reference sheets.
The problem is drift and incomplete composition coverage, not absence of a
theme. Older gallery language still describes treatments the runtime retired.

Untitled UI makes component anatomy explicit (label, supporting text, leading
and trailing slots), organizes variants on predictable axes, and composes
headers, controls, data, feedback and navigation into complete patterns. Its
table example `2218:468696` combines a reusable header, filters, selection,
sortable headings, rows and pagination. We need those composable slots with
Specimen tokens and behaviour, not a pasted React screenshot or purple skin.

## Coverage and implementation batches

Every family needs a real component or a documented composition using existing
components, an interactive catalog example, a fit policy, and relevant tests.
The inventory includes shared components, application components, marketing
sections, foundational treatments and shared page patterns. Marketing, contact,
pricing and email-layout examples belong in the library even when the current
museum application does not use them. They use Specimen branding and synthetic
content; they do not create payment, email or account services. Reference company
logos use owned branding or host-supplied identity assets under the brand
adaptation policy.

| Batch | Slots | Starting point / work |
| --- | --- | --- |
| Foundations | Brand, colour roles, type, icons, spacing, radius, motion, surfaces | Restore small brand palette; consolidate status hues; explicit hero gradient; remove rejected theme assets and guidance |
| Actions | Buttons, icon buttons, button groups, choices, badges, tags | Existing owned controls; inspect state/size/icon consistency and catalog all axes |
| Forms | Text, textarea, search, select, checkbox, radio, toggle, choice cards | Existing controls; complete examples and shared anatomy |
| Advanced forms | Slider, date picker, file upload | Add controlled accessible primitives; file ingestion stays with the host |
| Data layouts | Section/page/card headers, tables, pagination | Add typed slots, keyboard sorting/selection, compact presentation, empty/loading/error composition |
| Navigation | Application navigation, tabs, breadcrumbs, progress steps | Retain existing navigation; add missing breadcrumb and step patterns |
| Feedback | Dialogs, sheets, menus, alerts, toasts, tooltips, progress, skeletons, empty states | Existing primitives; complete real examples and mode/state review |
| Discovery | Command menu | Searchable keyboard-operated action list composed from owned controls |
| Content | Activity feed, messages, code snippet, inline CTA, section footer | Add content patterns or document existing compositions; copy and action states are real |
| Visualization | Metrics, progress, simple charts | Retain metrics/arc/progress; add accessible small charts with textual values and neutral/iris emphasis |
| Catalog | Search/navigation, live controls, documentation, composition examples | Dedicated Widgetbook app consumes the actual package; theme, density, device/viewport, text scale, RTL and motion controls; all variants and states registered |
| Application integration | Auth, setup, shell, Queue, workbench, intake, capture, search, history, help and operational surfaces | Audit and replace inconsistent local patterns with library components, retaining platform gestures, inputs, focus, safe areas and native capture/file integrations |

### Work ownership

1. Foundation agent: foundation tokens, brand primitives and related tests.
2. Data agent: new data/layout components and data-family examples/tests.
3. Forms agent: advanced inputs and command menu, with focused examples/tests.
4. Coordinator: catalog, remaining navigation/content patterns, documentation,
   active guidance/assets cleanup, integration and review.

The implementation also assigned auth/help, Intake/capture, and Source/Costs
screen families to their component owners. An independent adversarial reviewer
examined calendar behavior, selection, modal scope and final visual repairs. Device frames in Widgetbook are layout
evidence; they do not constitute physical-device or production acceptance.

Agents share this branch and edit separate files. Family barrels stay with the
family owner. The coordinator owns top-level barrels, catalog shell, app router,
this plan and session closeout. A dedicated agent added Widgetbook validation to the existing CI/local Flutter
checks after reading deployment policy. No deployment permissions, triggers or
production settings changed.

## Acceptance contract

- Brand hues originate in the palette; components consume semantic roles.
- No rejected yellow token, field preset or brand asset remains executable.
- All added interactive controls support focus, keyboard, disabled state and
  screen-reader naming. Busy controls do not submit twice.
- Actual available width determines fit. Exercise 320/390, 768 and 1180/1440 dp,
  100/200 percent text, both modes and RTL. Hit targets remain 48 dp.
- State is owned by the caller where application data is involved. Gallery
  examples are explicitly synthetic and do not contact production.
- New gallery controls are real Flutter components, not images or HTML stand-ins.
- Tests cover behaviour and boundary cases rather than implementation snapshots.
- Analyse package and application, run relevant existing component/contrast/fit
  gates, render and inspect new visual evidence. Do not bulk overwrite historical
  goldens to conceal baseline drift.
- Independent adversarial review examines the integrated code and rendered
  output. Fix findings and rerun the affected checks before calling it complete.
- Release work, if subsequently undertaken, follows `docs/DEPLOYMENT.md` and
  required review/CI. Local gallery evidence is not live product acceptance.

## Application adoption

The application already used owned controls and semantic tokens throughout. The
shared foundation change reaches all routes through `AppTheme` and `UiTheme`.
The integration removes repeated heading and selection implementations where
shared components improve them; it retains specialized evidence workflows.

| Surface | Integration and retained behavior | Evidence |
| --- | --- | --- |
| Sign-in, email return, setup and collection access | Shared brand accent/mark and section headers; stable focused form subtree; short-height spacing adapts | Auth, magic-link and routing tests; five widths at 200% RTL |
| Shell, Queue and search/filter flows | Existing owned navigation, fields, choices, lists, skeletons and empty states inherit consolidated tokens | Full app tests, screen/semantics matrix and reviewed light/dark renders |
| Workbench, readings, evidence and history | Owned field/decision controls retained; shared native selection adapter; shared history headers and corrected status-strip fit | Evidence/history tests, native selection tests, 2x screen renders |
| Intake, bulk intake and capture | Shared page/card headings, wrapping crop actions and accessible selected-region ink | Existing state/upload/capture tests, reviewed narrow and wide images |
| Sources, source selection and Costs | Shared responsive headings; original row, currency, missing-measurement and cursor semantics retained | 117 focused source/cost checks and screen goldens |
| Help and feedback | Shared headings, wrapping shortcuts, scroll-reachable glossary; native selection and fixed toast clipping | Help/routing tests, toast contract/shape tests, small-phone 2x review |
| Native assets and web shell | Approved palette regenerated in launcher/splash/web assets, configs and source generator | Source/raster regression guards and Android/iOS compilation |

The new finite pagination/table control does not replace cursor-based lazy
Queue or Source lists. The date picker does not coerce partial historical dates
into invented calendar dates. Upload controls do not own file transfer or main
Queue admission. These boundaries preserve product behavior.

## Catalog and native behavior

`apps/specimen_widgetbook` consumes the actual shared package, with an explicit
public-control ownership manifest. All 911 registered examples run in five viewport
configurations (320, 390, 768, 1180 and 1440 dp), including dark/light, RTL, 200%
text and touch/pointer modes. Cases expose live callbacks, disabled/busy/error
states and knobs; default-knob smoke coverage is not the Cartesian product of
all knobs. Focused package contracts exercise keyboard, focus, target size,
semantics, disabled state and reduced motion independently.

Dialogs/sheets remain inside the configured preview navigator and inherit its
tokens, direction, text scale and safe areas. Application modals retain root
navigator behavior. Text editing/selection delegates to Flutter's adaptive
native infrastructure. Civil calendar values normalize year/month/day to UTC
midnight so DST and device time zones cannot skip a day. File picking, camera,
permissions and file transfer stay with the platform-aware application host.

The optional `tool/design_system_preview.dart` starts the application's real
router/theme at the gallery without a session, repository or Firebase startup.
It rejects release mode. Widgetbook remains the managed catalog.

## Initial local validation record (before exhaustive expansion)

Local validation uses Flutter 3.38.5 / Dart 3.10.4 on macOS 27.0.1 arm64.
These totals describe the earlier implementation, not the expanded candidate.
The append-only entries in `docs/SESSION_LEARNINGS.md` record validation for each stage. It distinguishes local, synthetic and simulator evidence from release
or physical-device acceptance.

- Analysis: application, shared package and Widgetbook clean.
- Full application suite: 3,657 passed; seven predeclared live HTTP checks skipped.
- Full package suite: 1,467 passed, including the final native gallery-inset
  and icon/navigation accessibility corrections. After those corrections,
  the affected application semantics suites passed all 22 checks again.
- Widgetbook: six tests passed, including every case across five environments,
  actual-host modal inheritance, explicit inventory and interaction tests.
- Baseline qualification: isolated committed `473b48ea` passed all 398 selected
  package golden checks and 275 selected app checks using the same renderer,
  fonts and reference bytes. No environment failure was used to dismiss diffs.
- Visual adoption: all 18 package families reviewed in light/dark and narrow
  200% RTL at three scroll positions; all 230 changed app images reviewed.
  Updated 396 package images, added 96, and updated 230 app images. Normal
  comparisons passed 494 package and 241 app checks after adoption.
- Visual review found and repaired glass-example clipping, bidi hex labels,
  tall-toast clipping, status-strip glyph columns and native gallery insets.
  Independent review found and repaired calendar selected-state contrast and
  controlled-date reveal; timezone/DST checks also pass in Chicago and Auckland.
- CI integration: Widgetbook locked dependencies, format, analysis, tests and web
  build now run in the existing Flutter gate; 583 deployment-policy tests passed.
- Native: Android debug build passed with nonsecret CI placeholders; the iOS
  preview compiled and ran in isolated iPhone and iPad simulators. Native keyboard
  filtering, page switching, safe areas and calendar navigation were exercised.
  The native accessibility tree confirmed single icon-button labels after the
  tooltip correction. This is not physical-device or manual screen-reader acceptance.
- Final Widgetbook release web build passed. The local preview served at
  `http://127.0.0.1:5199` was inspected and its action callback exercised.

Known bounds: `UiDataTable` is bounded rather than virtualized; callers keep lazy
lists for large datasets. `UiChart` is a small single-series summary with textual
values and distinct missing/zero states. Geist remains the explicit fallback
until licensed Söhne assets are supplied. Real file-picker/camera operation,
manual VoiceOver/TalkBack acceptance and production-connected behavior are not
claimed by these local checks. No release or production deployment was performed.
