# Specimen Digitization client

The Flutter client a collections reviewer works in: photographs come in through
intake, a record is reviewed against its own evidence, and a decision is
recorded with a reason. It runs on the web, on Android and on iOS from one
codebase, and it is built from an in-repo design system rather than from
Material.

Firebase supplies identity, storage and the application database. The client
calls the scoped API; it never connects to PostgreSQL directly.

## The layers

Every file belongs to one layer and may import only the layer below it. The
import direction is a test, not a convention: `layering_test.dart` inside the
package and `no_material_imports_test.dart` in the application hold it.

```
L5  Screens        lib/src/screens/, lib/src/app/     a route, composed
L4  Patterns       lib/src/widgets/                   StatusChip, QueueRow, RiskMeter
                   ^ knows what a specimen is
                   ------------------------------------------------------
                   v knows nothing about specimens
L3  Controls       packages/specimen_ui/lib/src/controls/<family>/
                                                      UiButton, UiField, UiListRow
L2  Primitives     packages/specimen_ui/lib/src/primitives/
                                                      Pressable, Surface, FocusRing
L1  Foundation     packages/specimen_ui/lib/src/foundation/
                                                      colour, type, space, shape,
                                                      motion, density, icons, glass
L0  SDK            package:flutter/widgets.dart
```

The package cannot import the application, because the path dependency points
one way. A `UiButton` does not know what a specimen is; a `StatusChip` does.
Material survives only as infrastructure (`MaterialApp.router`, the bridge
`ThemeData`, `TextField`'s editing behaviour, the page transitions, and
`MaterialLocalizations` for one overlay string): four files under `lib/` import
`material.dart` and each of them says on the import line why.

The design system is documented in
[`packages/specimen_ui/README.md`](packages/specimen_ui/README.md) and specified
in [`design/10-component-library.md`](design/10-component-library.md).

## Running it

```bash
cd apps/specimen_digitization
flutter pub get --enforce-lockfile
flutter run -d chrome
```

`lib/firebase_options.dart` is gitignored. Copy `lib/firebase_options.ci.dart`
over it for a credential free local build; never commit the real one.

### The gallery

Visit `/gallery`. It renders every token and every control in every variant,
state, size, density and mode, and it needs no session: the route is mounted
whenever `kReleaseMode` is false and is absent from a release build, so it is
what a reviewer looks at and not what a museum sees.

Twelve pages: six foundation, five families and Fit, which draws every control
that declares a compact variant at 480, 360, 280 and 200 dp. Narrow the window
below 600 dp and the page list becomes a select above the content, because the
gallery shell chooses its arrangement by window class like any other screen.

## The gates

Every rule this client is held to is a test, so it runs wherever `flutter test`
runs. Each gate that cannot yet be zero carries a map of file to count that may
only shrink.

| Gate | Where | What it holds | Backlog |
|---|---|---|---|
| `no_color_literals` | `test/theme/` | `Color(0x` appears only in the package's `palette.dart` | none |
| `no_literal_geometry` | `test/theme/`, `packages/specimen_ui/test/gates/` | Every static size, radius, duration, inset and constraint is a token. Two tests: the package allows none outside its foundation, gallery and painters; the application burns a backlog down | package none, application 10 numbers over 3 files, all elapsed time |
| `no_material_components` | `test/theme/` | None of the 42 retired Material widgets is constructed anywhere under `lib/` | empty |
| `no_material_imports` | `test/theme/` | `material.dart` is imported only by the four named infrastructure files, and each still needs it | empty |
| `icons_unique` | `test/theme/` | Every glyph comes from `UiIcons` on Phosphor, and no two registry entries are the same glyph | empty |
| `fonts_bundled` | `test/theme/` | Geist and Geist Mono resolve to the bundled assets; `google_fonts` is absent from the lockfile | none |
| `no_dashes` | `test/theme/` | No em dash or en dash in a Dart string or in `design/*.md` | none |
| `contrast_test` | `test/theme/` | The bridge `ColorScheme` and the product roles clear their floors | none |
| `contrast_composite` | `packages/specimen_ui/test/foundation/` | Every text role on every surface and on each glass level over the lightest and darkest point of every field, in both modes | none |
| `layering` | `packages/specimen_ui/test/foundation/` | Import direction inside the package, L1 to L3 | none |
| `no_stand_ins` | `packages/specimen_ui/test/foundation/` | No `TODO(fe/` marker outlives its wave under the package's `lib/` | none |
| `no_fallback_text_style` | `packages/specimen_ui/test/foundation/` | Every gallery page and every overlay, pumped in a host that installs the framework fallback on purpose, draws in the product's own style | none |
| `glass_budget` | `packages/specimen_ui/lib/testing.dart` | Frosted panes per window, counted as `BackdropFilter` render objects, called by every gallery golden and by the application's golden harness. A page that exceeds the budget on purpose states its own number | none |
| `control_contract` | `packages/specimen_ui/test/harness/` | The fifteen clauses of 10 section 2 on every interactive control: states, 48 dp hit box, keyboard, focus ring, semantics, press feedback, 200 percent text, reduced motion, direction, density, tokens, gallery, one line labels, geometry from type, declared fit | none |
| `check_ui_strings.py` | `scripts/ci/` | Every user facing string against the checklist in 02, with a baseline | existing baseline |

The composition contract of
[`design/13-screen-composition.md`](design/13-screen-composition.md) section 5
adds five more under `test/composition/`; they are wave A's and are not in the
table above.

Run them:

```bash
cd apps/specimen_digitization
flutter analyze --fatal-infos
flutter test
(cd packages/specimen_ui && flutter analyze --fatal-infos && flutter test)
dart format --set-exit-if-changed lib test
```

Run each one on its own and read its own exit code. The two suites contend for
the machine, so a single command chaining both can be reaped without either
having failed.

## Goldens and fixtures

Three sets of checked-in binaries, answering three different questions.

| Set | Count | Question it answers |
|---|---|---|
| `test/golden/images/` | 121 | What does each screen look like at 390x844, 768x1024, 1180x820 and 1440x900, in both modes, with the record screen and intake also at 200 percent text |
| `packages/specimen_ui/test/gallery/goldens/` | 48 | What does each family of controls look like at one comfortable window. This is the taste review |
| `packages/specimen_ui/test/gallery/goldens/matrix/` | 288 | What does each gallery page do at the four window classes, at text scales 1.0, 1.3 and 2.0, in both modes. This is the fit review |
| `test/accessibility/fixtures/` | 8 | What does a screen reader hear on each top level surface |

**Goldens are generated on macOS.** Off macOS the test still builds the screen,
so every layout, overflow and semantics assertion in it runs; only the pixel
comparison is set aside, and `--update-goldens` refuses, so no file is ever
written by a platform that did not draw the rest of the set. Linux rasterises
the same bundled fonts one to eleven percent differently, which would otherwise
fail every file for a reason no reviewer could act on.

Regenerate, on macOS, and read the diff before committing it:

```bash
flutter test --update-goldens test/golden
flutter test --update-goldens test/accessibility
(cd packages/specimen_ui && flutter test --update-goldens test/gallery)
```

The screen goldens and the semantics fixtures are regenerated **once per wave
by the integrator**, never by a slot working in parallel: two branches that
both regenerate a binary revert one another with no conflict to warn either of
them. A slot regenerates them to look at, records the set that moved against
the set expected, and reverts with `git checkout -- test/golden/images
test/accessibility/fixtures`. Unexpected movement is a finding.

## Text scale and reduced motion

**Text scale.** `MediaQuery.textScaler` is the only source, and the root clamps
it once, to 0.85 through 2.0 (`lib/main.dart`). The control contract promises
200 percent and promises nothing above it, and nothing under 85 percent is
worth reading. No control reads or clamps the scaler itself. A height that
holds text is never a constant: it is
`max(density height, scaled line height + 2 * inset)`, so a control is
unchanged at 1.0 and grows above it. Type scales; space does not; arrangement
switches by window class; fit is decided from the constraints a control is
given. Tests pump at 1.0, 1.3 and 2.0. On the web the browser's own preference
never reaches Flutter, so the scale there is 1.0.

**Reduced motion.** Four sources are read, because no one of them covers every
platform on Flutter 3.38.5: `MediaQuery.disableAnimations` (Android),
`AccessibilityFeatures.reduceMotion` (iOS, where the media query reports
nothing), a `matchMedia` bridge (web), and the stored in-app preference on the
help screen, so a reviewer on a managed desktop can force it without an
operating system setting. `MotionTokens.of(context)` folds the live state into
every duration, so a transition collapses without a branch at the call site.
What keeps its motion is what carries information: an indeterminate progress
indicator becomes an opacity pulse rather than nothing.

## The documents

[`design/`](design/) is the source of truth for how this client looks, reads,
moves and adapts; [`design/README.md`](design/README.md) indexes all fourteen
documents and says which to read before which change. Start with
[`design/00-north-star.md`](design/00-north-star.md).

The refactor that built the design system is planned in
[`docs/execution/FRONT_END_REFACTOR.md`](../../docs/execution/FRONT_END_REFACTOR.md)
and its lessons are distilled in
[`docs/LESSONS_FRONT_END_REFACTOR.md`](../../docs/LESSONS_FRONT_END_REFACTOR.md).
The release contract is
[`docs/DEPLOYMENT.md`](../../docs/DEPLOYMENT.md): a merge to `main` is the only
production trigger, and no deploy command is ever run by hand.
