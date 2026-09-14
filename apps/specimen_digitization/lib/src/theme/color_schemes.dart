/// The two Material 3 `ColorScheme`s (design system, sections 3.1 to 3.3).
///
/// The seed is run through `ColorScheme.fromSeed` so the generated luminance
/// ladder is on record, then every role named in the design system is pinned
/// with `copyWith`. The generator proves the ladder is sane; the pins make sure
/// a future `material_color_utilities` release cannot silently move a shipped
/// color.
library;

import 'package:flutter/material.dart';

import 'tokens.dart';

/// The light scheme.
ColorScheme lightColorScheme() =>
    ColorScheme.fromSeed(
      seedColor: LightPalette.seed,
      brightness: Brightness.light,
    ).copyWith(
      brightness: Brightness.light,
      primary: LightPalette.primary,
      onPrimary: LightPalette.onPrimary,
      primaryContainer: LightPalette.primaryContainer,
      onPrimaryContainer: LightPalette.onPrimaryContainer,
      secondary: LightPalette.secondary,
      onSecondary: LightPalette.onSecondary,
      secondaryContainer: LightPalette.secondaryContainer,
      onSecondaryContainer: LightPalette.onSecondaryContainer,
      tertiary: LightPalette.tertiary,
      onTertiary: LightPalette.onTertiary,
      tertiaryContainer: LightPalette.tertiaryContainer,
      onTertiaryContainer: LightPalette.onTertiaryContainer,
      error: LightPalette.error,
      onError: LightPalette.onError,
      errorContainer: LightPalette.errorContainer,
      onErrorContainer: LightPalette.onErrorContainer,
      surface: LightPalette.surface,
      onSurface: LightPalette.onSurface,
      onSurfaceVariant: LightPalette.onSurfaceVariant,
      surfaceContainerLowest: LightPalette.surfaceContainerLowest,
      surfaceContainerLow: LightPalette.surfaceContainerLow,
      surfaceContainer: LightPalette.surfaceContainer,
      surfaceContainerHigh: LightPalette.surfaceContainerHigh,
      surfaceContainerHighest: LightPalette.surfaceContainerHighest,
      surfaceDim: LightPalette.surfaceDim,
      surfaceBright: LightPalette.surfaceBright,
      outline: LightPalette.outline,
      outlineVariant: LightPalette.outlineVariant,
      inverseSurface: LightPalette.inverseSurface,
      onInverseSurface: LightPalette.inverseOnSurface,
      inversePrimary: LightPalette.inversePrimary,
      scrim: LightPalette.scrim,
      shadow: LightPalette.shadow,
      // Elevation is carried by surface tone plus a hairline, never by a tint
      // that blends primary into a panel next to a specimen photograph
      // (section 5.4).
      surfaceTint: ThemePolicy.noSurfaceTint,
    );

/// The dark scheme.
ColorScheme darkColorScheme() =>
    ColorScheme.fromSeed(
      seedColor: DarkPalette.seed,
      brightness: Brightness.dark,
    ).copyWith(
      brightness: Brightness.dark,
      primary: DarkPalette.primary,
      onPrimary: DarkPalette.onPrimary,
      primaryContainer: DarkPalette.primaryContainer,
      onPrimaryContainer: DarkPalette.onPrimaryContainer,
      secondary: DarkPalette.secondary,
      onSecondary: DarkPalette.onSecondary,
      secondaryContainer: DarkPalette.secondaryContainer,
      onSecondaryContainer: DarkPalette.onSecondaryContainer,
      tertiary: DarkPalette.tertiary,
      onTertiary: DarkPalette.onTertiary,
      tertiaryContainer: DarkPalette.tertiaryContainer,
      onTertiaryContainer: DarkPalette.onTertiaryContainer,
      error: DarkPalette.error,
      onError: DarkPalette.onError,
      errorContainer: DarkPalette.errorContainer,
      onErrorContainer: DarkPalette.onErrorContainer,
      surface: DarkPalette.surface,
      onSurface: DarkPalette.onSurface,
      onSurfaceVariant: DarkPalette.onSurfaceVariant,
      surfaceContainerLowest: DarkPalette.surfaceContainerLowest,
      surfaceContainerLow: DarkPalette.surfaceContainerLow,
      surfaceContainer: DarkPalette.surfaceContainer,
      surfaceContainerHigh: DarkPalette.surfaceContainerHigh,
      surfaceContainerHighest: DarkPalette.surfaceContainerHighest,
      surfaceDim: DarkPalette.surfaceDim,
      surfaceBright: DarkPalette.surfaceBright,
      outline: DarkPalette.outline,
      outlineVariant: DarkPalette.outlineVariant,
      inverseSurface: DarkPalette.inverseSurface,
      onInverseSurface: DarkPalette.inverseOnSurface,
      inversePrimary: DarkPalette.inversePrimary,
      scrim: DarkPalette.scrim,
      shadow: DarkPalette.shadow,
      surfaceTint: ThemePolicy.noSurfaceTint,
    );
