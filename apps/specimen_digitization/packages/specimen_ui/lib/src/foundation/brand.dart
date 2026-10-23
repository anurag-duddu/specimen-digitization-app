/// Brand identity and its accessible secondary emphasis.
library;

import 'package:flutter/widgets.dart';

import 'color.dart';
import 'palette.dart';

/// The brand contract, separate from functional status colours.
///
/// The hero gradient is decoration. [secondary] is the accessible Iris family
/// used for selected controls, links and information; [iris] alone is a seed,
/// not a general-purpose foreground on light surfaces.
@immutable
class UiBrandColors {
  /// Selects the mode-specific foreground, fill and on-fill roles.
  const UiBrandColors({required this.secondary});

  /// An accessible foreground and container for secondary brand emphasis.
  final UiStatusTriple secondary;

  /// Exact principal ink seed from the brand reference.
  Color get obsidian => BrandPalette.obsidian;

  /// Exact warm canvas seed from the brand reference.
  Color get paper => BrandPalette.paper;

  /// Exact first endpoint of [heroGradient].
  Color get amber => BrandPalette.amber;

  /// Exact secondary brand seed and second endpoint of [heroGradient].
  Color get iris => BrandPalette.iris;

  /// Exact neutral surface seed from the brand reference.
  Color get mist => BrandPalette.mist;

  /// The approved gradient. Never place evidence or text directly over it.
  ///
  /// Direction is a fixed part of the visual identity, so RTL does not mirror
  /// the blend. Use a solid adjacent content panel for readable hero copy.
  LinearGradient get heroGradient => const LinearGradient(
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
    colors: <Color>[BrandPalette.amber, BrandPalette.iris],
  );

  /// The light theme's accessible secondary colour family.
  static const UiBrandColors light = UiBrandColors(
    secondary: UiStatusTriple(
      content: BrandPalette.irisContentLight,
      fill: BrandPalette.irisFillLight,
      onFill: BrandPalette.irisOnFillLight,
    ),
  );

  /// The dark theme's accessible secondary colour family.
  static const UiBrandColors dark = UiBrandColors(
    secondary: UiStatusTriple(
      content: BrandPalette.irisContentDark,
      fill: BrandPalette.irisFillDark,
      onFill: BrandPalette.irisOnFillDark,
    ),
  );
}
