/// The superellipse helpers (09 section 5).
///
/// A superellipse corner has continuous curvature, so the edge never visibly
/// starts to turn. Every corner in the product passes through here, which is
/// what keeps `BorderRadius.circular` out of the call sites.
library;

import 'package:flutter/widgets.dart';

/// The superellipse helpers.
///
/// A radius at least half the height is drawn as a capsule; there is no
/// hand tuning between the two shapes.
abstract final class Squircle {
  /// The border for [radius], or a capsule when [radius] is at least half of
  /// [height].
  static OutlinedBorder border(double radius, {double? height, BorderSide? side}) {
    final BorderSide edge = side ?? BorderSide.none;
    if (radius <= 0) {
      return RoundedSuperellipseBorder(
        borderRadius: BorderRadius.zero,
        side: edge,
      );
    }
    if (height != null && radius >= height / 2) {
      return StadiumBorder(side: edge);
    }
    return RoundedSuperellipseBorder(
      borderRadius: BorderRadius.circular(radius),
      side: edge,
    );
  }

  /// Clips [child] to a superellipse of [radius].
  static Widget clip({
    required double radius,
    required Widget child,
    Clip clipBehavior = Clip.antiAlias,
  }) => ClipRSuperellipse(
    borderRadius: BorderRadius.circular(radius),
    clipBehavior: clipBehavior,
    child: child,
  );

  /// True when [radius] on a box [height] tall is drawn as a capsule.
  static bool isCapsule(double radius, double height) =>
      height > 0 && radius >= height / 2;
}
