/// The camera surface the capture screen draws, behind an interface.
///
/// The emulator and CI have no camera, so the capture screen never talks to
/// the `camera` package directly: it talks to [CaptureCamera]. The production
/// implementation is [PlatformCaptureCamera]; a widget test supplies its own.
///
/// A level indicator is specified in the responsive spec, section 7, and is
/// deliberately absent here: it needs `accelerometerEventStream` from
/// `sensors_plus`, which is not a dependency of this app. Adding a package to
/// draw a spirit level is a decision for the step that adds it, not a silent
/// import. Nothing in this file fakes a tilt reading in its place.
library;

import 'dart:async';
import 'dart:typed_data';

import 'package:camera/camera.dart';
import 'package:flutter/widgets.dart';

import '../capture_quality.dart';

/// Why the in-app camera could not be used, in one sentence an operator can
/// act on. Never a code, never a stack.
enum CaptureUnavailable {
  /// The device reported no usable camera.
  noCamera('This device did not report a camera. Choose a file instead.'),

  /// Camera permission is not granted.
  permission(
    'Camera access is turned off for this app. Turn it on in device '
    'settings, or choose a file instead.',
  ),

  /// The camera is present but did not start.
  failed(
    'The camera did not start on this device. Take the photograph with the '
    'device camera app, or choose a file instead.',
  );

  const CaptureUnavailable(this.message);

  /// The plain explanation shown when the capture screen falls back.
  final String message;
}

/// Raised when the capture screen cannot open the camera at all.
class CaptureCameraUnavailable implements Exception {
  const CaptureCameraUnavailable(this.kind);

  /// Which of the three honest reasons applies.
  final CaptureUnavailable kind;

  /// The sentence shown to the operator.
  String get message => kind.message;

  @override
  String toString() => message;
}

/// Everything the capture screen needs from a camera.
///
/// Implementations are responsible for their own resources; the screen calls
/// [dispose] exactly once.
abstract class CaptureCamera {
  /// Starts the camera. Throws [CaptureCameraUnavailable] when it cannot.
  Future<void> start();

  /// True once [start] has completed and a preview can be drawn.
  bool get ready;

  /// Preview width divided by preview height, for the viewfinder box.
  double get aspectRatio;

  /// The live preview widget.
  Widget preview(BuildContext context);

  /// Coarse brightness readings from preview frames. May emit nothing at all
  /// on a platform that does not deliver frames; the screen treats an absent
  /// reading as "not measured", never as "fine".
  Stream<CapturePreviewReading> get readings;

  /// Locks focus and exposure on a point given in preview coordinates, 0 to 1
  /// from the top left. Silently does nothing where the platform has no such
  /// control, which is a fact the screen surfaces as an unlocked indicator.
  Future<bool> focusAt(Offset point);

  /// Takes one photograph.
  Future<XFile> capture();

  /// Releases the camera.
  Future<void> dispose();
}

/// Builds the camera the capture screen will use.
typedef CaptureCameraFactory = Future<CaptureCamera> Function();

/// The `camera` package implementation, used on Android and iOS.
///
/// Preview frames are read on a stride and reduced to a histogram in
/// [CapturePreviewReading]; no frame is retained, copied to disk, or sent
/// anywhere. `takePicture` and `startImageStream` cannot both be active on
/// every platform, so the stream is stopped around a capture and restarted
/// after it.
class PlatformCaptureCamera implements CaptureCamera {
  PlatformCaptureCamera({
    this.resolution = ResolutionPreset.veryHigh,
    Future<List<CameraDescription>> Function()? cameras,
  }) : _cameras = cameras ?? availableCameras;

  /// The preset the controller is created with. Specimen labels carry the
  /// smallest text on the frame, so the capture is as large as the platform
  /// will give.
  final ResolutionPreset resolution;

  final Future<List<CameraDescription>> Function() _cameras;
  final StreamController<CapturePreviewReading> _readings =
      StreamController<CapturePreviewReading>.broadcast();

  CameraController? _controller;
  bool _streaming = false;
  bool _disposed = false;

  @override
  bool get ready => _controller?.value.isInitialized ?? false;

  @override
  double get aspectRatio => _controller?.value.aspectRatio ?? 1;

  @override
  Stream<CapturePreviewReading> get readings => _readings.stream;

  @override
  Future<void> start() async {
    late final List<CameraDescription> found;
    try {
      found = await _cameras();
    } on CameraException catch (error) {
      throw CaptureCameraUnavailable(_classify(error));
    }
    if (found.isEmpty) {
      throw const CaptureCameraUnavailable(CaptureUnavailable.noCamera);
    }
    final CameraDescription back = found.firstWhere(
      (CameraDescription c) => c.lensDirection == CameraLensDirection.back,
      orElse: () => found.first,
    );
    final CameraController controller = CameraController(
      back,
      resolution,
      enableAudio: false,
      imageFormatGroup: ImageFormatGroup.yuv420,
    );
    try {
      await controller.initialize();
    } on CameraException catch (error) {
      await controller.dispose();
      throw CaptureCameraUnavailable(_classify(error));
    }
    if (_disposed) {
      await controller.dispose();
      return;
    }
    _controller = controller;
    await _startStream();
  }

  static CaptureUnavailable _classify(CameraException error) {
    final String code = error.code.toLowerCase();
    if (code.contains('permission') || code.contains('denied')) {
      return CaptureUnavailable.permission;
    }
    if (code.contains('notfound') || code.contains('no_available')) {
      return CaptureUnavailable.noCamera;
    }
    return CaptureUnavailable.failed;
  }

  Future<void> _startStream() async {
    final CameraController? controller = _controller;
    if (controller == null || _streaming || _disposed) return;
    try {
      await controller.startImageStream(_onFrame);
      _streaming = true;
    } on CameraException {
      // A platform with no frame stream leaves the hint unmeasured, which the
      // screen states rather than hides.
      _streaming = false;
    }
  }

  Future<void> _stopStream() async {
    final CameraController? controller = _controller;
    if (controller == null || !_streaming) return;
    _streaming = false;
    try {
      await controller.stopImageStream();
    } on CameraException {
      // Already stopped. Nothing to report.
    }
  }

  void _onFrame(CameraImage image) {
    if (_readings.isClosed || image.planes.isEmpty) return;
    try {
      final Plane plane = image.planes.first;
      final bool bgra = image.format.group == ImageFormatGroup.bgra8888;
      _readings.add(
        CapturePreviewReading.fromPlane(
          plane.bytes,
          width: image.width,
          height: image.height,
          bytesPerPixel: bgra ? 4 : (plane.bytesPerPixel ?? 1),
          bytesPerRow: plane.bytesPerRow,
          bgra: bgra,
        ),
      );
    } on ArgumentError {
      // A frame whose geometry this build does not understand is skipped. A
      // missing reading is reported as unmeasured, never as a pass.
    }
  }

  @override
  Widget preview(BuildContext context) {
    final CameraController? controller = _controller;
    if (controller == null || !controller.value.isInitialized) {
      return const SizedBox.expand();
    }
    return CameraPreview(controller);
  }

  @override
  Future<bool> focusAt(Offset point) async {
    final CameraController? controller = _controller;
    if (controller == null || !controller.value.isInitialized) return false;
    try {
      await controller.setFocusPoint(point);
      await controller.setFocusMode(FocusMode.locked);
      await controller.setExposurePoint(point);
      await controller.setExposureMode(ExposureMode.locked);
      return true;
    } on CameraException {
      return false;
    }
  }

  @override
  Future<XFile> capture() async {
    final CameraController? controller = _controller;
    if (controller == null || !controller.value.isInitialized) {
      throw const CaptureCameraUnavailable(CaptureUnavailable.failed);
    }
    await _stopStream();
    try {
      return await controller.takePicture();
    } on CameraException catch (error) {
      throw CaptureCameraUnavailable(_classify(error));
    } finally {
      await _startStream();
    }
  }

  @override
  Future<void> dispose() async {
    _disposed = true;
    await _stopStream();
    await _readings.close();
    await _controller?.dispose();
    _controller = null;
  }
}

/// Reads a capture's bytes once, so the manifest and the review step share
/// one read rather than touching the file twice.
Future<Uint8List> readCapture(XFile file) => file.readAsBytes();
