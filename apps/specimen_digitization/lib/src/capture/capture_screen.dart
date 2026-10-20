/// The full-screen capture route (07 section 5; 05 section 7).
///
/// `image_picker` hands the whole capture to the operating system's camera
/// app, which returns one photograph with no framing guide, no exposure hint
/// and no way to stay in the app across a batch. This screen replaces that
/// for Android and iOS: viewfinder, framing guides, tap to focus, an
/// uncalibrated exposure hint, a review step, and a batch mode that returns
/// to the viewfinder after each accepted photograph.
///
/// The preview is the evidence, so the frame carries no sky or navigation.
/// The close and send-mode controls sit above it, with a thumbnail, shutter
/// and Done below it.
///
/// What this screen does not do, stated rather than faked: it does not detect
/// the specimen, does not verify that anything is inside the guides, does not
/// grade focus or readability, and carries no level indicator, because the
/// accelerometer stream that would drive one needs a package this app does
/// not depend on. See `capture_camera.dart`.
library;

import 'dart:async';
import 'dart:math' as math;
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
import 'capture_camera.dart';
import 'capture_orientation.dart';
import 'capture_photo_editor.dart';

/// The compact intake-queue update shown while the camera remains open.
@immutable
class CaptureActivity {
  const CaptureActivity({
    required this.label,
    this.progress,
    this.problem = false,
  });

  final String label;
  final double? progress;
  final bool problem;
}

/// An accepted photo and the sensitivity selected when it was taken or reviewed.
@immutable
class CapturedPhoto {
  const CapturedPhoto({required this.file, required this.sensitive});

  final XFile file;
  final bool sensitive;
}

/// What the capture route hands back to the intake screen.
@immutable
class CaptureResult {
  const CaptureResult({
    this.files = const <XFile>[],
    this.unavailable,
    this.streamed = false,
  });

  /// Photographs the operator accepted, in capture order. May be empty.
  final List<XFile> files;

  /// Set when the operator explicitly chooses the fallback after the in-app
  /// camera becomes unavailable. Back and Close leave this unset.
  final CaptureUnavailable? unavailable;

  /// Each accepted file was handed to intake while the viewfinder stayed open.
  final bool streamed;

  /// True when the caller should fall back rather than report an empty batch.
  bool get needsFallback => unavailable != null;
}

/// The viewfinder, review step and batch counter.
///
/// Sensitive controls appear in the viewfinder and review only when
/// [onCaptured] is supplied. Without it, no [CapturedPhoto] is produced;
/// [onAccepted] and [CaptureResult.files] continue to carry files only.
class CaptureScreen extends StatefulWidget {
  const CaptureScreen({
    super.key,
    required this.camera,
    this.onAccepted,
    this.onCaptured,
    this.initialSensitive = false,
    this.autoIngest = false,
    this.onAutoIngestChanged,
    this.activity,
    this.activitySnapshot,
    this.statusLabel,
    this.statusBlocked = false,
    this.deviceFallbackAvailable = true,
  });

  /// Builds the camera. Injected so a widget test runs against a fake, since
  /// neither the emulator nor CI has a camera.
  final CaptureCameraFactory camera;

  /// Called for each accepted image without waiting for the whole batch.
  final ValueChanged<XFile>? onAccepted;

  /// Receives the same accepted file with its per-photo sensitivity.
  /// When both callbacks are supplied, each is called once for that photo.
  /// Supplying this callback enables both Sensitive controls. When null,
  /// neither control is shown and no [CapturedPhoto] is produced.
  final ValueChanged<CapturedPhoto>? onCaptured;

  /// The starting choice for this camera session; never persisted here.
  final bool initialSensitive;

  /// When true, the shutter sends the photograph to Intake immediately.
  final bool autoIngest;

  /// Persists a change made from inside the camera.
  final ValueChanged<bool>? onAutoIngestChanged;

  /// The intake transfer session, used only as a repaint signal.
  final Listenable? activity;

  /// Reads a plain, camera-safe summary of the intake queue.
  final CaptureActivity Function()? activitySnapshot;

  /// Optional batch summary, already composed by Intake. When non-null, this
  /// and [statusBlocked] override [activitySnapshot], even on [activity] ticks.
  /// A directly embedded widget can receive new values from its parent.
  /// Values passed to [route] are fixed when it is pushed; use [activity] and
  /// [activitySnapshot] for live updates while that route is open.
  final String? statusLabel;

  /// Whether [statusLabel] describes a photo the operator needs to fix.
  /// Used only when [statusLabel] is non-null, overriding the snapshot's tone
  /// even on [activity] ticks. Values passed to [route] are fixed when pushed;
  /// live route status must use [activity] and [activitySnapshot] instead.
  final bool statusBlocked;

  /// Whether a separate operating-system camera app is a meaningful fallback.
  /// Browser and desktop webcams have no second camera path to offer.
  final bool deviceFallbackAvailable;

  /// The route the intake screen pushes.
  ///
  /// Both Sensitive controls appear only when [onCaptured] is non-null.
  /// Otherwise no [CapturedPhoto] is produced; [onAccepted] and the result
  /// still carry files only. [initialSensitive] initializes those controls.
  ///
  /// [statusLabel] and [statusBlocked] are captured when the route is pushed;
  /// rebuilding its builder does not supply new values. A non-null
  /// [statusLabel] overrides [activitySnapshot], including its tone via
  /// [statusBlocked], even while [activity] ticks. Pass [activity] and
  /// [activitySnapshot] without [statusLabel] to keep the route status live.
  static Route<CaptureResult> route(
    CaptureCameraFactory camera, {
    ValueChanged<XFile>? onAccepted,
    ValueChanged<CapturedPhoto>? onCaptured,
    bool initialSensitive = false,
    bool autoIngest = false,
    ValueChanged<bool>? onAutoIngestChanged,
    Listenable? activity,
    CaptureActivity Function()? activitySnapshot,
    String? statusLabel,
    bool statusBlocked = false,
    bool deviceFallbackAvailable = true,
  }) => MaterialPageRoute<CaptureResult>(
    builder: (BuildContext context) => CaptureScreen(
      camera: camera,
      onAccepted: onAccepted,
      onCaptured: onCaptured,
      initialSensitive: initialSensitive,
      autoIngest: autoIngest,
      onAutoIngestChanged: onAutoIngestChanged,
      activity: activity,
      activitySnapshot: activitySnapshot,
      statusLabel: statusLabel,
      statusBlocked: statusBlocked,
      deviceFallbackAvailable: deviceFallbackAvailable,
    ),
    fullscreenDialog: true,
  );

  /// Fraction of the shorter viewfinder edge the specimen guide leaves clear.
  static const double specimenInset = 0.08;

  /// Where the label guide starts, as a fraction of the specimen guide's
  /// height measured from its top.
  static const double labelGuideTop = 0.62;

  /// How wide the label guide is, as a fraction of the specimen guide.
  static const double labelGuideWidth = 0.55;

  // A normalized crop adjustment, independent of image dimensions.
  static const double cropAdjustment = 0.02;
  static const double minimumCropExtent = 0.16;

  /// What the control that leaves the camera is called.
  static const String closeLabel = 'Close the camera';

  /// What the control that hands the batch back is called.
  static const String doneLabel = 'Done';

  /// What the shutter is called. A control that draws no word needs one
  /// (10 section 11).
  static const String shutterLabel = 'Take photo';

  @override
  State<CaptureScreen> createState() => _CaptureScreenState();
}

class _CaptureScreenState extends State<CaptureScreen>
    with WidgetsBindingObserver {
  static const _sensitiveLabel = 'Sensitive';

  final List<XFile> _accepted = <XFile>[];
  CaptureCamera? _camera;
  StreamSubscription<CapturePreviewReading>? _subscription;
  Future<void> _cameraLifecycle = Future<void>.value();
  CaptureUnavailable? _unavailable;
  CapturePreviewReading? _reading;
  Offset? _focusPoint;
  bool _focusLocked = false;
  bool _starting = true;
  bool _capturing = false;
  bool _editing = false;
  bool _autoIngest = false;
  bool _sensitive = false;
  bool _reviewSensitive = false;
  bool _cropping = false;
  bool _foreground = true;
  int _cameraGeneration = 0;
  int _acceptedCount = 0;
  Rect _crop = const Rect.fromLTWH(0.06, 0.06, 0.88, 0.88);
  XFile? _review;
  Uint8List? _reviewBytes;
  ImageProvider<Object>? _reviewImage;
  Uint8List? _lastShotBytes;
  ImageProvider? _lastShotThumbnail;
  int? _thumbnailWidth;
  CaptureDimensions? _reviewDimensions;
  String? _editError;
  String? _captureError;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _autoIngest = widget.autoIngest;
    _sensitive = widget.initialSensitive;
    _requestCameraStart();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final ui = context.ui;
    final width =
        ((ui.space.targetMin + ui.space.s2) *
                MediaQuery.devicePixelRatioOf(context))
            .ceil();
    if (_thumbnailWidth != width) {
      _thumbnailWidth = width;
      _setLastShotBytes(_lastShotBytes);
    }
  }

  void _setLastShotBytes(Uint8List? bytes) {
    final previous = _lastShotThumbnail;
    _lastShotBytes = bytes;
    _lastShotThumbnail = bytes == null
        ? null
        : ResizeImage.resizeIfNeeded(_thumbnailWidth, null, MemoryImage(bytes));
    if (previous != _lastShotThumbnail) unawaited(previous?.evict());
  }

  void _setReviewBytes(Uint8List? bytes) {
    final ImageProvider<Object>? previous = _reviewImage;
    _reviewBytes = bytes;
    if (bytes == null) {
      _reviewImage = null;
    } else {
      final double pixelRatio = MediaQuery.devicePixelRatioOf(context);
      final Size screen = MediaQuery.sizeOf(context);
      final int cacheSide = math.max(
        1,
        (math.max(screen.width, screen.height) * pixelRatio).ceil(),
      );
      _reviewImage = ResizeImage.resizeIfNeeded(
        cacheSide,
        null,
        MemoryImage(bytes),
      );
    }
    if (previous != null && previous != _reviewImage) {
      unawaited(previous.evict());
    }
  }

  @override
  void didUpdateWidget(covariant CaptureScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.autoIngest != widget.autoIngest && !_capturing) {
      _autoIngest = widget.autoIngest;
    }
  }

  void _queueCameraLifecycle(Future<void> Function() transition) {
    final Future<void> previous = _cameraLifecycle;
    _cameraLifecycle = () async {
      try {
        await previous;
      } catch (_) {
        // A failed controller must never prevent the next lifecycle request.
      }
      try {
        await transition();
      } catch (_) {
        // Start reports its own user-facing failure. Suspend is best-effort.
      }
    }();
  }

  void _requestCameraStart() {
    final int generation = ++_cameraGeneration;
    if (mounted && !_starting) setState(() => _starting = true);
    _queueCameraLifecycle(() => _start(generation));
  }

  Future<void> _start(int generation) async {
    if (!mounted ||
        !_foreground ||
        generation != _cameraGeneration ||
        _camera != null) {
      return;
    }
    try {
      final CaptureCamera camera = await widget.camera();
      if (!mounted || !_foreground || generation != _cameraGeneration) {
        await _releaseCamera(null, camera);
        return;
      }
      try {
        await camera.start();
      } catch (error, stackTrace) {
        await _releaseCamera(null, camera);
        Error.throwWithStackTrace(error, stackTrace);
      }
      if (!mounted || !_foreground || generation != _cameraGeneration) {
        await _releaseCamera(null, camera);
        return;
      }
      _subscription = camera.readings.listen(_onReading);
      setState(() {
        _camera = camera;
        _unavailable = null;
        _starting = false;
      });
    } on CaptureCameraUnavailable catch (error) {
      if (mounted && _foreground && generation == _cameraGeneration) {
        setState(() {
          _unavailable = error.kind;
          _starting = false;
        });
      }
    } catch (_) {
      if (mounted && _foreground && generation == _cameraGeneration) {
        setState(() {
          _unavailable = CaptureUnavailable.failed;
          _starting = false;
        });
      }
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    switch (state) {
      case AppLifecycleState.resumed:
        if (_foreground && _camera != null) return;
        // Android marks the activity inactive while its runtime camera
        // permission sheet is on top. In that case the original start is
        // still waiting for the permission result; starting a second camera
        // on resume would ask twice and can leave CameraX waiting forever
        // after "Don't ask again". A real background transition reaches
        // hidden/paused below and sets _foreground to false.
        if (_foreground && _starting && _camera == null) return;
        _foreground = true;
        _requestCameraStart();
        break;
      case AppLifecycleState.inactive:
        // See the resumed case above. Keep the pending start alive for a
        // transient system overlay, but continue to release an initialized
        // camera immediately and let hidden/paused handle real backgrounding.
        if (_starting && _camera == null) return;
        if (!_foreground) return;
        _foreground = false;
        _requestCameraSuspend();
        break;
      case AppLifecycleState.hidden:
      case AppLifecycleState.paused:
      case AppLifecycleState.detached:
        if (!_foreground) return;
        _foreground = false;
        _requestCameraSuspend();
        break;
    }
  }

  void _requestCameraSuspend() {
    ++_cameraGeneration;
    // A frame can rebuild while the controller is still disposing. Publish
    // its absence before releasing it, even when a review covers the preview.
    setState(() {
      _starting = true;
      _capturing = false;
    });
    _queueCameraLifecycle(_suspendCamera);
  }

  Future<void> _suspendCamera() async {
    final StreamSubscription<CapturePreviewReading>? subscription =
        _subscription;
    final CaptureCamera? camera = _camera;
    _subscription = null;
    _camera = null;
    await _releaseCamera(subscription, camera);
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
    final int generation = _cameraGeneration;
    final bool sensitive = _sensitive;
    bool isCurrent() =>
        mounted &&
        _foreground &&
        generation == _cameraGeneration &&
        identical(camera, _camera);
    setState(() {
      _capturing = true;
      _captureError = null;
    });
    try {
      final XFile file = await camera.capture();
      if (!isCurrent()) return;
      // Android CameraX can return upright JPEG pixels with the undefined
      // EXIF orientation value zero. Repair only that metadata value in an
      // in-memory copy before either submission path sees it; the camera's
      // temporary original remains untouched.
      final Uint8List capturedBytes = await readCapture(file);
      if (!isCurrent()) return;
      final Uint8List bytes = normalizeCameraExifOrientation(capturedBytes);
      if (_autoIngest) {
        final XFile normalized = await _normalizeCameraCapture(
          file,
          bytes: bytes,
        );
        if (!isCurrent()) return;
        _accept(normalized, bytes: bytes, sensitive: sensitive);
        return;
      }
      final CaptureDimensions dimensions = await captureDimensions(bytes);
      if (!isCurrent()) return;
      // Review owns an in-memory copy. The camera package's temporary path is
      // no longer retained, while these bytes remain available until Intake
      // accepts them or the operator retakes the photograph.
      final XFile review = await _normalizeCameraCapture(file, bytes: bytes);
      if (!isCurrent()) return;
      setState(() {
        _review = review;
        _setReviewBytes(bytes);
        _reviewSensitive = sensitive;
        _reviewDimensions = dimensions;
        _cropping = false;
        _editError = null;
      });
    } on FormatException {
      if (isCurrent()) {
        setState(
          () => _captureError = 'Photo could not be read. Take it again.',
        );
      }
    } on CaptureCameraUnavailable catch (error) {
      if (isCurrent()) setState(() => _unavailable = error.kind);
    } catch (_) {
      if (isCurrent()) {
        setState(() => _unavailable = CaptureUnavailable.failed);
      }
    } finally {
      if (isCurrent()) setState(() => _capturing = false);
    }
  }

  /// Camera Web can return a Blob-backed [XFile] without a filename or MIME
  /// type. Intake deliberately admits images by filename extension, so give
  /// camera output stable image metadata before either submission path sees
  /// it. Native captures that already carry matching metadata keep their
  /// original file handle and avoid an unnecessary byte copy.
  Future<XFile> _normalizeCameraCapture(XFile file, {Uint8List? bytes}) async {
    final String originalName = file.name.trim();
    String? extension = _supportedCameraExtension(originalName);
    extension ??= _cameraExtensionForMime(file.mimeType);

    Uint8List? capturedBytes = bytes;
    if (extension == null) {
      capturedBytes ??= await readCapture(file);
      extension = _cameraExtensionForBytes(capturedBytes);
    }
    if (extension == null) {
      throw const FormatException('Unsupported camera image format.');
    }

    final String mimeType = _cameraMimeForExtension(extension);
    final bool keepOriginalName =
        _isSafeCameraFilename(originalName) &&
        _supportedCameraExtension(originalName) != null;
    final String name = keepOriginalName
        ? originalName
        : 'camera-photo-${_acceptedCount + 1}.$extension';
    final String? originalMimeType = file.mimeType?.trim().toLowerCase();
    if (capturedBytes == null &&
        name == file.name &&
        (originalMimeType == null ||
            originalMimeType.isEmpty ||
            originalMimeType == mimeType)) {
      return file;
    }

    capturedBytes ??= await readCapture(file);
    return XFile.fromData(
      capturedBytes,
      path: name,
      name: name,
      mimeType: mimeType,
    );
  }

  void _retake() => setState(() {
    _review = null;
    _setReviewBytes(null);
    _reviewDimensions = null;
    _cropping = false;
    _editError = null;
  });

  /// Batch mode: accepting returns straight to the viewfinder for the next
  /// specimen rather than back to the intake screen.
  void _use() {
    final XFile? file = _review;
    if (file == null) return;
    _accept(file, bytes: _reviewBytes!, sensitive: _reviewSensitive);
  }

  void _accept(
    XFile file, {
    required Uint8List bytes,
    required bool sensitive,
  }) {
    final ValueChanged<XFile>? onAccepted = widget.onAccepted;
    final ValueChanged<CapturedPhoto>? onCaptured = widget.onCaptured;
    setState(() {
      _acceptedCount++;
      // A streamed photo is owned by Intake as soon as the callback returns.
      // Keep no result-file list for either streaming interface.
      if (onAccepted == null && onCaptured == null) _accepted.add(file);
      // The resized provider bounds decoded pixels, but its cache key also
      // retains the encoded bytes. Evict the old key when replacing the photo.
      _setLastShotBytes(bytes);
      _review = null;
      _setReviewBytes(null);
      _reviewDimensions = null;
      _cropping = false;
      _editError = null;
    });
    onAccepted?.call(file);
    onCaptured?.call(CapturedPhoto(file: file, sensitive: sensitive));
  }

  void _setAutoIngest(bool value) {
    setState(() => _autoIngest = value);
    widget.onAutoIngestChanged?.call(value);
  }

  Future<void> _rotate() => _edit(quarterTurns: 1);

  Future<void> _applyCrop() => _edit(crop: _crop);

  void _adjustCrop({double dx = 0, double dy = 0, double grow = 0}) {
    final shifted = _crop.shift(
      Offset(
        dx.clamp(-_crop.left, 1 - _crop.right),
        dy.clamp(-_crop.top, 1 - _crop.bottom),
      ),
    );
    final change = grow < 0
        ? math.max(
            grow,
            -math.max(
                  0,
                  math.min(shifted.width, shifted.height) -
                      CaptureScreen.minimumCropExtent,
                ) /
                2,
          )
        : grow;
    setState(() {
      _crop = Rect.fromLTRB(
        (shifted.left - change).clamp(0, 1),
        (shifted.top - change).clamp(0, 1),
        (shifted.right + change).clamp(0, 1),
        (shifted.bottom + change).clamp(0, 1),
      );
    });
  }

  Widget _cropControls(BuildContext context) => SingleChildScrollView(
    scrollDirection: Axis.horizontal,
    child: Row(
      children: [
        for (final (label, icon, dx, dy, grow)
            in <(String, IconSpec, double, double, double)>[
              (
                'Move left',
                UiIcons.previous,
                -CaptureScreen.cropAdjustment,
                0,
                0,
              ),
              ('Move right', UiIcons.next, CaptureScreen.cropAdjustment, 0, 0),
              (
                'Move up',
                UiIcons.collapse,
                0,
                -CaptureScreen.cropAdjustment,
                0,
              ),
              ('Move down', UiIcons.expand, 0, CaptureScreen.cropAdjustment, 0),
              (
                'Expand frame',
                UiIcons.enterFullscreen,
                0,
                0,
                CaptureScreen.cropAdjustment,
              ),
              (
                'Reduce frame',
                UiIcons.exitFullscreen,
                0,
                0,
                -CaptureScreen.cropAdjustment,
              ),
            ])
          UiIconButton(
            icon: icon,
            semanticsLabel: label,
            tooltip: label,
            onPressed: _editing
                ? null
                : () => _adjustCrop(dx: dx, dy: dy, grow: grow),
          ),
      ],
    ),
  );

  Future<void> _edit({int quarterTurns = 0, Rect? crop}) async {
    final Uint8List? bytes = _reviewBytes;
    if (bytes == null || _editing) return;
    setState(() {
      _editing = true;
      _editError = null;
    });
    try {
      final CaptureEditResult result = await applyCaptureEdit(
        CaptureEditRequest(
          bytes: bytes,
          quarterTurns: quarterTurns,
          crop: crop,
        ),
      );
      if (!mounted) return;
      final String original = _review?.name ?? 'camera-photo';
      final String stem = original.replaceFirst(RegExp(r'\.[^.]+$'), '');
      setState(() {
        _setReviewBytes(result.bytes);
        _reviewDimensions = CaptureDimensions(result.width, result.height);
        _review = XFile.fromData(
          result.bytes,
          path: '$stem-edited.png',
          name: '$stem-edited.png',
          mimeType: 'image/png',
        );
        _cropping = false;
        _crop = const Rect.fromLTWH(0.06, 0.06, 0.88, 0.88);
      });
    } catch (_) {
      if (mounted) {
        setState(() => _editError = 'Edit not applied. Retake or send as is.');
      }
    } finally {
      if (mounted) setState(() => _editing = false);
    }
  }

  void _finish({CaptureUnavailable? unavailable}) {
    if (!mounted) return;
    Navigator.of(context).pop(
      CaptureResult(
        files: List<XFile>.unmodifiable(_accepted),
        streamed: widget.onAccepted != null || widget.onCaptured != null,
        unavailable: unavailable,
      ),
    );
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _setLastShotBytes(null);
    _setReviewBytes(null);
    _foreground = false;
    ++_cameraGeneration;
    final StreamSubscription<CapturePreviewReading>? subscription =
        _subscription;
    final CaptureCamera? camera = _camera;
    _subscription = null;
    _camera = null;
    unawaited(_disposeAfterLifecycle(_cameraLifecycle, subscription, camera));
    super.dispose();
  }

  Future<void> _disposeAfterLifecycle(
    Future<void> lifecycle,
    StreamSubscription<CapturePreviewReading>? subscription,
    CaptureCamera? camera,
  ) async {
    try {
      await lifecycle;
    } catch (_) {
      // Continue releasing the controller even after a failed transition.
    }
    await _releaseCamera(subscription, camera);
  }

  Future<void> _releaseCamera(
    StreamSubscription<CapturePreviewReading>? subscription,
    CaptureCamera? camera,
  ) async {
    try {
      await subscription?.cancel();
    } catch (_) {
      // The stream may already be closed by a platform controller failure.
    }
    try {
      await camera?.dispose();
    } catch (_) {
      // Route disposal cannot surface an asynchronous controller error.
    }
  }

  @override
  Widget build(BuildContext context) => PopScope<CaptureResult>(
    canPop: false,
    onPopInvokedWithResult: (bool didPop, CaptureResult? _) {
      if (didPop) return;
      // A back gesture keeps what was already accepted. Nothing the
      // operator confirmed is thrown away by leaving.
      _finish();
    },
    // No sky and no navigation: the preview is the evidence and it fills the
    // window (07 section 5).
    child: UiScaffold(
      sky: SkyPreset.none,
      body: SafeArea(child: _body()),
    ),
  );

  Widget _body() {
    // An operator's unsent photograph wins over controller restart state. A
    // background/resume cycle may restart or fail the camera behind it, but
    // neither is allowed to replace the evidence they are still reviewing.
    if (_reviewBytes != null) return _reviewBody();
    if (!_starting && _unavailable != null) return _unavailableBody();
    final CaptureCamera? camera = _camera;
    if (_starting || camera == null) {
      return Center(
        child: UiProgress.ring(
          semanticsLabel: 'Starting the camera',
          size: UiProgressSize.large,
        ),
      );
    }
    return _viewfinder(camera);
  }

  Widget _closeButton() => UiIconButton(
    icon: UiIcons.close,
    semanticsLabel: CaptureScreen.closeLabel,
    tooltip: CaptureScreen.closeLabel,
    onPressed: _finish,
  );

  Widget _unavailableBody() {
    final UiThemeData ui = context.ui;
    return Column(
      children: [
        Padding(
          padding: EdgeInsetsDirectional.symmetric(
            horizontal: ui.space.s4,
            vertical: ui.space.s2,
          ),
          child: Align(
            alignment: AlignmentDirectional.centerStart,
            child: _closeButton(),
          ),
        ),
        Expanded(
          child: Center(
            child: SingleChildScrollView(
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
                        label:
                            widget.deviceFallbackAvailable &&
                                _unavailable == CaptureUnavailable.failed
                            ? 'Use phone camera'
                            : 'Choose files',
                        onPressed: () => _finish(unavailable: _unavailable),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _reviewBody() {
    final UiThemeData ui = context.ui;
    return Column(
      children: <Widget>[
        Expanded(
          flex: 2,
          child: Surface(
            role: SurfaceRole.matte,
            radius: ui.shape.sheet,
            child: LayoutBuilder(
              builder: (BuildContext context, BoxConstraints constraints) {
                final CaptureDimensions? dimensions = _reviewDimensions;
                final ImageProvider<Object> reviewImage = _reviewImage!;
                if (!_cropping || dimensions == null) {
                  return Center(
                    child: Image(
                      image: reviewImage,
                      fit: BoxFit.contain,
                      gaplessPlayback: true,
                      semanticLabel: 'The photo you took',
                    ),
                  );
                }
                final double scale = math.min(
                  constraints.maxWidth / dimensions.width,
                  constraints.maxHeight / dimensions.height,
                );
                final Size shown = Size(
                  dimensions.width * scale,
                  dimensions.height * scale,
                );
                return Stack(
                  fit: StackFit.expand,
                  children: <Widget>[
                    Center(
                      child: Image(
                        image: reviewImage,
                        width: shown.width,
                        height: shown.height,
                        fit: BoxFit.fill,
                        gaplessPlayback: true,
                        semanticLabel: 'The photo you took',
                      ),
                    ),
                    Center(
                      child: SizedBox.fromSize(
                        size: shown,
                        child: _CropSelection(
                          value: _crop,
                          onChanged: (Rect value) =>
                              setState(() => _crop = value),
                        ),
                      ),
                    ),
                  ],
                );
              },
            ),
          ),
        ),
        Flexible(
          child: ConstrainedBox(
            constraints: BoxConstraints(
              maxHeight: math.min(
                ui.space.readingMax,
                MediaQuery.sizeOf(context).height / 2,
              ),
            ),
            child: SingleChildScrollView(
              padding: EdgeInsetsDirectional.all(ui.space.s4),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: <Widget>[
                  Text('Photo ${_acceptedCount + 1}', style: ui.type.title),
                  SizedBox(height: ui.space.s2),
                  Text(
                    'All labels sharp and in frame?',
                    style: ui.type.body.copyWith(color: ui.color.ink),
                  ),
                  if (_editError != null) ...<Widget>[
                    SizedBox(height: ui.space.s3),
                    UiBanner(message: _editError!, tone: UiBannerTone.blocked),
                  ],
                  SizedBox(height: ui.space.s4),
                  if (_cropping) _cropControls(context),
                  if (_cropping) SizedBox(height: ui.space.s4),
                  if (_cropping)
                    UiButtonRow(
                      primary: UiButton(
                        key: const ValueKey<String>('capture-apply-crop'),
                        label: _editing ? 'Applying crop' : 'Apply crop',
                        leading: UiIcons.check,
                        onPressed: _editing ? null : _applyCrop,
                      ),
                      secondary: UiButton(
                        label: 'Cancel crop',
                        variant: UiButtonVariant.secondary,
                        onPressed: _editing
                            ? null
                            : () => setState(() => _cropping = false),
                      ),
                    )
                  else ...<Widget>[
                    Row(
                      children: <Widget>[
                        UiButton(
                          key: const ValueKey<String>('capture-rotate'),
                          label: _editing ? 'Rotating' : 'Rotate',
                          variant: UiButtonVariant.secondary,
                          leading: UiIcons.rotateView,
                          onPressed: _editing ? null : _rotate,
                        ),
                        SizedBox(width: ui.space.s2),
                        UiButton(
                          key: const ValueKey<String>('capture-crop'),
                          label: 'Crop',
                          variant: UiButtonVariant.secondary,
                          leading: UiIcons.correctRegions,
                          onPressed: _editing
                              ? null
                              : () => setState(() {
                                  _crop = const Rect.fromLTWH(
                                    0.06,
                                    0.06,
                                    0.88,
                                    0.88,
                                  );
                                  _cropping = true;
                                }),
                        ),
                      ],
                    ),
                    if (widget.onCaptured != null)
                      UiSwitch(
                        key: const ValueKey('capture-review-sensitive'),
                        label: _sensitiveLabel,
                        value: _reviewSensitive,
                        onChanged: _editing
                            ? null
                            : (value) =>
                                  setState(() => _reviewSensitive = value),
                      ),
                  ],
                ],
              ),
            ),
          ),
        ),
        if (!_cropping)
          Padding(
            padding: EdgeInsetsDirectional.fromSTEB(
              ui.space.s4,
              0,
              ui.space.s4,
              ui.space.s4,
            ),
            child: _reviewDecisions(),
          ),
      ],
    );
  }

  Widget _reviewDecisions() {
    final send = UiButton(
      key: const ValueKey<String>('capture-send'),
      label: 'Send',
      onPressed: _editing ? null : _use,
    );
    final retake = UiButton(
      label: 'Retake',
      variant: UiButtonVariant.secondary,
      onPressed: _editing ? null : _retake,
    );
    final width = math.max(
      send.intrinsicWidth(context),
      retake.intrinsicWidth(context),
    );
    return UiButtonRow(
      primary: _EqualWidthButton(button: send, width: width),
      secondary: _EqualWidthButton(button: retake, width: width),
    );
  }

  Widget _activityBar(BuildContext context) {
    Widget summary(BuildContext context) {
      final current = widget.statusLabel != null
          ? CaptureActivity(
              label: widget.statusLabel!,
              problem: widget.statusBlocked,
            )
          : widget.activitySnapshot?.call();
      if (current == null || current.label.isEmpty) {
        return const SizedBox.shrink();
      }
      final ui = context.ui;
      return Column(
        key: const ValueKey('capture-intake-activity'),
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          Semantics(
            container: true,
            liveRegion: true,
            child: Text(
              current.label,
              style: ui.type.bodySmall.copyWith(
                color: current.problem
                    ? ui.color.status.blocked.content
                    : ui.color.inkSecondary,
              ),
            ),
          ),
          if (current.progress != null) ...[
            SizedBox(height: ui.space.s2),
            UiProgress.bar(
              value: current.progress,
              semanticsLabel: 'Sending photos',
            ),
          ],
        ],
      );
    }

    final activity = widget.activity;
    if (activity == null) return summary(context);
    return AnimatedBuilder(
      animation: activity,
      builder: (context, _) => summary(context),
    );
  }

  Widget _viewfinder(CaptureCamera camera) {
    final ui = context.ui;
    return Column(
      children: [
        Padding(
          padding: EdgeInsetsDirectional.symmetric(
            horizontal: ui.space.s4,
            vertical: ui.space.s2,
          ),
          child: Row(
            children: [
              _closeButton(),
              SizedBox(width: ui.space.s2),
              Expanded(
                child: UiSegmented<bool>(
                  key: const ValueKey('capture-auto-ingest'),
                  segments: const [
                    UiSegment(value: false, label: 'Review'),
                    UiSegment(value: true, label: 'Send now'),
                  ],
                  value: _autoIngest,
                  onChanged: _capturing ? null : _setAutoIngest,
                ),
              ),
            ],
          ),
        ),
        Expanded(
          child: LayoutBuilder(
            builder: (context, constraints) {
              final preview = _viewfinderPreview(camera);
              final guidance = _viewfinderGuidance();
              final controls = _viewfinderControls();
              // Use the available window, not the device or its orientation.
              if (constraints.maxWidth >= WindowClass.mediumMin &&
                  constraints.maxWidth > constraints.maxHeight) {
                return Row(
                  children: [
                    Expanded(child: preview),
                    SizedBox(
                      width: math.min(
                        ui.space.readingMax,
                        constraints.maxWidth / 2,
                      ),
                      child: Column(
                        children: [
                          Expanded(child: guidance),
                          controls,
                        ],
                      ),
                    ),
                  ],
                );
              }
              return Column(
                children: [
                  Expanded(flex: 2, child: preview),
                  Expanded(child: guidance),
                  controls,
                ],
              );
            },
          ),
        ),
      ],
    );
  }

  Widget _viewfinderPreview(CaptureCamera camera) {
    final UiThemeData ui = context.ui;
    return LayoutBuilder(
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
                      key: const ValueKey<String>('capture-framing-guides'),
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
          ],
        );
      },
    );
  }

  Widget _viewfinderGuidance() {
    final ui = context.ui;
    final hint = _reading?.hint;
    return SingleChildScrollView(
      key: const ValueKey('capture-guidance'),
      padding: EdgeInsetsDirectional.all(ui.space.s4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Fit specimen and labels inside',
            style: ui.type.body.copyWith(color: ui.color.ink),
          ),
          if (hint != null) ...[
            SizedBox(height: ui.space.s2),
            Semantics(
              container: true,
              liveRegion: true,
              child: Text(
                hint,
                key: const ValueKey('capture-exposure-hint'),
                style: ui.type.bodySmall.copyWith(color: ui.color.inkSecondary),
              ),
            ),
          ],
          if (_captureError != null) ...[
            SizedBox(height: ui.space.s3),
            UiBanner(message: _captureError!, tone: UiBannerTone.blocked),
          ],
          SizedBox(height: ui.space.s2),
          _activityBar(context),
        ],
      ),
    );
  }

  Widget _viewfinderControls() {
    final ui = context.ui;
    final thumbnail = _lastShotThumbnail;
    return Padding(
      padding: EdgeInsetsDirectional.all(ui.space.s4),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (widget.onCaptured != null) ...[
            UiSwitch(
              key: const ValueKey('capture-sensitive'),
              label: _sensitiveLabel,
              value: _sensitive,
              onChanged: _capturing
                  ? null
                  : (value) => setState(() => _sensitive = value),
            ),
            SizedBox(height: ui.space.s2),
          ],
          Row(
            children: [
              Expanded(
                child: Align(
                  alignment: AlignmentDirectional.centerStart,
                  child: Semantics(
                    container: true,
                    liveRegion: true,
                    label: _acceptedCount == 1
                        ? '1 photo'
                        : '$_acceptedCount photos',
                    excludeSemantics: true,
                    child: Stack(
                      key: const ValueKey('capture-last-shot'),
                      children: [
                        SizedBox.square(
                          dimension: ui.space.targetMin + ui.space.s2,
                          child: thumbnail == null
                              ? const UiIcon(UiIcons.image)
                              : Image(
                                  image: thumbnail,
                                  fit: BoxFit.cover,
                                  gaplessPlayback: true,
                                  errorBuilder: (context, error, stack) =>
                                      const UiIcon(UiIcons.image),
                                ),
                        ),
                        PositionedDirectional(
                          bottom: 0,
                          end: 0,
                          child: UiBadge(_acceptedCount),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
              _Shutter(
                key: const ValueKey('capture-shutter'),
                onPressed: _capturing ? null : _capture,
              ),
              Expanded(
                child: Align(
                  alignment: AlignmentDirectional.centerEnd,
                  child: UiButton(
                    label: CaptureScreen.doneLabel,
                    variant: UiButtonVariant.secondary,
                    onPressed: _finish,
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

/// UiButton's capsule hugs its label even inside a wider box. Use its style
/// and pressable with an explicit surface width for this equal-choice pair.
class _EqualWidthButton extends UiButton {
  _EqualWidthButton({required UiButton button, required this.width})
    : super(
        key: button.key,
        label: button.label,
        variant: button.variant,
        onPressed: button.onPressed,
      );

  final double width;

  @override
  double intrinsicWidth(BuildContext context) => width;

  @override
  Widget build(BuildContext context) {
    final ui = context.ui;
    final style = UiButtonStyle.resolve(
      ui,
      variant,
      size,
      textScaler: MediaQuery.textScalerOf(context),
    );
    return Pressable(
      semanticsLabel: label,
      onPressed: onPressed,
      radius: ui.shape.inner,
      stateLayerColour: style.overlay,
      builder: (context, states) => DecoratedBox(
        key: ValueKey('capture-review-$label-surface'),
        decoration: ShapeDecoration(
          color: style.background.resolve(states),
          shape: Squircle.border(
            ui.shape.inner,
            side: style.side.resolve(states) ?? BorderSide.none,
          ),
        ),
        child: SizedBox(
          width: width,
          child: ConstrainedBox(
            constraints: BoxConstraints(minHeight: style.minHeight),
            child: Padding(
              padding: style.padding,
              child: Center(
                heightFactor: 1,
                child: UiLabel(
                  label,
                  style: style.label.copyWith(
                    color: style.foreground.resolve(states),
                  ),
                  textAlign: TextAlign.center,
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

const Set<String> _supportedCameraExtensions = <String>{
  'jpg',
  'jpeg',
  'png',
  'heic',
  'heif',
  'tif',
  'tiff',
  'dng',
};

String? _supportedCameraExtension(String name) {
  final int dot = name.lastIndexOf('.');
  if (dot <= 0 || dot == name.length - 1) return null;
  final String extension = name.substring(dot + 1).toLowerCase();
  return _supportedCameraExtensions.contains(extension) ? extension : null;
}

bool _isSafeCameraFilename(String name) {
  if (name.isEmpty || name.contains('/') || name.contains(r'\')) return false;
  return !name.codeUnits.any((int unit) => unit < 0x20 || unit == 0x7f);
}

String? _cameraExtensionForMime(String? mimeType) =>
    switch (mimeType?.trim().toLowerCase()) {
      'image/jpeg' || 'image/jpg' => 'jpg',
      'image/png' => 'png',
      'image/heic' => 'heic',
      'image/heif' => 'heif',
      'image/tiff' => 'tif',
      'image/dng' || 'image/x-adobe-dng' => 'dng',
      _ => null,
    };

String? _cameraExtensionForBytes(Uint8List bytes) {
  if (bytes.length >= 3 &&
      bytes[0] == 0xff &&
      bytes[1] == 0xd8 &&
      bytes[2] == 0xff) {
    return 'jpg';
  }
  const List<int> png = <int>[0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a];
  if (bytes.length >= png.length) {
    var matches = true;
    for (var index = 0; index < png.length; index++) {
      if (bytes[index] != png[index]) {
        matches = false;
        break;
      }
    }
    if (matches) return 'png';
  }
  return null;
}

String _cameraMimeForExtension(String extension) => switch (extension) {
  'jpg' || 'jpeg' => 'image/jpeg',
  'png' => 'image/png',
  'heic' || 'heif' => 'image/heic',
  'tif' || 'tiff' => 'image/tiff',
  'dng' => 'image/x-adobe-dng',
  _ => throw const FormatException('Unsupported camera image format.'),
};

enum _CropDrag { move, topLeft, topRight, bottomLeft, bottomRight }

/// A deliberately small cropper: one visible frame, four large corner
/// handles, and drag-to-move. The normalized value survives phone/tablet
/// resizing and maps directly to the pixels the operator sees.
class _CropSelection extends StatefulWidget {
  const _CropSelection({required this.value, required this.onChanged});

  final Rect value;
  final ValueChanged<Rect> onChanged;

  @override
  State<_CropSelection> createState() => _CropSelectionState();
}

class _CropSelectionState extends State<_CropSelection> {
  _CropDrag? _drag;
  Offset? _last;

  static const double _minimum = CaptureScreen.minimumCropExtent;
  static const double _handleRadius = 28;

  Rect _pixels(Size size) => Rect.fromLTRB(
    widget.value.left * size.width,
    widget.value.top * size.height,
    widget.value.right * size.width,
    widget.value.bottom * size.height,
  );

  void _start(DragStartDetails details, Size size) {
    final Rect crop = _pixels(size);
    final Offset point = details.localPosition;
    final List<(_CropDrag, Offset)> corners = <(_CropDrag, Offset)>[
      (_CropDrag.topLeft, crop.topLeft),
      (_CropDrag.topRight, crop.topRight),
      (_CropDrag.bottomLeft, crop.bottomLeft),
      (_CropDrag.bottomRight, crop.bottomRight),
    ];
    _drag = corners
        .where((item) => (item.$2 - point).distance <= _handleRadius)
        .map((item) => item.$1)
        .firstOrNull;
    if (_drag == null && crop.contains(point)) _drag = _CropDrag.move;
    _last = point;
  }

  void _update(DragUpdateDetails details, Size size) {
    final _CropDrag? drag = _drag;
    final Offset? previous = _last;
    if (drag == null || previous == null || size.isEmpty) return;
    final Offset delta = Offset(
      (details.localPosition.dx - previous.dx) / size.width,
      (details.localPosition.dy - previous.dy) / size.height,
    );
    _last = details.localPosition;
    Rect crop = widget.value;
    switch (drag) {
      case _CropDrag.move:
        final double dx = delta.dx.clamp(-crop.left, 1 - crop.right);
        final double dy = delta.dy.clamp(-crop.top, 1 - crop.bottom);
        crop = crop.shift(Offset(dx, dy));
        break;
      case _CropDrag.topLeft:
        crop = Rect.fromLTRB(
          (crop.left + delta.dx).clamp(0.0, crop.right - _minimum),
          (crop.top + delta.dy).clamp(0.0, crop.bottom - _minimum),
          crop.right,
          crop.bottom,
        );
        break;
      case _CropDrag.topRight:
        crop = Rect.fromLTRB(
          crop.left,
          (crop.top + delta.dy).clamp(0.0, crop.bottom - _minimum),
          (crop.right + delta.dx).clamp(crop.left + _minimum, 1.0),
          crop.bottom,
        );
        break;
      case _CropDrag.bottomLeft:
        crop = Rect.fromLTRB(
          (crop.left + delta.dx).clamp(0.0, crop.right - _minimum),
          crop.top,
          crop.right,
          (crop.bottom + delta.dy).clamp(crop.top + _minimum, 1.0),
        );
        break;
      case _CropDrag.bottomRight:
        crop = Rect.fromLTRB(
          crop.left,
          crop.top,
          (crop.right + delta.dx).clamp(crop.left + _minimum, 1.0),
          (crop.bottom + delta.dy).clamp(crop.top + _minimum, 1.0),
        );
        break;
    }
    widget.onChanged(crop);
  }

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (BuildContext context, BoxConstraints constraints) {
      final Size size = constraints.biggest;
      return Semantics(
        label:
            'Crop selection. Drag inside to move it, or drag a corner to resize it.',
        value:
            'Left ${(widget.value.left * 100).round()} percent, '
            'top ${(widget.value.top * 100).round()} percent, '
            'width ${(widget.value.width * 100).round()} percent, '
            'height ${(widget.value.height * 100).round()} percent',
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onPanStart: (DragStartDetails details) => _start(details, size),
          onPanUpdate: (DragUpdateDetails details) => _update(details, size),
          onPanEnd: (_) {
            _drag = null;
            _last = null;
          },
          child: CustomPaint(
            key: const ValueKey<String>('capture-crop-selection'),
            painter: _CropSelectionPainter(
              crop: _pixels(size),
              boundary: context.ui.color.paper,
              shade: context.ui.color.ink.withValues(alpha: 0.58),
              strokeWidth: context.ui.shape.stroke.emphasis,
            ),
          ),
        ),
      );
    },
  );
}

class _CropSelectionPainter extends CustomPainter {
  const _CropSelectionPainter({
    required this.crop,
    required this.boundary,
    required this.shade,
    required this.strokeWidth,
  });

  final Rect crop;
  final Color boundary;
  final Color shade;
  final double strokeWidth;

  @override
  void paint(Canvas canvas, Size size) {
    final Path shadePath = Path()
      ..fillType = PathFillType.evenOdd
      ..addRect(Offset.zero & size)
      ..addRect(crop);
    canvas.drawPath(shadePath, Paint()..color = shade);
    final Paint line = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth
      ..color = boundary;
    canvas.drawRect(crop, line);
    final Paint handle = Paint()
      ..style = PaintingStyle.fill
      ..color = boundary;
    for (final Offset corner in <Offset>[
      crop.topLeft,
      crop.topRight,
      crop.bottomLeft,
      crop.bottomRight,
    ]) {
      canvas.drawCircle(corner, 7, handle);
    }
  }

  @override
  bool shouldRepaint(_CropSelectionPainter old) =>
      old.crop != crop ||
      old.boundary != boundary ||
      old.shade != shade ||
      old.strokeWidth != strokeWidth;
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
