/// Intake and capture (screen blueprints, section 5).
///
/// The capture surface offers page-wide browser drop/picker or native
/// upload/camera. The manifest is the complete account of every selected
/// file, including local refusals, below the large intake surface.
library;

import 'dart:async';
import 'dart:ui' as ui;

import 'package:crypto/crypto.dart';
import 'package:desktop_drop/desktop_drop.dart';
import 'package:file_selector/file_selector.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:image_picker/image_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'capture/capture_camera.dart';
import 'capture/capture_screen.dart';
import 'capture_quality.dart';
import 'models.dart';
import 'screens/intake/capture_card.dart';
import 'screens/intake/manifest_entry.dart';
import 'screens/intake/manifest_panel.dart';
import 'screens/intake/intake_transfer_session.dart';
import 'widgets/motion_reveal.dart';
import 'widgets/upload_item.dart';
import 'widgets/repository_url_import_gate.dart';
import 'widgets/product_modal.dart';
import 'sources.dart';
import 'workspace.dart';

export 'screens/intake/manifest_entry.dart' show ManifestEntry;

/// Builds the production camera. A factory, not a constructor reference,
/// because the interface hands back a future.
Future<CaptureCamera> _platformCamera() async => PlatformCaptureCamera();

/// The largest file this client will read, in bytes.
const int intakeMaximumBytes = 25000000;

/// The largest image this client will try to decode locally.
const int intakeMaximumPixels = 40000000;

/// The largest single dimension this client will try to decode locally.
const int intakeMaximumSide = 20000;

/// The way from intake to the photographs a collection already holds.
///
/// Verb first, three words, inside the 24 character button budget.
const String intakeBrowseSourcesLabel = 'Add from storage';

/// What the message band's dismiss control is called.
const String dismissMessageLabel = 'Dismiss this message';

class IntakeScreen extends StatefulWidget {
  const IntakeScreen({
    super.key,
    required this.repository,
    required this.scope,
    required this.userId,
    required this.onComplete,
    this.onBrowseSources,
    this.pickImages,
    this.recoverCamera,
    this.openCapture,
    this.cameraFactory,
    this.webOverride,
  });
  final SpecimenRepository repository;
  final CollectionScope scope;
  final String userId;
  final VoidCallback onComplete;

  /// Opens the registered sources for this collection.
  ///
  /// Null where this build has none, which hides the control rather than
  /// offering one that cannot answer (blueprint 3).
  final VoidCallback? onBrowseSources;

  /// Test seam for both sources. When set, it replaces the file picker and
  /// the camera entirely.
  final Future<List<XFile>> Function(bool camera)? pickImages;

  /// Test seam for the interrupted-capture recovery path.
  final Future<List<XFile>> Function()? recoverCamera;

  /// Opens the full-screen capture route. Injected so a widget test can run
  /// the capture flow without a device camera.
  final Future<CaptureResult> Function(BuildContext context)? openCapture;

  /// Builds the camera the default capture route uses.
  final CaptureCameraFactory? cameraFactory;

  /// Test seam for the browser presentation. Production always uses [kIsWeb].
  final bool? webOverride;

  @override
  State<IntakeScreen> createState() => _IntakeScreenState();
}

class _IntakeScreenState extends State<IntakeScreen> {
  late IntakeTransferSession _session;
  List<ManifestEntry> get _entries => _session.entries;

  /// The frame's slots, so the upload action goes where 13 section 3.3 puts a
  /// screen's decision.
  UiScaffoldSlots? _slots;

  /// What the published action bar last said, so the frame is told once per
  /// change rather than once per frame.
  ({bool busy, int pending, bool current})? _publishedUpload;

  bool get _busy => _session.busy;
  bool _sensitive = true;
  bool get _stopRequested => _session.stopping;
  bool _choosing = false;
  bool _pageDragging = false;
  String? _error;

  String get _captureOwner => '${widget.userId}:${widget.scope.key}';
  static const String _captureKey = 'pending-camera-owner-v1';

  /// This client offers an in-app camera only where it has one.
  bool get _isWeb => widget.webOverride ?? kIsWeb;

  bool get _nativeCameraAvailable =>
      !kIsWeb &&
      !_isWeb &&
      (defaultTargetPlatform == TargetPlatform.android ||
          defaultTargetPlatform == TargetPlatform.iOS);

  bool get _cameraAvailable =>
      _nativeCameraAvailable ||
      (kIsWeb &&
          _isWeb &&
          (defaultTargetPlatform == TargetPlatform.android ||
              defaultTargetPlatform == TargetPlatform.iOS));

  @override
  void initState() {
    super.initState();
    _session = intakeTransferSession(
      widget.repository,
      widget.scope,
      widget.userId,
    );
    _session.addListener(_sessionChanged);
    _session.attachComplete(widget.onComplete);
    _recoverCamera();
  }

  void _sessionChanged() {
    if (!mounted) return;
    setState(() => _error ??= _session.restoreError);
  }

  @override
  void didUpdateWidget(covariant IntakeScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!identical(oldWidget.repository, widget.repository) ||
        oldWidget.scope.key != widget.scope.key ||
        oldWidget.userId != widget.userId) {
      _session.detachComplete(oldWidget.onComplete);
      _session.removeListener(_sessionChanged);
      _session = intakeTransferSession(
        widget.repository,
        widget.scope,
        widget.userId,
      );
      _session.addListener(_sessionChanged);
      _session.attachComplete(widget.onComplete);
      _sensitive = true;
      _error = null;
    } else if (oldWidget.onComplete != widget.onComplete) {
      _session.detachComplete(oldWidget.onComplete);
      _session.attachComplete(widget.onComplete);
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _slots = UiScaffoldSlots.of(context);
  }

  @override
  void dispose() {
    _session.detachComplete(widget.onComplete);
    _session.removeListener(_sessionChanged);
    _slots?.release(this);
    super.dispose();
  }

  // ------------------------------------------------------------------ input

  Future<void> _chooseFiles() => _collect(
    camera: false,
    load: () async => widget.pickImages != null
        ? await widget.pickImages!(false)
        : await openFiles(
            acceptedTypeGroups: <XTypeGroup>[
              const XTypeGroup(
                label: 'Specimen photographs',
                extensions: <String>[
                  'jpg',
                  'jpeg',
                  'png',
                  'heic',
                  'heif',
                  'tif',
                  'tiff',
                  'dng',
                ],
                uniformTypeIdentifiers: <String>['public.image'],
              ),
            ],
          ),
  );

  Future<void> _takePhotograph() => _collect(camera: true, load: _capture);

  /// The capture route first, the device camera app second.
  ///
  /// `image_picker` stays as the fallback because it is the only path that
  /// works when the in-app camera cannot start: no camera reported, camera
  /// permission refused, or a controller that will not initialise. The reason
  /// is shown as a plain sentence before the fallback runs.
  Future<List<XFile>> _capture() async {
    if (widget.pickImages != null) return widget.pickImages!(true);
    if (_nativeCameraAvailable) {
      final CaptureResult result = await _openCapture();
      if (!result.needsFallback) {
        return result.streamed ? <XFile>[] : result.files;
      }
      if (mounted) {
        setState(() => _error = result.unavailable!.message);
      }
    }
    return _devicePicker();
  }

  Future<CaptureResult> _openCapture() async {
    if (widget.openCapture != null) return widget.openCapture!(context);
    final CaptureResult? result = await Navigator.of(context).push(
      CaptureScreen.route(
        widget.cameraFactory ?? _platformCamera,
        onAccepted: _acceptCameraPhoto,
      ),
    );
    return result ?? const CaptureResult();
  }

  void _acceptCameraPhoto(XFile file) {
    // Admission and upload run under the intake route while the viewfinder
    // stays on top. Each accepted photograph can start before Done is tapped.
    unawaited(
      _acceptFiles(<XFile>[file], camera: true).then((_) => _session.start()),
    );
  }

  /// The pre-existing `image_picker` path, unchanged, including the owner
  /// marker that makes interrupted-capture recovery possible on Android.
  Future<List<XFile>> _devicePicker() async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    await prefs.setString(_captureKey, _captureOwner);
    try {
      final XFile? image = await ImagePicker().pickImage(
        source: ImageSource.camera,
        requestFullMetadata: false,
      );
      return image == null ? <XFile>[] : <XFile>[image];
    } finally {
      if (prefs.getString(_captureKey) == _captureOwner) {
        await prefs.remove(_captureKey);
      }
    }
  }

  Future<void> _collect({
    required bool camera,
    required Future<List<XFile>> Function() load,
  }) async {
    setState(() {
      _choosing = true;
      _error = null;
    });
    try {
      await _acceptFiles(await load(), camera: camera);
      if (camera) unawaited(_session.start());
    } catch (_) {
      if (mounted) {
        setState(
          () => _error =
              'The camera or file picker did not open. Check device '
              'permissions, then choose files.',
        );
      }
    } finally {
      if (mounted) setState(() => _choosing = false);
    }
  }

  /// Routes browser drops through the same byte, type, size and checksum
  /// admission path as the system picker.
  Future<void> _dropFiles(List<XFile> files) {
    if (files.isEmpty) {
      setState(
        () => _error =
            'No files were added. Drop image files, not a folder or link.',
      );
      return Future<void>.value();
    }
    return _collect(camera: false, load: () async => files);
  }

  void _openLinkImport() {
    unawaited(
      showProductModal<void>(
        context: context,
        title: 'Import from link',
        body: (BuildContext modal) => RepositoryUrlIntake(
          scope: widget.scope,
          userId: widget.userId,
          repository: sourcesIn(widget.repository),
          onBrowseSources: widget.onBrowseSources == null
              ? null
              : () {
                  Navigator.of(modal).pop();
                  widget.onBrowseSources!();
                },
        ),
        secondaryAction: (BuildContext modal) => UiButton(
          label: 'Close',
          variant: UiButtonVariant.ghost,
          onPressed: () => Navigator.of(modal).pop(),
        ),
      ),
    );
  }

  Future<void> _recoverCamera() async {
    if ((!_isWeb && defaultTargetPlatform == TargetPlatform.android) ||
        widget.recoverCamera != null) {
      final SharedPreferences prefs = await SharedPreferences.getInstance();
      if (!mounted || prefs.getString(_captureKey) != _captureOwner) return;
      setState(() => _choosing = true);
      try {
        final List<XFile> files;
        if (widget.recoverCamera != null) {
          files = await widget.recoverCamera!();
        } else {
          final LostDataResponse lost = await ImagePicker().retrieveLostData();
          if (lost.exception != null) throw lost.exception!;
          files =
              lost.files ??
              (lost.file == null ? <XFile>[] : <XFile>[lost.file!]);
        }
        if (!mounted) return;
        await _acceptFiles(files, camera: true);
        if (mounted && files.isNotEmpty) {
          setState(
            () => _error =
                'Recovered an interrupted photograph. Check its framing and '
                'readability before you upload.',
          );
        }
      } catch (_) {
        if (mounted) {
          setState(
            () => _error =
                'The interrupted photograph could not be recovered. Take it '
                'again, or choose the original file.',
          );
        }
      } finally {
        if (prefs.getString(_captureKey) == _captureOwner) {
          await prefs.remove(_captureKey);
        }
        if (mounted) setState(() => _choosing = false);
      }
    }
  }

  // ------------------------------------------------------------ examination

  /// Reads every chosen file, measures what this device can measure, and adds
  /// a row for each. A file this client refuses gets a Skipped row carrying
  /// its own reason rather than a banner the next rejection overwrites.
  Future<void> _acceptFiles(List<XFile> files, {required bool camera}) async {
    for (final XFile file in files) {
      try {
        final int size = await file.length();
        if (size == 0 || size > intakeMaximumBytes) {
          _skip(
            key: 'size:${file.name}:$size',
            name: file.name,
            why: size == 0
                ? 'This file is empty, so there is nothing to upload.'
                : 'This file is over 25 MB. Photograph it again at a smaller '
                      'size, or choose a smaller file.',
          );
          continue;
        }
        final Uint8List bytes = await file.readAsBytes();
        final String digest = sha256.convert(bytes).toString();
        final String extension = file.name.split('.').last.toLowerCase();
        final String mime = switch (extension) {
          'jpg' || 'jpeg' => 'image/jpeg',
          'png' => 'image/png',
          'heic' || 'heif' => 'image/heic',
          'tif' || 'tiff' => 'image/tiff',
          'dng' => 'image/x-adobe-dng',
          _ => '',
        };
        if (mime.isEmpty) {
          _skip(
            key: 'format:$digest',
            name: file.name,
            why:
                'This client uploads JPEG, PNG, HEIC, TIFF and DNG. Choose one '
                'of those formats.',
          );
          continue;
        }
        int? width;
        int? height;
        CaptureQuality? quality;
        bool excessiveResolution = false;
        try {
          final ui.ImmutableBuffer buffer =
              await ui.ImmutableBuffer.fromUint8List(bytes);
          final ui.Codec codec = await ui.instantiateImageCodecWithSize(
            buffer,
            getTargetSize: (int w, int h) {
              width = w;
              height = h;
              if (w > intakeMaximumSide ||
                  h > intakeMaximumSide ||
                  w * h > intakeMaximumPixels) {
                excessiveResolution = true;
                throw const FormatException(
                  'Image exceeds local decode limits',
                );
              }
              final double scale = w > h ? 256 / w : 256 / h;
              return ui.TargetImageSize(
                width: scale < 1 ? (w * scale).round().clamp(1, 256) : w,
                height: scale < 1 ? (h * scale).round().clamp(1, 256) : h,
              );
            },
          );
          try {
            final ui.FrameInfo frame = await codec.getNextFrame();
            try {
              final ByteData? pixels = await frame.image.toByteData(
                format: ui.ImageByteFormat.rawRgba,
              );
              if (pixels != null) {
                quality = CaptureQuality.measure(
                  pixels.buffer.asUint8List(),
                  frame.image.width,
                  frame.image.height,
                );
              }
            } finally {
              frame.image.dispose();
            }
          } finally {
            codec.dispose();
          }
        } catch (_) {
          /* An unsupported decoder or unavailable measurement is not a quality pass. */
        }
        if (excessiveResolution) {
          _skip(
            key: 'resolution:$digest',
            name: file.name,
            why:
                'This image is over 40 megapixels or over 20,000 pixels on one '
                'side. Upload a smaller derivative.',
          );
          continue;
        }
        final ManifestEntry? old = _entries
            .where(
              (ManifestEntry e) =>
                  e.digest == digest && e.state != UploadState.skipped,
            )
            .firstOrNull;
        if (old != null &&
            (old.settled ||
                old.checking ||
                old.state == UploadState.uploading)) {
          _skip(
            key: 'selected:$digest:${_entries.length}',
            name: file.name,
            why: old.settled
                ? 'This photograph was already uploaded in this intake.'
                : 'This photograph is already in the upload queue.',
          );
          continue;
        }
        final IntakeFile input = IntakeFile(
          name: file.name,
          bytes: bytes,
          mimeType: mime,
          sha256: digest,
          method: camera ? 'camera' : 'files',
          // Reselecting a queued file retains its declaration, including a
          // batch created before an item request was interrupted. A restored
          // server handle is resumed, never recreated with this local value.
          // New selections use the visible declaration, sensitive by default.
          // Resumed server uploads retain their existing classification.
          sensitive: old?.file?.sensitive ?? _sensitive,
          width: width,
          height: height,
        );
        if (!mounted) return;
        setState(() {
          if (old != null) {
            old.file = input;
            old.quality = quality;
            if (old.state != UploadState.accepted) {
              old.state = UploadState.ready;
              old.reason = 'Ready to resume from the server offset.';
              old.why = null;
            }
          } else {
            _entries.add(
              ManifestEntry(
                digest: digest,
                name: file.name,
                file: input,
                quality: quality,
                state: UploadState.ready,
              ),
            );
          }
        });
        _session.changed();
      } catch (_) {
        _skip(
          key: 'read:${file.name}:${_entries.length}',
          name: file.name,
          why:
              'This file could not be read. Check file permission or choose the original again.',
        );
      }
    }
  }

  void _skip({required String key, required String name, required String why}) {
    if (!mounted) return;
    setState(() {
      _entries.add(ManifestEntry.skipped(digest: key, name: name, why: why));
    });
    _session.changed();
  }

  void _remove(ManifestEntry entry) {
    _session.remove(entry);
  }

  // ------------------------------------------------------------ server work

  Future<void> _preflight(ManifestEntry entry) async {
    final IntakeFile? file = entry.file;
    if (file == null) return;
    setState(() {
      entry.checking = true;
      entry.preflightError = null;
    });
    try {
      final Json result = await widget.repository.preflight(widget.scope, file);
      if (mounted && identical(entry.file, file)) {
        setState(() => entry.preflight = result);
      }
    } catch (e) {
      if (mounted) {
        setState(
          () => entry.preflightError = e is ApiFailure
              ? e.message
              : 'The server check did not run. Retry, or have your '
                    'collection access confirmed.',
        );
      }
    } finally {
      if (mounted) setState(() => entry.checking = false);
    }
  }

  Future<void> _send() => _session.start();

  // ---------------------------------------------------------------- drawing

  int get _pendingCount =>
      _entries.where((ManifestEntry e) => e.sendable).length;

  /// The one message slot on this screen.
  ///
  /// A band rather than a card: it reports a condition of the device or the
  /// last attempt, which is operational rather than evidentiary, and it names
  /// what to do next in the same sentence (02 section 4.9).
  Widget _errorBand(BuildContext context) => UiBanner(
    message: _error!,
    tone: UiBannerTone.blocked,
    dismissLabel: dismissMessageLabel,
    onDismiss: () => setState(() => _error = null),
  );

  Widget _batchHeader(BuildContext context) => Row(
    children: <Widget>[
      Expanded(
        child: Semantics(
          header: true,
          child: Text(
            intakeTitle,
            style: context.ui.type.headline.copyWith(
              color: context.ui.color.ink,
            ),
          ),
        ),
      ),
      SizedBox(width: context.ui.space.s2),
      UiIconButton(
        key: const ValueKey<String>('intake-import-from-link'),
        icon: UiIcons.sourceImport,
        semanticsLabel: 'Import from link',
        tooltip: 'Import from link',
        variant: UiIconButtonVariant.secondary,
        onPressed: _openLinkImport,
      ),
    ],
  );

  Widget _sensitivityControl(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    mainAxisSize: MainAxisSize.min,
    children: <Widget>[
      UiCheckbox(
        key: const ValueKey<String>('intake-sensitivity'),
        label: 'Sensitive photographs',
        semanticsLabel:
            'Mark new photographs as sensitive. Applies to new files; existing uploads keep their classification.',
        value: _sensitive,
        onChanged: (bool value) => setState(() => _sensitive = value),
      ),
      Text(
        'For new files',
        style: context.ui.type.bodySmall.copyWith(
          color: context.ui.color.inkSecondary,
        ),
      ),
    ],
  );

  Widget _captureCard(
    BuildContext context, {
    required double minDropHeight,
  }) => IntakeCaptureCard(
    web: _isWeb,
    onChooseFiles: _choosing ? null : _chooseFiles,
    onTakePhotograph: _choosing ? null : _takePhotograph,
    // The page owns the only drop target, including the manifest and gutters.
    onDropFiles: null,
    cameraAvailable: _cameraAvailable,
    onBrowseSources: null,
    minDropHeight: _isWeb ? minDropHeight : 0,
    dragActive: _pageDragging,
  );

  /// True while the frame's action bar is the one drawing the upload action.
  ///
  /// A batch that is in flight keeps it there even as the rows settle and the
  /// pending count falls to zero: a control that moved back into the page
  /// half way through its own upload is the interface moving under the
  /// reviewer.
  bool get _uploadCarriedByFrame =>
      _slots != null && (_pendingCount > 0 || _busy);

  /// The one control that releases a batch.
  UiButton _uploadButton() => UiButton(
    key: const ValueKey<String>('intake-upload'),
    // The label is the present participle while a batch is in flight and the
    // control is disabled, which is what 02 section 4.3 asks for. The measured
    // progress is on the manifest, where the denominator is.
    label: intakeUploadLabel(uploading: _busy, pending: _pendingCount),
    leading: UiIcons.cloudUpload,
    onPressed: _busy || _pendingCount == 0 ? null : _send,
  );

  /// Puts the upload action in the frame's action bar (13 section 3.3).
  ///
  /// Only while there is a batch to send, and only while this screen is the
  /// route on top. A bar that says "Upload 0 photographs" and cannot be
  /// pressed is a pinned region with nothing to decide, and 13 section 2.3
  /// spends pinned height on nothing at its peril: a phone at 200 percent
  /// text pins 70 dp of top bar, 52 of band and 64 of navigation, which
  /// leaves 50 of the 236 the budget allows and an action bar is 80. The
  /// sources list and one source are routes under this one, so this screen
  /// stays mounted beneath them; without the [current] test its upload bar
  /// would follow the reviewer into a screen that has its own decision.
  ///
  /// Published only when what it says changes, so the frame is told about its
  /// own action bar once per change rather than once per frame.
  void _publishUpload({required bool current}) {
    final UiScaffoldSlots? slots = _slots;
    if (slots == null) return;
    final ({bool busy, int pending, bool current}) state = (
      busy: _busy,
      pending: _pendingCount,
      current: current,
    );
    if (state == _publishedUpload) return;
    _publishedUpload = state;
    slots.setActionBar(
      // The decision bar of 13 section 3.3, carrying the one decision this
      // screen has. It used to be a `UiButtonRow`, because a bar carrying
      // only a primary had no last resort and "Upload 0 photographs" with its
      // glyph overflowed a phone by five pixels at 200 percent text; the bar
      // measures its primary with its glyph now and lets it ellipsise at the
      // last resort the way a bar carrying two does (polish 3), so the frame
      // holds the same pattern at the same height on every screen that
      // decides.
      current && _uploadCarriedByFrame
          ? UiDecisionBar(primary: _uploadButton())
          : null,
      owner: this,
    );
  }

  /// Hosts without the application frame keep the upload action in-page.
  /// Production routes publish the same action through [_publishUpload].
  Widget? _inlineUpload() =>
      _slots == null && (_pendingCount > 0 || _busy) ? _uploadButton() : null;

  Widget _manifest(
    BuildContext context, {
    EdgeInsetsGeometry? padding,
    bool scrollable = true,
  }) => IntakeManifest(
    entries: _entries,
    busy: _busy,
    stopping: _busy && _stopRequested,
    onStop: _session.stop,
    onRemove: _remove,
    onServerCheck: _preflight,
    onRetry: (ManifestEntry entry) => unawaited(_session.start(only: entry)),
    padding: padding,
    scrollable: scrollable,
  );

  /// The one message slot, revealed above the sections.
  Widget _errorSlot(BuildContext context) {
    final UiThemeData ui = context.ui;
    // Height and opacity, no shake and no colour pulse: the control below
    // is already the retry (motion catalog, row 69).
    return MotionReveal(
      visible: _error != null,
      child: _error == null
          ? const SizedBox(width: double.infinity)
          : Padding(
              padding: EdgeInsetsDirectional.only(bottom: ui.space.s4),
              child: _errorBand(context),
            ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final UiThemeData ui = context.ui;
    // `ModalRoute.of` depends on the scope that carries `isCurrent`, so this
    // screen is rebuilt when a route is pushed over it or popped back off.
    _publishUpload(
      current:
          (ModalRoute.of(context)?.isCurrent ?? true) &&
          (WorkspaceBranchScope.maybeOf(context)?.active ?? true),
    );
    final Widget page = ColoredBox(
      color: ui.color.paper,
      child: LayoutBuilder(
        builder: (BuildContext context, BoxConstraints constraints) {
          final layout = UiLayoutMetrics.fromConstraints(
            constraints,
            textScaler: MediaQuery.textScalerOf(context),
          );
          final double textScale =
              MediaQuery.textScalerOf(context).scale(16) / 16;
          // Reserve scaled room for the title and classification control so
          // both remain visible before scrolling when the window permits it.
          final double dropHeight = constraints.hasBoundedHeight
              ? (constraints.maxHeight -
                        layout.gutter * 2 -
                        ui.space.s16 * (2 + textScale) -
                        (_cameraAvailable ? ui.space.s16 * 2 : 0))
                    .clamp(240.0, double.infinity)
              : 360;
          // One scroll keeps capture, classification and file errors reachable
          // at enlarged text sizes and short viewport heights.
          return CustomScrollView(
            slivers: [
              SliverPadding(
                padding: EdgeInsetsDirectional.all(layout.gutter),
                sliver: SliverToBoxAdapter(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      _errorSlot(context),
                      _batchHeader(context),
                      SizedBox(height: layout.gap),
                      _captureCard(context, minDropHeight: dropHeight),
                      SizedBox(height: layout.gap),
                      _sensitivityControl(context),
                      if (_entries.isNotEmpty) ...[
                        SizedBox(height: layout.sectionGap),
                        Align(
                          alignment: AlignmentDirectional.topStart,
                          child: ConstrainedBox(
                            constraints: BoxConstraints(
                              maxWidth: layout.readableMax,
                            ),
                            child: _manifest(
                              context,
                              padding: EdgeInsets.zero,
                              scrollable: false,
                            ),
                          ),
                        ),
                      ],
                      if (_inlineUpload() case final Widget upload) ...[
                        SizedBox(height: layout.gap),
                        Align(
                          alignment: AlignmentDirectional.centerStart,
                          child: upload,
                        ),
                      ],
                    ],
                  ),
                ),
              ),
              SliverToBoxAdapter(
                child: SizedBox(
                  height: layout.gap + UiScaffold.of(context).bottomInset,
                ),
              ),
            ],
          );
        },
      ),
    );
    if (!_isWeb) return page;
    return DropTarget(
      key: const ValueKey<String>('intake-page-drop-target'),
      onDragEntered: (_) => setState(() => _pageDragging = true),
      onDragExited: (_) => setState(() => _pageDragging = false),
      onDragDone: (DropDoneDetails details) {
        setState(() => _pageDragging = false);
        unawaited(
          _dropFiles(
            details.files.whereType<DropItemFile>().cast<XFile>().toList(),
          ),
        );
      },
      child: page,
    );
  }
}
