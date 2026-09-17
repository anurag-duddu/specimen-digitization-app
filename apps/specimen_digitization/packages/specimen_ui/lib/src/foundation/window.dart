/// Window size classes and the values that vary with them (11 section 3.1).
///
/// Arrangement is chosen from the width of the window, never from the
/// platform and never from the device type. This is the one place the
/// Material 3 breakpoints are written down.
///
/// Scaffolds, screens and patterns read [WindowClass] and [Adaptive]. A
/// control reads neither: what a control does with less room than it needs is
/// its fit policy, which reads the constraints it was given (11 section 3.3).
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

/// One value per window class, resolved to the nearest smaller class that is
/// set.
///
/// ```dart
/// const Adaptive<int> columns = Adaptive<int>(compact: 1, expanded: 3);
/// columns.of(context); // 1 on compact and medium, 3 from expanded up
/// ```
///
/// Every class is optional, so a layout declares only the widths where its
/// arrangement actually changes and the classes in between inherit downward.
/// [compact] is the base case: set it and [of] never returns null, because
/// every class resolves down to it.
@immutable
class Adaptive<T> {
  /// Declares a value for each class the arrangement changes at.
  const Adaptive({
    this.compact,
    this.medium,
    this.expanded,
    this.large,
    this.extraLarge,
  });

  /// Declares one value for every class. The escape hatch for a call site
  /// that takes an [Adaptive] where the value happens not to vary.
  const Adaptive.all(T value)
    : compact = value,
      medium = value,
      expanded = value,
      large = value,
      extraLarge = value;

  /// The value below 600, or null to fall through to nothing.
  final T? compact;

  /// The value from 600, or null to inherit [compact].
  final T? medium;

  /// The value from 840, or null to inherit the nearest smaller class.
  final T? expanded;

  /// The value from 1200, or null to inherit the nearest smaller class.
  final T? large;

  /// The value from 1600, or null to inherit the nearest smaller class.
  final T? extraLarge;

  /// The value [windowClass] resolves to.
  ///
  /// Walks down from [windowClass] and returns the first class that is set,
  /// or null when no class at or below it carries a value.
  T? resolve(WindowClass windowClass) {
    for (int i = windowClass.index; i >= 0; i--) {
      final T? value = _at(WindowClass.values[i]);
      if (value != null) return value;
    }
    return null;
  }

  /// The value for the window this context is painted into.
  T? of(BuildContext context) => resolve(WindowClass.of(context));

  T? _at(WindowClass windowClass) => switch (windowClass) {
    WindowClass.compact => compact,
    WindowClass.medium => medium,
    WindowClass.expanded => expanded,
    WindowClass.large => large,
    WindowClass.extraLarge => extraLarge,
  };

  @override
  bool operator ==(Object other) =>
      other is Adaptive<T> &&
      other.compact == compact &&
      other.medium == medium &&
      other.expanded == expanded &&
      other.large == large &&
      other.extraLarge == extraLarge;

  @override
  int get hashCode => Object.hash(compact, medium, expanded, large, extraLarge);
}
