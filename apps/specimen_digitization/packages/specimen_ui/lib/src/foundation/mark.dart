/// The interlocking Specimen Digitization brand mark.
///
/// The three pieces and the open counter follow the supplied brand reference.
/// Shared vector geometry keeps the identity consistent at every size.
library;

import 'package:flutter/widgets.dart';

import 'mark_geometry.dart';
import 'theme.dart';

/// The colour treatment of the same interlocking geometry.
enum UiMarkVariant {
  /// Obsidian or Paper outer pieces with an Amber-to-Iris middle piece.
  accent,

  /// All three pieces in the theme's ink role, with transparent negative space.
  mono,

  /// Obsidian outer pieces and the app icon's Amber-tipped fold, for Paper.
  appIcon,
}

/// The product's mark, drawn at [size].
///
/// The mark keeps its proportions and orientation in every writing direction.
/// It paints only the three brand pieces, leaving the surrounding field and
/// enclosed counter transparent. It is
/// an image to a screen reader, and [label] is what that image says; there is
/// no default, because the sentence a reviewer hears depends on where the mark
/// stands.
///
/// It is in the foundation rather than in a control family because it is the
/// brand itself: the launcher icons, the splash and this widget are three
/// renderings of one geometry, and nothing about it is a control.
class UiMark extends StatelessWidget {
  /// The brand mark with its Amber-to-Iris middle piece.
  const UiMark({required this.label, this.size = defaultSize, super.key})
    : variant = UiMarkVariant.accent,
      assert(size > 0, 'a mark with no size is not a mark');

  /// The same brand geometry entirely in the theme's ink role.
  const UiMark.mono({required this.label, this.size = defaultSize, super.key})
    : variant = UiMarkVariant.mono,
      assert(size > 0, 'a mark with no size is not a mark');

  /// The app-icon treatment, intended to sit on a Paper plate in either mode.
  ///
  /// The plate belongs to the host; this widget retains transparent negative
  /// space and the same geometry as the primary mark.
  const UiMark.appIcon({
    required this.label,
    this.size = defaultSize,
    super.key,
  }) : variant = UiMarkVariant.appIcon,
       assert(size > 0, 'a mark with no size is not a mark');

  /// The default size unless a call site asks for another.
  static const double defaultSize = 24;

  /// What the mark says where it stands. Required, never guessed.
  final String label;

  /// The side of the square containing the proportionally scaled mark.
  final double size;

  /// The colour treatment of the mark.
  final UiMarkVariant variant;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Semantics(
      image: true,
      label: label,
      child: SizedBox.square(
        dimension: size,
        child: CustomPaint(
          painter: _MarkPainter(
            ink: switch (variant) {
              UiMarkVariant.mono => ui.color.ink,
              UiMarkVariant.appIcon => ui.brand.obsidian,
              UiMarkVariant.accent =>
                ui.isDark ? ui.brand.paper : ui.brand.obsidian,
            },
            amber: ui.brand.amber,
            iris: ui.brand.iris,
            monochrome: variant == UiMarkVariant.mono,
            appIcon: variant == UiMarkVariant.appIcon,
          ),
        ),
      ),
    );
  }
}

class _MarkPainter extends CustomPainter {
  const _MarkPainter({
    required this.ink,
    required this.amber,
    required this.iris,
    required this.monochrome,
    required this.appIcon,
  });

  final Color ink;
  final Color amber;
  final Color iris;
  final bool monochrome;
  final bool appIcon;

  @override
  void paint(Canvas canvas, Size size) => MarkGeometry.paint(
    canvas,
    size,
    ink: ink,
    amber: amber,
    iris: iris,
    monochrome: monochrome,
    appIcon: appIcon,
  );

  @override
  bool shouldRepaint(covariant _MarkPainter oldDelegate) =>
      oldDelegate.ink != ink ||
      oldDelegate.amber != amber ||
      oldDelegate.iris != iris ||
      oldDelegate.monochrome != monochrome ||
      oldDelegate.appIcon != appIcon;
}
