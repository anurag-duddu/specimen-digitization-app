/// The full-screen capture route (07 section 5; 05 section 7).
///
/// `image_picker` hands the whole capture to the operating system's camera
/// app, which returns one photograph with no framing guide, no exposure hint
/// and no way to stay in the app across a batch. This screen replaces that
/// for Android and iOS: viewfinder, framing guides, tap to focus, an
/// uncalibrated exposure hint, a review step, and a batch mode that returns
/// to the viewfinder after each accepted photograph.
///
/// The preview is the evidence, so the frame carries no sky and no
/// navigation and the controls float over the pixels: a `glass.floating`
/// capsule at the top for leaving, and the shutter and the counter at the
/// bottom.
///
/// What this screen does not do, stated rather than faked: it does not detect
/// the specimen, does not verify that anything is inside the guides, does not
/// grade focus or readability, and carries no level indicator, because the
/// accelerometer stream that would drive one needs a package this app does
/// not depend on. See `capture_camera.dart`.
library;

import 'dart:async';
import 'dart:typed_data';

import 'package:camera/camera.dart' show XFile;
// `MaterialPageRoute` is infrastructure rather than anatomy: it is what gives
// a pushed route the platform's own transition (05 section 5), which 10
// section 1.3 keeps alongside `MaterialApp` and `MaterialPage`. Nothing
// Material is drawn on this screen.
import 'package:flutter/material.dart' show MaterialPageRoute;
import 'package:flutter/widgets.dart';
import 'package:specimen_ui/specimen_ui.dart';

import '../capture_quality.dart';
import '../widgets/not_calibrated_chip.dart';
import 'capture_camera.dart';

/// What the capture route hands back to the intake screen.
@immutable
class CaptureResult {
  const CaptureResult({this.files = const <XFile>[], this.unavailable});

  /// Photographs the operator accepted, in capture order. May be empty.
  final List<XFile> files;

  /// Set when the in-app camera could not be used at all, so the caller can
  /// fall back to the device camera app with a plain explanation.
  final CaptureUnavailable? unavailable;

  /// True when the caller should fall back rather than report an empty batch.
  bool get needsFallback => unavailable != null;
}

/// The viewfinder, review step and batch counter.
class CaptureScreen extends StatefulWidget {
  const CaptureScreen({super.key, required this.camera});

  /// Builds the camera. Injected so a widget test runs against a fake, since
  /// neither the emulator nor CI has a camera.
  final CaptureCameraFactory camera;

  /// The route the intake screen pushes.
  static Route<CaptureResult> route(CaptureCameraFactory camera) =>
      MaterialPageRoute<CaptureResult>(
        builder: (BuildContext context) => CaptureScreen(camera: camera),
        fullscreenDialog: true,
      );

  /// Fraction of the shorter viewfinder edge the specimen guide leaves clear.
  static const double specimenInset = 0.08;

  /// Where the label guide starts, as a fraction of the specimen guide's
  /// height measured from its top.
  static const double labelGuideTop = 0.62;

  /// How wide the label guide is, as a fraction of the specimen guide.
  static const double labelGuideWidth = 0.55;

  /// What the control that leaves the camera is called.
  static const String closeLabel = 'Close the camera';

  /// What the control that hands the batch back is called.
  static const String doneLabel = 'Done';

  /// What the shutter is called. A control that draws no word needs one
  /// (10 section 11).
  static const String shutterLabel = 'Take photograph';

  @override
  State<CaptureScreen> createState() => _CaptureScreenState();
}

class _CaptureScreenState extends State<CaptureScreen> {
  final List<XFile> _accepted = <XFile>[];
  CaptureCamera? _camera;
  StreamSubscription<CapturePreviewReading>? _subscription;
  CaptureUnavailable? _unavailable;
  CapturePreviewReading? _reading;
  Offset? _focusPoint;
  bool _focusLocked = false;
  bool _starting = true;
  bool _capturing = false;
  XFile? _review;
  Uint8List? _reviewBytes;

  @override
  void initState() {
    super.initState();
    _start();
  }

  Future<void> _start() async {
    try {
      final CaptureCamera camera = await widget.camera();
      await camera.start();
      if (!mounted) {
        await camera.dispose();
        return;
      }
      _subscription = camera.readings.listen(_onReading);
      setState(() {
        _camera = camera;
        _starting = false;
      });
    } on CaptureCameraUnavailable catch (error) {
      if (mounted) {
        setState(() {
          _unavailable = error.kind;
          _starting = false;
        });
      }
    } catch (_) {
      if (mounted) {
        setState(() {
          _unavailable = CaptureUnavailable.failed;
          _starting = false;
        });
      }
    }
  }

  /// Only rebuilds when the sentence would change, so a 30 frames per second
  /// preview does not drive 30 rebuilds per second.
  void _onReading(CapturePreviewReading reading) {
    if (!mounted) return;
    final CapturePreviewReading? previous = _reading;
    if (previous != null &&
        previous.hint == reading.hint &&
        previous.summary == reading.summary) {
      _reading = reading;
      return;
    }
    setState(() => _reading = reading);
  }

  Future<void> _focus(Offset local, Size size) async {
    final CaptureCamera? camera = _camera;
    if (camera == null || size.isEmpty) return;
    final Offset normalized = Offset(
      (local.dx / size.width).clamp(0.0, 1.0),
      (local.dy / size.height).clamp(0.0, 1.0),
    );
    final bool locked = await camera.focusAt(normalized);
    if (!mounted) return;
    setState(() {
      _focusPoint = local;
      _focusLocked = locked;
    });
  }

  Future<void> _capture() async {
    final CaptureCamera? camera = _camera;
    if (camera == null || _capturing) return;
    setState(() => _capturing = true);
    try {
      final XFile file = await camera.capture();
      final Uint8List bytes = await readCapture(file);
      if (!mounted) return;
      setState(() {
        _review = file;
        _reviewBytes = bytes;
      });
    } on CaptureCameraUnavailable catch (error) {
      if (mounted) setState(() => _unavailable = error.kind);
    } catch (_) {
      if (mounted) setState(() => _unavailable = CaptureUnavailable.failed);
    } finally {
      if (mounted) setState(() => _capturing = false);
    }
  }

  void _retake() => setState(() {
    _review = null;
    _reviewBytes = null;
  });

  /// Batch mode: accepting returns straight to the viewfinder for the next
  /// specimen rather than back to the intake screen.
  void _use() {
    final XFile? file = _review;
    if (file == null) return;
    setState(() {
      _accepted.add(file);
      _review = null;
      _reviewBytes = null;
    });
  }

  void _finish() {
    if (!mounted) return;
    Navigator.of(
      context,
    ).pop(CaptureResult(files: List<XFile>.unmodifiable(_accepted)));
  }

  void _fallback() {
    if (!mounted) return;
    Navigator.of(context).pop(CaptureResult(unavailable: _unavailable));
  }

  @override
  void dispose() {
    _subscription?.cancel();
    _camera?.dispose();
    super.dispose();
  }

  /// "1 photograph in this batch", pluralised, so the operator can leave the
  /// screen knowing what leaving costs.
  static String counterLabel(int count) => count == 1
      ? '1 photograph in this batch'
      : '$count photographs in this batch';

  @override
  Widget build(BuildContext context) => PopScope<CaptureResult>(
    canPop: false,
    onPopInvokedWithResult: (bool didPop, CaptureResult? _) {
      if (didPop) return;
      // A back gesture keeps what was already accepted. Nothing the
      // operator confirmed is thrown away by leaving.
      _unavailable == null ? _finish() : _fallback();
    },
    // No sky and no navigation: the preview is the evidence and it fills the
    // window (07 section 5).
    child: UiScaffold(
      sky: SkyPreset.none,
      body: SafeArea(child: _body()),
    ),
  );

  Widget _body() {
    if (_starting) {
      return Center(
        child: UiProgress.ring(
          semanticsLabel: 'Starting the camera',
          size: UiProgressSize.large,
        ),
      );
    }
    if (_unavailable != null) return _unavailableBody();
    if (_reviewBytes != null) return _reviewBody();
    return _viewfinder();
  }

  Widget _unavailableBody() {
    final UiThemeData ui = context.ui;
    return Center(
      child: Padding(
        padding: EdgeInsetsDirectional.all(ui.space.s6),
        child: ConstrainedBox(
          constraints: BoxConstraints(maxWidth: ui.space.readingMax),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Semantics(
                container: true,
                liveRegion: true,
                child: Text(
                  _unavailable!.message,
                  style: ui.type.bodyLarge.copyWith(color: ui.color.ink),
                ),
              ),
              SizedBox(height: ui.space.s6),
              UiButtonRow(
                primary: UiButton(
                  label: 'Use the device camera instead',
                  onPressed: _fallback,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _reviewBody() {
    final UiThemeData ui = context.ui;
    return Column(
      children: <Widget>[
        Expanded(
          child: Surface(
            role: SurfaceRole.matte,
            radius: ui.shape.sheet,
            child: Center(
              child: Image.memory(
                _reviewBytes!,
                fit: BoxFit.contain,
                gaplessPlayback: true,
                semanticLabel: 'The photograph you took',
              ),
            ),
          ),
        ),
        Padding(
          padding: EdgeInsetsDirectional.all(ui.space.s4),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Text(
                'Check the smallest text, the glare and that every label is '
                'inside the frame.',
                style: ui.type.body.copyWith(color: ui.color.ink),
              ),
              SizedBox(height: ui.space.s4),
              UiButtonRow(
                primary: UiButton(
                  label: 'Use photograph',
                  leading: UiIcons.check,
                  onPressed: _use,
                ),
                secondary: UiButton(
                  label: 'Retake',
                  variant: UiButtonVariant.secondary,
                  leading: UiIcons.retry,
                  onPressed: _retake,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _viewfinder() {
    final UiThemeData ui = context.ui;
    final CaptureCamera camera = _camera!;
    final String? hint = _reading?.hint;
    return Column(
      children: <Widget>[
        Expanded(
          child: LayoutBuilder(
            builder: (BuildContext context, BoxConstraints constraints) {
              final Size size = constraints.biggest;
              return Stack(
                fit: StackFit.expand,
                children: <Widget>[
                  // One node for the whole viewfinder: a screen reader hears
                  // "Viewfinder, button", not a bare tappable rectangle. The
                  // focus mark sits outside it so its own announcement is
                  // still reachable.
                  Semantics(
                    container: true,
                    button: true,
                    excludeSemantics: true,
                    label:
                        'Viewfinder. Activate to lock focus and exposure on '
                        'the centre of the frame.',
                    onTap: () => _focus(size.center(Offset.zero), size),
                    child: GestureDetector(
                      behavior: HitTestBehavior.opaque,
                      onTapDown: (TapDownDetails details) =>
                          _focus(details.localPosition, size),
                      child: Stack(
                        fit: StackFit.expand,
                        children: <Widget>[
                          camera.preview(context),
                          CustomPaint(
                            key: const ValueKey<String>(
                              'capture-framing-guides',
                            ),
                            painter: _FramingGuidePainter(
                              // Drawn in `paper` rather than in `ink`: the
                              // guide sits over a photograph, and the one
                              // thing a specimen photograph always has is
                              // dark ground around a pinned insect.
                              stroke: ui.color.paper,
                              width: ui.shape.stroke.emphasis,
                              radius: ui.shape.inner,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                  if (_focusPoint != null)
                    _FocusMark(at: _focusPoint!, locked: _focusLocked),
                  // The one capsule over the pixels: the way out of the
                  // camera, floating rather than welded into a bar, so the
                  // preview keeps the whole window.
                  PositionedDirectional(
                    top: ui.space.s4,
                    end: ui.space.s4,
                    child: GlassSurface(
                      level: GlassLevel.floating,
                      capsule: true,
                      padding: EdgeInsetsDirectional.all(ui.space.s1),
                      child: UiIconButton(
                        icon: UiIcons.close,
                        semanticsLabel: CaptureScreen.closeLabel,
                        tooltip: CaptureScreen.closeLabel,
                        onPressed: _finish,
                      ),
                    ),
                  ),
                ],
              );
            },
          ),
        ),
        Padding(
          padding: EdgeInsetsDirectional.all(ui.space.s4),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Semantics(
                container: true,
                liveRegion: true,
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    const NotCalibratedChip(),
                    SizedBox(width: ui.space.s3),
                    Expanded(
                      child: Text(
                        hint ??
                            (_reading == null
                                ? 'Exposure is not measured on this device.'
                                : 'No clipping measured in this frame.'),
                        style: ui.type.body.copyWith(color: ui.color.ink),
                      ),
                    ),
                  ],
                ),
              ),
              SizedBox(height: ui.space.s2),
              Text(
                'Framing, focus and label coverage are not checked here.',
                style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
              ),
              SizedBox(height: ui.space.s4),
              Row(
                children: <Widget>[
                  Expanded(
                    child: Semantics(
                      container: true,
                      liveRegion: true,
                      child: Text(
                        counterLabel(_accepted.length),
                        style: ui.type.body.copyWith(color: ui.color.ink),
                      ),
                    ),
                  ),
                  SizedBox(width: ui.space.s4),
                  _Shutter(
                    key: const ValueKey<String>('capture-shutter'),
                    onPressed: _capturing ? null : _capture,
                  ),
                  SizedBox(width: ui.space.s4),
                  UiButton(
                    label: CaptureScreen.doneLabel,
                    variant: UiButtonVariant.secondary,
                    onPressed: _finish,
                  ),
                ],
              ),
            ],
          ),
        ),
      ],
    );
  }
}

/// The shutter: an `ink` disc inside a `paper` ring (07 section 5).
///
/// A disc rather than a labelled button, because it is the one control on a
/// camera screen an operator finds without reading. It carries the name a
/// screen reader needs and the 0.98 press scale the control contract allows a
/// capsule; there is no shutter row in the motion catalog, so no sound, no
/// flash and no haptic is invented for it. The confirmation the operator gets
/// is the review step the capture opens.
class _Shutter extends StatelessWidget {
  const _Shutter({super.key, required this.onPressed});

  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    // 72 dp: the hit box plus one gutter on each side, so the disc is a
    // thumb's target with room around it rather than a number of its own.
    final double diameter = ui.space.targetMin + ui.space.s6;
    final double ring = ui.space.s1;
    return Pressable(
      semanticsLabel: CaptureScreen.shutterLabel,
      onPressed: onPressed,
      capsule: true,
      scaleOnPress: true,
      builder: (BuildContext context, Set<WidgetState> states) =>
          SizedBox.square(
            dimension: diameter,
            child: DecoratedBox(
              decoration: ShapeDecoration(
                color: ui.color.paper,
                shape: CircleBorder(
                  side: BorderSide(
                    color: ui.color.boundary,
                    width: ui.shape.stroke.boundary,
                  ),
                ),
              ),
              child: Padding(
                padding: EdgeInsetsDirectional.all(ring),
                child: DecoratedBox(
                  decoration: ShapeDecoration(
                    color: onPressed == null
                        ? ui.color.disabledFill
                        : ui.color.ink,
                    shape: const CircleBorder(),
                  ),
                ),
              ),
            ),
          ),
    );
  }
}

/// The specimen guide and the label guide, drawn over the preview.
///
/// A drawn rectangle, not a detector: nothing here verifies that the specimen
/// or its labels are inside the guides.
class _FramingGuidePainter extends CustomPainter {
  const _FramingGuidePainter({
    required this.stroke,
    required this.width,
    required this.radius,
  });

  final Color stroke;
  final double width;
  final double radius;

  @override
  void paint(Canvas canvas, Size size) {
    if (size.isEmpty) return;
    final double inset = size.shortestSide * CaptureScreen.specimenInset;
    final Rect specimen = Rect.fromLTRB(
      inset,
      inset,
      size.width - inset,
      size.height - inset,
    );
    final Paint paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = width
      ..color = stroke;
    canvas.drawRRect(
      RRect.fromRectAndRadius(specimen, Radius.circular(radius)),
      paint,
    );
    final double labelWidth = specimen.width * CaptureScreen.labelGuideWidth;
    final Rect labels = Rect.fromLTWH(
      specimen.center.dx - labelWidth / 2,
      specimen.top + specimen.height * CaptureScreen.labelGuideTop,
      labelWidth,
      specimen.height * (1 - CaptureScreen.labelGuideTop) - inset,
    );
    if (labels.height > 0) {
      canvas.drawRRect(
        RRect.fromRectAndRadius(labels, Radius.circular(radius)),
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(_FramingGuidePainter old) =>
      old.stroke != stroke || old.width != width || old.radius != radius;
}

/// The focus and exposure lock indicator, drawn where the operator tapped.
class _FocusMark extends StatelessWidget {
  const _FocusMark({required this.at, required this.locked});

  final Offset at;
  final bool locked;

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    final double side = ui.space.targetMin;
    final Widget mark = SizedBox.square(
      dimension: side,
      child: DecoratedBox(
        decoration: ShapeDecoration(
          shape: Squircle.border(
            ui.shape.inner,
            side: BorderSide(
              color: ui.color.paper,
              width: ui.shape.stroke.emphasis,
            ),
          ),
        ),
        child: Center(
          child: UiIcon(
            locked ? UiIcons.locked : UiIcons.unlocked,
            size: UiIconSize.inline,
            color: ui.color.paper,
          ),
        ),
      ),
    );
    return Positioned(
      left: at.dx - side / 2,
      top: at.dy - side / 2,
      child: IgnorePointer(
        child: Semantics(
          key: const ValueKey<String>('capture-focus-mark'),
          container: true,
          liveRegion: true,
          label: locked
              ? 'Focus and exposure locked'
              : 'This camera did not lock focus',
          child: mark,
        ),
      ),
    );
  }
}
