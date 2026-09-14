/// Window size classes (responsive and platform adaptation, section 2).
///
/// Layout decisions in this product are made from the window's width, never
/// from the platform or the device type. This is the one place the Material 3
/// breakpoints are written down.
library;

import 'package:flutter/widgets.dart';

/// The five Material 3 window size classes.
///
/// The boundaries are the published Material 3 values: 600, 840, 1200 and
/// 1600 logical pixels. Each class holds from its own minimum up to, but not
/// including, the next class's minimum.
enum WindowClass {
  /// Below 600. A phone in portrait, or a small window on a desktop.
  compact,

  /// 600 to 839. A phone in landscape, or a tablet in portrait.
  medium,

  /// 840 to 1199. A tablet in landscape, or a small desktop window.
  expanded,

  /// 1200 to 1599. A desktop window.
  large,

  /// 1600 and above. A wide desktop window.
  extraLarge;

  /// The smallest width that is [medium].
  static const double mediumMin = 600;

  /// The smallest width that is [expanded].
  static const double expandedMin = 840;

  /// The smallest width that is [large].
  static const double largeMin = 1200;

  /// The smallest width that is [extraLarge].
  static const double extraLargeMin = 1600;

  /// The class for a raw width in logical pixels.
  static WindowClass fromWidth(double width) {
    if (width < mediumMin) return WindowClass.compact;
    if (width < expandedMin) return WindowClass.medium;
    if (width < largeMin) return WindowClass.expanded;
    if (width < extraLargeMin) return WindowClass.large;
    return WindowClass.extraLarge;
  }

  /// The class for the window this context is painted into.
  ///
  /// Reads `MediaQuery.sizeOf`, so a widget that calls this rebuilds when the
  /// window is resized and only then.
  static WindowClass of(BuildContext context) =>
      fromWidth(MediaQuery.sizeOf(context).width);

  /// True for every class at or above [other].
  bool isAtLeast(WindowClass other) => index >= other.index;

  /// True only for [compact]. The single-pane, stacked, bottom-sheet case.
  bool get isCompact => this == WindowClass.compact;
}
