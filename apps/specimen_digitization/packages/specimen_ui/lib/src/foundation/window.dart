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

/// How a window arranges the workspace around its content (05 section 2,
/// amended 2026-10-17).
///
/// [WindowClass] says how wide a window is, and content reads it: how many
/// columns a list takes, whether a record's panes sit side by side, whether a
/// row of buttons stacks. This says where the chrome goes, and the chrome
/// reads it: the navigation, the workspace header, the form of the band, and
/// whether a modal is a sheet or a dialog. A window has one answer, so a
/// landscape phone that draws the tab bar also gets the sheet and the strip,
/// and every surface that asks gets it from here rather than from a number of
/// its own.
///
/// It reads three things the window class does not. The text scale, because
/// the docked arrangement puts a list pane beside the content that is
/// [listPaneWidth] wide at normal text and grows with the text, so at 200
/// percent the same window has half the room beside it. The height, so a
/// window under [dockedMinHeight] tall, a phone on its side, is arranged the
/// way it is upright. And a width boundary that is not a Material 3 one,
/// [dockedMinWidth]: with the 72 dp rail and the list pane open, a docked
/// 768 dp window leaves 384 dp beside them, about a phone's width.
///
/// The boundaries are the shell's own since 2026-10-01, written there as
/// literals until 2026-10-17 and moved here unchanged, so the captures and
/// the device check made on them (#347, #350) still describe what ships. The
/// list pane is 8 dp narrower than the shell's 320, see [listPaneWidth].
enum WindowArrangement {
  /// One pane at a time.
  ///
  /// The navigation is a tab bar along the bottom edge, a record stacks over
  /// the list it came from, a modal is a sheet and the band is a strip.
  stacked,

  /// The navigation docks down the start edge beside one content pane.
  ///
  /// The list pane opens beside a record when the reviewer asks for it.
  docked,

  /// Docked, with room for the list pane beside the record from the start.
  ///
  /// Material 3's list-detail canonical layout.
  listDetail;

  /// The least scaled width that docks.
  ///
  /// Scaled: multiplied by the text scale before it is compared, so a window
  /// at 200 percent text docks from 1536.
  static const double dockedMinWidth = 768;

  /// The least height that docks, whatever the width.
  static const double dockedMinHeight = 600;

  /// The least scaled width that opens the list beside a record.
  static const double listDetailMinWidth = 1100;

  /// The list pane's width at normal text.
  ///
  /// 312, so the rail and the pane together are the 384 dp the shell's
  /// hand-built 64 dp column and 320 dp list took before 2026-10-17. `UiRail`
  /// is 72 dp (10 section 4.4), and the 8 dp it grew by come out of the pane
  /// rather than out of the content: at 1180 by 820 with the list open, a
  /// record 8 dp narrower moves its decision bar's previous and next into the
  /// overflow menu, and that window is the review desk.
  static const double listPaneWidth = 312;

  /// The text scale the arrangement reads.
  ///
  /// The scaler's factor at 16 dp, held to 1 through 2: a window at reduced
  /// text docks no earlier than one at normal text, and the control contract
  /// promises nothing above 200 percent (11 section 2.1).
  static double textScaleOf(TextScaler textScaler) =>
      (textScaler.scale(16) / 16).clamp(1.0, 2.0);

  /// The arrangement for a window of [size] at [textScaler].
  static WindowArrangement fromSize(
    Size size, {
    TextScaler textScaler = TextScaler.noScaling,
  }) {
    final double scale = textScaleOf(textScaler);
    if (size.width < dockedMinWidth * scale || size.height < dockedMinHeight) {
      return WindowArrangement.stacked;
    }
    if (size.width < listDetailMinWidth * scale) {
      return WindowArrangement.docked;
    }
    return WindowArrangement.listDetail;
  }

  /// The arrangement for the window this context is painted into.
  ///
  /// Reads `MediaQuery.sizeOf` and `MediaQuery.textScalerOf`, so a widget
  /// that calls this rebuilds when the window is resized or the text scale
  /// changes, and only then.
  static WindowArrangement of(BuildContext context) => fromSize(
    MediaQuery.sizeOf(context),
    textScaler: MediaQuery.textScalerOf(context),
  );

  /// The list pane's width at [textScaler]: [listPaneWidth] scaled with the
  /// text and rounded up to the 8 dp grid.
  static double listPaneWidthOf(TextScaler textScaler) =>
      (listPaneWidth * textScaleOf(textScaler) / 8).ceil() * 8.0;

  /// True only for [stacked].
  bool get isStacked => this == WindowArrangement.stacked;

  /// True for [docked] and [listDetail]: the navigation is down the side.
  bool get isDocked => this != WindowArrangement.stacked;
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
