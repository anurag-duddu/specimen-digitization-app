/// The type scale and the monospace roles, as names over `package:specimen_ui`.
///
/// Geist carries everything proportional and Geist Mono carries every verbatim
/// role (09 section 4). Both ship as package assets, so the v1
/// `bundledProductFonts` flag is gone along with `google_fonts`: there is no
/// state left for it to describe, and no runtime fetch left to guard.
library;

import 'package:flutter/material.dart';
import 'package:specimen_ui/specimen_ui.dart';

/// The product `TextTheme`: the scale in 09 section 4.2, mapped onto the
/// Material slots by the bridge in 09 section 4.3.
TextTheme specimenTextTheme() => UiThemeData.light().toTextTheme();

/// The monospace roles (09 section 4.2), as a `ThemeExtension`.
///
/// Still an extension rather than a plain token group, because the screens and
/// patterns of this wave reach them through `context.mono`, which reads the
/// theme. They are values from `UiMonoType`; nothing is defined here.
@immutable
class SpecimenTypography extends ThemeExtension<SpecimenTypography> {
  /// Binds the five monospace roles.
  const SpecimenTypography({
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

  /// Checksums, evidence file ids, mutation keys. Always truncated to the
  /// first twelve characters with a copy control beside them.
  final TextStyle digest;

  /// The raw evidence escape hatch.
  final TextStyle code;

  /// The monospace roles. Identical in both modes: only the colour, which
  /// `ThemeData` supplies, differs.
  static SpecimenTypography standard() {
    final UiMonoType mono = UiMonoType.standard;
    return SpecimenTypography(
      literal: mono.literal,
      literalDense: mono.literalDense,
      identifier: mono.identifier,
      digest: mono.digest,
      code: mono.code,
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
