// The bridge is only useful if the infrastructure under `MaterialApp` can
// reach the tokens: Material 3 on, both brightnesses built, every Material
// role derived from a v2 token rather than from a generated seed, and nothing
// else on it at all.
//
// The v1 version of this file checked that four product `ThemeExtension`s and
// fifteen component themes were registered. They are gone: no call site reads
// `Theme.of` for a token any more, so the test that would have caught a
// missing extension is replaced by the one that catches a returning component
// theme.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_ui/specimen_ui.dart';

void main() {
  final Map<String, (ThemeData, UiThemeData)> themes =
      <String, (ThemeData, UiThemeData)>{
        'light': (AppTheme.light(), UiThemeData.light()),
        'dark': (AppTheme.dark(), UiThemeData.dark()),
      };

  themes.forEach((String name, (ThemeData, UiThemeData) pair) {
    final ThemeData theme = pair.$1;
    final UiThemeData ui = pair.$2;

    group('$name theme', () {
      test('uses Material 3', () {
        expect(theme.useMaterial3, isTrue);
      });

      test('the ink ripple is gone from the theme itself', () {
        expect(
          theme.splashFactory,
          NoSplash.splashFactory,
          reason:
              '09 section 11 rejects the ink ripple outright, and switching '
              'it off in the theme removes it from the editing infrastructure '
              'the package still builds on',
        );
      });

      test('has the brightness it claims', () {
        expect(theme.brightness, theme.colorScheme.brightness);
      });

      test('switches M3 surface tint off', () {
        expect(theme.colorScheme.surfaceTint, GroundPalette.transparent);
      });

      test('the scaffold ground is the surface role', () {
        expect(theme.scaffoldBackgroundColor, theme.colorScheme.surface);
      });

      test('the selection colours are the tokens', () {
        // The caret and the highlight are published from inside the field as
        // well; the drag handles are drawn by the Material selection controls
        // above the editor and read them from here (11 section 4).
        expect(theme.textSelectionTheme.cursorColor, ui.color.ink);
        expect(theme.textSelectionTheme.selectionColor, ui.color.selection);
        expect(theme.textSelectionTheme.selectionHandleColor, ui.color.ink);
      });

      test('the page transitions are on the theme', () {
        expect(theme.pageTransitionsTheme, specimenPageTransitions);
      });

      test('no component theme shapes a control', () {
        // The retirement, held by a test rather than by review. Every entry
        // here was a `specimen*Theme` in `lib/src/theme/component_themes.dart`
        // until the last Material widget left the screens; each is now
        // whatever `UiThemeData.toThemeData` leaves it, which is the
        // framework's own. A component theme that comes back fails here.
        final ThemeData base = ui.toThemeData();
        expect(theme.appBarTheme, base.appBarTheme);
        expect(theme.cardTheme, base.cardTheme);
        expect(theme.inputDecorationTheme, base.inputDecorationTheme);
        expect(theme.filledButtonTheme, base.filledButtonTheme);
        expect(theme.outlinedButtonTheme, base.outlinedButtonTheme);
        expect(theme.textButtonTheme, base.textButtonTheme);
        expect(theme.iconButtonTheme, base.iconButtonTheme);
        expect(theme.chipTheme, base.chipTheme);
        expect(theme.dialogTheme, base.dialogTheme);
        expect(theme.bottomSheetTheme, base.bottomSheetTheme);
        expect(theme.menuTheme, base.menuTheme);
        expect(theme.dividerTheme, base.dividerTheme);
        expect(theme.iconTheme, base.iconTheme);
        expect(theme.snackBarTheme, base.snackBarTheme);
        expect(theme.tooltipTheme, base.tooltipTheme);
        expect(theme.navigationRailTheme, base.navigationRailTheme);
      });

      test('no product ThemeExtension is registered', () {
        // `SpecimenColors`, `SpecimenTypography`, `SpecimenSpacing`,
        // `SpecimenSizing` and `SpecimenShape` were the v1 way to a token.
        // `context.ui` is the only way now, and an extension on the bridge
        // would be a second source for the same value.
        expect(theme.extensions, isEmpty);
      });
    });
  });

  test('the Material roles are derived from the v2 colour roles', () {
    // 09 section 3.1 names three surfaces, not a six-step ramp: the window is
    // `ground`, everything solid on it is `paper`, and the photograph sits on
    // `matte`. `toColorScheme` maps those onto the slots the infrastructure
    // widgets read; nothing is generated from a seed any more.
    final ColorScheme light = AppTheme.light().colorScheme;
    expect(light.surface, UiColor.light.ground);
    expect(light.onSurface, UiColor.light.ink);
    expect(light.onSurfaceVariant, UiColor.light.inkSecondary);
    expect(light.surfaceContainer, UiColor.light.paper);
    expect(light.outline, UiColor.light.boundary);
    expect(light.outlineVariant, UiColor.light.hairline);
    expect(light.error, UiColor.light.status.blocked.content);

    final ColorScheme dark = AppTheme.dark().colorScheme;
    expect(dark.surface, UiColor.dark.ground);
    expect(dark.onSurface, UiColor.dark.ink);
    expect(dark.surfaceContainerHighest, UiColor.dark.matte);
    expect(dark.outline, UiColor.dark.boundary);
  });

  test('the ground is the window background in both modes', () {
    expect(AppTheme.light().scaffoldBackgroundColor, UiColor.light.ground);
    expect(AppTheme.dark().scaffoldBackgroundColor, UiColor.dark.ground);
  });

  test('the type scale matches the design system', () {
    final TextTheme text = AppTheme.light().textTheme;
    // 09 section 4.3 derives the Material slots from the product scale, never
    // the other way round. Compared field by field because `ThemeData` colours
    // the text theme on the way through, so the styles are not identical.
    void expectSameShape(TextStyle? slot, TextStyle role, String name) {
      expect(slot?.fontFamily, role.fontFamily, reason: '$name family');
      expect(slot?.fontSize, role.fontSize, reason: '$name size');
      expect(slot?.fontWeight, role.fontWeight, reason: '$name weight');
      expect(slot?.height, role.height, reason: '$name line height');
      expect(slot?.letterSpacing, role.letterSpacing, reason: '$name tracking');
    }

    expectSameShape(text.bodyLarge, UiType.standard.bodyLarge, 'bodyLarge');
    expectSameShape(text.bodyMedium, UiType.standard.body, 'bodyMedium');
    expectSameShape(text.labelSmall, UiType.standard.labelSmall, 'labelSmall');
    expectSameShape(text.titleLarge, UiType.standard.titleLarge, 'titleLarge');
    expectSameShape(
      text.displayLarge,
      UiType.standard.displayLarge,
      'displayLarge',
    );
  });

  test('every text role carries the packaged Geist family', () {
    final TextTheme text = AppTheme.light().textTheme;
    for (final TextStyle? style in <TextStyle?>[
      text.displayLarge,
      text.headlineLarge,
      text.titleMedium,
      text.bodyMedium,
      text.labelSmall,
    ]) {
      expect(style?.fontFamily, UiFonts.sansFamily);
    }
  });

  test('reduced motion collapses a decorative duration to zero', () {
    const MotionTokens normal = MotionTokens();
    const MotionTokens reduced = MotionTokens(reduced: true);
    expect(normal.standard, MotionTokens.standardRaw);
    expect(reduced.standard, Duration.zero);
    expect(
      reduced.meaningful(MotionTokens.standardRaw),
      MotionTokens.standardRaw,
      reason: 'progress carries information, so it keeps its duration',
    );
  });

  testWidgets('a widget reads the tokens through context.ui', (
    WidgetTester tester,
  ) async {
    late UiThemeData ui;
    await tester.pumpWidget(
      UiTheme(
        data: UiThemeData.light(),
        child: MaterialApp(
          theme: AppTheme.light(),
          home: Builder(
            builder: (BuildContext context) {
              ui = context.ui;
              return const SizedBox.shrink();
            },
          ),
        ),
      ),
    );
    expect(ui.color.ground, UiColor.light.ground);
    expect(
      ui.color.status.cleared.content,
      UiColor.light.status.cleared.content,
    );
    expect(ui.space.s4, UiSpace.standard.s4);
    expect(ui.type.displayHero.fontSize, 64);
    expect(ui.shape.tile, 20);
    expect(ui.icons.cleared.defaultGlyph, UiIcons.cleared.filled);
  });
}
