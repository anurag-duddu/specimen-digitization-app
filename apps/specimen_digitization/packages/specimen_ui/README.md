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
`UiType.controlHeightFor` instead (11 sections 2 and 5).

## Fit: what a control does with less room than it needs

11 section 3.3 in one paragraph. A label never wraps: it is a `UiLabel`, one
line, and it ends in an ellipsis with the whole of it on the semantics label.
A control never shrinks below its intrinsic width; given less, it switches to
the compact variant it declares, through `FitBuilder`. Content is not a label
and wraps as content should: a row's title and subtitle, a banner's sentence,
a dialog's body, an empty state's copy.

Each control's variants are its own. A top bar ellipsises its title and then
collapses its actions into an overflow menu, which needs `UiTopBarAction`
rather than a widget it cannot read. A tab strip scrolls with fading edges. A
data tile steps its numeral down one display role at a time and then scales
it. A list row's `UiRowTrailing` drops its word and keeps its glyph. A
banner's and a toast's action move under the words. A modal's actions stack
with the primary on top. The gallery's fit section on each family page shows
all of it at 480, 360, 280 and 200 dp.

## Seeing it

`flutter run -d chrome` and visit `/gallery`. The route is mounted outside
release builds and needs no session. The package's golden tests render the
same pages, so a change to a token shows as a diff on a gallery page before it
shows on a screen.

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
