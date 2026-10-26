/// Density, resolved from the input modality (09 section 6).
///
/// Density is chosen by what the reviewer last touched the window with, never
/// by the platform or the device type. A control's hit box is 48 dp in both
/// densities; in [UiDensityMode.pointer] the extra 8 dp is transparent slop
/// around the 40 dp visual.
library;

import 'package:flutter/gestures.dart' show PointerDeviceKind;
import 'package:flutter/foundation.dart'
    show kIsWeb, defaultTargetPlatform, TargetPlatform;
import 'package:flutter/widgets.dart';

import 'input_capabilities_platform.dart';

/// Available inputs, rather than the input used for the most recent gesture.
///
/// A tablet with a trackpad supports both. Hover must not hide navigation
/// labels from the touch input that remains available on that device.
@immutable
class UiInputCapabilities {
  /// Declares the capabilities available to a host or deterministic preview.
  const UiInputCapabilities({required this.touch, required this.hover});

  /// Touch or stylus input is available.
  final bool touch;

  /// An attached pointer can reveal hover content.
  final bool hover;

  static UiInputCapabilities _platform() {
    final mobile =
        defaultTargetPlatform == TargetPlatform.android ||
        defaultTargetPlatform == TargetPlatform.iOS;
    return UiInputCapabilities(
      touch: platformSupportsTouch() ?? (kIsWeb || mobile),
      hover: platformSupportsHover() ?? (!kIsWeb && !mobile),
    );
  }
}

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
    gutter: 16,
    tilePadding: 16,
  );

  /// The pointer row. 40 visual, 48 hit box.
  static const UiDensity pointer = UiDensity(
    mode: UiDensityMode.pointer,
    rowHeight: 48,
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
  const Density({
    super.key,
    required this.child,
    this.initialMode,
    this.inputCapabilities,
  });

  /// The subtree that reads the density.
  final Widget child;

  /// Forces a density instead of resolving one. Tests use this so a golden
  /// does not depend on which pointer the harness synthesised last.
  final UiDensityMode? initialMode;

  /// Optional host capability override. Tests and previews can model a hybrid
  /// device independently of the density used to draw its controls.
  final UiInputCapabilities? inputCapabilities;

  /// Available inputs for adaptive labels. This never infers hover from width.
  /// Observed touch remains available after later mouse gestures.
  static UiInputCapabilities inputsOf(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<_DensityScope>()?.inputs ??
      UiInputCapabilities._platform();

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
    PointerDeviceKind.invertedStylus || PointerDeviceKind.unknown => null,
  };

  @override
  State<Density> createState() => _DensityState();
}

class _DensityState extends State<Density> {
  UiDensityMode? _seen;
  bool _touchSeen = false;
  late final void Function() _stopListening;

  @override
  void initState() {
    super.initState();
    _stopListening = listenToPlatformInputCapabilities(() {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    _stopListening();
    super.dispose();
  }

  void _record(PointerEvent event) {
    final UiDensityMode? mode = Density.modeFor(event.kind);
    if (mode == null ||
        (mode == _seen && (mode != UiDensityMode.touch || _touchSeen))) {
      return;
    }
    setState(() {
      _seen = mode;
      if (mode == UiDensityMode.touch) _touchSeen = true;
    });
  }

  @override
  Widget build(BuildContext context) {
    final UiDensityMode? forced = widget.initialMode;
    final UiDensity density = forced != null
        ? UiDensity.of(forced)
        : _seen != null
        ? UiDensity.of(_seen!)
        : Density._fromWidth(MediaQuery.maybeSizeOf(context)?.width);
    final baseline =
        widget.inputCapabilities ??
        (forced == null
            ? UiInputCapabilities._platform()
            : UiInputCapabilities(
                touch: forced == UiDensityMode.touch,
                hover: forced == UiDensityMode.pointer,
              ));
    final inputs = UiInputCapabilities(
      touch: baseline.touch || (forced == null && _touchSeen),
      hover:
          baseline.hover || (forced == null && _seen == UiDensityMode.pointer),
    );
    return Listener(
      // Down rather than hover, so a trackpad that only ever scrolls does not
      // pull a tablet into the pointer row, and behavior is transparent so
      // nothing below this stops seeing the event.
      onPointerDown: _record,
      onPointerHover: _record,
      behavior: HitTestBehavior.translucent,
      child: _DensityScope(
        density: density,
        inputs: inputs,
        child: widget.child,
      ),
    );
  }
}

class _DensityScope extends InheritedWidget {
  const _DensityScope({
    required this.density,
    required this.inputs,
    required super.child,
  });

  final UiDensity density;
  final UiInputCapabilities inputs;

  @override
  bool updateShouldNotify(_DensityScope oldWidget) =>
      oldWidget.density.mode != density.mode ||
      oldWidget.inputs.touch != inputs.touch ||
      oldWidget.inputs.hover != inputs.hover;
}
