/// Component defaults for the Material widgets still on screens.
///
/// 10 section 1.3 retires every one of these; until the screen waves replace
/// them, they read the v2 tokens so a screen that has not been touched yet
/// still renders in the new system. Corners are superellipses, the ripple is
/// gone from the theme itself, and every edge comes from `boundary` or
/// `hairline` rather than from a generated outline.
///
/// Elevation is surface tone plus a hairline, never a shadow and never a
/// surface tint, so `surfaceTintColor` is off on every component that has it.
library;

import 'package:flutter/material.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'semantic_colors.dart';
import 'tokens.dart';

/// A superellipse at [radius], which is what every corner in this product is
/// (09 section 5).
OutlinedBorder _shape(double radius, [BorderSide side = BorderSide.none]) =>
    Squircle.border(radius, side: side);

/// The capsule every button, chip and search field now draws.
OutlinedBorder _capsule([BorderSide side = BorderSide.none]) =>
    StadiumBorder(side: side);

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
    ShapeScale.radiusLg,
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
    borderRadius: BorderRadius.circular(ShapeScale.radiusMd),
    borderSide: BorderSide(
      color: scheme.outline,
      width: ShapeScale.strokeBoundary,
    ),
  ),
  enabledBorder: OutlineInputBorder(
    borderRadius: BorderRadius.circular(ShapeScale.radiusMd),
    borderSide: BorderSide(
      color: scheme.outline,
      width: ShapeScale.strokeBoundary,
    ),
  ),
  focusedBorder: OutlineInputBorder(
    borderRadius: BorderRadius.circular(ShapeScale.radiusMd),
    borderSide: BorderSide(
      color: scheme.onSurface,
      width: ShapeScale.strokeEmphasis,
    ),
  ),
  errorBorder: OutlineInputBorder(
    borderRadius: BorderRadius.circular(ShapeScale.radiusMd),
    borderSide: BorderSide(
      color: scheme.error,
      width: ShapeScale.strokeBoundary,
    ),
  ),
  focusedErrorBorder: OutlineInputBorder(
    borderRadius: BorderRadius.circular(ShapeScale.radiusMd),
    borderSide: BorderSide(
      color: scheme.error,
      width: ShapeScale.strokeEmphasis,
    ),
  ),
  // Finding V-8. Material draws the disabled border and the disabled
  // label at 38 percent of `onSurface`, which measures 2.3:1. A field a
  // reviewer cannot use still has to be a field they can find.
  disabledBorder: OutlineInputBorder(
    borderRadius: BorderRadius.circular(ShapeScale.radiusMd),
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
        shape: _capsule(),
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
        shape: _capsule(),
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
        shape: _capsule(),
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

/// Chips are capsules now, with a 1 dp boundary and no shadow.
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
      shape: _capsule(),
    );

/// Level 3: dialogs sit on `surfaceContainerHigh` in light and `surfaceBright`
/// in dark, with a scrim behind them.
DialogThemeData specimenDialogTheme(ColorScheme scheme) => DialogThemeData(
  backgroundColor: scheme.brightness == Brightness.light
      ? scheme.surfaceContainerHigh
      : scheme.surfaceBright,
  surfaceTintColor: ThemePolicy.noSurfaceTint,
  elevation: 6,
  shape: _shape(ShapeScale.radiusXl),
);

/// Level 1: the bottom sheet, plus a scrim.
BottomSheetThemeData specimenBottomSheetTheme(ColorScheme scheme) =>
    BottomSheetThemeData(
      backgroundColor: scheme.surfaceContainerLow,
      surfaceTintColor: ThemePolicy.noSurfaceTint,
      elevation: 1,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(
          top: Radius.circular(ShapeScale.radiusXl),
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
        ShapeScale.radiusLg,
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

/// Material Symbols axes, for the screens still drawing them (03 section
/// 6.1). Dark mode sets grade -25, Google's guidance for reducing glare on a
/// light symbol against a dark ground. Removed with the last `Symbols.` call
/// site.
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
      shape: _shape(ShapeScale.radiusLg),
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
      indicatorShape: _capsule(),
    );
