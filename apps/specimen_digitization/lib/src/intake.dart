import 'dart:convert';
import 'dart:ui' as ui;
import 'package:crypto/crypto.dart';
import 'package:file_selector/file_selector.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'models.dart';

class ManifestEntry {
  ManifestEntry({
    required this.digest,
    this.file,
    this.session,
    this.state = 'Reselect original to resume',
    this.progress = 0,
  });
  final String digest;
  IntakeFile? file;
  Json? session;
  String state;
  double progress;
}

class IntakeScreen extends StatefulWidget {
  const IntakeScreen({
    super.key,
    required this.repository,
    required this.scope,
    required this.userId,
    required this.onComplete,
  });
  final SpecimenRepository repository;
  final CollectionScope scope;
  final String userId;
  final VoidCallback onComplete;
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
  @override
  void initState() {
    super.initState();
    _restore();
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
      _error = null;
    });
    try {
      final List<XFile> files;
      if (camera) {
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
      for (final file in files) {
        final size = await file.length();
        if (size == 0 || size > 25000000) {
          if (mounted) {
            setState(
              () => _error =
                  '${file.name}: choose a non-empty image under 25 MB.',
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
        try {
          final codec = await ui.instantiateImageCodec(bytes);
          final frame = await codec.getNextFrame();
          width = frame.image.width;
          height = frame.image.height;
          frame.image.dispose();
          codec.dispose();
        } catch (_) {
          /* Original may need the server's approved HEIC/TIFF/RAW decoder. */
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
              if (old.state != 'Accepted') old.state = 'Ready to resume';
            } else {
              _entries.add(
                ManifestEntry(
                  digest: digest,
                  file: input,
                  state: 'Ready for upload',
                ),
              );
            }
          });
        }
      }
    } catch (_) {
      if (mounted) {
        setState(
          () => _error =
              'Capture or file selection unavailable. Check device permissions or select files instead.',
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
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
                ? e.message
                : 'Interrupted — retry to resume from the server checkpoint',
          );
        }
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
                  'JPEG and PNG previews supported. HEIC, TIFF and RAW require an approved server decoder and profile; unsupported files receive a validation reason.',
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
