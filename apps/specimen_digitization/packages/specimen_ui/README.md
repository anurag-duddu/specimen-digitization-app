# specimen_ui

The design system the Specimen Digitization client is built from: tokens,
primitives and controls on `package:flutter/widgets.dart`.

It is not a theme over Material. Material stays only as infrastructure
(`MaterialApp.router`, `ThemeData`, `TextField`'s editing behaviour, the page
transitions), and every component a reviewer sees is owned here. The direction
is [`design/09-brand-direction.md`](../../design/09-brand-direction.md); the
library is specified in
[`design/10-component-library.md`](../../design/10-component-library.md).

## What is in it

| Layer | Directory | What it holds |
| --- | --- | --- |
| Foundation | `lib/src/foundation/` | Colour, fields, glass, type, shape, space, density, motion, icons, window classes, the theme |
| Primitives | `lib/src/primitives/` | Geometry and state with no styling opinions: `Pressable`, `Surface`, `GlassSurface`, `FieldLayer`, `FocusRing`, `Squircle`, `Popover`, `ModalRoutes`, `FieldCore`, `UiLabel`, `FitBuilder`, `Announcer`, `Scrim` |
| Controls | `lib/src/controls/<family>/` | The thirty components a screen composes, one barrel per family: actions, inputs, overlays, navigation, data |
| Gallery | `lib/src/gallery/` | Every token and component in every state, both modes, both densities |

At 0.2.0 all five families are built. There is no Material component left to
reach for: a page is a `UiScaffold` with a `UiTopBar`, a navigation and a
body, and the frame hosts the toast layer itself, so `UiToasts.show(context,
message: ...)` works from anywhere inside it.

Beside the components there is one arrangement, because every screen needs it
and no two should disagree about it: `UiButtonRow` (11 section 3.4) draws a
primary action, an optional secondary and optional tertiary actions on one
line with the primary last, and stacks them with the primary on top when the
line does not fit or the window is compact.

## Consuming it

The application depends on it by path, so its version moves with the
application rather than with pub.dev:

```yaml
dependencies:
  specimen_ui:
    path: packages/specimen_ui
```

Wrap the application once and read tokens from the context:

```dart
UiTheme(
  data: UiThemeData.light(),
  child: MaterialApp.router(
    theme: UiThemeData.light().toThemeData(),
    darkTheme: UiThemeData.dark().toThemeData(),
    themeMode: ThemeMode.system,
    routerConfig: router,
  ),
);

// In a widget:
final ui = context.ui;
Text('Queue', style: ui.type.headline);
Surface(radius: ui.shape.tile, child: body);
```

`Density` sits at the application root and resolves the density from the last
pointer event, so `ui.density` follows the input modality rather than the
platform. `UiTheme` and `Density` go **above** the router, never inside a
page: a route pushed over the page reads them from there, and a modal that
finds no scope falls back to the light tokens. The package's own test harness
is wired the same way, for the same reason.

`UiTheme` also publishes the product's ambient text style, `type.body` in
`ink` with the decoration cleared, so nothing under it is ever drawn in the
framework's fallback. An application adds one thing of its own: the text scale
clamp, `MediaQuery.withClampedTextScaling(minScaleFactor: 0.85,
maxScaleFactor: 2.0)`, because the control contract promises 200 percent and
promises nothing above it. No control reads or clamps the scaler itself; a
control that has to contain text derives its height from
`UiType.controlHeightFor` instead, or from `UiType.heightAround` where its
resting height is a size rather than the density row (11 sections 2 and 5).

What a control does with less width than it needs is its own fit policy, and
it reads the constraints it was given rather than the window (11 section 3.3).
A label inside a control is a `UiLabel`, which is one line and ends in an
ellipsis with the whole word on a tooltip; a control with more than one
arrangement declares them to a `FitBuilder`, widest first.

## Fit: what a control does with less room than it needs

11 section 3.3 in one paragraph. A label never wraps: it is a `UiLabel`, one
line, and it ends in an ellipsis with the whole of it on the semantics label.
A control never shrinks below its intrinsic width; given less, it switches to
the compact variant it declares, through `FitBuilder`. Content is not a label
and wraps as content should: a row's title and subtitle, a banner's sentence,
a dialog's body, an empty state's copy.

Each control's variants are its own. A top bar ellipsises its title and then
collapses its actions into an overflow menu, which needs `UiTopBarAction`
rather than a widget it cannot read. A tab strip and a pill scroll with fading
edges, through the `EdgeFadedRow` primitive they share, and the chosen tab or
destination is scrolled into view. A
data tile steps its numeral down one display role at a time and then scales
it. A list row's `UiRowTrailing` drops its word and keeps its glyph. A
banner's and a toast's action move under the words. A modal's actions stack
with the primary on top. The gallery's fit section on each family page shows
all of it at 480, 360, 280 and 200 dp.

## Composition: how a screen is put together

13 section 3 in one paragraph, and the reason wave A exists. A screen is one
scroll: a `CustomScrollView` whose slivers are the regions, never a list
inside a list. `UiCollapsingHeader` pins the thing under review between a
maximum and a minimum fraction of the viewport, with a `chrome` slot riding
its lower edge that shrinks to one row at the minimum. `UiStatusStrip` states
the disposition and what blocks it on one line. `UiDecisionBar` decides, in
the scaffold's action bar, one row tall. `UiBanner.strip` is the one line
environment band with the sentence behind a tap. A routed screen fills the
action bar, hides the navigation pill and asks for the one line band through
`UiScaffoldSlots.of(context)`, the same way it publishes a
`UiScaffoldExclusion`; it names itself as the owner and calls `release(this)`
on the way out, because a router builds the screen arriving before it disposes
the screen leaving.

Two markers say what a widget tree cannot. `PinnedChrome(region:, extent:)`
marks a region that holds viewport height, and `PrimaryRegion(minExtent:)`
marks the one region the screen exists to show. `UiScaffold` marks its own top
bar, banner, action bar and floating navigation, and `UiCollapsingHeader`
marks the extent it pins, so a screen usually marks only its primary region.
Both are free: each builds its child and nothing else, so a marker adds one
element and no render object, and `PinnedChrome.extentOf` and
`PrimaryRegion.minExtentOf` are the one rule for reading a height off one. The
composition gates in `apps/specimen_digitization/test/composition/` find them
by type and sum what they report against the budget in 13 section 2.3.

## Seeing it

`flutter run -d chrome` and visit `/gallery`. The route is mounted outside
release builds and needs no session. The package's golden tests render the
same pages, so a change to a token shows as a diff on a gallery page before it
shows on a screen. Narrow the window below 600 dp and the page list becomes a
select above the content: the shell chooses its arrangement by window class,
like any other scaffold in the system.

Thirteen pages: six foundation, five families, Fit, which draws every
control of the fit table in
[11 section 3.3](../../design/11-fit-and-scale.md) at 200, 280, 360 and 480 dp,
and Composition, which draws the record screen of
[13 section 4.1](../../design/13-screen-composition.md) whole, at rest and
scrolled, beside the patterns it is built from.
Two golden sets answer two different questions. A family golden is the taste
review, one page at one comfortable window. The matrix under
`test/gallery/goldens/matrix/` is the fit review: every page at the four
window classes by three text scales by two modes, which is where a label that
wraps at a phone width or a control that clips at 200 percent text shows up.
The Composition page takes a third set of its own, at 390, 768 and 1180 dp,
because an arrangement is only evidence at more than one width.

## Adding a component

The process is [10 section 9](../../design/10-component-library.md), the
definition of done for a component. In short:

1. The component has an entry in 10 section 4, or the change amends that entry.
2. It has a style object holding every token it uses, and no literal anywhere.
3. `expectControlContract` passes, from `test/harness/control_contract.dart`.
4. Behaviour tests cover every variant and every state transition it owns.
5. It appears on its family's gallery page in every variant, size and state,
   and the family golden is regenerated in all four combinations. The family
   owns its own golden window, so taking a taller one moves no other family's
   files.
6. Reduced motion, 200 percent text and right-to-left are exercised in its
   tests.
7. `flutter analyze --fatal-infos` is clean here and in the application.
8. `CHANGELOG.md` has an entry naming the Material widget it retires.
9. No `TODO(fe/` stand-in for another family's control is left behind. If a
   sibling family has not merged yet, say so in the closeout; the
   `no_stand_ins` gate fails on a marker that outlives its wave.

A control goes in its family directory and is exported from that family's
barrel. The top barrel, `lib/specimen_ui.dart`, lists the five family barrels
and is not edited when a control is added.

## Running its checks

```bash
cd apps/specimen_digitization/packages/specimen_ui
flutter pub get
flutter analyze --fatal-infos
flutter test
```

## Licence

Geist and Geist Mono are SIL Open Font License 1.1; the text is in
`LICENSES/OFL-Geist.txt` and is registered with `LicenseRegistry` when a theme
is built. Phosphor Icons is MIT, through `phosphor_flutter`.
