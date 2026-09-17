/// Fit: measuring a label, and choosing the variant that fits the width a
/// control was given (11 section 3.3).
///
/// A control has an intrinsic width: its widest label at the current text
/// scale, plus its padding and its glyphs. Given at least that, it lays out
/// as the gallery draws it. Given less, it switches to the compact variant it
/// declares, and when none fits the label ends in an ellipsis. Nothing here
/// decides which variants a control has; it decides which of the declared
/// ones is drawn.
library;

import 'package:flutter/widgets.dart';

import '../foundation/type.dart';

/// The size one unbroken line of [text] takes in [style].
///
/// Measured at the text scale and in the direction [context] is painted in,
/// through the same `TextPainter` the engine lays a paragraph out with, so a
/// control's declared intrinsic width is the width it actually needs rather
/// than an estimate. The strut is the role's own (`UiType.strutOf`), so the
/// height this returns is the line box `UiType.lineHeightOf` promises.
///
/// Laid out against an unbounded width, which is what makes the result the
/// text's intrinsic extent rather than whatever box it was handed.
Size measureLabel(BuildContext context, String text, TextStyle style) {
  final TextPainter painter = TextPainter(
    text: TextSpan(text: text, style: style),
    textDirection: Directionality.of(context),
    textScaler: MediaQuery.textScalerOf(context),
    strutStyle: UiType.strutOf(style),
    maxLines: 1,
  )..layout();
  final Size size = painter.size;
  painter.dispose();
  return size;
}

/// One arrangement a control declares, and the width it needs to draw it.
@immutable
class FitVariant {
  /// Declares an arrangement that needs [intrinsicWidth] logical pixels.
  const FitVariant({required this.intrinsicWidth, required this.builder});

  /// The narrowest width this arrangement draws correctly at.
  ///
  /// The control measures it, usually with [measureLabel] plus its own
  /// padding and glyphs, so it is already at the current text scale.
  final double intrinsicWidth;

  /// Draws the arrangement.
  ///
  /// `lastResort` is true when no declared variant fitted and this one was
  /// drawn anyway. A control answers it by ellipsising its labels and moving
  /// the full text to its tooltip and its semantics label, which is rule 4 of
  /// 11 section 3.3. It never answers it by wrapping or by shrinking below
  /// its hit box.
  final Widget Function(BuildContext context, bool lastResort) builder;
}

/// Draws the first declared variant that fits the width it is given.
///
/// ```dart
/// FitBuilder(
///   variants: <FitVariant>[
///     FitVariant(intrinsicWidth: full, builder: (_, _) => _labelled()),
///     FitVariant(intrinsicWidth: glyphs, builder: (_, last) => _glyphs(last)),
///   ],
/// )
/// ```
///
/// The variants are tried in the order the control lists them, which is the
/// order the table in 11 section 3.3 gives for that control. When none fits,
/// the last is drawn with the last resort flag set rather than the control
/// shrinking, wrapping, or overflowing in silence.
class FitBuilder extends StatelessWidget {
  /// Draws the first of [variants] that fits.
  const FitBuilder({super.key, required this.variants})
    : assert(variants.length != 0, 'a control declares at least one variant');

  /// The arrangements, widest first.
  final List<FitVariant> variants;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (BuildContext context, BoxConstraints constraints) {
      final double available = constraints.maxWidth;
      for (final FitVariant variant in variants) {
        // An unbounded parent is asking for the intrinsic width, so the first
        // variant is the answer: a control never shrinks itself.
        if (available.isInfinite || variant.intrinsicWidth <= available) {
          return variant.builder(context, false);
        }
      }
      return variants.last.builder(context, true);
    },
  );
}
