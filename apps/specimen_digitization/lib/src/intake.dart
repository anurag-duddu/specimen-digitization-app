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
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:image_picker/image_picker.dart';
import 'package:material_symbols_icons/symbols.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'capture/capture_camera.dart';
import 'capture/capture_screen.dart';
import 'capture_quality.dart';
import 'layout/window_class.dart';
import 'models.dart';
import 'screens/intake/capture_card.dart';
import 'screens/intake/manifest_entry.dart';
import 'screens/intake/manifest_panel.dart';
import 'theme/icons.dart';
import 'vocabulary.dart';
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

class IntakeScreen extends StatefulWidget {
  const IntakeScreen({
    super.key,
    required this.repository,
    required this.scope,
    required this.userId,
    required this.onComplete,
    this.pickImages,
    this.recoverCamera,
    this.openCapture,
    this.cameraFactory,
  });
  final SpecimenRepository repository;
  final CollectionScope scope;
  final String userId;
  final VoidCallback onComplete;

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

  bool get _mobile => _cameraAvailable;

  @override
  void initState() {
    super.initState();
    _restore().then((_) => _recoverCamera());
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
              : 'The server check did not run. Retry, or ask your '
                    'administrator to confirm your collection access.',
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
    // produce 200 buzzes (motion, rows 66 and 67).
    if (wholeBatchSettled && _mobile) HapticFeedback.lightImpact();
  }

  // ---------------------------------------------------------------- drawing

  int get _pendingCount =>
      _entries.where((ManifestEntry e) => e.sendable).length;

  Widget _errorCard(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Padding(
      padding: EdgeInsets.only(bottom: context.space.space4),
      child: Card(
        color: theme.colorScheme.errorContainer,
        child: Padding(
          padding: EdgeInsets.all(context.space.space4),
          child: Semantics(
            liveRegion: true,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Icon(
                  Symbols.error,
                  size: context.sizes.iconAction,
                  color: theme.colorScheme.onErrorContainer,
                ),
                SizedBox(width: context.space.space3),
                Expanded(
                  child: Text(
                    _error!,
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: theme.colorScheme.onErrorContainer,
                    ),
                  ),
                ),
                IconButton(
                  onPressed: () => setState(() => _error = null),
                  icon: const Icon(Symbols.close),
                  iconSize: context.sizes.iconAction,
                  tooltip: 'Dismiss this message',
                  color: theme.colorScheme.onErrorContainer,
                  constraints: BoxConstraints(
                    minWidth: context.sizes.targetMin,
                    minHeight: context.sizes.targetMin,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _captureColumn(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.stretch,
    mainAxisSize: MainAxisSize.min,
    children: <Widget>[
      if (_error != null) _errorCard(context),
      IntakeCaptureCard(
        sensitive: _newSensitive,
        onSensitivityChanged: _busy
            ? null
            : (bool value) => setState(() => _newSensitive = value),
        onChooseFiles: _busy ? null : _chooseFiles,
        onTakePhotograph: _busy ? null : _takePhotograph,
        cameraAvailable: _cameraAvailable,
        confirmed: _qualityConfirmed,
        onConfirmedChanged: _busy
            ? null
            : (bool value) => setState(() => _qualityConfirmed = value),
        onUpload: _busy || !_qualityConfirmed || _pendingCount == 0
            ? null
            : _send,
        uploading: _busy,
        pendingCount: _pendingCount,
      ),
    ],
  );

  Widget _manifest(
    BuildContext context, {
    EdgeInsetsGeometry? padding,
    bool nested = false,
  }) => IntakeManifest(
    entries: _entries,
    busy: _busy,
    stopping: _busy && _stopRequested,
    onStop: () => setState(() => _stopRequested = true),
    onRemove: _remove,
    onServerCheck: _preflight,
    padding: padding,
    nested: nested,
  );

  @override
  Widget build(BuildContext context) {
    final WindowClass window = WindowClass.of(context);
    // One column below 600dp, two at 600dp and above (blueprint 5). The
    // decision reads the window, never the platform.
    if (window.isCompact) {
      return ListView(
        padding: EdgeInsets.all(context.space.space4),
        children: <Widget>[
          _captureColumn(context),
          SizedBox(height: context.space.space6),
          _manifest(context, padding: EdgeInsets.zero, nested: true),
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
            padding: EdgeInsets.all(context.space.space6),
            child: _captureColumn(context),
          ),
        ),
        VerticalDivider(width: context.space.space0),
        Expanded(child: _manifest(context)),
      ],
    );
  }
}
