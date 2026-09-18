/// Intake and capture (screen blueprints, section 5).
///
/// Two cards. The capture card says how photographs arrive and carries the one
/// confirmation that releases a batch; the manifest is the complete account of
/// what happened to every file, including the ones this client refused. Below
/// 600dp they stack; at 600dp and above the capture card is fixed on the left
/// and the manifest scrolls beside it, so the button an operator presses
/// repeatedly never scrolls away from the list it fills
/// (responsive, section 3.4).
library;

import 'dart:convert';
import 'dart:ui' as ui;

import 'package:crypto/crypto.dart';
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
import 'theme/motion.dart';
import 'vocabulary.dart';
import 'widgets/motion_reveal.dart';
import 'widgets/upload_item.dart';

export 'screens/intake/manifest_entry.dart' show ManifestEntry;

/// Fixed width of the capture column at 600dp and above (blueprint 5).
const double intakeCaptureColumnWidth = 420;

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

  @override
  State<IntakeScreen> createState() => _IntakeScreenState();
}

class _IntakeScreenState extends State<IntakeScreen> {
  final List<ManifestEntry> _entries = <ManifestEntry>[];

  /// The frame's slots, so the upload action goes where 13 section 3.3 puts a
  /// screen's decision.
  UiScaffoldSlots? _slots;

  /// What the published action bar last said, so the frame is told once per
  /// change rather than once per frame.
  ({bool busy, bool confirmed, int pending, bool current})? _publishedUpload;

  bool _busy = false;
  bool _stopRequested = false;
  bool _qualityConfirmed = false;
  bool _newSensitive = true;
  String? _error;

  String get _storageKey =>
      'upload-handles-v1:${widget.userId}:${widget.scope.key}';
  String get _captureOwner => '${widget.userId}:${widget.scope.key}';
  static const String _captureKey = 'pending-camera-owner-v1';

  /// This client offers an in-app camera only where it has one.
  bool get _cameraAvailable =>
      !kIsWeb &&
      (defaultTargetPlatform == TargetPlatform.android ||
          defaultTargetPlatform == TargetPlatform.iOS);

  @override
  void initState() {
    super.initState();
    _restore().then((_) => _recoverCamera());
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _slots = UiScaffoldSlots.of(context);
  }

  @override
  void dispose() {
    _slots?.release(this);
    super.dispose();
  }

  // ---------------------------------------------------------------- storage

  Future<void> _restore() async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    final String? saved = prefs.getString(_storageKey);
    if (saved != null && mounted) {
      try {
        final Iterable<ManifestEntry> restored = objects(jsonDecode(saved)).map(
          (Json e) => ManifestEntry.restored(
            digest: e['digest'],
            handle: <String, dynamic>{'upload_id': e['upload_id']},
          ),
        );
        setState(() => _entries.addAll(restored));
      } catch (_) {
        setState(
          () => _error =
              'Saved uploads could not be read. Select your files again to '
              'match them with the server.',
        );
      }
    }
  }

  Future<void> _persist() async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    // Persist only opaque upload handles and checksums, never image bytes,
    // credentials or label content.
    await prefs.setString(
      _storageKey,
      jsonEncode(
        _entries
            .where(
              (ManifestEntry e) =>
                  e.session?['upload_id'] != null && !e.settled,
            )
            .map(
              (ManifestEntry e) => <String, dynamic>{
                'digest': e.digest,
                'upload_id': e.session!['upload_id'],
              },
            )
            .toList(),
      ),
    );
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
    if (_cameraAvailable) {
      final CaptureResult result = await _openCapture();
      if (!result.needsFallback) return result.files;
      if (mounted) {
        setState(() => _error = result.unavailable!.message);
      }
    }
    return _devicePicker();
  }

  Future<CaptureResult> _openCapture() async {
    if (widget.openCapture != null) return widget.openCapture!(context);
    final CaptureResult? result = await Navigator.of(
      context,
    ).push(CaptureScreen.route(widget.cameraFactory ?? _platformCamera));
    return result ?? const CaptureResult();
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
      _busy = true;
      _qualityConfirmed = false;
      _error = null;
    });
    try {
      await _acceptFiles(await load(), camera: camera);
    } catch (_) {
      if (mounted) {
        setState(
          () => _error =
              'The camera or file picker did not open. Check device '
              'permissions, then choose files.',
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _recoverCamera() async {
    if ((!kIsWeb && defaultTargetPlatform == TargetPlatform.android) ||
        widget.recoverCamera != null) {
      final SharedPreferences prefs = await SharedPreferences.getInstance();
      if (!mounted || prefs.getString(_captureKey) != _captureOwner) return;
      setState(() => _busy = true);
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
        if (mounted) setState(() => _busy = false);
      }
    }
  }

  // ------------------------------------------------------------ examination

  /// Reads every chosen file, measures what this device can measure, and adds
  /// a row for each. A file this client refuses gets a Skipped row carrying
  /// its own reason rather than a banner the next rejection overwrites.
  Future<void> _acceptFiles(List<XFile> files, {required bool camera}) async {
    for (final XFile file in files) {
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
              throw const FormatException('Image exceeds local decode limits');
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
      final IntakeFile input = IntakeFile(
        name: file.name,
        bytes: bytes,
        mimeType: mime,
        sha256: digest,
        method: camera ? 'camera' : 'files',
        // Reselecting a queued file retains its declaration, including a
        // batch created before an item request was interrupted. A restored
        // server handle is resumed, never recreated with this local value.
        sensitive: old?.file?.sensitive ?? _newSensitive,
        width: width,
        height: height,
      );
      if (!mounted) return;
      setState(() {
        // Adding a photograph clears the batch confirmation, so a tick can
        // never authorise a file the operator had not yet chosen (H5.3).
        _qualityConfirmed = false;
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
    }
  }

  void _skip({required String key, required String name, required String why}) {
    if (!mounted) return;
    setState(() {
      _qualityConfirmed = false;
      _entries.add(ManifestEntry.skipped(digest: key, name: name, why: why));
    });
  }

  void _remove(ManifestEntry entry) {
    setState(() => _entries.remove(entry));
    _persist();
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

  Future<void> _send() async {
    setState(() {
      _busy = true;
      _stopRequested = false;
      _error = null;
    });
    final List<ManifestEntry> batch = _entries
        .where((ManifestEntry e) => e.sendable)
        .toList(growable: false);
    int reached = 0;
    for (final ManifestEntry entry in batch) {
      if (!mounted) break;
      // Stop is checked between files only: a transfer already in flight
      // finishes rather than leaving a half-written upload behind (H3.7).
      if (_stopRequested) break;
      reached++;
      try {
        setState(() {
          entry.checking = true;
          entry.reason = null;
          entry.why = null;
        });
        entry.session = entry.session == null
            ? await widget.repository.createIntake(
                widget.scope,
                entry.file!,
                'intake-${entry.digest}',
              )
            : await widget.repository.resumeIntake(
                widget.scope,
                entry.session!['upload_id'],
              );
        if (mounted) setState(() => entry.checking = false);
        await _persist();
        if (entry.session!['state'] == 'duplicate') {
          if (mounted) {
            setState(() {
              entry.state = UploadState.duplicate;
              entry.reason =
                  'This photograph matches an existing record by checksum.';
              entry.why =
                  'No new record was created and the existing record is '
                  'unchanged.';
            });
          }
          await _persist();
          continue;
        }
        if (!mounted) break;
        setState(() => entry.state = UploadState.uploading);
        await widget.repository.upload(
          widget.scope,
          entry.session!,
          entry.file!,
          (double progress) {
            if (mounted) setState(() => entry.observeProgress(progress));
          },
        );
        final Json fresh = await widget.repository.resumeIntake(
          widget.scope,
          entry.session!['upload_id'],
        );
        entry.session = fresh;
        await widget.repository.completeIntake(
          widget.scope,
          fresh['upload_id'],
          'complete-${entry.digest}',
        );
        if (mounted) {
          setState(() {
            entry.state = UploadState.accepted;
            entry.reason = null;
            entry.why = null;
            entry.progress = 1;
          });
        }
        await _persist();
        widget.onComplete();
      } catch (e) {
        if (mounted) {
          setState(() {
            entry.checking = false;
            if (e is ApiFailure && e.message.startsWith('image_codec_')) {
              entry.state = UploadState.failed;
              entry.reason =
                  'The server cannot decode this file '
                  '(${vocabularyLabel(e.message.substring(12))}). '
                  'Your upload is kept.';
              entry.why =
                  'Ask an administrator to check the approved codec, '
                  'collection profile and runtime.';
            } else if (e is ApiFailure) {
              entry.state = UploadState.failed;
              entry.reason = e.message;
              entry.why = null;
            } else {
              entry.state = UploadState.interrupted;
              entry.reason =
                  'Uploading again resumes from where the server stopped.';
              entry.why = null;
            }
          });
        }
        if (e is ApiFailure && (e.status == 401 || e.status == 403)) break;
      }
    }
    if (mounted && _stopRequested) {
      setState(() {
        for (final ManifestEntry entry in batch.skip(reached)) {
          entry.state = UploadState.ready;
          entry.reason =
              'Stopped before this file started. Upload again to continue.';
          entry.why = null;
        }
      });
    }
    final bool wholeBatchSettled =
        batch.isNotEmpty &&
        batch.every((ManifestEntry e) => e.settled) &&
        !_stopRequested;
    if (mounted) {
      setState(() {
        _busy = false;
        _stopRequested = false;
      });
    }
    // One haptic per batch, never one per file: a 200 image batch must not
    // produce 200 buzzes (motion catalog, rows 66 and 67). The platform
    // check lives inside the helper, so the rule is in one place.
    if (wholeBatchSettled) SpecimenHaptics.batchComplete();
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

  /// The screen's own name and purpose (13 section 4.4's batch header).
  Widget _batchHeader(BuildContext context) {
    final UiThemeData ui = context.ui;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Semantics(
          container: true,
          header: true,
          child: Text(
            intakeTitle,
            style: ui.type.headline.copyWith(color: ui.color.ink),
          ),
        ),
        SizedBox(height: ui.space.s2),
        Text(intakePurpose, style: ui.type.body.copyWith(color: ui.color.ink)),
      ],
    );
  }

  Widget _captureCard(BuildContext context) => IntakeCaptureCard(
    sensitive: _newSensitive,
    onSensitivityChanged: _busy
        ? null
        : (bool value) => setState(() => _newSensitive = value),
    onChooseFiles: _busy ? null : _chooseFiles,
    onTakePhotograph: _busy ? null : _takePhotograph,
    cameraAvailable: _cameraAvailable,
  );

  /// The pre-upload checks, and the upload action where there is no frame to
  /// put it in.
  Widget _checks(BuildContext context) => IntakeChecks(
    confirmed: _qualityConfirmed,
    onConfirmedChanged: _busy
        ? null
        : (bool value) => setState(() => _qualityConfirmed = value),
    // The frame carries the action while there is a batch to send. Before
    // there is one, and in any host with no `UiScaffold` above this screen,
    // the control stays here, so the one thing that releases a batch is never
    // somewhere a reviewer cannot find it.
    upload: _uploadCarriedByFrame ? null : _uploadButton(),
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
    onPressed: _busy || !_qualityConfirmed || _pendingCount == 0 ? null : _send,
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
    final ({bool busy, bool confirmed, int pending, bool current}) state = (
      busy: _busy,
      confirmed: _qualityConfirmed,
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

  Widget _sourcesEntry(BuildContext context) => UiButtonRow(
    primary: UiButton(
      label: intakeBrowseSourcesLabel,
      variant: UiButtonVariant.secondary,
      leading: UiIcons.sources,
      onPressed: _busy ? null : widget.onBrowseSources,
    ),
  );

  Widget _manifest(
    BuildContext context, {
    EdgeInsetsGeometry? padding,
    bool scrollable = true,
  }) => IntakeManifest(
    entries: _entries,
    busy: _busy,
    stopping: _busy && _stopRequested,
    onStop: () => setState(() => _stopRequested = true),
    onRemove: _remove,
    onServerCheck: _preflight,
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
    _publishUpload(current: ModalRoute.of(context)?.isCurrent ?? true);
    // Two declared arrangements, one per window class: a single scroll below
    // 600 dp and two columns from 600 up, with the capture card fixed on the
    // start edge so the control an operator presses repeatedly never scrolls
    // away from the list it fills (05 section 3.4; 07 section 5). The window
    // decides, never the platform.
    final bool twoColumn =
        const Adaptive<bool>(compact: false, medium: true).of(context) ?? false;
    if (!twoColumn) {
      // One scroll of sections with an `s6` gap between them (13 section
      // 4.4). The manifest used to be a shrink wrapped list inside this one,
      // which is the nesting 13 section 2.1 forbids, and the capture card
      // used to carry the checks and the upload as well, which laid it out
      // 1018 dp tall in an 844 dp window.
      //
      // The checks are under the manifest rather than over it, which is the
      // one place this differs from 13 section 4.4's order. 13 section 2.5
      // asks for the manifest's first row inside the first viewport, and at
      // 200 percent text on a 390 by 844 phone the chrome takes 122 dp and
      // leaves 722: the header is 137 of it and the capture card 320, so the
      // manifest starts at 643 with the checks after it and at 964 with the
      // checks before it. Section 2.5 is the clause the gates measure, and
      // the checks read better where they now are anyway: the confirmation
      // that releases a batch sits next to the control that sends it.
      final List<Widget> sections = <Widget>[
        _batchHeader(context),
        _captureCard(context),
        _manifest(context, padding: EdgeInsets.zero, scrollable: false),
        _checks(context),
        if (widget.onBrowseSources != null) _sourcesEntry(context),
      ];
      return CustomScrollView(
        slivers: <Widget>[
          SliverPadding(
            padding: EdgeInsetsDirectional.all(ui.space.s4),
            sliver: SliverList.separated(
              itemCount: sections.length + 1,
              itemBuilder: (BuildContext context, int index) =>
                  index == 0 ? _errorSlot(context) : sections[index - 1],
              separatorBuilder: (BuildContext context, int index) =>
                  SizedBox(height: index == 0 ? 0 : ui.space.s6),
            ),
          ),
          SliverToBoxAdapter(
            child: SizedBox(
              height: ui.space.s4 + UiScaffold.of(context).bottomInset,
            ),
          ),
        ],
      );
    }
    return Row(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        SizedBox(
          key: const ValueKey<String>('intake-capture-column'),
          width: intakeCaptureColumnWidth,
          child: SingleChildScrollView(
            padding: EdgeInsetsDirectional.all(ui.space.s6),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                _errorSlot(context),
                _batchHeader(context),
                SizedBox(height: ui.space.s6),
                _captureCard(context),
                SizedBox(height: ui.space.s6),
                _checks(context),
                if (widget.onBrowseSources != null) ...<Widget>[
                  SizedBox(height: ui.space.s6),
                  _sourcesEntry(context),
                ],
                SizedBox(
                  height: ui.space.s4 + UiScaffold.of(context).bottomInset,
                ),
              ],
            ),
          ),
        ),
        // Decorative separation between two panes, never a boundary
        // (09 section 3.1).
        const UiHairline.vertical(),
        Expanded(child: _manifest(context)),
      ],
    );
  }
}
