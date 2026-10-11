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

// Intake status is deliberately a little more responsive than the main
// workspace queue: the operator may still be beside the camera waiting for a
// just-taken photograph to clear processing.
const int _processingPollMilliseconds = 5000;

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
    Duration? processingPollInterval,
  }) : processingPollInterval =
           processingPollInterval ??
           const Duration(milliseconds: _processingPollMilliseconds);

  final SpecimenRepository repository;
  final CollectionScope scope;
  final String userId;

  /// Test seam for a slow local preference write at the sign-out boundary.
  final Future<void> Function()? beforePersist;
  final Duration processingPollInterval;
  final List<ManifestEntry> entries = <ManifestEntry>[];
  final Set<VoidCallback> _completed = <VoidCallback>{};
  final Set<VoidCallback> _handedOff = <VoidCallback>{};
  Timer? _processingPoll;
  bool _refreshingProcessing = false;
  bool busy = false;
  bool stopping = false;
  bool _closed = false;
  bool _completionWhileDetached = false;
  bool _handoffWhileDetached = false;
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

  /// Registers for a record moving from Intake into the existing Queue.
  void attachHandoff(VoidCallback callback) {
    _handedOff.add(callback);
    if (_handoffWhileDetached) {
      _handoffWhileDetached = false;
      scheduleMicrotask(() {
        if (!_closed && _handedOff.contains(callback)) callback();
      });
    }
  }

  void detachHandoff(VoidCallback callback) => _handedOff.remove(callback);

  /// Whether at least one server-held photograph still needs status refreshes.
  bool get needsProcessingPoll =>
      !_closed && entries.any(_needsProcessingRefresh);

  /// Processing checks are useful only while Intake or its camera route is
  /// observing this session. Reattaching a listener restarts a poll that was
  /// paused when the last route went away or after access was unavailable.
  @override
  void addListener(VoidCallback listener) {
    super.addListener(listener);
    _scheduleProcessingPoll();
  }

  @override
  void removeListener(VoidCallback listener) {
    super.removeListener(listener);
    if (_closed || hasListeners) return;
    _processingPoll?.cancel();
    _processingPoll = null;
  }

  bool _needsProcessingRefresh(ManifestEntry entry) =>
      entry.tracksProcessing ||
      (entry.specimenId != null &&
          entry.state == UploadState.processingBlocked &&
          entry.specimen == null);

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
        final Object? specimenId = value['specimen_id'];
        if (specimenId is String && specimenId.isNotEmpty) {
          final UploadState state = _restoredTrackingState(value['state']);
          entries.add(
            ManifestEntry.tracking(
              digest: digest,
              name: 'Photograph ${digest.substring(0, 12)}',
              handle: <String, dynamic>{'upload_id': value['upload_id']},
              specimenId: specimenId,
              state: state,
              reason: state == UploadState.inMainQueue
                  ? 'Processing finished. This photograph is in the main Queue.'
                  : state == UploadState.processingBlocked
                  ? 'Processing needs attention.'
                  : 'Checking processing status.',
            ),
          );
        } else {
          entries.add(
            ManifestEntry.restored(
              digest: digest,
              handle: <String, dynamic>{'upload_id': value['upload_id']},
            ),
          );
        }
      }
      changed();
      await refreshProcessingStatuses();
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
              (entry) =>
                  entry.session?['upload_id'] != null &&
                  (!entry.settled || entry.specimenId != null),
            )
            .map(
              (entry) => <String, dynamic>{
                'digest': entry.digest,
                'upload_id': entry.session!['upload_id'],
                if (entry.specimenId != null) ...<String, dynamic>{
                  'specimen_id': entry.specimenId,
                  'state': entry.state.name,
                },
              },
            )
            .toList(),
      ),
    );
  }

  void remove(ManifestEntry entry) {
    if ((entry.removable || entry.dismissible) &&
        entry.state != UploadState.uploading &&
        entry.state != UploadState.processing) {
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
    if (only != null && canRetryProcessing(only)) {
      return retryProcessing(only);
    }
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
      if (completion['upload_state'] == 'duplicate') {
        entry.state = UploadState.duplicate;
        entry.reason =
            'This photograph is already in the collection. No new record was created.';
        entry.why = null;
      } else if (completion['specimen_id'] is String &&
          (completion['specimen_id'] as String).isNotEmpty) {
        entry.specimenId = completion['specimen_id'] as String;
        // Completion and an immediate Queue handoff are notified together
        // after persistence below, so one shared listener cannot run twice.
        _applyProcessingSummary(
          entry,
          Specimen(completion),
          notifyHandoff: false,
        );
      } else {
        // Compatibility with servers that acknowledge storage before returning
        // the created record identifier. This row cannot claim processing.
        entry.state = UploadState.accepted;
        entry.reason = intakeCompletionReason(completion);
        entry.why = null;
      }
      entry.progress = 1;
      entry.file = null; // Release image bytes when the server holds them.
      changed();
      await persist();
      _scheduleProcessingPoll();
      if (entry.state == UploadState.inMainQueue) _notifyHandoff();
      if (_completed.isEmpty) _completionWhileDetached = true;
      for (final VoidCallback callback in _completed.toList()) {
        // Intake may use the same refresh callback for both milestones. An
        // upload whose completion response already contains a final Queue
        // disposition handed off above, so that shared callback has already
        // run. Complete-only listeners still keep their original contract.
        if (entry.state == UploadState.inMainQueue &&
            _handedOff.contains(callback)) {
          continue;
        }
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

  /// Refreshes only records still owned by the Intake queue. The existing
  /// Queue remains unchanged and receives the record once a disposition exists.
  Future<void> refreshProcessingStatuses() async {
    if (_closed || _refreshingProcessing || !needsProcessingPoll) return;
    _processingPoll?.cancel();
    _processingPoll = null;
    _refreshingProcessing = true;
    var changedAny = false;
    var scheduleNext = true;
    try {
      for (final ManifestEntry entry
          in entries.where(_needsProcessingRefresh).toList()) {
        if (_closed) return;
        final String specimenId = entry.specimenId!;
        try {
          final SpecimenPage page = await repository.specimenPage(
            scope,
            filters: <String, String>{'specimen_id': specimenId},
          );
          if (_closed) return;
          final Specimen? specimen = page.items
              .where((Specimen item) => item.id == specimenId)
              .firstOrNull;
          if (specimen == null) {
            entry.reason =
                'The server record is not available yet. Checking again shortly.';
          } else {
            _applyProcessingSummary(entry, specimen);
          }
          changedAny = true;
        } on ApiFailure catch (error) {
          entry.reason = error.status == 401 || error.status == 403
              ? 'Processing status cannot be checked with the current access.'
              : 'Processing status is temporarily unavailable. Checking again shortly.';
          changedAny = true;
          if (error.status == 401 || error.status == 403) {
            scheduleNext = false;
            break;
          }
        } catch (_) {
          entry.reason =
              'Processing status is temporarily unavailable. Checking again shortly.';
          changedAny = true;
        }
      }
      if (changedAny && !_closed) {
        changed();
        await persist();
      }
    } finally {
      _refreshingProcessing = false;
      if (scheduleNext) _scheduleProcessingPoll();
    }
  }

  /// True only when the server summary explicitly offers a retry action.
  bool canRetryProcessing(ManifestEntry entry) =>
      entry.state == UploadState.processingBlocked &&
      entry.specimen != null &&
      (entry.specimen!.data['available_actions'] as List<dynamic>? ??
              const <dynamic>[])
          .contains('retry');

  /// Retries a blocked server run without re-uploading the photograph.
  Future<void> retryProcessing(ManifestEntry entry) async {
    if (_closed || busy || !canRetryProcessing(entry)) return;
    busy = true;
    entry.checking = true;
    entry.reason = 'Asking the server to retry processing.';
    changed();
    try {
      final Specimen current = entry.specimen!;
      final Specimen refreshed = await repository.retry(
        scope,
        current,
        'Retry processing from Intake.',
        'intake-retry-${entry.digest}-${current.revision}',
      );
      if (_closed) return;
      _applyProcessingSummary(entry, refreshed);
      await persist();
    } on ApiFailure catch (error) {
      if (_closed) return;
      entry.reason = error.message;
    } catch (_) {
      if (_closed) return;
      entry.reason = 'Processing did not restart. Try again.';
    } finally {
      if (!_closed) {
        entry.checking = false;
        busy = false;
        changed();
        _scheduleProcessingPoll();
      }
    }
  }

  void _applyProcessingSummary(
    ManifestEntry entry,
    Specimen specimen, {
    bool notifyHandoff = true,
  }) {
    final UploadState previous = entry.state;
    entry.specimen = specimen;
    entry.specimenId = specimen.id;
    entry.why = null;
    final String? disposition = specimen.disposition;
    if (const <String>{
      'cleared',
      'needs_human_review',
      'deferred',
    }.contains(disposition)) {
      entry.state = UploadState.inMainQueue;
      entry.reason =
          'Processing finished. This photograph is now in the main Queue.';
      if (notifyHandoff && previous != UploadState.inMainQueue) {
        _notifyHandoff();
      }
      return;
    }
    entry.state = switch (specimen.state) {
      'processing_blocked' ||
      'paused' ||
      'cancelled' ||
      'completed' => UploadState.processingBlocked,
      _ => UploadState.processing,
    };
    entry.reason = switch (specimen.state) {
      'pending' => 'Waiting for processing to start.',
      'running' => 'Processing is underway.',
      'retry_scheduled' => 'Processing will retry automatically.',
      'paused' => 'Processing is paused.',
      'cancelled' => 'Processing was cancelled.',
      'processing_blocked' => 'Processing needs attention.',
      'completed' =>
        'Processing finished, but its main Queue outcome is not available.',
      _ => 'Waiting for the latest processing status.',
    };
  }

  void _notifyHandoff() {
    if (_handedOff.isEmpty) _handoffWhileDetached = true;
    for (final VoidCallback callback in _handedOff.toList()) {
      callback();
    }
  }

  void _scheduleProcessingPoll() {
    _processingPoll?.cancel();
    _processingPoll = null;
    if (!hasListeners ||
        !needsProcessingPoll ||
        processingPollInterval == Duration.zero) {
      return;
    }
    _processingPoll = Timer(
      processingPollInterval,
      () => unawaited(refreshProcessingStatuses()),
    );
  }

  void close() {
    _closed = true;
    stopping = true;
    _processingPoll?.cancel();
    _processingPoll = null;
    for (final ManifestEntry entry in entries) {
      entry.file = null;
    }
    entries.clear();
    _completed.clear();
    _handedOff.clear();
    unawaited(persist());
    dispose();
  }
}

UploadState _restoredTrackingState(Object? value) => switch (value) {
  'inMainQueue' => UploadState.inMainQueue,
  'processingBlocked' => UploadState.processingBlocked,
  _ => UploadState.processing,
};

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
    return 'Uploaded to the collection. Processing needs attention in Intake.';
  }
  if (status == 'running') {
    return 'Uploaded to the collection. Processing is running.';
  }
  if (status == 'completed') {
    return 'Uploaded to the collection. Processing is complete.';
  }
  return 'Uploaded to Intake. Processing status is not available yet.';
}
