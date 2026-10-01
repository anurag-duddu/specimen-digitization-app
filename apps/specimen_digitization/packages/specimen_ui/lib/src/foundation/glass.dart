/// Surface levels and legacy appearance preferences.
///
/// Standard recipes are opaque, neutral and shadowless at every level.
/// Quality values remain readable for persisted preferences and custom recipes.
library;

import 'package:flutter/widgets.dart';

import 'palette.dart';

/// A retained preference for custom surface recipes.
///
/// [UiGlass.light] and [UiGlass.dark] stay flat in every mode.
enum GlassQuality {
  /// Every sigma as specified.
  full,

  /// Every sigma halved.
  reduced,

  /// No blur at all: the pane is opaque `paper` with a hairline edge.
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

  /// What replaces the blur under [GlassQuality.off]: opaque `paper`.
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

  /// Neutral, opaque surfaces in light mode. Legacy quality settings do not
  /// reintroduce blur, highlights or shadows.
  static final UiGlass light = _flatSet(
    GroundPalette.paperLight,
    GroundPalette.hairlineLight,
  );

  /// The same hierarchy in dark mode, without a coloured cast.
  static final UiGlass dark = _flatSet(
    GroundPalette.paperDark,
    GroundPalette.hairlineDark,
  );

  static UiGlass _flatSet(Color paper, Color edge) {
    UiGlassStyle style(GlassLevel level) => UiGlassStyle(
      level: level,
      sigma: 0,
      fill: paper,
      highlight: GroundPalette.transparent,
      stroke: edge,
      shadow: null,
      opaqueFallback: paper,
    );
    return UiGlass(
      flat: style(GlassLevel.flat),
      floating: style(GlassLevel.floating),
      modal: style(GlassLevel.modal),
    );
  }

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
