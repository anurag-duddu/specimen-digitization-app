/// Raw colour primitives for the design system.
///
/// This is the only file in the package or the application allowed to carry a
/// `Color(0x...)` literal (09 section 3; gate `no_color_literals`). Everything
/// else reads a role. Nothing here imports Flutter beyond `Color`, so the
/// primitives stay usable from a pure Dart test.
///
/// Neutral roles follow the adaptive reset. Status triples retain their
/// existing meanings; contrast tests cover text and actionable boundaries.
library;

// This file is a value table, not an API: each constant's meaning is its
// group's comment plus the role that reads it in `color.dart`. A doc comment
// per constant would restate the identifier and nothing else, so the rule is
// switched off here and only here.
// ignore_for_file: public_member_api_docs

import 'dart:ui' show Color;

/// Ground, ink and the neutral edges (09 section 3.1).
abstract final class GroundPalette {
  /// Neutral backgrounds keep evidence and status colour meaningful.
  static const Color groundLight = Color(0xFFFAFAFA);
  static const Color groundDark = Color(0xFF111111);

  /// Solid surface where glass is not warranted: list bodies, tables, fields.
  static const Color paperLight = Color(0xFFFFFFFF);
  static const Color paperDark = Color(0xFF181818);

  /// The letterbox behind a photograph. Lowest surface in light, highest in
  /// dark, so label paper reads as paper in both.
  static const Color matteLight = Color(0xFFFFFFFF);
  static const Color matteDark = Color(0xFF202020);

  /// Primary text, glyphs, the filled navigation disc, primary buttons.
  static const Color inkLight = Color(0xFF171717);
  static const Color inkDark = Color(0xFFF5F5F5);

  /// Supporting text, labels above fields, timestamps.
  static const Color inkSecondaryLight = Color(0xFF4D4D4D);
  static const Color inkSecondaryDark = Color(0xFFBDBDBD);

  /// Units, hints and placeholder text, above 4.5:1 on neutral surfaces.
  static const Color inkTertiaryLight = Color(0xFF666666);
  static const Color inkTertiaryDark = Color(0xFFA0A0A0);

  /// Decorative separation. 1 dp. Never a boundary, so it stays under 3:1.
  static const Color hairlineLight = Color(0xFFE0E0E0);
  static const Color hairlineDark = Color(0xFF303030);

  /// Actionable boundaries, above 3:1 on their neutral surfaces.
  static const Color boundaryLight = Color(0xFF808080);
  static const Color boundaryDark = Color(0xFF808080);

  /// Text and glyphs of a disabled control. A disabled control in this product
  /// states a server reason and has to stay readable (03 section 3.6).
  static const Color disabledContentLight = Color(0xFF666666);
  static const Color disabledContentDark = Color(0xFFA8A8A8);

  /// Edge of a disabled control, still discernible on a neutral surface.
  static const Color disabledOutlineLight = Color(0xFF808080);
  static const Color disabledOutlineDark = Color(0xFF808080);

  /// Opacity of the fill behind a disabled control, over [inkLight].
  static const double disabledFillOpacityLight = 0.06;
  static const double disabledFillOpacityDark = 0.08;

  /// Behind opaque modal surfaces.
  static const Color scrim = Color(0xFF000000);
  static const double scrimOpacityLight = 0.32;
  static const double scrimOpacityDark = 0.56;

  /// Pure white. The glass highlight and the light glass fill.
  static const Color white = Color(0xFFFFFFFF);

  /// Fully transparent. M3 blends `surfaceTint` into an elevated surface,
  /// which puts a cast on any panel next to a photograph, so the tint is
  /// switched off everywhere.
  static const Color transparent = Color(0x00000000);
}

/// The mark (09 section 3.4). One hue at one value in both modes.
abstract final class AccentPalette {
  /// The current position, the active marker, the mark. Never a fill, never a
  /// status, never a focus ring.
  static const Color accent = Color(0xFFE8FF47);

  /// Anything drawn on [accent].
  static const Color onAccent = Color(0xFF111214);
}

/// Light-field centres and their centre alpha (09 section 3.2).
///
/// A field is a radial gradient from the centre colour at the centre alpha to
/// fully transparent at its radius. Dark is not an inversion: the alphas drop
/// by more than half so the fields read as light in a dark room.
abstract final class FieldPalette {
  static const Color sunLight = Color(0xFFF2FF66);
  static const Color sunDark = Color(0xFFB7C700);
  static const double sunAlphaLight = 0.90;
  static const double sunAlphaDark = 0.32;

  static const Color violetLight = Color(0xFFCDBBFF);
  static const Color violetDark = Color(0xFF6E5AD1);
  static const double violetAlphaLight = 0.85;
  static const double violetAlphaDark = 0.40;

  static const Color roseLight = Color(0xFFFFB8D6);
  static const Color roseDark = Color(0xFFC4568F);
  static const double roseAlphaLight = 0.80;
  static const double roseAlphaDark = 0.36;

  static const Color mintLight = Color(0xFFA9F2D8);
  static const Color mintDark = Color(0xFF2FA07E);
  static const double mintAlphaLight = 0.85;
  static const double mintAlphaDark = 0.36;

  static const Color emberLight = Color(0xFFFFB466);
  static const Color emberDark = Color(0xFFC87A2C);
  static const double emberAlphaLight = 0.85;
  static const double emberAlphaDark = 0.36;
}

/// Glass fills, highlights, strokes and shadows (09 section 3.3).
///
/// Sigmas and opacities only; the recipe that assembles them is
/// `foundation/glass.dart`.
abstract final class GlassPalette {
  static const Color fillLight = GroundPalette.white;
  static const Color fillDark = Color(0xFF1C1E22);

  static const double flatSigma = 16;
  static const double flatFillOpacityLight = 0.62;
  static const double flatFillOpacityDark = 0.55;

  static const double floatingSigma = 20;
  static const double floatingFillOpacityLight = 0.66;
  static const double floatingFillOpacityDark = 0.58;

  static const double modalSigma = 24;
  static const double modalFillOpacityLight = 0.72;
  static const double modalFillOpacityDark = 0.66;

  /// A 1 dp inner line along the top edge only, drawn as a vertical gradient
  /// so it fades before the corners.
  static const Color highlight = GroundPalette.white;
  static const double highlightOpacityLight = 0.85;
  static const double highlightOpacityDark = 0.12;

  /// The pane's own edge: ink in light, white in dark.
  static const double strokeOpacityLight = 0.06;
  static const double strokeOpacityDark = 0.08;

  /// Shadows exist at the floating and modal levels only.
  static const Color shadowDark = Color(0xFF000000);
  static const double floatingShadowOpacityLight = 0.08;
  static const double floatingShadowOpacityDark = 0.24;
  static const double floatingShadowBlur = 16;
  static const double floatingShadowOffsetY = 4;

  static const double modalShadowOpacityLight = 0.12;
  static const double modalShadowOpacityDark = 0.32;
  static const double modalShadowBlur = 24;
  static const double modalShadowOffsetY = 8;

  /// What `GlassQuality.off` puts in place of the blur.
  static const double opaqueFallbackOpacity = 1;
}

/// The seven hue primitives that carry every status token, plus the fixed
/// colours that do not follow a primitive.
///
/// Carried from v1 (03 section 3.4) unchanged in value, as 09 section 3.5
/// requires: they pass the composite contrast test on the v2 surfaces because
/// `paper` and light glass are both lighter than the v1 surface ramp.
abstract final class StatusPalette {
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
  // against ink rather than against an on-fill colour.
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

  // Synthetic environment band.
  static const Color environmentFillLight = Color(0xFFF7E3B4);
  static const Color environmentOnFillLight = Color(0xFF4A3400);
  static const Color environmentFillDark = Color(0xFF4A3608);
  static const Color environmentOnFillDark = Color(0xFFF2D79B);
}
