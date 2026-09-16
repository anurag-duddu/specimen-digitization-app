// The theme is only useful if a widget can actually reach it: Material 3 on,
// both brightnesses built, every product extension registered, and every
// Material role derived from a v2 token rather than from a generated seed.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_digitization/src/theme/semantic_colors.dart';
import 'package:specimen_digitization/src/theme/spacing.dart';
import 'package:specimen_digitization/src/theme/tokens.dart';
import 'package:specimen_digitization/src/theme/typography.dart';
import 'package:specimen_ui/specimen_ui.dart';

void main() {
  final Map<String, ThemeData> themes = <String, ThemeData>{
    'light': AppTheme.light(),
    'dark': AppTheme.dark(),
  };

  themes.forEach((String name, ThemeData theme) {
    group('$name theme', () {
      test('uses Material 3', () {
        expect(theme.useMaterial3, isTrue);
      });

      test('carries every product extension', () {
        expect(
          theme.extension<SpecimenColors>(),
          isNotNull,
          reason: 'product colors',
        );
        expect(
          theme.extension<SpecimenTypography>(),
          isNotNull,
          reason: 'monospace roles',
        );
        expect(
          theme.extension<SpecimenSpacing>(),
          isNotNull,
          reason: 'spacing grid',
        );
        expect(theme.extension<SpecimenSizing>(), isNotNull, reason: 'sizing');
        expect(
          theme.extension<SpecimenShape>(),
          isNotNull,
          reason: 'radii and strokes',
        );
      });

      test('the ink ripple is gone from the theme itself', () {
        expect(
          theme.splashFactory,
          NoSplash.splashFactory,
          reason:
              '09 section 11 rejects the ink ripple outright, and switching '
              'it off in the theme removes it from every Material widget '
              'still on a screen before a single call site changes',
        );
      });

      test('has the brightness it claims', () {
        expect(theme.brightness, theme.colorScheme.brightness);
      });

      test('switches M3 surface tint off', () {
        expect(theme.colorScheme.surfaceTint, ThemePolicy.noSurfaceTint);
        expect(theme.appBarTheme.surfaceTintColor, ThemePolicy.noSurfaceTint);
        expect(theme.cardTheme.surfaceTintColor, ThemePolicy.noSurfaceTint);
        expect(theme.dialogTheme.surfaceTintColor, ThemePolicy.noSurfaceTint);
        expect(
          theme.bottomSheetTheme.surfaceTintColor,
          ThemePolicy.noSurfaceTint,
        );
      });

      test('the app bar does not float', () {
        expect(theme.appBarTheme.elevation, 0);
        expect(theme.appBarTheme.scrolledUnderElevation, 0);
      });

      test('the scaffold ground is the surface role', () {
        expect(theme.scaffoldBackgroundColor, theme.colorScheme.surface);
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
    expect(text.bodyLarge?.fontSize, TypeScale.bodyLargeSize);
    expect(text.bodyMedium?.fontSize, TypeScale.bodyMediumSize);
    expect(text.labelSmall?.fontSize, TypeScale.labelSmallSize);
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

    expectSameShape(text.bodyMedium, UiType.standard.body, 'bodyMedium');
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

  testWidgets('a widget can read the tokens through the theme', (
    WidgetTester tester,
  ) async {
    late SpecimenColors seen;
    late SpecimenSpacing space;
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        darkTheme: AppTheme.dark(),
        themeMode: ThemeMode.system,
        home: Builder(
          builder: (BuildContext context) {
            seen = Theme.of(context).extension<SpecimenColors>()!;
            space = Theme.of(context).extension<SpecimenSpacing>()!;
            return const SizedBox.shrink();
          },
        ),
      ),
    );
    expect(seen.clearedContent, ProductPalette.greenContentLight);
    expect(space.space4, SpaceScale.space4);
  });

  testWidgets('a widget reads the v2 tokens through context.ui', (
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
    expect(ui.type.displayHero.fontSize, 64);
    expect(ui.shape.tile, 20);
    expect(ui.icons.cleared.defaultGlyph, UiIcons.cleared.filled);
  });
}
