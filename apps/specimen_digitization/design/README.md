# Front-end design foundation

This folder is the single source of truth for how the Specimen Digitization
client should look, read, move and adapt. Every document is written for a senior
designer and a senior Flutter engineer reading together. Read them in order the
first time; afterwards, go straight to the one that covers your change.

| File | What it settles | Read before |
|---|---|---|
| [00-north-star.md](00-north-star.md) | The one goal statement, the experience we are building, the bar we hold ourselves to, and the sequencing of the redesign | Any front-end work |
| [01-usability-heuristics-audit.md](01-usability-heuristics-audit.md) | Nielsen Norman Group ten-heuristic audit of the current app: what works, what fails, severity, and pass criteria for the redesign | Changing any flow |
| [02-ux-writing-guidelines.md](02-ux-writing-guidelines.md) | Voice, tone, vocabulary, pattern rules, before and after rewrites, and the checklist every user-facing string must pass | Writing or editing any string |
| [03-design-system.md](03-design-system.md) | Principles, brand direction, color and type tokens, spacing, shape, icons, the atomic component inventory, and the Flutter theme implementation plan | Adding or restyling any widget |
| [04-motion-and-microinteractions.md](04-motion-and-microinteractions.md) | Motion principles, duration and easing tokens, tooling decision (built-in, animations package, Rive), and the per-interaction catalog | Adding any animation or transition |
| [05-responsive-and-platform-adaptation.md](05-responsive-and-platform-adaptation.md) | Window size classes, navigation per class, screen-by-screen layouts, input modalities, iOS, Android and web conventions, camera capture, testing matrix | Changing layout or navigation |
| [06-accessibility.md](06-accessibility.md) | WCAG 2.2 AA commitment, audit of current semantics, requirements by principle, and the testing plan | Every UI pull request |
| [07-screen-blueprints.md](07-screen-blueprints.md) | The redesigned information architecture and a blueprint for every screen, with what changes from today and why | Building any screen |
| [08-verification-report.md](08-verification-report.md) | The independent re-audit of the rebuilt client: every pass criterion and every dimension of the bar marked Pass, Partial or Fail with its evidence, the ranked remaining defects with their exact fixes, and the gate results | Picking up any remaining defect, or claiming a criterion now passes |
| [09-brand-direction.md](09-brand-direction.md) | The agreed 2026-09-16 visual direction: frosted glass over light fields, Geist, Phosphor, superellipse shape, the accent, density, the mark; supersedes sections 2 to 6 of 03 | Any front-end work from the refactor on |
| [10-component-library.md](10-component-library.md) | What makes the design system strong and how each property is enforced; the `specimen_ui` package: layers, the control contract, every primitive and control, the gallery, the gates, the definition of done; supersedes sections 7 and 8 of 03 | Adding or changing any component |
| [11-fit-and-scale.md](11-fit-and-scale.md) | Units (what Flutter has for `px` and `rem`), text scale, window classes, the fit policy of every control, the one edge field anatomy, the one text style source, contract clauses 13 to 15, waves F and G | Any sizing, responsive or field work |
| [12-verification-report-v2.md](12-verification-report-v2.md) | The re-audit of the rebuilt client after the refactor: the eight dimensions of the bar re-measured, the fit matrix at three text scales, the reduced motion and dark mode passes, the glass measurement that chooses `GlassQuality`, the device captures, and six new defects with their file and line | Picking up a defect from the refactor, or claiming a dimension of the bar is met |
| [screenshots/](screenshots/) | Captures of the current app used as evidence in the audit | Reference only |

## Evidence from the rebuild

| Evidence | What it is |
|---|---|
| [screenshots/](screenshots/) | Captures of the client before the rebuild, used in the heuristics and accessibility audits |
| [screenshots/rebuild/](screenshots/rebuild/) and [screenshots/rebuild-smoke.md](screenshots/rebuild-smoke.md) | Device captures of the rebuilt client on Android phone and tablet. Taken before the motion and polish pull request, so the environment banner still shows the copy that step retired |
| [screenshots/refactor/](screenshots/refactor/) | 43 device captures of the client after the refactor, taken 2026-09-17 against `cbe78eb`: an Android phone, an iPad Pro 13 inch and a desktop browser, in both modes, with a record on them. The evidence for section "Device captures" of 12, including its three recorded gaps |
| `../test/golden/images/` | 121 size-class goldens: every screen at 390x844, 768x1024, 1180x820 and 1440x900, light and dark, with the record screen and intake also at 200 percent text. Regenerate with `flutter test --update-goldens test/golden` |
| `../packages/specimen_ui/test/gallery/goldens/matrix/` | 288 gallery matrix goldens: twelve family pages at the four window classes, at text scales 1.0, 1.3 and 2.0, in both modes. This is where a control's own fit policy is pictured. Regenerate with `flutter test --update-goldens test/gallery/matrix_golden_test.dart` inside the package |
| `../test/accessibility/fixtures/` | The checked-in semantics tree for each top-level surface. A change to what a screen reader hears shows up here as a diff. Regenerate with `flutter test --update-goldens test/accessibility` |
| `../test/verification/` | The instruments the second report measures with: the fit matrix, the reduced motion sweep over the routed application, the dark mode sweep at every window class, plus the capture target and the glass probe, which are run by hand rather than by `flutter test` |

## How these documents relate

The north star sets the goal. The heuristics audit and accessibility audit say
what is wrong today. The design system, writing guidelines and motion system say
what right looks like. The responsive document says how right adapts to each
window and platform. The screen blueprints put all of it together per screen.
The verification report closes the loop: it measures the built client against the
pass criteria and the bar, and says with evidence which ones are met. There are
two of them now. 08 measured the v1 client, whose interface was Material 3 with
the product's tokens on it; 12 measures the owned component library that
replaced it. They are not two runs of one instrument, and 12 says so in its
first paragraphs.

## Rules that apply across every document

- No em-dashes or en-dashes in any user-facing string or in these documents.
- Colors, type, spacing, radius, elevation and motion come from tokens. A widget
  never contains a literal color, size or duration.
- Status is never color alone. Every status pairs a label, an icon and a color.
- Unmeasured stays unmeasured. The interface never renders a missing measurement
  as zero, a score as truth, or agreement as correctness.
- Every consequential action asks for a reason, shows its consequence before the
  confirm control, and can be cancelled.
- Layout responds to window size, never to device type.
- Every interactive control has a semantic label, a minimum 48 dp target and a
  visible focus state.

## Changing these documents

Treat them like code. Propose changes in a pull request, cite the source or the
evidence, and update the north star if a change alters the goal or the bar.
