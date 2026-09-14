/// Component defaults (design system, sections 5.3, 5.4, 5.9 and 8.3).
///
/// Component themes carry the defaults; call sites do not restyle. Elevation
/// is surface tone plus a hairline outline, never a shadow and never a surface
/// tint, so `surfaceTintColor` is switched off on every component that has it.
library;

import 'package:flutter/material.dart';

import 'semantic_colors.dart';
import 'tokens.dart';

/// Rounded rectangle at one of the six radius steps.
RoundedRectangleBorder _shape(
  double radius, [
  BorderSide side = BorderSide.none,
]) => RoundedRectangleBorder(
  borderRadius: BorderRadius.circular(radius),
  side: side,
);

/// The app bar: no shadow, no tint, no elevation change on scroll.
AppBarTheme specimenAppBarTheme(ColorScheme scheme) => AppBarTheme(
  backgroundColor: scheme.surface,
  foregroundColor: scheme.onSurface,
  surfaceTintColor: ThemePolicy.noSurfaceTint,
  shadowColor: ThemePolicy.noSurfaceTint,
  elevation: 0,
  scrolledUnderElevation: 0,
  toolbarHeight: SizeScale.appBar,
  centerTitle: false,
);

/// Cards sit at elevation level 0: a tone step plus a 1dp hairline.
CardThemeData specimenCardTheme(ColorScheme scheme) => CardThemeData(
  color: scheme.surfaceContainer,
  surfaceTintColor: ThemePolicy.noSurfaceTint,
  shadowColor: ThemePolicy.noSurfaceTint,
  elevation: 0,
  clipBehavior: Clip.antiAlias,
  shape: _shape(
    ShapeScale.radiusSm,
    BorderSide(color: scheme.outlineVariant, width: ShapeScale.strokeHairline),
  ),
);

/// Input fields: a boundary the user must be able to find, so `outline`
/// rather than `outlineVariant`.
InputDecorationTheme specimenInputTheme(
  ColorScheme scheme,
  SpecimenColors tokens,
) => InputDecorationTheme(
  filled: true,
  fillColor: scheme.surfaceContainerLowest,
  border: OutlineInputBorder(
    borderRadius: BorderRadius.circular(ShapeScale.radiusXs),
    borderSide: BorderSide(
      color: scheme.outline,
      width: ShapeScale.strokeBoundary,
    ),
  ),
  enabledBorder: OutlineInputBorder(
    borderRadius: BorderRadius.circular(ShapeScale.radiusXs),
    borderSide: BorderSide(
      color: scheme.outline,
      width: ShapeScale.strokeBoundary,
    ),
  ),
  focusedBorder: OutlineInputBorder(
    borderRadius: BorderRadius.circular(ShapeScale.radiusXs),
    borderSide: BorderSide(
      color: scheme.primary,
      width: ShapeScale.strokeEmphasis,
    ),
  ),
  errorBorder: OutlineInputBorder(
    borderRadius: BorderRadius.circular(ShapeScale.radiusXs),
    borderSide: BorderSide(
      color: scheme.error,
      width: ShapeScale.strokeBoundary,
    ),
  ),
  focusedErrorBorder: OutlineInputBorder(
    borderRadius: BorderRadius.circular(ShapeScale.radiusXs),
    borderSide: BorderSide(
      color: scheme.error,
      width: ShapeScale.strokeEmphasis,
    ),
  ),
  // Finding V-8. Material draws the disabled border and the disabled
  // label at 38 percent of `onSurface`, which measures 2.3:1. A field a
  // reviewer cannot use still has to be a field they can find.
  disabledBorder: OutlineInputBorder(
    borderRadius: BorderRadius.circular(ShapeScale.radiusXs),
    borderSide: BorderSide(
      color: tokens.disabledOutline,
      width: ShapeScale.strokeBoundary,
    ),
  ),
);

/// Buttons are `radius.sm`, not fully rounded, and always carry a 48dp box.
///
/// Every one of these passes the disabled pair explicitly (finding V-8).
/// A disabled control in this product states why the server forbids the
/// decision, and Material's 38 percent default draws that sentence at 2.3:1.
FilledButtonThemeData specimenFilledButtonTheme(SpecimenColors tokens) =>
    FilledButtonThemeData(
      style: FilledButton.styleFrom(
        minimumSize: const Size(SizeScale.targetMin, SizeScale.targetMin),
        shape: _shape(ShapeScale.radiusSm),
        disabledForegroundColor: tokens.disabledContent,
        disabledBackgroundColor: tokens.disabledContainer,
        disabledIconColor: tokens.disabledContent,
      ),
    );

OutlinedButtonThemeData specimenOutlinedButtonTheme(
  ColorScheme scheme,
  SpecimenColors tokens,
) => OutlinedButtonThemeData(
  style:
      OutlinedButton.styleFrom(
        minimumSize: const Size(SizeScale.targetMin, SizeScale.targetMin),
        shape: _shape(ShapeScale.radiusSm),
        side: BorderSide(
          color: scheme.outline,
          width: ShapeScale.strokeBoundary,
        ),
        disabledForegroundColor: tokens.disabledContent,
        disabledIconColor: tokens.disabledContent,
      ).copyWith(
        // `styleFrom` has no disabled side, and a disabled outlined button that
        // keeps the live `outline` border reads as available.
        side: WidgetStateProperty.resolveWith<BorderSide>(
          (Set<WidgetState> states) => BorderSide(
            color: states.contains(WidgetState.disabled)
                ? tokens.disabledOutline
                : scheme.outline,
            width: ShapeScale.strokeBoundary,
          ),
        ),
      ),
);

TextButtonThemeData specimenTextButtonTheme(SpecimenColors tokens) =>
    TextButtonThemeData(
      style: TextButton.styleFrom(
        minimumSize: const Size(SizeScale.targetMin, SizeScale.targetMin),
        shape: _shape(ShapeScale.radiusSm),
        disabledForegroundColor: tokens.disabledContent,
        disabledIconColor: tokens.disabledContent,
      ),
    );

IconButtonThemeData specimenIconButtonTheme(SpecimenColors tokens) =>
    IconButtonThemeData(
      style: IconButton.styleFrom(
        minimumSize: const Size(SizeScale.targetMin, SizeScale.targetMin),
        iconSize: SizeScale.iconAction,
        disabledForegroundColor: tokens.disabledContent,
      ),
    );

/// Chips: `radius.xs`, a 1dp boundary, no shadow.
ChipThemeData specimenChipTheme(ColorScheme scheme, SpecimenColors tokens) =>
    ChipThemeData(
      backgroundColor: scheme.surfaceContainerLow,
      selectedColor: scheme.secondaryContainer,
      surfaceTintColor: ThemePolicy.noSurfaceTint,
      shadowColor: ThemePolicy.noSurfaceTint,
      elevation: 0,
      pressElevation: 0,
      disabledColor: tokens.disabledContainer,
      side: BorderSide(color: scheme.outline, width: ShapeScale.strokeBoundary),
      shape: _shape(ShapeScale.radiusXs),
    );

/// Level 3: dialogs sit on `surfaceContainerHigh` in light and `surfaceBright`
/// in dark, with a scrim behind them.
DialogThemeData specimenDialogTheme(ColorScheme scheme) => DialogThemeData(
  backgroundColor: scheme.brightness == Brightness.light
      ? scheme.surfaceContainerHigh
      : scheme.surfaceBright,
  surfaceTintColor: ThemePolicy.noSurfaceTint,
  elevation: 6,
  shape: _shape(ShapeScale.radiusMd),
);

/// Level 1: the bottom sheet, plus a scrim.
BottomSheetThemeData specimenBottomSheetTheme(ColorScheme scheme) =>
    BottomSheetThemeData(
      backgroundColor: scheme.surfaceContainerLow,
      surfaceTintColor: ThemePolicy.noSurfaceTint,
      elevation: 1,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(
          top: Radius.circular(ShapeScale.radiusLg),
        ),
      ),
    );

/// Level 2: menus, dropdowns and tooltips.
MenuThemeData specimenMenuTheme(ColorScheme scheme) => MenuThemeData(
  style: MenuStyle(
    backgroundColor: WidgetStatePropertyAll<Color>(scheme.surfaceContainer),
    surfaceTintColor: const WidgetStatePropertyAll<Color>(
      ThemePolicy.noSurfaceTint,
    ),
    elevation: const WidgetStatePropertyAll<double>(3),
    shape: WidgetStatePropertyAll<OutlinedBorder>(
      _shape(
        ShapeScale.radiusSm,
        BorderSide(
          color: scheme.outlineVariant,
          width: ShapeScale.strokeHairline,
        ),
      ),
    ),
  ),
);

/// Hairlines are decorative. `space` is left at its default so this theme does
/// not move any existing layout.
DividerThemeData specimenDividerTheme(ColorScheme scheme) => DividerThemeData(
  color: scheme.outlineVariant,
  thickness: ShapeScale.strokeHairline,
);

/// Material Symbols axes (design system, section 6.1). Dark mode sets grade
/// -25, which is Google's guidance for reducing glare on light symbols against
/// a dark ground.
IconThemeData specimenIconTheme(ColorScheme scheme) => IconThemeData(
  color: scheme.onSurface,
  size: SizeScale.iconAction,
  fill: 0,
  weight: 400,
  grade: scheme.brightness == Brightness.light ? 0 : -25,
  opticalSize: SizeScale.iconAction,
);

SnackBarThemeData specimenSnackBarTheme(ColorScheme scheme, TextTheme text) =>
    SnackBarThemeData(
      backgroundColor: scheme.inverseSurface,
      contentTextStyle: text.bodyMedium?.copyWith(
        color: scheme.onInverseSurface,
      ),
      actionTextColor: scheme.inversePrimary,
      elevation: 6,
      shape: _shape(ShapeScale.radiusSm),
    );

TooltipThemeData specimenTooltipTheme(ColorScheme scheme, TextTheme text) =>
    TooltipThemeData(
      decoration: BoxDecoration(
        color: scheme.surfaceContainer,
        borderRadius: BorderRadius.circular(ShapeScale.radiusSm),
        border: Border.all(
          color: scheme.outlineVariant,
          width: ShapeScale.strokeHairline,
        ),
      ),
      textStyle: text.bodySmall?.copyWith(color: scheme.onSurface),
    );

/// The navigation rail: level 0, a selected destination on
/// `primaryContainer`.
NavigationRailThemeData specimenNavigationRailTheme(ColorScheme scheme) =>
    NavigationRailThemeData(
      backgroundColor: scheme.surfaceContainer,
      elevation: 0,
      indicatorColor: scheme.primaryContainer,
      minWidth: SizeScale.rail,
      indicatorShape: _shape(ShapeScale.radiusSm),
    );
