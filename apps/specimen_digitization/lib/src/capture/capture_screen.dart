/// The full-screen capture route (screen blueprints, section 5; responsive
/// and platform adaptation, section 7).
///
/// `image_picker` hands the whole capture to the operating system's camera
/// app, which returns one photograph with no framing guide, no exposure hint
/// and no way to stay in the app across a batch. This screen replaces that
/// for Android and iOS: viewfinder, framing guides, tap to focus, an
/// uncalibrated exposure hint, a review step, and a batch mode that returns
/// to the viewfinder after each accepted photograph.
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
import 'package:flutter/material.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../capture_quality.dart';
import '../theme/icons.dart';
import '../theme/motion.dart';
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
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return PopScope<CaptureResult>(
      canPop: false,
      onPopInvokedWithResult: (bool didPop, CaptureResult? _) {
        if (didPop) return;
        // A back gesture keeps what was already accepted. Nothing the
        // operator confirmed is thrown away by leaving.
        _unavailable == null ? _finish() : _fallback();
      },
      child: Scaffold(
        backgroundColor: theme.colorScheme.inverseSurface,
        appBar: AppBar(
          backgroundColor: theme.colorScheme.inverseSurface,
          foregroundColor: theme.colorScheme.onInverseSurface,
          title: const Text('Take photographs'),
          leading: IconButton(
            onPressed: _unavailable == null ? _finish : _fallback,
            icon: const Icon(Symbols.close),
            tooltip: 'Close the camera',
          ),
          actions: <Widget>[
            if (_unavailable == null)
              Padding(
                padding: EdgeInsets.only(right: context.space.space4),
                child: TextButton(
                  onPressed: _finish,
                  style: TextButton.styleFrom(
                    foregroundColor: theme.colorScheme.onInverseSurface,
                    minimumSize: Size(
                      context.sizes.targetMin,
                      context.sizes.targetMin,
                    ),
                  ),
                  child: const Text('Done'),
                ),
              ),
          ],
        ),
        body: SafeArea(child: _body(context)),
      ),
    );
  }

  Widget _body(BuildContext context) {
    if (_starting) {
      return Center(
        child: Semantics(
          liveRegion: true,
          child: CircularProgressIndicator(
            semanticsLabel: 'Starting the camera',
            color: Theme.of(context).colorScheme.onInverseSurface,
          ),
        ),
      );
    }
    if (_unavailable != null) return _unavailableBody(context);
    if (_reviewBytes != null) return _reviewBody(context);
    return _viewfinder(context);
  }

  Widget _unavailableBody(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Center(
      child: Padding(
        padding: EdgeInsets.all(context.space.space6),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Semantics(
              liveRegion: true,
              child: Text(
                _unavailable!.message,
                style: theme.textTheme.bodyLarge?.copyWith(
                  color: theme.colorScheme.onInverseSurface,
                ),
              ),
            ),
            SizedBox(height: context.space.space6),
            FilledButton(
              onPressed: _fallback,
              child: const Text('Use the device camera instead'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _reviewBody(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Column(
      children: <Widget>[
        Expanded(
          child: Center(
            child: Image.memory(
              _reviewBytes!,
              fit: BoxFit.contain,
              gaplessPlayback: true,
              semanticLabel: 'The photograph you took',
            ),
          ),
        ),
        Padding(
          padding: EdgeInsets.all(context.space.space4),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Text(
                'Check the smallest text, the glare and that every label is '
                'inside the frame.',
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: theme.colorScheme.onInverseSurface,
                ),
              ),
              SizedBox(height: context.space.space4),
              Row(
                children: <Widget>[
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: _retake,
                      icon: const Icon(Symbols.refresh),
                      label: const Text('Retake'),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: theme.colorScheme.onInverseSurface,
                        side: BorderSide(
                          color: theme.colorScheme.onInverseSurface,
                          width: context.shape.strokeBoundary,
                        ),
                        minimumSize: Size(
                          context.sizes.targetMin,
                          context.sizes.targetMin,
                        ),
                      ),
                    ),
                  ),
                  SizedBox(width: context.space.space4),
                  Expanded(
                    child: FilledButton.icon(
                      onPressed: _use,
                      icon: const Icon(Symbols.check),
                      label: const Text('Use photograph'),
                      style: FilledButton.styleFrom(
                        minimumSize: Size(
                          context.sizes.targetMin,
                          context.sizes.targetMin,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _viewfinder(BuildContext context) {
    final ThemeData theme = Theme.of(context);
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
                              stroke: theme.colorScheme.onInverseSurface,
                              width: context.shape.strokeEmphasis,
                              radius: context.shape.radiusSm,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                  if (_focusPoint != null)
                    _FocusMark(
                      at: _focusPoint!,
                      locked: _focusLocked,
                      color: theme.colorScheme.onInverseSurface,
                    ),
                ],
              );
            },
          ),
        ),
        Padding(
          padding: EdgeInsets.all(context.space.space4),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Semantics(
                liveRegion: true,
                child: Row(
                  children: <Widget>[
                    const NotCalibratedChip(),
                    SizedBox(width: context.space.space3),
                    Expanded(
                      child: Text(
                        hint ??
                            (_reading == null
                                ? 'Exposure is not measured on this device.'
                                : 'No clipping measured in this frame.'),
                        style: theme.textTheme.bodyMedium?.copyWith(
                          color: theme.colorScheme.onInverseSurface,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              SizedBox(height: context.space.space2),
              Text(
                'Framing, focus and label coverage are not checked here.',
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onInverseSurface,
                ),
              ),
              SizedBox(height: context.space.space4),
              Row(
                children: <Widget>[
                  Expanded(
                    child: Semantics(
                      liveRegion: true,
                      child: Text(
                        counterLabel(_accepted.length),
                        style: theme.textTheme.bodyMedium?.copyWith(
                          color: theme.colorScheme.onInverseSurface,
                        ),
                      ),
                    ),
                  ),
                  FilledButton.icon(
                    key: const ValueKey<String>('capture-shutter'),
                    onPressed: _capturing ? null : _capture,
                    icon: const Icon(Symbols.photo_camera),
                    label: Text(_capturing ? 'Capturing' : 'Capture'),
                    style: FilledButton.styleFrom(
                      minimumSize: Size(
                        context.sizes.targetMin,
                        context.sizes.targetMin,
                      ),
                    ),
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
  const _FocusMark({
    required this.at,
    required this.locked,
    required this.color,
  });

  final Offset at;
  final bool locked;
  final Color color;

  @override
  Widget build(BuildContext context) {
    final double side = context.sizes.targetMin;
    final MotionTokens motion = MotionTokens.of(context);
    final Widget mark = Container(
      width: side,
      height: side,
      decoration: BoxDecoration(
        border: Border.all(color: color, width: context.shape.strokeEmphasis),
        borderRadius: BorderRadius.circular(context.shape.radiusXs),
      ),
      alignment: Alignment.center,
      child: Icon(
        locked ? Symbols.lock : Symbols.lock_open,
        size: context.sizes.iconInline,
        color: color,
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
          child: motion.reduced
              ? mark
              : AnimatedOpacity(
                  opacity: 1,
                  duration: motion.quick,
                  curve: MotionTokens.standardCurve,
                  child: mark,
                ),
        ),
      ),
    );
  }
}
