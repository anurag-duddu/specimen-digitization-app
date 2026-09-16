/// The two themes the application runs on.
///
/// `UiThemeData.toThemeData()` builds everything derived from a token: the
/// colour scheme, the text theme, the ground, and the removal of the ink
/// splash. This file adds the component themes for the Material widgets that
/// are still on screens, and the product `ThemeExtension`s the patterns of
/// this wave read through `context.tokens` and its siblings.
///
/// Light and dark are both first class; `themeMode` follows the platform.
library;

import 'package:flutter/material.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'component_themes.dart';
import 'semantic_colors.dart';
import 'spacing.dart';
import 'typography.dart';

/// Assembles the token layer into `ThemeData`.
abstract final class AppTheme {
  static ThemeData? _light;
  static ThemeData? _dark;

  /// The light theme.
  static ThemeData light() =>
      _light ??= _build(UiThemeData.light(), SpecimenColors.light);

  /// The dark theme.
  static ThemeData dark() =>
      _dark ??= _build(UiThemeData.dark(), SpecimenColors.dark);

  static ThemeData _build(UiThemeData ui, SpecimenColors colors) {
    final ThemeData base = ui.toThemeData();
    final ColorScheme scheme = base.colorScheme;
    final TextTheme text = base.textTheme;
    return base.copyWith(
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
      ],
    );
  }
}
