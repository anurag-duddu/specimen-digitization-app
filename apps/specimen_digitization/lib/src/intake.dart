import 'dart:convert';
import 'dart:ui' as ui;
import 'package:crypto/crypto.dart';
import 'package:file_selector/file_selector.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'models.dart';
import 'capture_quality.dart';
import 'review_context.dart';
import 'vocabulary.dart';
import 'widgets/caveat_text.dart';

/// The state of an upload that already exists in collection storage.
/// Used as a sentinel as well as a label, so it lives in one place.
const String duplicateUploadState = 'Already in collection';

class ManifestEntry {
  ManifestEntry({
    required this.digest,
    this.file,
    this.session,
    this.state = 'Select this file again to resume',
    this.progress = 0,
    this.quality,
  });
  final String digest;
  IntakeFile? file;
  Json? session;
  String state;

  /// The expandable half of [state], when the state carries a caveat.
  String? why;
  double progress;
  CaptureQuality? quality;
  Json? preflight;
  String? preflightError;
  bool checking = false;
}

class IntakeScreen extends StatefulWidget {
  const IntakeScreen({
    super.key,
    required this.repository,
    required this.scope,
    required this.userId,
    required this.onComplete,
    this.pickImages,
    this.recoverCamera,
  });
  final SpecimenRepository repository;
  final CollectionScope scope;
  final String userId;
  final VoidCallback onComplete;
  final Future<List<XFile>> Function(bool camera)? pickImages;
  final Future<List<XFile>> Function()? recoverCamera;
  @override
  State<IntakeScreen> createState() => _IntakeScreenState();
}

class _IntakeScreenState extends State<IntakeScreen> {
  final _entries = <ManifestEntry>[];
  bool _busy = false;
  bool _qualityConfirmed = false;
  bool _newSensitive = true;
  String? _error;
  String get _storageKey =>
      'upload-handles-v1:${widget.userId}:${widget.scope.key}';
  Future<void> _preflight(ManifestEntry entry) async {
    final file = entry.file;
    if (file == null) return;
    setState(() {
      entry.checking = true;
      entry.preflightError = null;
    });
    try {
      final result = await widget.repository.preflight(widget.scope, file);
      if (mounted && identical(entry.file, file)) {
        setState(() => entry.preflight = result);
      }
    } catch (e) {
      if (mounted) {
        setState(
          () => entry.preflightError = e is ApiFailure
              ? e.message
              : 'The server check did not run. Retry, or ask your administrator to confirm your collection access.',
        );
      }
    } finally {
      if (mounted) setState(() => entry.checking = false);
    }
  }

  @override
  void initState() {
    super.initState();
    _restore().then((_) => _recoverCamera());
  }

  Future<void> _restore() async {
    final prefs = await SharedPreferences.getInstance();
    final saved = prefs.getString(_storageKey);
    if (saved != null && mounted) {
      try {
        final restored = objects(jsonDecode(saved)).map(
          (e) => ManifestEntry(
            digest: e['digest'],
            session: {'upload_id': e['upload_id']},
          ),
        );
        setState(() => _entries.addAll(restored));
      } catch (_) {
        setState(
          () => _error =
              'Saved uploads could not be read. Select your files again to match them with the server.',
        );
      }
    }
  }

  Future<void> _persist() async {
    final prefs = await SharedPreferences.getInstance();
    // Persist only opaque upload handles and checksums, never image bytes, tokens or label content.
    await prefs.setString(
      _storageKey,
      jsonEncode(
        _entries
            .where(
              (e) =>
                  e.session?['upload_id'] != null &&
                  e.state != 'Accepted' &&
                  e.state != duplicateUploadState,
            )
            .map(
              (e) => {'digest': e.digest, 'upload_id': e.session!['upload_id']},
            )
            .toList(),
      ),
    );
  }

  Future<void> _pick({bool camera = false}) async {
    setState(() {
      _busy = true;
      _qualityConfirmed = false;
      _error = null;
    });
    try {
      final List<XFile> files;
      if (camera) {
        final prefs = await SharedPreferences.getInstance();
        await prefs.setString(_captureKey, _captureOwner);
      }
      if (widget.pickImages != null) {
        files = await widget.pickImages!(camera);
      } else if (camera) {
        final image = await ImagePicker().pickImage(
          source: ImageSource.camera,
          requestFullMetadata: false,
        );
        files = image == null ? [] : [image];
      } else {
        files = await openFiles(
          acceptedTypeGroups: [
            const XTypeGroup(
              label: 'Specimen photographs',
              extensions: [
                'jpg',
                'jpeg',
                'png',
                'heic',
                'heif',
                'tif',
                'tiff',
                'dng',
              ],
              uniformTypeIdentifiers: ['public.image'],
            ),
          ],
        );
      }
      await _acceptFiles(files, camera: camera);
    } catch (_) {
      if (mounted) {
        setState(
          () => _error =
              'The camera or file picker did not open. Check device permissions, then choose files.',
        );
      }
    } finally {
      if (camera) {
        final prefs = await SharedPreferences.getInstance();
        if (prefs.getString(_captureKey) == _captureOwner) {
          await prefs.remove(_captureKey);
        }
      }
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _acceptFiles(List<XFile> files, {required bool camera}) async {
    for (final file in files) {
      final size = await file.length();
      if (size == 0 || size > 25000000) {
        if (mounted) {
          setState(
            () => _error =
                '${file.name} was skipped. Images must be under 25 MB and not empty.',
          );
        }
        continue;
      }
      final bytes = await file.readAsBytes();
      final digest = sha256.convert(bytes).toString();
      final extension = file.name.split('.').last.toLowerCase();
      final mime = switch (extension) {
        'jpg' || 'jpeg' => 'image/jpeg',
        'png' => 'image/png',
        'heic' || 'heif' => 'image/heic',
        'tif' || 'tiff' => 'image/tiff',
        'dng' => 'image/x-adobe-dng',
        _ => '',
      };
      if (mime.isEmpty) {
        if (mounted) {
          setState(
            () => _error =
                '${file.name} was skipped. Choose a JPEG, PNG, HEIC, TIFF or DNG image.',
          );
        }
        continue;
      }
      int? width;
      int? height;
      CaptureQuality? quality;
      bool excessiveResolution = false;
      try {
        final buffer = await ui.ImmutableBuffer.fromUint8List(bytes);
        final codec = await ui.instantiateImageCodecWithSize(
          buffer,
          getTargetSize: (w, h) {
            width = w;
            height = h;
            if (w > 20000 || h > 20000 || w * h > 40000000) {
              excessiveResolution = true;
              throw const FormatException('Image exceeds local decode limits');
            }
            final scale = w > h ? 256 / w : 256 / h;
            return ui.TargetImageSize(
              width: scale < 1 ? (w * scale).round().clamp(1, 256) : w,
              height: scale < 1 ? (h * scale).round().clamp(1, 256) : h,
            );
          },
        );
        try {
          final frame = await codec.getNextFrame();
          try {
            final pixels = await frame.image.toByteData(
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
        if (mounted) {
          setState(
            () => _error =
                '${file.name} was skipped. It is over 40 megapixels or over 20,000 pixels on one side.',
          );
        }
        continue;
      }
      final old = _entries.where((e) => e.digest == digest).firstOrNull;
      final input = IntakeFile(
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
      if (mounted) {
        setState(() {
          if (old != null) {
            old.file = input;
            old.quality = quality;
            if (old.state != 'Accepted') old.state = 'Ready to resume';
          } else {
            _entries.add(
              ManifestEntry(
                digest: digest,
                file: input,
                quality: quality,
                state: 'Ready for upload',
              ),
            );
          }
        });
      }
    }
  }

  /// File sizes read as "4.2 MB", to one decimal (guideline 4.14).
  static String _megabytes(int bytes) => (bytes / 1000000).toStringAsFixed(1);

  String get _captureOwner => '${widget.userId}:${widget.scope.key}';
  static const _captureKey = 'pending-camera-owner-v1';
  Future<void> _recoverCamera() async {
    if ((!kIsWeb && defaultTargetPlatform == TargetPlatform.android) ||
        widget.recoverCamera != null) {
      final prefs = await SharedPreferences.getInstance();
      if (!mounted || prefs.getString(_captureKey) != _captureOwner) return;
      setState(() => _busy = true);
      try {
        final List<XFile> files;
        if (widget.recoverCamera != null) {
          files = await widget.recoverCamera!();
        } else {
          final lost = await ImagePicker().retrieveLostData();
          if (lost.exception != null) throw lost.exception!;
          files = lost.files ?? (lost.file == null ? [] : [lost.file!]);
        }
        if (!mounted) return;
        await _acceptFiles(files, camera: true);
        if (mounted && files.isNotEmpty) {
          setState(
            () => _error =
                'Recovered an interrupted photograph. Check its framing and readability before you upload.',
          );
        }
      } catch (_) {
        if (mounted) {
          setState(
            () => _error =
                'The interrupted photograph could not be recovered. Take it again, or choose the original file.',
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

  Future<void> _send() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    for (final entry in _entries.where(
      (e) =>
          e.file != null &&
          e.state != 'Accepted' &&
          e.state != duplicateUploadState,
    )) {
      if (!mounted) break;
      try {
        setState(() => entry.state = 'Checking upload');
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
        await _persist();
        if (entry.session!['state'] == 'duplicate') {
          if (mounted) {
            setState(() {
              entry.state = duplicateUploadState;
              entry.why =
                  'This photograph matches an existing record by checksum. '
                  'No new record was created.';
            });
          }
          await _persist();
          continue;
        }
        if (!mounted) break;
        setState(() => entry.state = 'Uploading');
        await widget.repository.upload(
          widget.scope,
          entry.session!,
          entry.file!,
          (progress) {
            if (mounted) setState(() => entry.progress = progress);
          },
        );
        final fresh = await widget.repository.resumeIntake(
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
            entry.state = 'Accepted';
            entry.why = null;
            entry.progress = 1;
          });
        }
        await _persist();
        widget.onComplete();
      } catch (e) {
        if (mounted) {
          setState(() {
            if (e is ApiFailure && e.message.startsWith('image_codec_')) {
              entry.state =
                  'The server cannot decode this file '
                  '(${vocabularyLabel(e.message.substring(12))}). '
                  'Your upload is kept.';
              entry.why =
                  'Ask an administrator to check the approved codec, collection '
                  'profile and runtime.';
            } else if (e is ApiFailure) {
              entry.state = e.message;
              entry.why = null;
            } else {
              entry.state = 'Interrupted';
              entry.why =
                  'Uploading again resumes from where the server stopped.';
            }
          });
        }
        if (e is ApiFailure && (e.status == 401 || e.status == 403)) break;
      }
    }
    if (mounted) setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) {
    final camera =
        !kIsWeb &&
        (defaultTargetPlatform == TargetPlatform.android ||
            defaultTargetPlatform == TargetPlatform.iOS);
    return ListView(
      padding: const EdgeInsets.all(24),
      children: [
        Text(
          'Add photographs',
          style: Theme.of(context).textTheme.headlineMedium,
        ),
        const SizedBox(height: 8),
        const Text('One photograph per specimen.'),
        Text(
          'Your original file is never changed. Processing continues after you '
          'leave this screen.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: 24),
        Card(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(Icons.add_photo_alternate_outlined, size: 40),
                const SizedBox(height: 16),
                Text(
                  'Source photographs',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: 8),
                DropdownButtonFormField<bool>(
                  key: const ValueKey('intake-sensitivity'),
                  initialValue: _newSensitive,
                  decoration: const InputDecoration(
                    labelText: 'Sensitivity of new photographs',
                    helperText: 'Applies to photographs you add next.',
                  ),
                  items: const [
                    DropdownMenuItem(value: true, child: Text('Sensitive')),
                    DropdownMenuItem(
                      value: false,
                      child: Text('Non-sensitive'),
                    ),
                  ],
                  onChanged: _busy
                      ? null
                      : (value) => setState(() => _newSensitive = value!),
                ),
                const SizedBox(height: 8),
                const Text(
                  'Choose Non-sensitive only if these photographs and their labels '
                  'are suitable for ordinary collection access.',
                ),
                const SizedBox(height: 16),
                const CaveatText(
                  label:
                      'HEIC, TIFF and DNG may not preview on this device. You can '
                      'still upload them.',
                  why:
                      'Previews depend on this device. The server verifies the '
                      'bytes, format and dimensions of the file when the upload '
                      'completes. If the server cannot decode it, your upload is '
                      'kept so you can retry.',
                ),
                const SizedBox(height: 16),
                Wrap(
                  spacing: 12,
                  runSpacing: 12,
                  children: [
                    FilledButton.icon(
                      onPressed: _busy ? null : () => _pick(),
                      icon: const Icon(Icons.upload_file),
                      label: const Text('Choose files'),
                    ),
                    OutlinedButton.icon(
                      onPressed: _busy || !camera
                          ? null
                          : () => _pick(camera: true),
                      icon: const Icon(Icons.camera_alt_outlined),
                      label: const Text('Take photograph'),
                    ),
                  ],
                ),
                if (!camera)
                  const Padding(
                    padding: EdgeInsets.only(top: 12),
                    child: Text(
                      'Camera capture is available in the iOS and Android apps. In '
                      'a browser, choose a file instead.',
                    ),
                  ),
                const SizedBox(height: 16),
                const Text('Before you upload, check:'),
                for (final check in const [
                  'Sharp focus',
                  'Smallest text readable',
                  'Even exposure',
                  'No glare',
                  'Every label inside the frame',
                ])
                  Text('• $check'),
                CheckboxListTile(
                  contentPadding: EdgeInsets.zero,
                  value: _qualityConfirmed,
                  onChanged: _busy
                      ? null
                      : (v) => setState(() => _qualityConfirmed = v!),
                  title: const Text('I checked framing and readability'),
                ),
                Text(
                  'The server runs its own checks.',
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ),
          ),
        ),
        if (_error != null)
          Semantics(
            liveRegion: true,
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Text(_error!),
            ),
          ),
        const SizedBox(height: 20),
        Text(
          'Selected files · ${_entries.length}',
          style: Theme.of(context).textTheme.titleLarge,
        ),
        const SizedBox(height: 8),
        const CaveatText(
          label: 'After a restart, select the same files again to resume.',
          why:
              'Checksums match your files to the uploads already on the server. '
              'Records that were accepted are not created twice.',
        ),
        const SizedBox(height: 16),
        if (_entries.isEmpty)
          const Padding(
            padding: EdgeInsets.all(24),
            child: Text('No files selected yet.'),
          ),
        ..._entries.map(
          (e) => Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    e.file?.name ??
                        'Interrupted upload ${e.digest.substring(0, 12)}',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 8),
                  Semantics(
                    liveRegion: true,
                    child: e.why == null
                        ? Text(e.state)
                        : CaveatText(label: e.state, why: e.why!),
                  ),
                  Text(
                    e.session != null
                        ? 'Existing upload · sensitivity unchanged'
                        : e.file?.sensitive == false
                        ? 'Non-sensitive photograph'
                        : 'Sensitive photograph',
                  ),
                  if (e.file != null)
                    Text(
                      '${_megabytes(e.file!.bytes.length)} MB · ${e.file!.width ?? '?'} × ${e.file!.height ?? '?'} pixels',
                    ),
                  if (e.file != null)
                    CaptureQualityView(
                      quality: e.quality,
                      previewBytes: e.file!.bytes,
                    ),
                  if (e.file != null) ...[
                    const CaveatText(
                      label:
                          'Send this image to the server for a decode check.',
                      why:
                          'Nothing is created and no outside service is called. '
                          'Your local measurements stay on this device until you '
                          'choose an action.',
                    ),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: OutlinedButton(
                        onPressed: e.checking || _busy
                            ? null
                            : () => _preflight(e),
                        child: Text(
                          e.checking ? 'Checking…' : 'Send for server check',
                        ),
                      ),
                    ),
                    if (e.preflightError != null) Text(e.preflightError!),
                    if (e.preflight != null) ...[
                      if (objectOf(e.preflight!['decode'])['reason'] ==
                          'memory_limit_unavailable')
                        const CaveatText(
                          label:
                              'The server check is not available. Ask the service '
                              'administrator to enable memory-limit enforcement.',
                          why:
                              'Changing the image format will not help. Ordinary '
                              'image intake is checked separately and is '
                              'unaffected.',
                        ),
                      Text(
                        'Server check: ${vocabularyLabel(textOf(e.preflight!['status']))}. Check quality yourself as well.',
                      ),
                      for (final issue in e.preflight!['issues'] as List? ?? [])
                        Text(vocabularyLabel(issue.toString())),
                      Text(
                        'Not measured: ${e.preflight!['unmeasured'] ?? 'Not recorded'}',
                      ),
                      EvidenceDetails(
                        title: 'Server codec support and check evidence',
                        value: e.preflight!,
                      ),
                    ],
                  ],
                  SelectableText(
                    'Checksum (SHA-256) ${e.digest}',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                  if (e.state == 'Uploading')
                    LinearProgressIndicator(
                      value: e.progress,
                      semanticsLabel: e.file == null
                          ? 'Uploading'
                          : 'Uploading ${_megabytes((e.progress * e.file!.bytes.length).round())} of ${_megabytes(e.file!.bytes.length)} megabytes',
                    ),
                ],
              ),
            ),
          ),
        ),
        const SizedBox(height: 16),
        Align(
          alignment: Alignment.centerLeft,
          child: FilledButton.icon(
            onPressed:
                _busy ||
                    !_qualityConfirmed ||
                    !_entries.any(
                      (e) =>
                          e.file != null &&
                          e.state != 'Accepted' &&
                          e.state != duplicateUploadState,
                    )
                ? null
                : _send,
            icon: const Icon(Icons.cloud_upload_outlined),
            label: Text(_busy ? 'Uploading…' : 'Upload selected files'),
          ),
        ),
      ],
    );
  }
}
