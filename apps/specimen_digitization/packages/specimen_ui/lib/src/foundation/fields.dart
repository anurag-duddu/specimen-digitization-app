/// Light fields and sky presets (09 section 3.2).
///
/// A field is a radial gradient from a centre colour at a centre alpha to
/// fully transparent at its radius. Fields are painted once, behind
/// everything, by `FieldLayer`. Nothing else in the product paints a gradient.
library;

import 'package:flutter/widgets.dart';

import 'palette.dart';

/// The five named fields.
enum UiFieldName {
  /// Acid yellow.
  sun,

  /// Lavender.
  violet,

  /// Rose.
  rose,

  /// Mint.
  mint,

  /// Warm amber.
  ember,
}

/// One field: a centre colour and the alpha it carries at its centre.
///
/// The alpha falls from [centreAlpha] to zero at the placement's radius on
/// the Gaussian profile in `FieldPainter.profile`. The values here are the
/// centre, which is what the composite contrast gate measures against
/// (09 section 3.7).
@immutable
class UiFieldStyle {
  /// Binds a centre colour to its centre alpha.
  const UiFieldStyle({required this.centre, required this.centreAlpha});

  /// The colour at the centre of the gradient.
  final Color centre;

  /// The alpha at the centre. Zero at the radius.
  final double centreAlpha;

  /// The opaque colour at the centre of this field over [background].
  ///
  /// The brightest or darkest point the field can put under a text role, and
  /// therefore one of the two extremes the contrast gate composites against.
  Color extremeOver(Color background) =>
      Color.alphaBlend(centre.withValues(alpha: centreAlpha), background);
}

/// Where one field sits inside a window, as a fraction of the window.
@immutable
class UiFieldPlacement {
  /// Places [field] at ([x], [y]) with radius [radius], all as fractions of
  /// the window, scaled to [alphaScale] of the field's own centre alpha.
  const UiFieldPlacement({
    required this.field,
    required this.x,
    required this.y,
    required this.radius,
    this.alphaScale = 1,
  });

  /// Which of the five fields this places.
  final UiFieldName field;

  /// Horizontal centre, as a fraction of the window's width.
  final double x;

  /// Vertical centre, as a fraction of the window's height.
  final double y;

  /// Radius as a fraction of the window's **longer** side.
  ///
  /// 09 section 3.2 holds this between 45 and 70 percent. It was a fraction
  /// of the shorter side until the presets were measured at real windows: on
  /// a 390 by 844 phone that put the sun field's half intensity point 7
  /// percent of the way down the window, which reads as a spot in a corner
  /// rather than as light. On the longer side the same fractions reach
  /// between a quarter and a half of every window in the size class table.
  final double radius;

  /// A multiplier on the field's centre alpha, for a preset that wants the
  /// same hue quieter.
  final double alphaScale;
}

/// The three sky presets. A field is placed by preset per surface role, never
/// per screen.
enum SkyPreset {
  /// Sign-in, queue, intake, sources, help and empty states.
  home,

  /// The workbench, the region editor and the large-record fallback.
  work,

  /// Sheets, dialogs, popovers and toasts. They blur what is beneath them
  /// instead of carrying a field of their own.
  none,
}

/// The five fields and the three presets, per mode.
@immutable
class UiFields {
  /// Binds the five fields. Prefer [UiFields.light] and [UiFields.dark].
  const UiFields({
    required this.sun,
    required this.violet,
    required this.rose,
    required this.mint,
    required this.ember,
  });

  /// Acid yellow.
  final UiFieldStyle sun;

  /// Lavender.
  final UiFieldStyle violet;

  /// Rose.
  final UiFieldStyle rose;

  /// Mint.
  final UiFieldStyle mint;

  /// Warm amber.
  final UiFieldStyle ember;

  /// The light column of 09 section 3.2.
  static const UiFields light = UiFields(
    sun: UiFieldStyle(
      centre: FieldPalette.sunLight,
      centreAlpha: FieldPalette.sunAlphaLight,
    ),
    violet: UiFieldStyle(
      centre: FieldPalette.violetLight,
      centreAlpha: FieldPalette.violetAlphaLight,
    ),
    rose: UiFieldStyle(
      centre: FieldPalette.roseLight,
      centreAlpha: FieldPalette.roseAlphaLight,
    ),
    mint: UiFieldStyle(
      centre: FieldPalette.mintLight,
      centreAlpha: FieldPalette.mintAlphaLight,
    ),
    ember: UiFieldStyle(
      centre: FieldPalette.emberLight,
      centreAlpha: FieldPalette.emberAlphaLight,
    ),
  );

  /// The dark column. Not an inversion: the alphas drop by more than half so
  /// the fields read as light in a dark room rather than as coloured paint.
  static const UiFields dark = UiFields(
    sun: UiFieldStyle(
      centre: FieldPalette.sunDark,
      centreAlpha: FieldPalette.sunAlphaDark,
    ),
    violet: UiFieldStyle(
      centre: FieldPalette.violetDark,
      centreAlpha: FieldPalette.violetAlphaDark,
    ),
    rose: UiFieldStyle(
      centre: FieldPalette.roseDark,
      centreAlpha: FieldPalette.roseAlphaDark,
    ),
    mint: UiFieldStyle(
      centre: FieldPalette.mintDark,
      centreAlpha: FieldPalette.mintAlphaDark,
    ),
    ember: UiFieldStyle(
      centre: FieldPalette.emberDark,
      centreAlpha: FieldPalette.emberAlphaDark,
    ),
  );

  /// The field named by [name].
  UiFieldStyle operator [](UiFieldName name) => switch (name) {
    UiFieldName.sun => sun,
    UiFieldName.violet => violet,
    UiFieldName.rose => rose,
    UiFieldName.mint => mint,
    UiFieldName.ember => ember,
  };

  /// Every field, by the name 09 gives it.
  Map<String, UiFieldStyle> get all => <String, UiFieldStyle>{
    for (final UiFieldName name in UiFieldName.values) name.name: this[name],
  };

  /// The placements of [preset]. Identical in both modes; only the colours
  /// and alphas differ.
  List<UiFieldPlacement> sky(SkyPreset preset) => switch (preset) {
    SkyPreset.home => _home,
    SkyPreset.work => _work,
    SkyPreset.none => const <UiFieldPlacement>[],
  };

  static const List<UiFieldPlacement> _home = <UiFieldPlacement>[
    UiFieldPlacement(field: UiFieldName.sun, x: 0.18, y: 0.06, radius: 0.55),
    UiFieldPlacement(field: UiFieldName.violet, x: 0.92, y: 0.28, radius: 0.60),
    UiFieldPlacement(field: UiFieldName.rose, x: 0.70, y: 0.96, radius: 0.50),
  ];

  static const List<UiFieldPlacement> _work = <UiFieldPlacement>[
    UiFieldPlacement(
      field: UiFieldName.violet,
      x: 1.00,
      y: 0.00,
      radius: 0.45,
      alphaScale: 0.60,
    ),
  ];

  /// How far a field stays clear of the photograph matte (09 section 2,
  /// principle 1). A colour cast on a faded label is a data error.
  static const double matteExclusion = 24;
}
