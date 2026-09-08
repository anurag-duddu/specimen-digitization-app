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

class ManifestEntry {
  ManifestEntry({
    required this.digest,
    this.file,
    this.session,
    this.state = 'Reselect original to resume',
    this.progress = 0,
    this.quality,
  });
  final String digest;
  IntakeFile? file;
  Json? session;
  String state;
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
              : 'Server preflight unavailable. Retry or check collection access.',
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
              'Saved upload handles could not be read. Reselect files to reconcile with the server.',
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
                  !e.state.startsWith('Duplicate'),
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
              'Capture or file selection unavailable. Check device permissions or select files instead.',
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
            () =>
                _error = '${file.name}: choose a non-empty image under 25 MB.',
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
          setState(() => _error = '${file.name}: unsupported file type.');
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
                '${file.name}: image exceeds the local 40 megapixel / 20,000 pixel axis limit.',
          );
        }
        continue;
      }
      final input = IntakeFile(
        name: file.name,
        bytes: bytes,
        mimeType: mime,
        sha256: digest,
        method: camera ? 'camera' : 'files',
        width: width,
        height: height,
      );
      final old = _entries.where((e) => e.digest == digest).firstOrNull;
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
                'Recovered an interrupted camera photograph. Check its framing and readability before uploading.',
          );
        }
      } catch (_) {
        if (mounted) {
          setState(
            () => _error =
                'The interrupted camera photograph could not be recovered. Capture again or choose the original file.',
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
          !e.state.startsWith('Duplicate'),
    )) {
      if (!mounted) break;
      try {
        setState(() => entry.state = 'Checking manifest');
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
            setState(
              () => entry.state = 'Duplicate — existing record retained',
            );
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
            entry.progress = 1;
          });
        }
        await _persist();
        widget.onComplete();
      } catch (e) {
        if (mounted) {
          setState(
            () => entry.state = e is ApiFailure
                ? e.message.startsWith('image_codec_')
                      ? 'Server decoding is blocked (${labelOf(e.message.substring(12))}). The uploaded original is retained. Ask an administrator to check the approved codec, collection profile and runtime, then retry completion.'
                      : e.message
                : 'Interrupted — retry to resume from the server checkpoint',
          );
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
          'Bring a specimen into focus',
          style: Theme.of(context).textTheme.headlineMedium,
        ),
        const SizedBox(height: 8),
        const Text(
          'One photograph per specimen. Originals remain unchanged; processing continues after you leave.',
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
                  'Select source photographs',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: 8),
                const Text(
                  'Local previews depend on this device. HEIC and approved TIFF/DNG families require a configured server codec and collection profile. Files can upload without a local preview; server completion verifies bytes, format and dimensions. A decoder block retains the upload for retry.',
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
                      'Direct camera capture is available in the Android and iOS app. In a browser, choose a photograph from your device.',
                    ),
                  ),
                const SizedBox(height: 16),
                const Text(
                  'Before submitting: check sharp focus, readable smallest text, even exposure, no glare, and every label inside the frame. Server quality checks are required; this client does not certify image quality.',
                ),
                CheckboxListTile(
                  contentPadding: EdgeInsets.zero,
                  value: _qualityConfirmed,
                  onChanged: _busy
                      ? null
                      : (v) => setState(() => _qualityConfirmed = v!),
                  title: const Text('I checked framing and readability'),
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
          'Upload manifest · ${_entries.length} items',
          style: Theme.of(context).textTheme.titleLarge,
        ),
        const SizedBox(height: 8),
        const Text(
          'After a restart, reselect the same original files. Checksums reconcile saved upload handles with server offsets; accepted records are not recreated.',
        ),
        const SizedBox(height: 16),
        if (_entries.isEmpty)
          const Padding(
            padding: EdgeInsets.all(24),
            child: Text('Your selected photographs will appear here.'),
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
                  Semantics(liveRegion: true, child: Text(e.state)),
                  if (e.file != null)
                    Text(
                      '${e.file!.bytes.length} bytes · ${e.file!.width ?? '?'} × ${e.file!.height ?? '?'} px',
                    ),
                  if (e.file != null)
                    CaptureQualityView(
                      quality: e.quality,
                      previewBytes: e.file!.bytes,
                    ),
                  if (e.file != null) ...[
                    const Text(
                      'Optional server preflight sends this original image to the collection service for decoding checks. It creates no specimen and makes no external provider call. Local measurements stay on this device until you choose an action.',
                    ),
                    Align(
                      alignment: Alignment.centerLeft,
                      child: OutlinedButton(
                        onPressed: e.checking || _busy
                            ? null
                            : () => _preflight(e),
                        child: Text(
                          e.checking
                              ? 'Checking on server…'
                              : 'Send image for server preflight',
                        ),
                      ),
                    ),
                    if (e.preflightError != null) Text(e.preflightError!),
                    if (e.preflight != null) ...[
                      if (objectOf(e.preflight!['decode'])['reason'] ==
                          'memory_limit_unavailable')
                        const Text(
                          'Server preflight requires memory-limit enforcement on an approved runtime. Ask the service administrator to configure it. Changing this image format will not resolve that block; ordinary supported-image intake is checked separately.',
                        ),
                      Text(
                        'Server preflight: ${labelOf(textOf(e.preflight!['status']))}. Manual quality review remains required.',
                      ),
                      for (final issue in e.preflight!['issues'] as List? ?? [])
                        Text(labelOf(issue.toString())),
                      Text(
                        'Unmeasured: ${e.preflight!['unmeasured'] ?? 'Not recorded'}',
                      ),
                      EvidenceDetails(
                        title:
                            'Server codec capabilities and preflight evidence',
                        value: e.preflight!,
                      ),
                    ],
                  ],
                  SelectableText(
                    'SHA-256 ${e.digest}',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                  if (e.state == 'Uploading')
                    LinearProgressIndicator(
                      value: e.progress,
                      semanticsLabel: 'Upload progress',
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
                          !e.state.startsWith('Duplicate'),
                    )
                ? null
                : _send,
            icon: const Icon(Icons.cloud_upload_outlined),
            label: Text(
              _busy ? 'Uploading…' : 'Upload / resume selected files',
            ),
          ),
        ),
      ],
    );
  }
}
