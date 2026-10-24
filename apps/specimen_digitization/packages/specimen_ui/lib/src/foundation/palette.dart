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

/// Provider-prescribed colours, scoped to the Google sign-in button.
///
/// The Light and Dark themes of the custom button on
/// https://developers.google.com/identity/branding-guidelines (fill, a 1 px
/// stroke and the label colour of each). The button's measurements and type
/// are in `google_sign_in_brand.dart`; this file keeps the colours because it
/// is the only one allowed to carry a colour literal.
abstract final class GoogleSignInPalette {
  static const Color fillLight = Color(0xFFFFFFFF);
  static const Color borderLight = Color(0xFF747775);
  static const Color labelLight = Color(0xFF1F1F1F);
  static const Color fillDark = Color(0xFF131314);
  static const Color borderDark = Color(0xFF8E918F);
  static const Color labelDark = Color(0xFFE3E3E3);
}

/// Exact seeds from the owner's SD_brand.png reference.
///
/// Seeds describe identity. Text and control boundaries use the accessible
/// derived roles below; the amber-to-iris gradient is decorative brand space.
abstract final class BrandPalette {
  static const Color obsidian = Color(0xFF0E0E11);
  static const Color paper = Color(0xFFFAF9F6);
  static const Color amber = Color(0xFFF5A45B);
  static const Color iris = Color(0xFF7B61FF);
  static const Color mist = Color(0xFFE6E6EA);

  static const Color irisContentLight = Color(0xFF5B46C4);
  static const Color irisFillLight = Color(0xFFEEEAFE);
  static const Color irisOnFillLight = Color(0xFF382477);
  static const Color irisContentDark = Color(0xFFB7A8FF);
  static const Color irisFillDark = Color(0xFF2E254E);
  static const Color irisOnFillDark = Color(0xFFE2DBFF);
}

/// Neutral surfaces, typography and boundaries, derived from the brand seeds.
abstract final class GroundPalette {
  static const Color groundLight = BrandPalette.paper;
  static const Color groundDark = BrandPalette.obsidian;
  static const Color paperLight = Color(0xFFFFFFFF);
  static const Color paperDark = Color(0xFF19191E);

  /// Neutral photograph letterboxes. These never carry a brand tint.
  static const Color matteLight = paperLight;
  static const Color matteDark = Color(0xFF25252B);

  static const Color inkLight = BrandPalette.obsidian;
  static const Color inkDark = BrandPalette.paper;
  static const Color inkSecondaryLight = Color(0xFF494950);
  static const Color inkSecondaryDark = Color(0xFFC4C4CC);
  static const Color inkTertiaryLight = Color(0xFF64646E);
  static const Color inkTertiaryDark = Color(0xFFAEAEB8);

  /// Decorative separation, never the only way to find a control.
  static const Color hairlineLight = BrandPalette.mist;
  static const Color hairlineDark = Color(0xFF36363E);
  static const Color boundaryLight = Color(0xFF82828C);
  static const Color boundaryDark = Color(0xFF858590);

  /// Disabled reasons stay readable; disabled controls do not fade their text.
  static const Color disabledContentLight = inkTertiaryLight;
  static const Color disabledContentDark = inkTertiaryDark;
  static const Color disabledOutlineLight = boundaryLight;
  static const Color disabledOutlineDark = boundaryDark;
  static const double disabledFillOpacityLight = 0.06;
  static const double disabledFillOpacityDark = 0.08;

  static const Color scrim = Color(0xFF000000);
  static const double scrimOpacityLight = 0.32;
  static const double scrimOpacityDark = 0.56;
  static const Color white = paperLight;
  static const Color transparent = Color(0x00000000);
}

/// Secondary brand emphasis. Use accessible iris roles for text and edges.
abstract final class AccentPalette {
  static const Color accent = BrandPalette.iris;
  static const Color onAccent = BrandPalette.obsidian;
}

/// Compatibility names for the former decorative field API.
///
/// No former hue survives. Amber, Iris and Mist are the only decorative
/// colours. Low opacities keep existing explicit field opt-ins restrained;
/// standard application themes continue to suppress all field placements.
abstract final class FieldPalette {
  static const Color sunLight = BrandPalette.amber;
  static const Color sunDark = BrandPalette.amber;
  static const double sunAlphaLight = 0.12;
  static const double sunAlphaDark = 0.045;
  static const Color violetLight = BrandPalette.iris;
  static const Color violetDark = BrandPalette.iris;
  static const double violetAlphaLight = 0.12;
  static const double violetAlphaDark = 0.045;
  static const Color roseLight = BrandPalette.iris;
  static const Color roseDark = BrandPalette.iris;
  static const double roseAlphaLight = 0.12;
  static const double roseAlphaDark = 0.045;
  static const Color mintLight = BrandPalette.mist;
  static const Color mintDark = BrandPalette.mist;
  static const double mintAlphaLight = 0.12;
  static const double mintAlphaDark = 0.045;
  static const Color emberLight = BrandPalette.amber;
  static const Color emberDark = BrandPalette.amber;
  static const double emberAlphaLight = 0.12;
  static const double emberAlphaDark = 0.045;
}

/// Glass fills, highlights, strokes and shadows (09 section 3.3).
///
/// Sigmas and opacities only; the recipe that assembles them is
/// `foundation/glass.dart`.
abstract final class GlassPalette {
  static const Color fillLight = GroundPalette.white;
  static const Color fillDark = GroundPalette.paperDark;

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
  static const Color shadowDark = GroundPalette.scrim;
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

/// Functional colour families and compatibility aliases.
///
/// Success, warning and error have distinct hues because they communicate
/// consequences. Processing and external references share Iris. Observations
/// and deferred work share neutrals; their labels and icons carry meaning.
abstract final class StatusPalette {
  // Success: a person affirmed it.
  static const Color greenContentLight = Color(0xFF236447);
  static const Color greenFillLight = Color(0xFFE1EFE7);
  static const Color greenOnFillLight = Color(0xFF17432F);
  static const Color greenContentDark = Color(0xFF8FCBA9);
  static const Color greenFillDark = Color(0xFF20392D);
  static const Color greenOnFillDark = Color(0xFFC7E8D5);

  // Informational emphasis: derived Iris, with no additional blue or teal.
  static const Color steelContentLight = BrandPalette.irisContentLight;
  static const Color steelFillLight = BrandPalette.irisFillLight;
  static const Color steelOnFillLight = BrandPalette.irisOnFillLight;
  static const Color steelContentDark = BrandPalette.irisContentDark;
  static const Color steelFillDark = BrandPalette.irisFillDark;
  static const Color steelOnFillDark = BrandPalette.irisOnFillDark;
  static const Color tealContentLight = steelContentLight;
  static const Color tealFillLight = steelFillLight;
  static const Color tealOnFillLight = steelOnFillLight;
  static const Color tealContentDark = steelContentDark;
  static const Color tealFillDark = steelFillDark;
  static const Color tealOnFillDark = steelOnFillDark;

  // Warning: warm amber relatives, never fluorescent or yellow-green.
  static const Color ochreContentLight = Color(0xFF805025);
  static const Color ochreFillLight = Color(0xFFFAE9D8);
  static const Color ochreOnFillLight = Color(0xFF573214);
  static const Color ochreContentDark = Color(0xFFF5BA83);
  static const Color ochreFillDark = Color(0xFF442D1D);
  static const Color ochreOnFillDark = Color(0xFFFFDDC0);

  // Error: reserved for blocking and destructive outcomes.
  static const Color oxideContentLight = Color(0xFFAC3C35);
  static const Color oxideFillLight = Color(0xFFF8E4E1);
  static const Color oxideOnFillLight = Color(0xFF6C2722);
  static const Color oxideContentDark = Color(0xFFF1A49A);
  static const Color oxideFillDark = Color(0xFF472824);
  static const Color oxideOnFillDark = Color(0xFFF9D8D2);

  // Neutral: classification alone does not earn another decorative hue.
  static const Color slateContentLight = GroundPalette.inkSecondaryLight;
  static const Color slateFillLight = BrandPalette.mist;
  static const Color slateOnFillLight = BrandPalette.obsidian;
  static const Color slateContentDark = GroundPalette.inkSecondaryDark;
  static const Color slateFillDark = GroundPalette.hairlineDark;
  static const Color slateOnFillDark = BrandPalette.paper;
  static const Color clayContentLight = slateContentLight;
  static const Color clayFillLight = slateFillLight;
  static const Color clayOnFillLight = slateOnFillLight;
  static const Color clayContentDark = slateContentDark;
  static const Color clayFillDark = slateFillDark;
  static const Color clayOnFillDark = slateOnFillDark;

  static const Color diffAddedFillLight = greenFillLight;
  static const Color diffAddedFillDark = greenFillDark;
  static const Color diffChangedFillLight = ochreFillLight;
  static const Color diffChangedFillDark = ochreFillDark;

  // Two-tone strokes remain visible on arbitrary photographic evidence.
  static const Color regionCasingLight = GroundPalette.white;
  static const Color regionCasingDark = BrandPalette.obsidian;
  static const Color regionSelectedCore = BrandPalette.iris;
  static const Color regionSelectedCasing = BrandPalette.obsidian;

  static const Color environmentFillLight = ochreFillLight;
  static const Color environmentOnFillLight = ochreOnFillLight;
  static const Color environmentFillDark = ochreFillDark;
  static const Color environmentOnFillDark = ochreOnFillDark;
}
