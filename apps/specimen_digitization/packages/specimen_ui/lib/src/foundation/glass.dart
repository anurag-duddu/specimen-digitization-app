/// Glass levels and the quality setting (09 section 3.3).
///
/// Glass is a container, not a texture: a pane the user reads as one thing.
/// The budget the gate enforces is at most four panes per window and at most
/// one modal, and repeated items are never glass.
library;

import 'package:flutter/widgets.dart';

import 'palette.dart';

/// How much blur the device can afford.
///
/// The default per platform is a measurement, recorded in the verification
/// report, not a preference.
enum GlassQuality {
  /// Every sigma as specified.
  full,

  /// Every sigma halved.
  reduced,

  /// No blur at all: the pane is `paper` at 92 percent.
  off,
}

/// The three levels.
enum GlassLevel {
  /// In-flow panes: tile groups, the top bar, filter rows.
  flat,

  /// Navigation, popovers, menus, toasts, the sticky action bar.
  floating,

  /// Sheets and dialogs, which also carry the scrim.
  modal,
}

/// One glass level: the whole recipe, resolved for a mode.
@immutable
class UiGlassStyle {
  /// Binds one level's recipe.
  const UiGlassStyle({
    required this.level,
    required this.sigma,
    required this.fill,
    required this.highlight,
    required this.stroke,
    required this.shadow,
    required this.opaqueFallback,
  });

  /// Which level this is.
  final GlassLevel level;

  /// `ImageFilter.blur` sigma, before [GlassQuality] is applied.
  final double sigma;

  /// The translucent fill painted over the blur.
  final Color fill;

  /// The 1 dp inner line along the top edge, drawn as a vertical gradient so
  /// it fades before the corners.
  final Color highlight;

  /// The pane's own edge.
  final Color stroke;

  /// The drop shadow, or null at [GlassLevel.flat].
  final BoxShadow? shadow;

  /// What replaces the blur under [GlassQuality.off]: `paper` at 92 percent.
  final Color opaqueFallback;

  /// The sigma this level paints at under [quality]. Zero means no blur.
  double sigmaFor(GlassQuality quality) => switch (quality) {
    GlassQuality.full => sigma,
    GlassQuality.reduced => sigma / 2,
    GlassQuality.off => 0,
  };

  /// The fill this level paints under [quality].
  Color fillFor(GlassQuality quality) =>
      quality == GlassQuality.off ? opaqueFallback : fill;
}

/// The three levels, per mode.
@immutable
class UiGlass {
  /// Binds the three levels. Prefer [UiGlass.light] and [UiGlass.dark].
  const UiGlass({
    required this.flat,
    required this.floating,
    required this.modal,
  });

  /// In-flow panes.
  final UiGlassStyle flat;

  /// Panes that sit above the content.
  final UiGlassStyle floating;

  /// Sheets and dialogs.
  final UiGlassStyle modal;

  /// At most this many glass panes are on screen at once.
  static const int maxPanesPerWindow = 4;

  /// At most this many of them are modal.
  static const int maxModalPanes = 1;

  /// The light column of 09 section 3.3.
  static final UiGlass light = UiGlass(
    flat: UiGlassStyle(
      level: GlassLevel.flat,
      sigma: GlassPalette.flatSigma,
      fill: GlassPalette.fillLight.withValues(
        alpha: GlassPalette.flatFillOpacityLight,
      ),
      highlight: GlassPalette.highlight.withValues(
        alpha: GlassPalette.highlightOpacityLight,
      ),
      stroke: GroundPalette.inkLight.withValues(
        alpha: GlassPalette.strokeOpacityLight,
      ),
      shadow: null,
      opaqueFallback: GroundPalette.paperLight.withValues(
        alpha: GlassPalette.opaqueFallbackOpacity,
      ),
    ),
    floating: UiGlassStyle(
      level: GlassLevel.floating,
      sigma: GlassPalette.floatingSigma,
      fill: GlassPalette.fillLight.withValues(
        alpha: GlassPalette.floatingFillOpacityLight,
      ),
      highlight: GlassPalette.highlight.withValues(
        alpha: GlassPalette.highlightOpacityLight,
      ),
      stroke: GroundPalette.inkLight.withValues(
        alpha: GlassPalette.strokeOpacityLight,
      ),
      shadow: BoxShadow(
        color: GroundPalette.inkLight.withValues(
          alpha: GlassPalette.floatingShadowOpacityLight,
        ),
        blurRadius: GlassPalette.floatingShadowBlur,
        offset: const Offset(0, GlassPalette.floatingShadowOffsetY),
      ),
      opaqueFallback: GroundPalette.paperLight.withValues(
        alpha: GlassPalette.opaqueFallbackOpacity,
      ),
    ),
    modal: UiGlassStyle(
      level: GlassLevel.modal,
      sigma: GlassPalette.modalSigma,
      fill: GlassPalette.fillLight.withValues(
        alpha: GlassPalette.modalFillOpacityLight,
      ),
      highlight: GlassPalette.highlight.withValues(
        alpha: GlassPalette.highlightOpacityLight,
      ),
      stroke: GroundPalette.inkLight.withValues(
        alpha: GlassPalette.strokeOpacityLight,
      ),
      shadow: BoxShadow(
        color: GroundPalette.inkLight.withValues(
          alpha: GlassPalette.modalShadowOpacityLight,
        ),
        blurRadius: GlassPalette.modalShadowBlur,
        offset: const Offset(0, GlassPalette.modalShadowOffsetY),
      ),
      opaqueFallback: GroundPalette.paperLight.withValues(
        alpha: GlassPalette.opaqueFallbackOpacity,
      ),
    ),
  );

  /// The dark column. The pane is lifted by its highlight rather than by
  /// white.
  static final UiGlass dark = UiGlass(
    flat: UiGlassStyle(
      level: GlassLevel.flat,
      sigma: GlassPalette.flatSigma,
      fill: GlassPalette.fillDark.withValues(
        alpha: GlassPalette.flatFillOpacityDark,
      ),
      highlight: GlassPalette.highlight.withValues(
        alpha: GlassPalette.highlightOpacityDark,
      ),
      stroke: GroundPalette.white.withValues(
        alpha: GlassPalette.strokeOpacityDark,
      ),
      shadow: null,
      opaqueFallback: GroundPalette.paperDark.withValues(
        alpha: GlassPalette.opaqueFallbackOpacity,
      ),
    ),
    floating: UiGlassStyle(
      level: GlassLevel.floating,
      sigma: GlassPalette.floatingSigma,
      fill: GlassPalette.fillDark.withValues(
        alpha: GlassPalette.floatingFillOpacityDark,
      ),
      highlight: GlassPalette.highlight.withValues(
        alpha: GlassPalette.highlightOpacityDark,
      ),
      stroke: GroundPalette.white.withValues(
        alpha: GlassPalette.strokeOpacityDark,
      ),
      shadow: BoxShadow(
        color: GlassPalette.shadowDark.withValues(
          alpha: GlassPalette.floatingShadowOpacityDark,
        ),
        blurRadius: GlassPalette.floatingShadowBlur,
        offset: const Offset(0, GlassPalette.floatingShadowOffsetY),
      ),
      opaqueFallback: GroundPalette.paperDark.withValues(
        alpha: GlassPalette.opaqueFallbackOpacity,
      ),
    ),
    modal: UiGlassStyle(
      level: GlassLevel.modal,
      sigma: GlassPalette.modalSigma,
      fill: GlassPalette.fillDark.withValues(
        alpha: GlassPalette.modalFillOpacityDark,
      ),
      highlight: GlassPalette.highlight.withValues(
        alpha: GlassPalette.highlightOpacityDark,
      ),
      stroke: GroundPalette.white.withValues(
        alpha: GlassPalette.strokeOpacityDark,
      ),
      shadow: BoxShadow(
        color: GlassPalette.shadowDark.withValues(
          alpha: GlassPalette.modalShadowOpacityDark,
        ),
        blurRadius: GlassPalette.modalShadowBlur,
        offset: const Offset(0, GlassPalette.modalShadowOffsetY),
      ),
      opaqueFallback: GroundPalette.paperDark.withValues(
        alpha: GlassPalette.opaqueFallbackOpacity,
      ),
    ),
  );

  /// The style for [level].
  UiGlassStyle operator [](GlassLevel level) => switch (level) {
    GlassLevel.flat => flat,
    GlassLevel.floating => floating,
    GlassLevel.modal => modal,
  };

  /// Every level, by name.
  Map<String, UiGlassStyle> get all => <String, UiGlassStyle>{
    for (final GlassLevel level in GlassLevel.values) level.name: this[level],
  };
}
