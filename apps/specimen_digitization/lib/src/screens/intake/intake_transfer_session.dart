/// An intake transfer survives a change of collection route within this app
/// session. Only upload handles and checksums are saved across app restarts;
/// the operator must reselect interrupted image bytes after a restart.
library;

import 'dart:async';
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../models.dart';
import '../../theme/motion.dart';
import '../../vocabulary.dart';
import '../../widgets/upload_item.dart';
import 'manifest_entry.dart';

/// The repository owns the lifetime boundary. A different signed-in user or
/// collection never sees another user's queue, even if the repository is reused.
final Expando<Map<String, IntakeTransferSession>> _sessions =
    Expando<Map<String, IntakeTransferSession>>('intake transfer sessions');

IntakeTransferSession intakeTransferSession(
  SpecimenRepository repository,
  CollectionScope scope,
  String userId,
) {
  final Map<String, IntakeTransferSession> sessions = _sessions[repository] ??=
      <String, IntakeTransferSession>{};
  return sessions.putIfAbsent(
    '$userId:${scope.key}',
    () => IntakeTransferSession(repository, scope, userId)..restore(),
  );
}

/// Clears retained image bytes when the host ends the signed-in session.
/// The app shell can call this at sign-out; it is safe after a transfer ends.
void forgetIntakeTransfers(SpecimenRepository repository, String userId) {
  final Map<String, IntakeTransferSession>? sessions = _sessions[repository];
  if (sessions == null) return;
  for (final String key
      in sessions.keys.where((key) => key.startsWith('$userId:')).toList()) {
    sessions.remove(key)?.close();
  }
}

class IntakeTransferSession extends ChangeNotifier {
  IntakeTransferSession(
    this.repository,
    this.scope,
    this.userId, {
    this.beforePersist,
  });

  final SpecimenRepository repository;
  final CollectionScope scope;
  final String userId;

  /// Test seam for a slow local preference write at the sign-out boundary.
  final Future<void> Function()? beforePersist;
  final List<ManifestEntry> entries = <ManifestEntry>[];
  final Set<VoidCallback> _completed = <VoidCallback>{};
  bool busy = false;
  bool stopping = false;
  bool _closed = false;
  bool _completionWhileDetached = false;
  String? restoreError;

  String get _storageKey => 'upload-handles-v1:$userId:${scope.key}';

  void attachComplete(VoidCallback callback) {
    _completed.add(callback);
    if (_completionWhileDetached) {
      _completionWhileDetached = false;
      scheduleMicrotask(() {
        if (!_closed && _completed.contains(callback)) callback();
      });
    }
  }

  void detachComplete(VoidCallback callback) => _completed.remove(callback);

  void changed() {
    if (!_closed) notifyListeners();
  }

  Future<void> restore() async {
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    final String? saved = prefs.getString(_storageKey);
    if (saved == null || _closed) return;
    try {
      final dynamic parsed = jsonDecode(saved);
      if (parsed is! List) throw const FormatException('Upload handles');
      for (final dynamic value in parsed) {
        if (value is! Map ||
            value['digest'] is! String ||
            value['upload_id'] is! String) {
          throw const FormatException('Upload handle');
        }
        final String digest = value['digest'] as String;
        if (digest.length < 12 ||
            entries.any((entry) => entry.digest == digest)) {
          continue;
        }
        entries.add(
          ManifestEntry.restored(
            digest: digest,
            handle: <String, dynamic>{'upload_id': value['upload_id']},
          ),
        );
      }
      changed();
    } catch (_) {
      restoreError =
          'Saved uploads could not be read. Select your files again to match them with the server.';
      changed();
    }
  }

  Future<void> persist() async {
    await beforePersist?.call();
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    if (_closed) {
      await prefs.remove(_storageKey);
      return;
    }
    await prefs.setString(
      _storageKey,
      jsonEncode(
        entries
            .where(
              (entry) => entry.session?['upload_id'] != null && !entry.settled,
            )
            .map(
              (entry) => <String, dynamic>{
                'digest': entry.digest,
                'upload_id': entry.session!['upload_id'],
              },
            )
            .toList(),
      ),
    );
  }

  void remove(ManifestEntry entry) {
    if (entry.removable && entry.state != UploadState.uploading) {
      entries.remove(entry);
      changed();
      unawaited(persist());
    }
  }

  /// Stops after the current file; the API has no abort endpoint for a chunk
  /// already in flight. Unstarted files remain ready for an explicit retry.
  void stop() {
    stopping = true;
    changed();
  }

  /// Starts a single serial pump. New files may be admitted while it runs.
  /// Failed entries remain visible and are retried only by another action.
  Future<void> start({ManifestEntry? only}) async {
    if (_closed || busy) return;
    busy = true;
    stopping = false;
    changed();
    final Set<ManifestEntry> attempted = <ManifestEntry>{};
    try {
      while (!_closed && !stopping) {
        final ManifestEntry? entry =
            only ??
            entries
                .where((e) => e.sendable && !attempted.contains(e))
                .firstOrNull;
        if (entry == null || !entry.sendable || attempted.contains(entry)) {
          break;
        }
        attempted.add(entry);
        final bool authorized = await _sendOne(entry);
        if (!authorized || only != null) break;
      }
    } finally {
      if (!_closed && stopping) {
        for (final ManifestEntry entry in entries) {
          if (entry.sendable && !attempted.contains(entry)) {
            entry.state = UploadState.ready;
            entry.reason =
                'Stopped before this file started. Upload again to continue.';
            entry.why = null;
          }
        }
      }
      busy = false;
      stopping = false;
      changed();
      if (!_closed &&
          attempted.isNotEmpty &&
          attempted.every((entry) => entry.settled)) {
        SpecimenHaptics.batchComplete();
      }
    }
  }

  Future<bool> _sendOne(ManifestEntry entry) async {
    final IntakeFile? file = entry.file;
    if (file == null) return true;
    try {
      entry.checking = true;
      entry.reason = null;
      entry.why = null;
      changed();
      entry.session = entry.session == null
          ? await repository.createIntake(scope, file, 'intake-${entry.digest}')
          : await repository.resumeIntake(
              scope,
              entry.session!['upload_id'] as String,
            );
      if (_closed) return false;
      entry.checking = false;
      changed();
      await persist();
      if (_closed) return false;
      if (entry.session!['state'] == 'duplicate') {
        entry.state = UploadState.duplicate;
        entry.reason =
            'This photograph matches an existing record by checksum.';
        entry.why =
            'No new record was created and the existing record is unchanged.';
        entry.file = null;
        changed();
        await persist();
        return true;
      }
      entry.state = UploadState.uploading;
      changed();
      await repository.upload(scope, entry.session!, file, (double progress) {
        entry.observeProgress(progress);
        changed();
      });
      if (_closed) return false;
      final Json fresh = await repository.resumeIntake(
        scope,
        entry.session!['upload_id'] as String,
      );
      if (_closed) return false;
      entry.session = fresh;
      final Json completion = await repository.completeIntake(
        scope,
        fresh['upload_id'] as String,
        'complete-${entry.digest}',
      );
      if (_closed) return false;
      entry.state = UploadState.accepted;
      entry.reason = intakeCompletionReason(completion);
      entry.why = null;
      entry.progress = 1;
      entry.file = null; // Release image bytes when the server holds them.
      changed();
      await persist();
      if (_completed.isEmpty) _completionWhileDetached = true;
      for (final VoidCallback callback in _completed.toList()) {
        callback();
      }
      return true;
    } catch (error) {
      if (_closed) return false;
      entry.checking = false;
      if (error is ApiFailure && error.message.startsWith('image_codec_')) {
        entry.state = UploadState.failed;
        entry.reason =
            'The server cannot decode this file (${vocabularyLabel(error.message.substring(12))}). Your upload is kept.';
        entry.why =
            'Ask an administrator to check the approved codec, collection profile and runtime.';
      } else if (error is ApiFailure) {
        entry.state = UploadState.failed;
        entry.reason = error.message;
        entry.why = null;
      } else {
        entry.state = UploadState.interrupted;
        entry.reason = 'Uploading again resumes from where the server stopped.';
        entry.why = null;
      }
      changed();
      await persist();
      return error is! ApiFailure ||
          (error.status != 401 && error.status != 403);
    }
  }

  void close() {
    _closed = true;
    stopping = true;
    for (final ManifestEntry entry in entries) {
      entry.file = null;
    }
    entries.clear();
    _completed.clear();
    unawaited(persist());
    dispose();
  }
}

/// Upload acceptance and processing are separate facts. The completion
/// response is a snapshot; a pending run may still be waiting for a worker.
String intakeCompletionReason(Json completion) {
  final Object? status = completion['status'] ?? completion['stage'];
  if (status == 'pending') {
    return 'Uploaded to the collection. Processing is queued.';
  }
  if (status == 'processing_blocked') {
    if (completion['blocker'] == 'sensitive_record_not_processed') {
      return 'Uploaded to the collection. Sensitive records are held from processing.';
    }
    if (completion['blocker'] == 'collection_processing_unconfigured') {
      return 'Uploaded to the collection. Processing awaits collection setup.';
    }
    return 'Uploaded to the collection. Processing is blocked; check the queue.';
  }
  if (status == 'running') {
    return 'Uploaded to the collection. Processing is running.';
  }
  if (status == 'completed') {
    return 'Uploaded to the collection. Processing is complete.';
  }
  return 'Uploaded to the collection. Check the queue for processing status.';
}
