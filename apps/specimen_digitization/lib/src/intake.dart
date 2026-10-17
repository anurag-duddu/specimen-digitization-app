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
import 'package:flutter/semantics.dart';
import 'package:flutter/widgets.dart';
import 'package:image_picker/image_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:specimen_ui/specimen_ui.dart';

import 'app/shell.dart';
import 'capture/capture_camera.dart';
import 'capture/capture_screen.dart';
import 'capture_quality.dart';
import 'intake_image_dimensions.dart';
import 'models.dart';
import 'screens/intake/capture_card.dart';
import 'screens/intake/manifest_entry.dart';
import 'screens/intake/manifest_panel.dart';
import 'screens/intake/intake_status.dart';
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

bool _exceedsLocalResolutionLimit(int width, int height) =>
    width > intakeMaximumSide ||
    height > intakeMaximumSide ||
    width * height > intakeMaximumPixels;

/// The way from intake to the photographs a collection already holds.
///
/// Verb first, three words, inside the 24 character button budget.
const String intakeBrowseSourcesLabel = 'Add from storage';

/// What the message band's dismiss control is called.
const String dismissMessageLabel = 'Dismiss this message';

const String _unreadablePhotoMessage =
    'Could not read this photo. Choose it again.';

class IntakeScreen extends StatefulWidget {
  const IntakeScreen({
    super.key,
    required this.repository,
    required this.scope,
    required this.userId,
    required this.onComplete,
    this.onBrowseSources,
    this.pickImages,
    this.pickFiles,
    this.recoverCamera,
    this.openCapture,
    this.cameraFactory,
    this.webOverride,
    this.onViewSpecimens,
    this.restoreAccess,
    this.accessVerified = false,
  });
  final SpecimenRepository repository;
  final CollectionScope scope;
  final String userId;
  final VoidCallback onComplete;
  final VoidCallback? onViewSpecimens;

  /// Rechecks authorization for this same user and collection.
  final Future<bool> Function()? restoreAccess;
  final bool accessVerified;

  /// Opens the registered sources for this collection.
  ///
  /// Null where this build has none, which hides the control rather than
  /// offering one that cannot answer (blueprint 3).
  final VoidCallback? onBrowseSources;

  /// Test seam for both sources. When set, it replaces the file picker and
  /// the camera entirely.
  final Future<List<XFile>> Function(bool camera)? pickImages;

  /// File-only picker seam, including the camera's Choose files fallback.
  final Future<List<XFile>> Function()? pickFiles;

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
  late final VoidCallback _transferRefresh;
  List<ManifestEntry> get _entries => _session.entries;

  /// The frame's slots, so the upload action goes where 13 section 3.3 puts a
  /// screen's decision.
  UiScaffoldSlots? _slots;

  /// What the published action bar last said, so the frame is told once per
  /// change rather than once per frame.
  ({bool busy, int pending, bool current, bool signInRequired})?
  _publishedUpload;

  bool get _busy => _session.busy;
  bool _sensitive = false;
  bool get _stopRequested => _session.stopping;
  bool _choosing = false;
  bool _pageDragging = false;
  bool _autoIngest = false;
  bool _autoIngestLoaded = false;
  bool _transferRefreshScheduled = false;
  String? _error;
  Future<void> _cameraAdmissions = Future<void>.value();
  XFile? _lastCameraFile;
  ManifestEntry? _lastCameraEntry;

  /// The session's [IntakeTransferSession.movedToQueue] already spoken for,
  /// so a photo that moves to the main Queue is announced once, and a route
  /// that attaches later never repeats an earlier move.
  int _announcedMoves = 0;

  /// Moves not yet spoken. A count, not a sentence: two moves before one
  /// frame are one announcement of two photos, never the last one alone.
  int _pendingMoves = 0;

  /// True while the main Queue's last photo collapses out of the manifest.
  /// The Photos section stays mounted until that exit finishes, so the row
  /// leaves the way every other row does instead of vanishing.
  bool _holdPhotos = false;

  /// Wraps the Photos section, so focus inside it is noticed when the last
  /// row leaves and the section goes with it.
  final FocusNode _photosFocus = FocusNode(
    debugLabel: 'Intake photos',
    skipTraversal: true,
    canRequestFocus: false,
  );

  /// The screen heading, where focus lands if the section it was in leaves.
  final FocusNode _headingFocus = FocusNode(
    debugLabel: 'Intake heading',
    skipTraversal: true,
  );

  String get _captureOwner => '${widget.userId}:${widget.scope.key}';
  static const String _captureKey = 'pending-camera-owner-v1';
  static const String _captureSensitiveKey = '$_captureKey:sensitive';
  String get _autoIngestKey =>
      'camera-auto-ingest-v1:${widget.userId}:${widget.scope.key}';

  /// Camera availability is discovered by the camera itself. This keeps the
  /// same real-time path available to browser and desktop webcams without
  /// assuming that every device actually has one.
  bool get _isWeb => widget.webOverride ?? kIsWeb;

  bool get _nativeCameraAvailable =>
      !kIsWeb &&
      !_isWeb &&
      (defaultTargetPlatform == TargetPlatform.android ||
          defaultTargetPlatform == TargetPlatform.iOS);

  bool get _cameraAvailable => true;

  @override
  void initState() {
    super.initState();
    _transferRefresh = _scheduleTransferRefresh;
    _session = intakeTransferSession(
      widget.repository,
      widget.scope,
      widget.userId,
    );
    _session.addListener(_sessionChanged);
    _announcedMoves = _session.movedToQueue;
    // Preserve the existing Intake completion contract. The main Queue still
    // decides what it can display, while Intake independently tracks the
    // photograph until processing hands it over.
    _session.attachComplete(_transferRefresh);
    _session.attachHandoff(_transferRefresh);
    unawaited(_loadAutoIngest());
    _recoverCamera();
    _resumeVerifiedSession();
  }

  void _resumeVerifiedSession() {
    final session = _session;
    if (!widget.accessVerified || !session.signInRequired) return;
    scheduleMicrotask(() {
      if (mounted && identical(session, _session) && widget.accessVerified) {
        unawaited(session.resumeAfterSignIn());
      }
    });
  }

  Future<void> _restoreAccess() async {
    final session = _session;
    if (await widget.restoreAccess?.call() == true &&
        mounted &&
        identical(session, _session)) {
      await session.resumeAfterSignIn();
    }
  }

  /// Upload acceptance and the later main-Queue handoff both refresh the
  /// workspace. Coalescing one event-loop turn prevents an immediate handoff
  /// from issuing the same refresh twice, including after route reattachment.
  void _scheduleTransferRefresh() {
    if (_transferRefreshScheduled) return;
    _transferRefreshScheduled = true;
    scheduleMicrotask(() {
      _transferRefreshScheduled = false;
      if (mounted) widget.onComplete();
    });
  }

  void _sessionChanged() {
    if (!mounted) return;
    if (_lastCameraEntry != null &&
        (!_entries.contains(_lastCameraEntry) ||
            _lastCameraEntry!.state != UploadState.ready)) {
      _lastCameraFile = null;
      _lastCameraEntry = null;
    }
    final int moved = _session.movedToQueue - _announcedMoves;
    if (moved > 0) {
      _announcedMoves = _session.movedToQueue;
      _announceMoved(moved);
      if (_entries.isEmpty &&
          !(context.ui.motion.reduced ||
              MediaQuery.disableAnimationsOf(context))) {
        _holdPhotos = true;
      }
    }
    if (_entries.isEmpty &&
        _session.departureCount == 0 &&
        _photosFocus.hasFocus) {
      // The Photos section is about to close, now or after a last row's
      // exit. Wherever focus is inside it (a row, Stop, the summary), it
      // goes to the screen heading rather than to nowhere or to whatever
      // focus history picks (06 section 3). This is the only handover for
      // an emptied list: the manifest leaves it to this screen
      // ([IntakeManifest.hostHandlesEmptyFocus]). Checked before the rebuild
      // that removes the focused control, so focus is still inside.
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _headingFocus.requestFocus();
      });
    }
    setState(() => _error ??= _session.restoreError);
  }

  /// Speaks the move once, after the frame that removes the rows, politely.
  /// Coalesced, so several rows leaving together are one sentence.
  void _announceMoved(int count) {
    final bool scheduled = _pendingMoves > 0;
    _pendingMoves += count;
    if (scheduled) return;
    WidgetsBinding.instance
      ..addPostFrameCallback((_) {
        final int pending = _pendingMoves;
        _pendingMoves = 0;
        if (pending == 0 || !mounted) return;
        if (!MediaQuery.supportsAnnounceOf(context)) return;
        unawaited(
          SemanticsService.sendAnnouncement(
            View.of(context),
            movedToQueueLine(pending),
            Directionality.of(context),
          ),
        );
      })
      ..ensureVisualUpdate();
  }

  /// The manifest has finished collapsing its leaving rows.
  void _exitsSettled() {
    if (!mounted || !_holdPhotos) return;
    setState(() => _holdPhotos = false);
  }

  @override
  void didUpdateWidget(covariant IntakeScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!identical(oldWidget.repository, widget.repository) ||
        oldWidget.scope.key != widget.scope.key ||
        oldWidget.userId != widget.userId) {
      _session.detachComplete(_transferRefresh);
      _session.detachHandoff(_transferRefresh);
      _session.removeListener(_sessionChanged);
      _session = intakeTransferSession(
        widget.repository,
        widget.scope,
        widget.userId,
      );
      _session.addListener(_sessionChanged);
      _announcedMoves = _session.movedToQueue;
      _pendingMoves = 0;
      _holdPhotos = false;
      _session.attachComplete(_transferRefresh);
      _session.attachHandoff(_transferRefresh);
      _sensitive = false;
      _autoIngest = false;
      _autoIngestLoaded = false;
      _error = null;
      unawaited(_loadAutoIngest());
    }
    if (!oldWidget.accessVerified && widget.accessVerified) {
      _resumeVerifiedSession();
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _slots = UiScaffoldSlots.of(context);
  }

  @override
  void dispose() {
    _session.detachComplete(_transferRefresh);
    _session.detachHandoff(_transferRefresh);
    _session.removeListener(_sessionChanged);
    _slots?.release(this);
    _photosFocus.dispose();
    _headingFocus.dispose();
    super.dispose();
  }

  // ------------------------------------------------------------------ input

  Future<void> _chooseFiles() => _collect(camera: false, load: _pickFiles);

  Future<List<XFile>> _pickFiles() async => widget.pickFiles != null
      ? await widget.pickFiles!()
      : widget.pickImages != null
      ? await widget.pickImages!(false)
      : await openFiles(
          acceptedTypeGroups: <XTypeGroup>[
            const XTypeGroup(
              label: 'Photos',
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
        );

  Future<void> _takePhotograph() => _collect(camera: true, load: _capture);

  Future<void> _loadAutoIngest() async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    final bool value = prefs.getBool(_autoIngestKey) ?? false;
    if (!mounted) return;
    setState(() {
      _autoIngest = value;
      _autoIngestLoaded = true;
    });
  }

  Future<void> _setAutoIngest(bool value) async {
    setState(() {
      _autoIngest = value;
      _autoIngestLoaded = true;
    });
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    await prefs.setBool(_autoIngestKey, value);
  }

  /// Follow the camera's offered fallback: permission/no-camera failures
  /// choose existing photos; a native controller failure may use the OS camera.
  Future<List<XFile>> _capture() async {
    final session = _session;
    final sensitive = _sensitive;
    if (widget.pickImages != null) return widget.pickImages!(true);
    if (_cameraAvailable) {
      final CaptureResult result = await _openCapture();
      if (!result.needsFallback) {
        return result.streamed ? <XFile>[] : result.files;
      }
      if (!mounted || !identical(session, _session)) return <XFile>[];
      Future<List<XFile>> chooseExistingPhotos() async {
        final files = await _pickFiles();
        if (!mounted || !identical(session, _session)) return <XFile>[];
        await _acceptFiles(files, camera: false, sensitive: sensitive);
        return <XFile>[];
      }

      // Browsers and desktops have no separate operating-system camera.
      if (!_nativeCameraAvailable) return chooseExistingPhotos();
      // Permission and no-camera fallbacks explicitly offer Choose files.
      if (result.unavailable != CaptureUnavailable.failed) {
        return chooseExistingPhotos();
      }
    }
    return _devicePicker();
  }

  Future<CaptureResult> _openCapture() async {
    if (widget.openCapture != null) return widget.openCapture!(context);
    // Intake lives inside a stateful shell navigator. The camera must cover
    // that shell as well as the branch page; otherwise the collection header
    // and bottom navigation squeeze a phone-landscape viewfinder until its
    // shutter and Done controls are off-screen.
    final CaptureResult? result =
        await Navigator.of(context, rootNavigator: true).push(
          CaptureScreen.route(
            widget.cameraFactory ?? _platformCamera,
            onCaptured: _acceptCameraPhoto,
            canRemovePhoto: _canRemoveCameraPhoto,
            removePhoto: _removeCameraPhoto,
            initialSensitive: _sensitive,
            autoIngest: _autoIngest,
            onAutoIngestChanged: (bool value) =>
                unawaited(_setAutoIngest(value)),
            activity: _session,
            activitySnapshot: _captureActivity,
            deviceFallbackAvailable: _nativeCameraAvailable,
          ),
        );
    _lastCameraFile = null;
    _lastCameraEntry = null;
    return result ?? const CaptureResult();
  }

  void _acceptCameraPhoto(CapturedPhoto photo) {
    // Admission and upload run under the intake route while the viewfinder
    // stays on top. Each accepted photograph can start before Done is tapped.
    final session = _session;
    _lastCameraFile = null;
    _lastCameraEntry = null;
    _cameraAdmissions = _cameraAdmissions.then((_) async {
      if (!mounted || !identical(session, _session)) return;
      ManifestEntry? admittedEntry;
      final admitted = await _acceptFiles(
        <XFile>[photo.file],
        camera: true,
        sensitive: photo.sensitive,
        onAdmitted: (entry) => admittedEntry = entry,
      );
      // In Review mode the camera's explicit Send authorizes this admission.
      if (admitted > 0 && mounted && identical(session, _session)) {
        _lastCameraFile = photo.file;
        _lastCameraEntry = admittedEntry;
        session.changed();
        unawaited(session.start());
      }
    });
  }

  bool _canRemoveCameraPhoto(XFile file) {
    final entry = _lastCameraEntry;
    return mounted &&
        identical(file, _lastCameraFile) &&
        entry != null &&
        _entries.contains(entry) &&
        entry.state == UploadState.ready &&
        !entry.checking &&
        entry.session == null;
  }

  bool _removeCameraPhoto(XFile file) {
    if (!_canRemoveCameraPhoto(file)) return false;
    final entry = _lastCameraEntry!;
    _lastCameraFile = null;
    _lastCameraEntry = null;
    _session.remove(entry);
    return true;
  }

  /// The `image_picker` path. Its recovery marker preserves ownership and
  /// the pending photo's declaration, not a preference for the next session.
  Future<List<XFile>> _devicePicker() async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    await prefs.setString(_captureKey, _captureOwner);
    await prefs.setBool(_captureSensitiveKey, _sensitive);
    try {
      final XFile? image = await ImagePicker().pickImage(
        source: ImageSource.camera,
        requestFullMetadata: false,
      );
      return image == null ? <XFile>[] : <XFile>[image];
    } finally {
      if (prefs.getString(_captureKey) == _captureOwner) {
        await prefs.remove(_captureKey);
        await prefs.remove(_captureSensitiveKey);
      }
    }
  }

  Future<void> _collect({
    required bool camera,
    required Future<List<XFile>> Function() load,
  }) async {
    final session = _session;
    final sensitive = _sensitive;
    setState(() {
      _choosing = true;
      _error = null;
    });
    try {
      final files = await load();
      if (!mounted || !identical(session, _session)) return;
      final int admitted = await _acceptFiles(
        files,
        camera: camera,
        sensitive: sensitive,
      );
      // The in-app camera streams only photographs the operator explicitly
      // sent. A platform picker cannot host that review UI, so manual mode
      // leaves its photograph ready in the Intake queue for the page action.
      // An empty return (including streamed captures) or a local refusal is
      // not an instruction to restart photographs already waiting in Intake.
      if (camera &&
          _autoIngest &&
          admitted > 0 &&
          identical(session, _session)) {
        unawaited(session.start());
      }
    } catch (_) {
      if (mounted) {
        setState(() => _error = 'Picker did not open. Try Choose files.');
      }
    } finally {
      if (mounted) setState(() => _choosing = false);
    }
  }

  /// Routes browser drops through the same byte, type, size and checksum
  /// admission path as the system picker.
  Future<void> _dropFiles(List<XFile> files) {
    if (files.isEmpty) {
      setState(() => _error = 'No photos added. Drop photos here.');
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
      final Object? declaration = prefs.get(_captureSensitiveKey);
      // Older markers used the previous Sensitive default. Missing or
      // malformed declarations must never downgrade a recovered photo.
      final bool sensitive = declaration is bool ? declaration : true;
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
        await _acceptFiles(files, camera: true, sensitive: sensitive);
        if (mounted && files.isNotEmpty) {
          setState(() => _error = 'Recovered a photo. Check it, then send.');
        }
      } catch (_) {
        if (mounted) {
          setState(() => _error = _unreadablePhotoMessage);
        }
      } finally {
        if (prefs.getString(_captureKey) == _captureOwner) {
          await prefs.remove(_captureKey);
          await prefs.remove(_captureSensitiveKey);
        }
        if (mounted) setState(() => _choosing = false);
      }
    }
  }

  // ------------------------------------------------------------ examination

  /// Reads every chosen file, measures what this device can measure, and adds
  /// a row for each. A file this client refuses gets a Skipped row carrying
  /// its own reason rather than a banner the next rejection overwrites.
  Future<int> _acceptFiles(
    List<XFile> files, {
    required bool camera,
    bool? sensitive,
    ValueChanged<ManifestEntry>? onAdmitted,
  }) async {
    final session = _session;
    final declaration = sensitive ?? _sensitive;
    bool owns() => mounted && identical(session, _session);
    int admitted = 0;
    for (final XFile file in files) {
      if (!owns()) return admitted;
      try {
        final int size = await file.length();
        if (!owns()) return admitted;
        if (size == 0 || size > intakeMaximumBytes) {
          _skip(
            key: 'size:${file.name}:$size',
            name: file.name,
            why: size == 0
                ? 'Empty file. Choose another.'
                : 'Over 25 MB. Choose a smaller photo.',
          );
          continue;
        }
        final Uint8List bytes = await file.readAsBytes();
        if (!owns()) return admitted;
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
            why: 'Use JPEG, PNG, HEIC, TIFF or DNG.',
          );
          continue;
        }
        final EncodedImageDimensions? encodedDimensions =
            readEncodedImageDimensions(bytes, mimeType: mime);
        CaptureQuality? quality;
        bool excessiveResolution =
            encodedDimensions != null &&
            _exceedsLocalResolutionLimit(
              encodedDimensions.width,
              encodedDimensions.height,
            );
        if (!excessiveResolution) {
          try {
            final ui.ImmutableBuffer buffer =
                await ui.ImmutableBuffer.fromUint8List(bytes);
            final ui.Codec codec = await ui.instantiateImageCodecWithSize(
              buffer,
              getTargetSize: (int w, int h) {
                if (_exceedsLocalResolutionLimit(w, h)) {
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
        }
        if (!owns()) return admitted;
        if (excessiveResolution) {
          _skip(
            key: 'resolution:$digest',
            name: file.name,
            why: 'Over 40 megapixels. Choose a smaller photo.',
          );
          continue;
        }
        final ManifestEntry? old = _entries
            .where(
              (ManifestEntry e) =>
                  e.digest == digest && e.state != UploadState.skipped,
            )
            .firstOrNull;
        if (!mounted || !identical(session, _session)) return admitted;
        if (old != null &&
            (old.settled ||
                old.checking ||
                old.state == UploadState.uploading ||
                (old.state == UploadState.ready && old.file != null))) {
          if (UiToastHost.maybeOf(context) != null) {
            UiToasts.show(
              context,
              message: 'Already in the list',
              icon: UiIcons.copy,
            );
          } else {
            setState(() => _error = 'Already in the list');
          }
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
          // Recovery supplies the pending photo's declaration. Other new
          // selections use the visible declaration, off by default.
          // Resumed server uploads retain their existing classification.
          sensitive: old?.file?.sensitive ?? declaration,
          width: encodedDimensions?.width,
          height: encodedDimensions?.height,
        );
        if (!mounted) return admitted;
        setState(() {
          if (old != null) {
            old.file = input;
            old.quality = quality;
            if (old.state != UploadState.accepted) {
              old.state = UploadState.ready;
              old.reason = 'Ready to send.';
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
        onAdmitted?.call(old ?? _entries.last);
        _session.changed();
        admitted++;
      } catch (_) {
        if (!owns()) return admitted;
        _skip(
          key: 'read:${file.name}:${_entries.length}',
          name: file.name,
          why: _unreadablePhotoMessage,
        );
      }
    }
    return admitted;
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

  void _setPhotoSensitivity(ManifestEntry entry, bool sensitive) {
    final file = entry.file;
    if (file == null ||
        entry.state != UploadState.ready ||
        entry.checking ||
        entry.session != null ||
        !_entries.contains(entry)) {
      return;
    }
    entry.file = IntakeFile(
      name: file.name,
      bytes: file.bytes,
      mimeType: file.mimeType,
      sha256: file.sha256,
      method: file.method,
      sensitive: sensitive,
      width: file.width,
      height: file.height,
    );
    _session.changed();
  }

  // ------------------------------------------------------------ server work

  Future<void> _preflight(ManifestEntry entry) async {
    final session = _session;
    final IntakeFile? file = entry.file;
    if (file == null ||
        session.busy ||
        entry.checking ||
        !session.entries.contains(entry)) {
      return;
    }
    bool owns() =>
        mounted &&
        identical(session, _session) &&
        session.entries.contains(entry) &&
        identical(entry.file, file);
    entry.checking = true;
    entry.preflightError = null;
    session.changed();
    try {
      final Json result = await widget.repository.preflight(widget.scope, file);
      if (owns()) entry.preflight = result;
    } catch (e) {
      if (owns()) {
        entry.preflightError = e is ApiFailure
            ? e.message
            : 'Photo not checked. Try again.';
      }
    } finally {
      entry.checking = false;
      if (owns()) session.changed();
    }
  }

  Future<void> _send() => _session.start();

  CaptureActivity _captureActivity() {
    final ManifestEntry? active = _entries
        .where((ManifestEntry entry) => entry.state == UploadState.uploading)
        .firstOrNull;
    return CaptureActivity(
      label: _session.summary,
      progress: active?.progress,
      problem: _entries.any(
        (entry) => intakeStatus(entry).tone == IntakeTone.error,
      ),
    );
  }

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

  Widget _batchHeader(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: <Widget>[
      Focus(
        focusNode: _headingFocus,
        includeSemantics: false,
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
      if (_entries.isEmpty) ...[
        SizedBox(height: context.ui.space.s2),
        Text(
          intakePurpose,
          style: context.ui.type.body.copyWith(
            color: context.ui.color.inkSecondary,
          ),
        ),
      ],
    ],
  );

  Widget _sensitivityControl(BuildContext context) => Align(
    alignment: AlignmentDirectional.centerStart,
    child: UiSwitch(
      key: const ValueKey<String>('intake-sensitivity'),
      label: 'Mark sensitive',
      semanticsLabel: 'Mark sensitive for new photos',
      value: _sensitive,
      onChanged: (bool value) => setState(() => _sensitive = value),
    ),
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
    autoIngest: _autoIngest,
    onAutoIngestChanged: !_autoIngestLoaded || _choosing
        ? null
        : (bool value) => unawaited(_setAutoIngest(value)),
    onBrowseSources: null,
    onImportFromLink: _openLinkImport,
    minDropHeight: _isWeb ? minDropHeight : 0,
    dragActive: _pageDragging,
    hasPhotos: _entries.isNotEmpty,
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
    onPressed: _busy || _pendingCount == 0 || _session.signInRequired
        ? null
        : _send,
    disabledReason: _session.signInRequired ? intakeSignedOutReason : null,
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
    final ({bool busy, int pending, bool current, bool signInRequired}) state =
        (
          busy: _busy,
          pending: _pendingCount,
          current: current,
          signInRequired: _session.signInRequired,
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
    activity: _session,
    busy: _busy,
    stopping: _busy && _stopRequested,
    onStop: _session.stop,
    onRemove: _remove,
    onServerCheck: _preflight,
    onRetry: (ManifestEntry entry) => unawaited(_session.start(only: entry)),
    onChooseFile: _chooseFiles,
    onSensitivityChanged: _setPhotoSensitivity,
    onViewSpecimens: widget.onViewSpecimens,
    sent: _session.sentCount,
    duplicates: _session.duplicateCount,
    padding: padding,
    scrollable: scrollable,
    onExitsSettled: _exitsSettled,
    hostHandlesEmptyFocus: _session.departureCount == 0,
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
          final topInset =
              AppSidebarScope.maybeOf(context)?.mobileNavigation == true
              ? ui.space.s2
              : layout.gutter;
          // One scroll keeps capture, classification and file errors reachable
          // at enlarged text sizes and short viewport heights.
          return CustomScrollView(
            slivers: [
              SliverPadding(
                padding: EdgeInsetsDirectional.fromSTEB(
                  layout.gutter,
                  topInset,
                  layout.gutter,
                  layout.gutter,
                ),
                sliver: SliverToBoxAdapter(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      _errorSlot(context),
                      if (_session.signInRequired)
                        UiBanner(
                          message: intakeSignedOutReason,
                          tone: UiBannerTone.blocked,
                          actionLabel: widget.restoreAccess == null
                              ? null
                              : 'Check access',
                          onAction: widget.restoreAccess == null
                              ? null
                              : _restoreAccess,
                        ),
                      _batchHeader(context),
                      SizedBox(height: layout.gap),
                      _captureCard(context, minDropHeight: 0),
                      SizedBox(height: layout.gap),
                      _sensitivityControl(context),
                      // The section closes the way a banner does when the
                      // main Queue takes its last photo (motion, row 10).
                      MotionReveal(
                        visible:
                            _entries.isNotEmpty ||
                            _holdPhotos ||
                            _session.departureCount > 0,
                        child: Focus(
                          focusNode: _photosFocus,
                          includeSemantics: false,
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              SizedBox(height: layout.sectionGap),
                              Semantics(
                                header: true,
                                child: Text('Photos', style: ui.type.title),
                              ),
                              SizedBox(height: ui.space.s2),
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
                          ),
                        ),
                      ),
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
