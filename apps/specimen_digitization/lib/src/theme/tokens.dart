/// Raw design primitives for the Specimen Digitization client.
///
/// Every value here is transcribed from `design/03-design-system.md`. This is
/// the only file in the repository allowed to carry a `Color(0x...)` literal
/// (design system, section 8.1). Nothing in this file imports Flutter beyond
/// `Color`, so the primitives stay usable from pure Dart tests.
library;

import 'dart:ui' show Color;

/// Values that express a policy of the system rather than a color in it.
abstract final class ThemePolicy {
  /// Fully transparent. M3 blends `surfaceTint` into an elevated surface,
  /// which puts a green cast on any panel adjacent to a specimen photograph,
  /// so the tint is switched off everywhere (design system, section 5.4).
  static const Color noSurfaceTint = Color(0x00000000);
}

/// Material 3 `ColorScheme` roles, light mode (design system, section 3.2).
///
/// The seed `#14513D` is run through `ColorScheme.fromSeed` to prove the
/// luminance ladder is sane, then every role below is pinned with `copyWith`
/// so a future `material_color_utilities` change cannot move a shipped color.
abstract final class LightPalette {
  /// Deep herbarium green. Seed for the generated tonal palettes.
  static const Color seed = Color(0xFF14513D);

  static const Color surface = Color(0xFFFBFCFA);
  static const Color surfaceContainerLowest = Color(0xFFFFFFFF);
  static const Color surfaceContainerLow = Color(0xFFF4F6F2);
  static const Color surfaceContainer = Color(0xFFEEF1EB);
  static const Color surfaceContainerHigh = Color(0xFFE7EBE4);
  static const Color surfaceContainerHighest = Color(0xFFE1E5DD);
  static const Color surfaceDim = Color(0xFFDADED6);

  /// Equals [surface] in light mode. Dialog and menu ground.
  static const Color surfaceBright = Color(0xFFFBFCFA);

  static const Color onSurface = Color(0xFF161B17);
  static const Color onSurfaceVariant = Color(0xFF414A42);
  static const Color outline = Color(0xFF6C756C);
  static const Color outlineVariant = Color(0xFFC0C8BF);

  static const Color primary = Color(0xFF14513D);
  static const Color onPrimary = Color(0xFFFFFFFF);
  static const Color primaryContainer = Color(0xFFBCEDD7);
  static const Color onPrimaryContainer = Color(0xFF00291D);

  static const Color secondary = Color(0xFF2F5A78);
  static const Color onSecondary = Color(0xFFFFFFFF);
  static const Color secondaryContainer = Color(0xFFD3E4F1);
  static const Color onSecondaryContainer = Color(0xFF0A2E48);

  static const Color tertiary = Color(0xFF1D6A73);
  static const Color onTertiary = Color(0xFFFFFFFF);
  static const Color tertiaryContainer = Color(0xFFCFEAEE);
  static const Color onTertiaryContainer = Color(0xFF043F46);

  static const Color error = Color(0xFFA32617);
  static const Color onError = Color(0xFFFFFFFF);
  static const Color errorContainer = Color(0xFFFADAD3);
  static const Color onErrorContainer = Color(0xFF5C1409);

  static const Color inverseSurface = Color(0xFF2B312C);
  static const Color inverseOnSurface = Color(0xFFEFF2EB);
  static const Color inversePrimary = Color(0xFF8BD6B6);

  static const Color scrim = Color(0xFF000000);
  static const Color shadow = Color(0xFF000000);

  /// Scrim opacity behind dialogs and sheets in light mode.
  static const double scrimOpacity = 0.40;
}

/// Material 3 `ColorScheme` roles, dark mode (design system, section 3.3).
///
/// Dark is not an inverted light mode. The surface ramp takes larger tonal
/// steps because tonal separation is harder to see at low luminance, and the
/// accents are lifted in lightness and reduced in chroma so they do not bloom.
abstract final class DarkPalette {
  static const Color seed = LightPalette.seed;

  static const Color surface = Color(0xFF101311);
  static const Color surfaceContainerLowest = Color(0xFF0A0D0B);
  static const Color surfaceContainerLow = Color(0xFF181C19);
  static const Color surfaceContainer = Color(0xFF1C201D);
  static const Color surfaceContainerHigh = Color(0xFF262B27);
  static const Color surfaceContainerHighest = Color(0xFF313631);
  static const Color surfaceBright = Color(0xFF373C37);

  /// Equals [surface] in dark mode.
  static const Color surfaceDim = Color(0xFF101311);

  static const Color onSurface = Color(0xFFE2E6DF);
  static const Color onSurfaceVariant = Color(0xFFBFC8BE);
  static const Color outline = Color(0xFF8A938A);
  static const Color outlineVariant = Color(0xFF424A42);

  static const Color primary = Color(0xFF7FD6B0);
  static const Color onPrimary = Color(0xFF00382A);
  static const Color primaryContainer = Color(0xFF0F4535);
  static const Color onPrimaryContainer = Color(0xFF9CE7C4);

  static const Color secondary = Color(0xFF9CC3E4);
  static const Color onSecondary = Color(0xFF0A2E48);
  static const Color secondaryContainer = Color(0xFF123249);
  static const Color onSecondaryContainer = Color(0xFFCBE0F3);

  static const Color tertiary = Color(0xFF7ED3DD);
  static const Color onTertiary = Color(0xFF00363C);
  static const Color tertiaryContainer = Color(0xFF0C3D43);
  static const Color onTertiaryContainer = Color(0xFFA9E4EA);

  static const Color error = Color(0xFFF0A79A);
  static const Color onError = Color(0xFF5A140A);
  static const Color errorContainer = Color(0xFF5C1A10);
  static const Color onErrorContainer = Color(0xFFFFD9D0);

  static const Color inverseSurface = Color(0xFFE2E6DF);
  static const Color inverseOnSurface = Color(0xFF2B312C);
  static const Color inversePrimary = Color(0xFF14513D);

  static const Color scrim = Color(0xFF000000);
  static const Color shadow = Color(0xFF000000);

  /// Scrim opacity behind dialogs and sheets in dark mode.
  static const double scrimOpacity = 0.60;
}

/// The seven hue primitives that carry every product token, plus the handful
/// of fixed colors that do not follow a primitive (design system, section 3.4).
///
/// Meaning comes from the icon and the word. The hue is an index into a
/// meaning the label already states, never the statement itself.
abstract final class ProductPalette {
  // Green. A human affirmed it.
  static const Color greenContentLight = Color(0xFF1A6D4F);
  static const Color greenFillLight = Color(0xFFD3EFE1);
  static const Color greenOnFillLight = Color(0xFF063D2A);
  static const Color greenContentDark = Color(0xFF2CBB86);
  static const Color greenFillDark = Color(0xFF0E3B2B);
  static const Color greenOnFillDark = Color(0xFFA5E9CA);

  // Steel. A machine produced it.
  static const Color steelContentLight = Color(0xFF2F6594);
  static const Color steelFillLight = Color(0xFFD9E7F4);
  static const Color steelOnFillLight = Color(0xFF0B3554);
  static const Color steelContentDark = Color(0xFF78A9D4);
  static const Color steelFillDark = Color(0xFF14344B);
  static const Color steelOnFillDark = Color(0xFFB8D6F0);

  // Teal. An external authority.
  static const Color tealContentLight = Color(0xFF1D6A73);
  static const Color tealFillLight = Color(0xFFCFEAEE);
  static const Color tealOnFillLight = Color(0xFF043F46);
  static const Color tealContentDark = Color(0xFF31B4C3);
  static const Color tealFillDark = Color(0xFF0D383D);
  static const Color tealOnFillDark = Color(0xFFA9E4EA);

  // Ochre. Attention, not failure.
  static const Color ochreContentLight = Color(0xFF84580B);
  static const Color ochreFillLight = Color(0xFFF7E3B4);
  static const Color ochreOnFillLight = Color(0xFF4A3400);
  static const Color ochreContentDark = Color(0xFFE19512);
  static const Color ochreFillDark = Color(0xFF43310A);
  static const Color ochreOnFillDark = Color(0xFFF2D79B);

  // Oxide. A stop.
  static const Color oxideContentLight = Color(0xFFA83D28);
  static const Color oxideFillLight = Color(0xFFF8DDD6);
  static const Color oxideOnFillLight = Color(0xFF5C1B0E);
  static const Color oxideContentDark = Color(0xFFE1907F);
  static const Color oxideFillDark = Color(0xFF4E241B);
  static const Color oxideOnFillDark = Color(0xFFFFCFC3);

  // Slate. An observation, not a decision.
  static const Color slateContentLight = Color(0xFF546275);
  static const Color slateFillLight = Color(0xFFDFE4EB);
  static const Color slateOnFillLight = Color(0xFF2E3846);
  static const Color slateContentDark = Color(0xFF99A6B5);
  static const Color slateFillDark = Color(0xFF29313A);
  static const Color slateOnFillDark = Color(0xFFC8D3DF);

  // Clay. Shelved, not judged.
  static const Color clayContentLight = Color(0xFF6D5E52);
  static const Color clayFillLight = Color(0xFFE7E1DA);
  static const Color clayOnFillLight = Color(0xFF3E3630);
  static const Color clayContentDark = Color(0xFFB0A397);
  static const Color clayFillDark = Color(0xFF332D28);
  static const Color clayOnFillDark = Color(0xFFDED3C8);

  // Diff highlight fills. Body text sits directly on these, so they are tuned
  // against `onSurface` rather than against an on-fill color.
  static const Color diffAddedFillLight = Color(0xFFD6F2E4);
  static const Color diffAddedFillDark = Color(0xFF123B2C);
  static const Color diffChangedFillLight = Color(0xFFFBEBC8);
  static const Color diffChangedFillDark = Color(0xFF40300B);

  // Region overlay casings. A stroke drawn over an arbitrary photograph needs
  // a casing so it survives whatever pixel is behind it.
  static const Color regionCasingLight = Color(0xFFFFFFFF);
  static const Color regionCasingDark = Color(0xFF101311);

  /// Selection over the image is transient, so it is the one token that does
  /// not follow the mode.
  static const Color regionSelectedCore = Color(0xFFFFC02E);
  static const Color regionSelectedCasing = Color(0xFF101311);

  // Synthetic environment band. Retuned from the pair already shipping in
  // `workspace.dart`, which passed contrast but was not tokenized.
  static const Color environmentFillLight = Color(0xFFF7E3B4);
  static const Color environmentOnFillLight = Color(0xFF4A3400);
  static const Color environmentFillDark = Color(0xFF4A3608);
  static const Color environmentOnFillDark = Color(0xFFF2D79B);

  /// Reserved for the focus ring. Never used for status.
  static const Color focusRingLight = Color(0xFF0F5FA8);
  static const Color focusRingDark = Color(0xFF7FC4F5);

  /// Opacity of the disabled container fill over `onSurface`.
  static const double disabledContainerOpacity = 0.12;
}

/// The 4px base grid (design system, section 5.1).
///
/// Vertical rhythm inside a pane uses [space2], [space4], [space6] and
/// [space8] only. [space1], [space3] and [space5] are for internal component
/// construction.
abstract final class SpaceScale {
  static const double space0 = 0;
  static const double space1 = 4;
  static const double space2 = 8;
  static const double space3 = 12;
  static const double space4 = 16;
  static const double space5 = 20;
  static const double space6 = 24;
  static const double space8 = 32;
  static const double space10 = 40;
  static const double space12 = 48;

  /// Maximum. Above this, the layout is wrong.
  static const double space16 = 64;
}

/// Fixed sizes (design system, section 5.2).
abstract final class SizeScale {
  static const double iconInline = 20;
  static const double iconAction = 24;
  static const double iconDisplay = 40;

  /// Hit box for every interactive element, on every platform, always.
  static const double targetMin = 48;

  /// Smallest a control may look. Below this, pad the hit box transparently.
  static const double targetVisualMin = 40;

  static const double rowCompact = 72;
  static const double rowMedium = 64;
  static const double rowExpanded = 56;
  static const double appBar = 56;
  static const double rail = 80;
  static const double paneDetailMin = 400;

  /// Maximum measure for prose.
  static const double readingMax = 640;
}

/// The six corner radius steps we use out of M3's ten (section 5.3), and the
/// four stroke widths (section 5.9).
abstract final class ShapeScale {
  static const double radiusNone = 0;
  static const double radiusXs = 4;
  static const double radiusSm = 8;
  static const double radiusMd = 12;
  static const double radiusLg = 16;

  /// Effectively full. Avatars and the progress ring cap only. Prefer a
  /// `StadiumBorder` where the API takes a shape rather than a radius.
  static const double radiusFull = 999;

  static const double strokeHairline = 1;
  static const double strokeBoundary = 1;
  static const double strokeEmphasis = 2;
  static const double strokeStrong = 3;

  /// Focus ring geometry (section 5.8): a 2dp stroke, a 2dp gap in the parent
  /// surface color, and a radius of the component radius plus 4.
  static const double focusRingStroke = 2;
  static const double focusRingGap = 2;
  static const double focusRingRadiusOffset = 4;
}

/// The type scale (design system, section 4.2), in logical pixels.
abstract final class TypeScale {
  static const double displayLargeSize = 40;
  static const double displayMediumSize = 32;
  static const double displaySmallSize = 28;
  static const double headlineLargeSize = 28;
  static const double headlineMediumSize = 24;
  static const double headlineSmallSize = 20;
  static const double titleLargeSize = 18;
  static const double titleMediumSize = 16;
  static const double titleSmallSize = 14;
  static const double bodyLargeSize = 16;
  static const double bodyMediumSize = 14;
  static const double bodySmallSize = 12;
  static const double labelLargeSize = 14;
  static const double labelMediumSize = 12;
  static const double labelSmallSize = 11;

  static const double monoLiteralSize = 16;
  static const double monoLiteralDenseSize = 14;
  static const double monoIdentifierSize = 13;
  static const double monoDigestSize = 12;
  static const double monoCodeSize = 13;
}
