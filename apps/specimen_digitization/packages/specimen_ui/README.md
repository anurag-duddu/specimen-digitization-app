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
| Foundation | `lib/src/foundation/` | Colour, fields, glass, type, shape, space, density, motion, icons, the theme |
| Primitives | `lib/src/primitives/` | Geometry and state with no styling opinions: `Pressable`, `Surface`, `GlassSurface`, `FieldLayer`, `FocusRing`, `Squircle`, `Popover`, `ModalRoutes`, `FieldCore`, `Announcer`, `Scrim` |
| Controls | `lib/src/controls/<family>/` | The components a screen composes, one barrel per family |
| Gallery | `lib/src/gallery/` | Every token and component in every state, both modes, both densities |

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
platform.

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
   and the family golden is regenerated in all four combinations.
6. Reduced motion, 200 percent text and right-to-left are exercised in its
   tests.
7. `flutter analyze --fatal-infos` is clean here and in the application.
8. `CHANGELOG.md` has an entry naming the Material widget it retires.

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
