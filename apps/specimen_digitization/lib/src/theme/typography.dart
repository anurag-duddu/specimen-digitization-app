/// The type scale and the monospace roles (design system, sections 4.1 to 4.3).
///
/// One family, IBM Plex Sans, fills both M3 typeface slots; hierarchy is
/// carried by weight and size alone. Verbatim transcription, identifiers and
/// digests are set in JetBrains Mono, whose dotted zero and disambiguated
/// `1`, `l`, `I` keep a literal reading readable as evidence.
///
/// Line heights are stated as the design system states them, target pixels
/// divided by the font size, so the table can be checked against the document
/// without arithmetic.
library;

import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import 'tokens.dart';

/// Tabular figures, so a changed digit is visible by position.
const List<FontFeature> _tabular = <FontFeature>[FontFeature.tabularFigures()];

/// Tabular figures with code ligatures off. A ligature replaces a character
/// sequence with one glyph, which is precisely wrong for verbatim text.
const List<FontFeature> _verbatim = <FontFeature>[
  FontFeature.tabularFigures(),
  FontFeature.disable('liga'),
  FontFeature.disable('calt'),
];

/// The type scale, before the family is applied.
///
/// Colors are deliberately absent: `ThemeData` derives them from the
/// `ColorScheme` through `Typography.material2021`.
TextTheme _scale() => const TextTheme(
  displayLarge: TextStyle(
    fontSize: TypeScale.displayLargeSize,
    fontWeight: FontWeight.w600,
    height: 48 / TypeScale.displayLargeSize,
    letterSpacing: -0.4,
  ),
  displayMedium: TextStyle(
    fontSize: TypeScale.displayMediumSize,
    fontWeight: FontWeight.w600,
    height: 40 / TypeScale.displayMediumSize,
    letterSpacing: -0.3,
  ),
  displaySmall: TextStyle(
    fontSize: TypeScale.displaySmallSize,
    fontWeight: FontWeight.w600,
    height: 36 / TypeScale.displaySmallSize,
    letterSpacing: -0.2,
  ),
  headlineLarge: TextStyle(
    fontSize: TypeScale.headlineLargeSize,
    fontWeight: FontWeight.w600,
    height: 36 / TypeScale.headlineLargeSize,
    letterSpacing: -0.2,
  ),
  headlineMedium: TextStyle(
    fontSize: TypeScale.headlineMediumSize,
    fontWeight: FontWeight.w600,
    height: 32 / TypeScale.headlineMediumSize,
    letterSpacing: -0.15,
  ),
  headlineSmall: TextStyle(
    fontSize: TypeScale.headlineSmallSize,
    fontWeight: FontWeight.w600,
    height: 28 / TypeScale.headlineSmallSize,
    letterSpacing: -0.1,
  ),
  titleLarge: TextStyle(
    fontSize: TypeScale.titleLargeSize,
    fontWeight: FontWeight.w600,
    height: 26 / TypeScale.titleLargeSize,
    letterSpacing: 0,
  ),
  titleMedium: TextStyle(
    fontSize: TypeScale.titleMediumSize,
    fontWeight: FontWeight.w600,
    height: 24 / TypeScale.titleMediumSize,
    letterSpacing: 0.05,
  ),
  titleSmall: TextStyle(
    fontSize: TypeScale.titleSmallSize,
    fontWeight: FontWeight.w600,
    height: 20 / TypeScale.titleSmallSize,
    letterSpacing: 0.05,
  ),
  bodyLarge: TextStyle(
    fontSize: TypeScale.bodyLargeSize,
    fontWeight: FontWeight.w400,
    height: 26 / TypeScale.bodyLargeSize,
    letterSpacing: 0,
  ),
  bodyMedium: TextStyle(
    fontSize: TypeScale.bodyMediumSize,
    fontWeight: FontWeight.w400,
    height: 22 / TypeScale.bodyMediumSize,
    letterSpacing: 0,
  ),
  bodySmall: TextStyle(
    fontSize: TypeScale.bodySmallSize,
    fontWeight: FontWeight.w400,
    height: 18 / TypeScale.bodySmallSize,
    letterSpacing: 0.1,
  ),
  labelLarge: TextStyle(
    fontSize: TypeScale.labelLargeSize,
    fontWeight: FontWeight.w600,
    height: 20 / TypeScale.labelLargeSize,
    letterSpacing: 0.1,
  ),
  labelMedium: TextStyle(
    fontSize: TypeScale.labelMediumSize,
    fontWeight: FontWeight.w600,
    height: 16 / TypeScale.labelMediumSize,
    letterSpacing: 0.3,
  ),
  labelSmall: TextStyle(
    fontSize: TypeScale.labelSmallSize,
    fontWeight: FontWeight.w600,
    height: 16 / TypeScale.labelSmallSize,
    letterSpacing: 0.4,
  ),
);

/// Whether the IBM Plex Sans and JetBrains Mono files are bundled under
/// `assets/google_fonts/`.
///
/// The design system requires both families to be bundled and
/// `GoogleFonts.config.allowRuntimeFetching` to be false, because collection
/// rooms have unreliable networks and a reviewer must never wait on
/// fonts.google.com to read a label. Committing the font binaries is a
/// separate change, so until they land this stays false and the product
/// renders in the platform sans and the platform monospace, with the font
/// features that make a transcription readable applied either way.
///
/// Flip this to true in the same change that adds the assets, the
/// `flutter: assets:` entry and the OFL license registration.
bool bundledProductFonts = false;

/// Monospace fallbacks, in the order a platform is likely to have them. Every
/// one of them disambiguates `1`, `l` and `I` better than a proportional face,
/// which is the property the literal roles depend on.
const List<String> _monoFallback = <String>[
  'JetBrains Mono',
  'SF Mono',
  'Menlo',
  'Consolas',
  'Roboto Mono',
  'monospace',
];

final Map<bool, TextTheme> _sansCache = <bool, TextTheme>{};

/// The product `TextTheme`: the scale, in IBM Plex Sans once the family is
/// bundled and in the platform sans until then.
///
/// Built once per process per mode. `google_fonts` resolves a family the first
/// time a style is created, so rebuilding the theme on every frame would
/// repeat that work for no benefit.
TextTheme specimenTextTheme() => _sansCache.putIfAbsent(
  bundledProductFonts,
  () => bundledProductFonts
      ? GoogleFonts.ibmPlexSansTextTheme(_scale())
      : _scale(),
);

/// The monospace roles (design system, section 4.3).
///
/// These are deliberately not `TextTheme` roles: a call site should not be
/// able to reach a verbatim style by accident.
@immutable
class SpecimenTypography extends ThemeExtension<SpecimenTypography> {
  const SpecimenTypography({
    required this.literal,
    required this.literalDense,
    required this.identifier,
    required this.digest,
    required this.code,
  });

  /// Verbatim label transcription in a reading card.
  final TextStyle literal;

  /// Verbatim transcription inside a field row's literal layer.
  final TextStyle literalDense;

  /// Specimen IDs, catalog numbers, region IDs, revision numbers.
  final TextStyle identifier;

  /// Digests, artifact IDs, lease IDs, mutation keys. Always truncated to the
  /// first twelve characters with a copy control beside them.
  final TextStyle digest;

  /// The raw evidence escape hatch, on `surfaceContainerHighest`.
  final TextStyle code;

  static final Map<bool, SpecimenTypography> _cache =
      <bool, SpecimenTypography>{};

  /// The monospace roles. Identical in both modes: only the color, which
  /// `ThemeData` supplies, differs.
  static SpecimenTypography standard() => _cache.putIfAbsent(
    bundledProductFonts,
    () => SpecimenTypography(
      literal: _mono(
        size: TypeScale.monoLiteralSize,
        weight: FontWeight.w400,
        lineHeight: 26,
        tracking: 0,
        features: _verbatim,
      ),
      literalDense: _mono(
        size: TypeScale.monoLiteralDenseSize,
        weight: FontWeight.w400,
        lineHeight: 22,
        tracking: 0,
        features: _verbatim,
      ),
      identifier: _mono(
        size: TypeScale.monoIdentifierSize,
        weight: FontWeight.w500,
        lineHeight: 20,
        tracking: 0.2,
        features: _tabular,
      ),
      digest: _mono(
        size: TypeScale.monoDigestSize,
        weight: FontWeight.w400,
        lineHeight: 18,
        tracking: 0.2,
        features: _tabular,
      ),
      code: _mono(
        size: TypeScale.monoCodeSize,
        weight: FontWeight.w400,
        lineHeight: 20,
        tracking: 0,
        features: _tabular,
      ),
    ),
  );

  /// One monospace role, in JetBrains Mono once the family is bundled and in
  /// the platform monospace until then. The font features travel either way.
  static TextStyle _mono({
    required double size,
    required FontWeight weight,
    required double lineHeight,
    required double tracking,
    required List<FontFeature> features,
  }) {
    if (bundledProductFonts) {
      return GoogleFonts.jetBrainsMono(
        fontSize: size,
        fontWeight: weight,
        height: lineHeight / size,
        letterSpacing: tracking,
        fontFeatures: features,
      );
    }
    return TextStyle(
      fontFamily: _monoFallback.first,
      fontFamilyFallback: _monoFallback,
      fontSize: size,
      fontWeight: weight,
      height: lineHeight / size,
      letterSpacing: tracking,
      fontFeatures: features,
    );
  }

  @override
  SpecimenTypography copyWith({
    TextStyle? literal,
    TextStyle? literalDense,
    TextStyle? identifier,
    TextStyle? digest,
    TextStyle? code,
  }) => SpecimenTypography(
    literal: literal ?? this.literal,
    literalDense: literalDense ?? this.literalDense,
    identifier: identifier ?? this.identifier,
    digest: digest ?? this.digest,
    code: code ?? this.code,
  );

  @override
  SpecimenTypography lerp(SpecimenTypography? other, double t) {
    if (other == null) return this;
    return SpecimenTypography(
      literal: TextStyle.lerp(literal, other.literal, t)!,
      literalDense: TextStyle.lerp(literalDense, other.literalDense, t)!,
      identifier: TextStyle.lerp(identifier, other.identifier, t)!,
      digest: TextStyle.lerp(digest, other.digest, t)!,
      code: TextStyle.lerp(code, other.code, t)!,
    );
  }
}
