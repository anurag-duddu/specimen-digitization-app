/// The two themes the application runs on (design system, section 8.1).
///
/// Light and dark are both first class and both defined by hand in the design
/// system. `themeMode` follows the platform.
library;

import 'package:flutter/material.dart';

import 'color_schemes.dart';
import 'component_themes.dart';
import 'motion.dart';
import 'semantic_colors.dart';
import 'spacing.dart';
import 'typography.dart';

/// Assembles the token layer into `ThemeData`.
abstract final class AppTheme {
  static ThemeData? _light;
  static ThemeData? _dark;

  /// The light theme.
  static ThemeData light() => _light ??= _build(
    scheme: lightColorScheme(),
    colors: SpecimenColors.light,
  );

  /// The dark theme.
  static ThemeData dark() =>
      _dark ??= _build(scheme: darkColorScheme(), colors: SpecimenColors.dark);

  static ThemeData _build({
    required ColorScheme scheme,
    required SpecimenColors colors,
  }) {
    final TextTheme text = specimenTextTheme();
    return ThemeData(
      useMaterial3: true,
      brightness: scheme.brightness,
      colorScheme: scheme,
      textTheme: text,
      scaffoldBackgroundColor: scheme.surface,
      canvasColor: scheme.surface,
      // Density follows the input modality, seeded from the platform. A touch
      // probe overrides it per window in the adaptation step; hit boxes stay
      // at 48 in every case (design system, section 5.6).
      visualDensity: VisualDensity.adaptivePlatformDensity,
      appBarTheme: specimenAppBarTheme(scheme),
      cardTheme: specimenCardTheme(scheme),
      inputDecorationTheme: specimenInputTheme(scheme, colors),
      filledButtonTheme: specimenFilledButtonTheme(colors),
      outlinedButtonTheme: specimenOutlinedButtonTheme(scheme, colors),
      textButtonTheme: specimenTextButtonTheme(colors),
      iconButtonTheme: specimenIconButtonTheme(colors),
      chipTheme: specimenChipTheme(scheme, colors),
      dialogTheme: specimenDialogTheme(scheme),
      bottomSheetTheme: specimenBottomSheetTheme(scheme),
      menuTheme: specimenMenuTheme(scheme),
      dividerTheme: specimenDividerTheme(scheme),
      iconTheme: specimenIconTheme(scheme),
      snackBarTheme: specimenSnackBarTheme(scheme, text),
      tooltipTheme: specimenTooltipTheme(scheme, text),
      navigationRailTheme: specimenNavigationRailTheme(scheme),
      extensions: <ThemeExtension<dynamic>>[
        colors,
        SpecimenTypography.standard(),
        const SpecimenSpacing(),
        const SpecimenSizing(),
        const SpecimenShape(),
        const MotionTokens(),
      ],
    );
  }
}
