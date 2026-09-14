// The theme is only useful if a widget can actually reach it: Material 3 on,
// both brightnesses built, and every product extension registered.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/theme/app_theme.dart';
import 'package:specimen_digitization/src/theme/motion.dart';
import 'package:specimen_digitization/src/theme/semantic_colors.dart';
import 'package:specimen_digitization/src/theme/spacing.dart';
import 'package:specimen_digitization/src/theme/tokens.dart';
import 'package:specimen_digitization/src/theme/typography.dart';

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
        expect(
          theme.extension<MotionTokens>(),
          isNotNull,
          reason: 'motion tokens',
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

  test('the two themes are pinned to the design system palettes', () {
    expect(AppTheme.light().colorScheme.primary, LightPalette.primary);
    expect(AppTheme.light().colorScheme.surface, LightPalette.surface);
    expect(AppTheme.light().colorScheme.onSurface, LightPalette.onSurface);
    expect(AppTheme.dark().colorScheme.primary, DarkPalette.primary);
    expect(AppTheme.dark().colorScheme.surface, DarkPalette.surface);
    expect(AppTheme.dark().colorScheme.onSurface, DarkPalette.onSurface);
  });

  test('the type scale matches the design system', () {
    final TextTheme text = AppTheme.light().textTheme;
    expect(text.bodyLarge?.fontSize, TypeScale.bodyLargeSize);
    expect(text.bodyLarge?.height, 26 / TypeScale.bodyLargeSize);
    expect(text.bodyMedium?.fontSize, TypeScale.bodyMediumSize);
    expect(text.titleLarge?.fontWeight, FontWeight.w600);
    expect(text.labelSmall?.fontSize, TypeScale.labelSmallSize);
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
}
