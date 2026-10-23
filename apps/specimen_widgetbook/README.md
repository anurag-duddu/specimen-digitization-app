# Specimen Widgetbook

The component workbench for the real `specimen_ui` Flutter package. All actions
use local demonstration state. It has no Firebase configuration, app session or
production backend connection.

```sh
cd apps/specimen_digitization
flutter pub get --enforce-lockfile
cd ../specimen_widgetbook
flutter pub get --enforce-lockfile
flutter run -d chrome --web-port 5199
```

The checked-in lockfile resolves Widgetbook 3.23 on Flutter 3.38.5 / Dart 3.10.4.
Widgetbook 3.25 requires a newer Flutter SDK; upgrading the app SDK is a separate
compatibility decision.

Use Navigation to search a component or state. Addons controls the appearance,
input density, reading direction, motion preference, text scale and viewport.
Knobs changes the selected story's inputs. Copy a story URL to share its chosen
configuration with someone running the same build. On narrow windows these
panels are available from the bottom bar.

The catalog registers 157 public controls across 193 groups and 911 examples. The
reference coverage test reconciles all 95 actual pages of the supplied Untitled
UI file, including shared assets, marketing sections and application examples.
Its page accounting is a structural check; the per-family audits retain visual
and device validation limits. Application patterns include 45 modal and 16
slideout recipes with local controlled state.

The catalog is split by family in `lib/catalog/`. Components are registered in
`lib/catalog.dart`; stories render the package widgets, never duplicate product
implementations. Keep use-case names stable for shareable URLs. Every story
explains its purpose and interaction contract. Reference sheets preserve the
older `/gallery` comparisons while individually named stories manage components.

Edit controls, foundations and tokens in
`apps/specimen_digitization/packages/specimen_ui/lib/`. The application and
Widgetbook both depend directly on that same directory, so shared changes flow
into both builds without copying components or publishing a package. The catalog's
`shared_package_source_test.dart` checks the resolved package and library paths
for both targets and rejects cached packages, copies or redirected libraries.
Install the locked dependencies for both targets before running the catalog tests.

Keep stories in `lib/catalog/` as examples of those shared controls. Knobs only
change a story's local demonstration inputs; they do not edit the shared widget,
its defaults or application data. After a shared source edit, hot reload each
running app and Widgetbook target. Restart or rebuild when a change affects
initialization, assets or native code. Each target then uses the same updated
implementation with its own state and configuration.

Run the shared package, catalog and application checks before delivery. CI tests
both consumers against the shared source, and release builds compile those same
files. Web delivery follows the protected repository release workflows; native
apps receive the change in their next rebuilt and distributed binary. Local hot
reload and Widgetbook previews do not update an already deployed or installed app.

Brand authority is `SD_brand.png`: Amber–Iris hero, Iris secondary, Obsidian,
Paper and Mist. Functional status colours communicate outcomes. Phosphor is the
icon family. Geist and Geist Mono are the bundled fallback for the reference's
Söhne; no Söhne font asset is supplied.

The environment sits above the preview navigator. Each story owns its navigator
and toast queue; switching stories disposes pending routes and callbacks, while
rebuilding the same story retains that scope. `UiModalNavigator` explicitly
contains dialogs and sheets inside the chosen viewport, so their tokens, safe
areas, text scale and direction match the trigger. The actual application keeps
its root-navigator modal behavior. Selection and editing use Flutter's adaptive
platform infrastructure through the package's owned adapters.

```sh
flutter analyze --fatal-infos
flutter test
flutter build web
```

The sibling app provides `tool/design_system_preview.dart` for backend-free
native reference-sheet review using its actual router and theme.

The source-render continuation inspected 31 selected Figma frames directly.
The resulting additions include feature benefits, structured editorial bylines,
featured articles with sidebars, grouped careers, full FAQ search and recovery,
blog sorting and pagination, and remembered-session preference contracts. Blog,
Article and Team pages compose the complete demonstrated journeys. All examples
use synthetic content and local callbacks.

Historical validation recorded for the expanded catalog on 23 October 2026,
before subsequent component refinements and release work:

- All 38 Widgetbook checks passed, including all 911 examples at default knobs in
  five environments: 320, 390, 768, 1180 and 1440 dp, with light/dark, 200% text,
  RTL and touch/pointer coverage. This does not exercise every knob combination.
- The shared package passed 1,656 tests, including exact golden comparisons.
  The continuation repairs menu and table-help focus, disabled-row navigation,
  long-list keyboard selection, large-text values and full disclosure questions,
  bounded carousels, and story-owned toast lifetime. Package goldens are unchanged.
  Six application screenshots at 200% text were independently reviewed and updated
  to show the full disclosure title; surrounding interface and fixed footer are
  unchanged. Comparisons remain exact. Detailed integration evidence is recorded in
  `docs/SESSION_LEARNINGS.md` at the repository root.
- The integrated application passed all 3,657 tests, with seven existing opt-in
  live-backend tests skipped. Shared-package, catalog and application analysis
  reported no issues. Two additional 390 dp/200% text regressions showed full
  workbench field/history endpoints remain reachable through actual scrolling
  and the fixed approval action opens its confirmation sheet; the 13-case
  focused rerun, including the documentation typography gate, also passed.
- iPhone/iPad simulator and Android emulator checks passed against the
  source frozen at that point: hero actions, FAQ filtering/expansion/no-results/reset,
  both remembered-session preferences and completed receipts, and dark-mode
  header navigation. All 21 screenshots were retained, runtime errors were
  absent, and copied runtime files were verified byte-identical to source.
  The catalog preview used 320 dp on phones and 768 dp on the tablet.
- Before this continuation, the catalog built and launched in an isolated iPad simulator. Light/dark
  rendering and applying a paired-calendar range from 15 September to 10 October
  were inspected, with no runtime errors reported through the Dart MCP. The
  expanded catalog also built and passed isolated Flutter Driver smoke checks in
  an iPhone simulator and Android emulator. Each check rendered the brand hero,
  exercised a real tap and callback receipt, and produced a reviewed screenshot.
  Native checks precede the final Mon to Sun weekday-label refinement; all 12 affected
  images were independently reviewed and the package/catalog suites passed.
- The baseline implementation passed the local gates in `scripts/ci/verify.sh`: security/policy,
  19,245 Python tests (50 skips), UI writing, package/catalog/app checks, the
  actual browser OAuth contract, formatting, both web release builds and local
  route/security-header smoke checks. The run resumed at unchanged remaining
  gates after formatter-only corrections; it was not one uninterrupted run.
  Scanner findings were repaired without weakening coverage.
- At the end of that continuation, package/catalog analysis, formatting, all
  repository security/policy checks and UI writing checks passed. The web release
  catalog built and ran locally on port 5199. Browser checks exercised FAQ search/reset and full
  questions, journal sorting, and the completed remembered-session receipt.
  The application web release also built; all 11 declared routes and five
  security headers passed the local artifact smoke check.

The current request authorizes integration and release across the application
and platforms. That authorization does not turn the historical checks above into
validation of later source changes. Current delivery must follow
`docs/DEPLOYMENT.md` at the repository root and be verified on the released commit.

Viewport and platform controls are simulations. They demonstrate layout and
adaptive behavior; physical device interaction, browser accessibility testing,
and production release acceptance require their own evidence. Historical golden
images are never silently regenerated by Widgetbook.
