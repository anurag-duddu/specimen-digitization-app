/// The type scale (09 section 4.2) and the Material bridge (09 section 4.3).
///
/// One family carries the whole product. Hierarchy comes from size and weight:
/// numerals go light as they go large, units are small and tracked, and
/// everything else is sentence case.
///
/// Weight is set with `FontVariation('wght', n)` because the faces are
/// variable, with `fontWeight` mirrored so a platform fallback face picks a
/// sensible weight if the asset ever fails to load.
library;

import 'package:flutter/widgets.dart';

import 'fonts.dart';

/// Tabular figures, so a changed digit is visible by position.
const List<FontFeature> _tabular = <FontFeature>[FontFeature.tabularFigures()];

/// Tabular figures with ligatures and contextual alternates off. A ligature
/// replaces two characters with one glyph, which is exactly wrong for
/// verbatim evidence (09 section 4.1).
const List<FontFeature> _verbatim = <FontFeature>[
  FontFeature.tabularFigures(),
  FontFeature.disable('liga'),
  FontFeature.disable('calt'),
];

/// The nearest `FontWeight` to a variable `wght` axis value.
///
/// Mirrored onto every style so that a fallback face, which has no axis,
/// still renders at the right density.
FontWeight _mirror(int wght) => switch (wght) {
  <= 150 => FontWeight.w100,
  <= 250 => FontWeight.w200,
  <= 350 => FontWeight.w300,
  <= 450 => FontWeight.w400,
  <= 550 => FontWeight.w500,
  <= 650 => FontWeight.w600,
  <= 750 => FontWeight.w700,
  <= 850 => FontWeight.w800,
  _ => FontWeight.w900,
};

/// One role of the proportional scale.
TextStyle _sans({
  required double size,
  required int wght,
  required double line,
  required double tracking,
  List<FontFeature>? features,
}) => TextStyle(
  fontFamily: UiFonts.sans,
  package: UiFonts.package,
  fontSize: size,
  fontWeight: _mirror(wght),
  fontVariations: <FontVariation>[FontVariation('wght', wght.toDouble())],
  height: line,
  letterSpacing: tracking * size,
  fontFeatures: features,
);

/// One monospace role.
TextStyle _mono({
  required double size,
  required double line,
  required double tracking,
  required List<FontFeature> features,
}) => TextStyle(
  fontFamily: UiFonts.mono,
  package: UiFonts.package,
  fontSize: size,
  fontWeight: _mirror(400),
  fontVariations: const <FontVariation>[FontVariation('wght', 400)],
  height: line,
  letterSpacing: tracking * size,
  fontFeatures: features,
);

/// The monospace roles (03 section 4.3, set in Geist Mono by 09 section 4.2).
///
/// These are deliberately not roles of the proportional scale: a call site
/// should not be able to reach a verbatim style by accident.
@immutable
class UiMonoType {
  /// Binds the five monospace roles.
  const UiMonoType({
    required this.literal,
    required this.literalDense,
    required this.identifier,
    required this.digest,
    required this.code,
  });

  /// Verbatim label transcription in a reading card.
  final TextStyle literal;

  /// Verbatim transcription inside a field row's layers.
  final TextStyle literalDense;

  /// Specimen ids, catalogue numbers, region ids, version numbers.
  final TextStyle identifier;

  /// Checksums, evidence file ids, mutation keys.
  final TextStyle digest;

  /// The raw evidence escape hatch.
  final TextStyle code;

  /// The standard set. Identical in both modes: only the colour differs, and
  /// the colour comes from the surrounding `DefaultTextStyle`.
  static final UiMonoType standard = UiMonoType(
    literal: _mono(size: 15, line: 1.45, tracking: 0, features: _verbatim),
    literalDense: _mono(size: 13, line: 1.40, tracking: 0, features: _verbatim),
    identifier: _mono(size: 13, line: 1.40, tracking: 0.01, features: _tabular),
    digest: _mono(size: 12, line: 1.35, tracking: 0.01, features: _tabular),
    code: _mono(size: 13, line: 1.45, tracking: 0, features: _tabular),
  );

  /// Every monospace role, by the name 09 gives it.
  Map<String, TextStyle> get all => <String, TextStyle>{
    'mono.literal': literal,
    'mono.literalDense': literalDense,
    'mono.identifier': identifier,
    'mono.digest': digest,
    'mono.code': code,
  };
}

/// Every type role in the product.
@immutable
class UiType {
  /// Binds every role. Prefer [UiType.standard].
  const UiType({
    required this.displayHero,
    required this.displayLarge,
    required this.displayMedium,
    required this.headline,
    required this.titleLarge,
    required this.title,
    required this.bodyLarge,
    required this.body,
    required this.bodySmall,
    required this.label,
    required this.labelSmall,
    required this.unit,
    required this.mono,
  });

  /// One number per window: the count that matters, a distance, a total.
  final TextStyle displayHero;

  /// Tile numerals.
  final TextStyle displayLarge;

  /// Section numerals, the record count in the queue header.
  final TextStyle displayMedium;

  /// Screen titles.
  final TextStyle headline;

  /// Pane titles, sheet titles.
  final TextStyle titleLarge;

  /// Row titles, card titles, button labels at `lg`.
  final TextStyle title;

  /// Reading text on wide windows.
  final TextStyle bodyLarge;

  /// Default text.
  final TextStyle body;

  /// Secondary lines in rows, help text.
  final TextStyle bodySmall;

  /// Field labels, chip text, button labels at `md`. Sentence case.
  final TextStyle label;

  /// Badges, key caps, navigation labels.
  final TextStyle labelSmall;

  /// The upper case unit beside a numeral. The only upper case in the
  /// product, and the reason the gate for upper case has an exception.
  final TextStyle unit;

  /// The monospace roles.
  final UiMonoType mono;

  /// The scale in 09 section 4.2. Identical in both modes.
  static final UiType standard = UiType(
    displayHero: _sans(
      size: 64,
      wght: 200,
      line: 1.00,
      tracking: -0.020,
      features: _tabular,
    ),
    displayLarge: _sans(
      size: 48,
      wght: 300,
      line: 1.05,
      tracking: -0.020,
      features: _tabular,
    ),
    displayMedium: _sans(
      size: 36,
      wght: 300,
      line: 1.10,
      tracking: -0.015,
      features: _tabular,
    ),
    headline: _sans(size: 28, wght: 400, line: 1.15, tracking: -0.010),
    titleLarge: _sans(size: 22, wght: 500, line: 1.20, tracking: 0),
    title: _sans(size: 17, wght: 500, line: 1.25, tracking: 0),
    bodyLarge: _sans(size: 17, wght: 400, line: 1.45, tracking: 0),
    body: _sans(size: 15, wght: 400, line: 1.45, tracking: 0),
    bodySmall: _sans(size: 13, wght: 400, line: 1.40, tracking: 0.005),
    label: _sans(size: 13, wght: 500, line: 1.20, tracking: 0.020),
    labelSmall: _sans(size: 11, wght: 500, line: 1.20, tracking: 0.030),
    unit: _sans(size: 12, wght: 400, line: 1.00, tracking: 0.080),
    mono: UiMonoType.standard,
  );

  /// Every proportional role, by the name 09 gives it.
  Map<String, TextStyle> get all => <String, TextStyle>{
    'display.hero': displayHero,
    'display.large': displayLarge,
    'display.medium': displayMedium,
    'headline': headline,
    'title.large': titleLarge,
    'title': title,
    'body.large': bodyLarge,
    'body': body,
    'body.small': bodySmall,
    'label': label,
    'label.small': labelSmall,
    'unit': unit,
  };

  /// Every role, proportional and monospace, by name.
  Map<String, TextStyle> get allRoles => <String, TextStyle>{
    ...all,
    ...mono.all,
  };

  /// The Material bridge (09 section 4.3) lives on `UiThemeData` rather than
  /// here.
  ///
  /// `TextTheme` is declared in `package:flutter/material.dart`, and nothing
  /// in `foundation/` may import it except `theme.dart` (10 section 8, gate
  /// `layering`). `UiThemeData.toTextTheme()` maps every role below onto the
  /// Material slot 09 section 4.3 names for it.

  /// The specimen line that proves Geist Mono disambiguates its characters.
  ///
  /// Rendered at [UiMonoType.literal] on the foundation gallery page and
  /// pinned by that golden (09 section 4.1). If a pair stops being distinct,
  /// the golden is where it shows.
  static const String monoSpecimen = '0O 1lI 5S 2Z 8B';
}
