/// Density, resolved from the input modality (09 section 6).
///
/// Density is chosen by what the reviewer last touched the window with, never
/// by the platform or the device type. A control's hit box is 48 dp in both
/// densities; in [UiDensityMode.pointer] the extra 8 dp is transparent slop
/// around the 40 dp visual.
library;

import 'package:flutter/gestures.dart' show PointerDeviceKind;
import 'package:flutter/widgets.dart';

/// The two densities.
enum UiDensityMode {
  /// The last pointer event was a touch or a stylus, or no pointer event has
  /// been seen on a window narrower than [UiDensity.pointerDefaultWidth].
  touch,

  /// The last pointer event was a mouse or a trackpad.
  pointer,
}

/// The measurements one density carries.
@immutable
class UiDensity {
  /// Binds one density's row.
  const UiDensity({
    required this.mode,
    required this.rowHeight,
    required this.controlHeight,
    required this.gutter,
    required this.tilePadding,
  });

  /// Which row of 09 section 6 this is.
  final UiDensityMode mode;

  /// Height of a list row.
  final double rowHeight;

  /// Visual height of a control. The hit box is [hitBox] in both densities.
  final double controlHeight;

  /// Screen and pane gutter.
  final double gutter;

  /// Padding inside a tile.
  final double tilePadding;

  /// A window narrower than this with no pointer event yet is touch.
  static const double pointerDefaultWidth = 840;

  /// The hit box, in both densities. Density never changes it.
  static const double hitBox = 48;

  /// The touch row.
  static const UiDensity touch = UiDensity(
    mode: UiDensityMode.touch,
    rowHeight: 56,
    controlHeight: 48,
    gutter: 20,
    tilePadding: 20,
  );

  /// The pointer row. 40 visual, 48 hit box.
  static const UiDensity pointer = UiDensity(
    mode: UiDensityMode.pointer,
    rowHeight: 44,
    controlHeight: 40,
    gutter: 16,
    tilePadding: 16,
  );

  /// The row for [mode].
  static UiDensity of(UiDensityMode mode) =>
      mode == UiDensityMode.touch ? touch : pointer;

  /// True for the touch row.
  bool get isTouch => mode == UiDensityMode.touch;

  /// The transparent slop around a control's visual, per side.
  double get slop => (hitBox - controlHeight) / 2;
}

/// Publishes the resolved density to the tree, and watches the pointer.
///
/// One of these sits at the application root. It records the kind of the last
/// pointer event and rebuilds its subtree when the resolved density changes,
/// so a reviewer who puts down the mouse and picks up the tablet gets the
/// touch row without a restart.
class Density extends StatefulWidget {
  /// Wraps [child] in a density probe.
  const Density({super.key, required this.child, this.initialMode});

  /// The subtree that reads the density.
  final Widget child;

  /// Forces a density instead of resolving one. Tests use this so a golden
  /// does not depend on which pointer the harness synthesised last.
  final UiDensityMode? initialMode;

  /// The density this context sits in.
  ///
  /// The only way to read it. A widget that wants a row height calls this,
  /// never `Platform` and never `defaultTargetPlatform`.
  static UiDensity of(BuildContext context) {
    final _DensityScope? scope = context
        .dependOnInheritedWidgetOfExactType<_DensityScope>();
    if (scope != null) return scope.density;
    return _fromWidth(MediaQuery.maybeSizeOf(context)?.width);
  }

  /// The density a window of [width] starts in before any pointer event.
  static UiDensity _fromWidth(double? width) =>
      width != null && width >= UiDensity.pointerDefaultWidth
      ? UiDensity.pointer
      : UiDensity.touch;

  /// The density [kind] selects, or null when that kind carries no signal.
  static UiDensityMode? modeFor(PointerDeviceKind kind) => switch (kind) {
    PointerDeviceKind.mouse ||
    PointerDeviceKind.trackpad => UiDensityMode.pointer,
    PointerDeviceKind.touch || PointerDeviceKind.stylus => UiDensityMode.touch,
    PointerDeviceKind.invertedStylus ||
    PointerDeviceKind.unknown => null,
  };

  @override
  State<Density> createState() => _DensityState();
}

class _DensityState extends State<Density> {
  UiDensityMode? _seen;

  void _record(PointerEvent event) {
    final UiDensityMode? mode = Density.modeFor(event.kind);
    if (mode == null || mode == _seen) return;
    setState(() => _seen = mode);
  }

  @override
  Widget build(BuildContext context) {
    final UiDensityMode? forced = widget.initialMode;
    final UiDensity density = forced != null
        ? UiDensity.of(forced)
        : _seen != null
        ? UiDensity.of(_seen!)
        : Density._fromWidth(MediaQuery.maybeSizeOf(context)?.width);
    return Listener(
      // Down rather than hover, so a trackpad that only ever scrolls does not
      // pull a tablet into the pointer row, and behavior is transparent so
      // nothing below this stops seeing the event.
      onPointerDown: _record,
      onPointerHover: _record,
      behavior: HitTestBehavior.translucent,
      child: _DensityScope(density: density, child: widget.child),
    );
  }
}

class _DensityScope extends InheritedWidget {
  const _DensityScope({required this.density, required super.child});

  final UiDensity density;

  @override
  bool updateShouldNotify(_DensityScope oldWidget) =>
      oldWidget.density.mode != density.mode;
}
