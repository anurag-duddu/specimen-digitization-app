/// An intake transfer survives a change of collection route within this app
/// session. Only upload handles and checksums are saved across app restarts;
/// the operator must reselect interrupted image bytes after a restart.
library;

import 'dart:async';
import 'dart:convert';

import 'package:flutter/widgets.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../blocker_words.dart';
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

class IntakeTransferSession extends ChangeNotifier with WidgetsBindingObserver {
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
  final Map<String, String> _startDispatchFailures = <String, String>{};
  final Map<String, int> _processingRevisions = <String, int>{};
  Timer? _processingPoll;
  bool _refreshingProcessing = false;
  bool _observingAppLifecycle = false;
  bool _appInBackground = false;
  bool busy = false;
  bool stopping = false;
  bool _closed = false;
  bool _completionWhileDetached = false;
  bool _handoffWhileDetached = false;
  String? restoreError;

  /// How many photographs this session has moved out of Intake because the
  /// server put them in the main Queue. Monotonic, so a screen that attaches
  /// later can remember where it started and announce only what it saw.
  /// Rows dropped at [restore] were finished in an earlier session and are
  /// not counted: nothing on screen changes for them.
  int movedToQueue = 0;

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
      scheduleMicrotask(() {
        if (!_closed &&
            _handoffWhileDetached &&
            _handedOff.contains(callback)) {
          _handoffWhileDetached = false;
          _notifyHandoff();
        }
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
    final bool wasObserved = hasListeners;
    super.addListener(listener);
    if (!wasObserved) {
      WidgetsBinding.instance.addObserver(this);
      _observingAppLifecycle = true;
      final AppLifecycleState? state = WidgetsBinding.instance.lifecycleState;
      _appInBackground = state != null && state != AppLifecycleState.resumed;
    }
    _scheduleProcessingPoll(immediately: !wasObserved);
  }

  @override
  void removeListener(VoidCallback listener) {
    super.removeListener(listener);
    if (_closed || hasListeners) return;
    _processingPoll?.cancel();
    _processingPoll = null;
    _stopObservingAppLifecycle();
  }

  /// Returning from the camera, another app, or the lock screen checks the
  /// existing server record. It never submits an image or restarts a run.
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _appInBackground = state != AppLifecycleState.resumed;
    _scheduleProcessingPoll(immediately: !_appInBackground);
  }

  // A known blocker is not a final Queue outcome. Normal server recovery,
  // administrative resume, or delayed publication can still change it, even
  // when this client already holds an earlier blocked summary.
  bool _needsProcessingRefresh(ManifestEntry entry) =>
      entry.tracksProcessing ||
      (entry.specimenId != null &&
          entry.state == UploadState.processingBlocked &&
          entry.specimen?.state != 'cancelled');

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
      var droppedFinished = false;
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
          // Finished in an earlier session: the main Queue owns it now, so
          // it no longer belongs in this device's Intake list.
          if (state == UploadState.inMainQueue) {
            droppedFinished = true;
            continue;
          }
          entries.add(
            ManifestEntry.tracking(
              digest: digest,
              name: 'Photograph ${digest.substring(0, 12)}',
              handle: <String, dynamic>{'upload_id': value['upload_id']},
              specimenId: specimenId,
              state: state,
              reason: state == UploadState.processingBlocked
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
      if (droppedFinished) await persist();
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
        !entry.checking &&
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
      if (!_closed && _retireFinished()) {
        changed();
        await persist();
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
        if (entry.checking) continue;
        final String specimenId = entry.specimenId!;
        final Specimen? summaryAtRead = entry.specimen;
        try {
          final Specimen? specimen;
          final SpecimenRepository source = repository;
          if (source is IntakeProcessingRepository) {
            specimen = await (source as IntakeProcessingRepository)
                .intakeProcessingStatus(scope, specimenId);
          } else {
            final SpecimenPage page = await repository.specimenPage(
              scope,
              filters: <String, String>{'specimen_id': specimenId},
            );
            specimen = page.items
                .where((Specimen item) => item.id == specimenId)
                .firstOrNull;
          }
          if (_closed) return;
          // A read started before a user action cannot replace its newer
          // outcome or re-enable controls while that action is in flight.
          if (entry.checking || !identical(entry.specimen, summaryAtRead)) {
            continue;
          }
          if (specimen == null) {
            entry.specimen = null;
            entry.reason =
                'The server record is not available yet. Checking again shortly.';
          } else if (specimen.id != specimenId) {
            throw const ApiFailure(
              'The requested photo could not be verified.',
            );
          } else {
            _applyProcessingSummary(entry, specimen);
          }
          changedAny = true;
        } on ApiFailure catch (error) {
          if (_closed) return;
          if (entry.checking || !identical(entry.specimen, summaryAtRead)) {
            continue;
          }
          entry.specimen = null;
          entry.reason = error.status == 401 || error.status == 403
              ? 'Sign in again or check collection access to see this photo’s processing status.'
              : 'Processing status is temporarily unavailable. Checking again shortly.';
          changedAny = true;
          if (error.status == 401 || error.status == 403) {
            scheduleNext = false;
            break;
          }
        } catch (_) {
          if (_closed) return;
          if (entry.checking || !identical(entry.specimen, summaryAtRead)) {
            continue;
          }
          entry.specimen = null;
          entry.reason =
              'Processing status is temporarily unavailable. Checking again shortly.';
          changedAny = true;
        }
      }
      if (_retireFinished()) changedAny = true;
      if (changedAny && !_closed) {
        changed();
        await persist();
      }
    } finally {
      _refreshingProcessing = false;
      if (scheduleNext) _scheduleProcessingPoll();
    }
  }

  /// True only when the server offers the appropriate explicit recovery.
  bool canRetryProcessing(ManifestEntry entry) =>
      intakeProcessingRetryAction(entry) != null &&
      (intakeProcessingRetryAction(entry) != 'start_processing' ||
          repository is IntakeProcessingRepository);

  /// Retries a blocked server run without re-uploading the photograph.
  Future<void> retryProcessing(ManifestEntry entry) async {
    if (_closed || busy || entry.checking || !canRetryProcessing(entry)) return;
    final String action = intakeProcessingRetryAction(entry)!;
    busy = true;
    entry.checking = true;
    entry.reason = action == 'start_processing'
        ? 'Asking processing to start for this saved photo.'
        : 'Asking the server to retry processing.';
    changed();
    var checkStatusImmediately = false;
    try {
      final Specimen current = entry.specimen!;
      final SpecimenRepository source = repository;
      final Specimen refreshed;
      if (action == 'start_processing') {
        final Json response = await (source as IntakeProcessingRepository)
            .startIntakeProcessing(
              scope,
              current,
              'intake-start-${entry.digest}-${current.revision}',
            );
        if (_closed) return;
        refreshed = Specimen(response);
        final Object? dispatch = response['dispatch'];
        final Object? dispatchStatus = dispatch is Map
            ? dispatch['status']
            : null;
        switch (dispatchStatus) {
          case 'requested':
            _startDispatchFailures.remove(current.id);
          case 'failed':
            _startDispatchFailures[current.id] =
                'Processing could not be started. Your photo is saved. Retry start when the service is available.';
          case 'unconfigured':
            _startDispatchFailures[current.id] =
                'Processing is not set up for this collection. Your photo is saved; ask your collection administrator to finish setup.';
          default:
            throw const ApiFailure(
              'The processing start could not be confirmed.',
            );
        }
      } else if (source is IntakeProcessingRepository) {
        refreshed = await (source as IntakeProcessingRepository)
            .retryIntakeProcessing(
              scope,
              current,
              'Retry processing from Intake.',
              'intake-retry-${entry.digest}-${current.revision}',
            );
      } else {
        refreshed = await repository.retry(
          scope,
          current,
          'Retry processing from Intake.',
          'intake-retry-${entry.digest}-${current.revision}',
        );
      }
      if (_closed) return;
      if (refreshed.id != entry.specimenId) {
        throw const ApiFailure('The requested photo could not be verified.');
      }
      _applyProcessingSummary(entry, refreshed);
      _retireFinished();
      await persist();
    } on ApiFailure catch (error) {
      if (_closed) return;
      entry.specimen = null;
      entry.reason = error.status == 401 || error.status == 403
          ? 'Your photo is saved. Sign in again or check collection access before retrying.'
          : error.status == 409
          ? 'This photo’s processing status changed. Checking it before offering another retry.'
          : 'The request could not be confirmed. Your photo is saved; checking its status before offering another retry.';
      checkStatusImmediately = error.status != 401 && error.status != 403;
    } catch (_) {
      if (_closed) return;
      entry.specimen = null;
      entry.reason =
          'The request could not be confirmed. Your photo is saved; checking its status before offering another retry.';
      checkStatusImmediately = true;
    } finally {
      if (!_closed) {
        entry.checking = false;
        busy = false;
        changed();
        _scheduleProcessingPoll(immediately: checkStatusImmediately);
      }
    }
  }

  void _applyProcessingSummary(
    ManifestEntry entry,
    Specimen specimen, {
    bool notifyHandoff = true,
  }) {
    // A status read may finish after the user has received a newer Retry
    // acknowledgement. Never restore its old actions or blocked state.
    final int knownRevision = _processingRevisions[specimen.id] ?? 0;
    if (specimen.revision < knownRevision) return;
    _processingRevisions[specimen.id] = specimen.revision;
    final UploadState previous = entry.state;
    entry.specimen = specimen;
    entry.specimenId = specimen.id;
    entry.why = null;
    // A photo in line is picked up by the processing already under way, so an
    // earlier start that did not go through no longer needs attention.
    if (specimen.state != 'pending' || intakeWaitingInLine(specimen)) {
      _startDispatchFailures.remove(specimen.id);
    }
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
      'pending' when intakeWaitingInLine(specimen) => intakeInLineReason,
      'pending' =>
        _startDispatchFailures[specimen.id] ??
            'Waiting for processing to start.',
      'running' => 'Processing is underway.',
      'retry_scheduled' when specimen.data['blocker'] == 'model_rate_limited' =>
        'The processing service is busy. This photograph is waiting for another processing attempt.',
      'retry_scheduled' => 'Processing will retry automatically.',
      'paused' => 'Processing is paused.',
      'cancelled' => 'Processing was cancelled.',
      'processing_blocked' => intakeProcessingBlockerReason(specimen),
      'completed' =>
        'Processing finished, but its main Queue outcome is not available.',
      _ => 'Waiting for the latest processing status.',
    };
  }

  /// Takes every row the server has put in the main Queue out of Intake.
  ///
  /// Owner, 2026-10-12: "once it ends up in the main queue, we dont need that
  /// in the intake right?" Only [UploadState.inMainQueue] leaves. A row that
  /// is blocked, failed, in line, uploading or processing stays where the
  /// operator can act on it. Callers persist afterwards, so the list saved
  /// on this device loses the row too.
  bool _retireFinished() {
    final int before = entries.length;
    entries.removeWhere(
      (ManifestEntry entry) => entry.state == UploadState.inMainQueue,
    );
    final int moved = before - entries.length;
    movedToQueue += moved;
    return moved > 0;
  }

  void _notifyHandoff() {
    if (_handedOff.isEmpty) _handoffWhileDetached = true;
    for (final VoidCallback callback in _handedOff.toList()) {
      callback();
    }
  }

  void _scheduleProcessingPoll({bool immediately = false}) {
    _processingPoll?.cancel();
    _processingPoll = null;
    if (!hasListeners ||
        _appInBackground ||
        _refreshingProcessing ||
        !needsProcessingPoll ||
        processingPollInterval == Duration.zero) {
      return;
    }
    _processingPoll = Timer(
      immediately ? Duration.zero : processingPollInterval,
      () => unawaited(refreshProcessingStatuses()),
    );
  }

  void _stopObservingAppLifecycle() {
    if (!_observingAppLifecycle) return;
    WidgetsBinding.instance.removeObserver(this);
    _observingAppLifecycle = false;
  }

  void close() {
    _closed = true;
    stopping = true;
    _processingPoll?.cancel();
    _processingPoll = null;
    _stopObservingAppLifecycle();
    for (final ManifestEntry entry in entries) {
      entry.file = null;
    }
    entries.clear();
    _completed.clear();
    _handedOff.clear();
    _startDispatchFailures.clear();
    _processingRevisions.clear();
    unawaited(persist());
    dispose();
  }
}

/// What a saved photo waiting behind another in its collection says.
const String intakeInLineReason =
    'Waiting for its turn. Photos are processed one at a time.';

/// True when the server reports this pending run waiting behind the
/// processing already under way in its collection.
bool intakeWaitingInLine(Specimen? specimen) {
  if (specimen?.state != 'pending') return false;
  final Object? progress = specimen!.data['intake_progress'];
  return progress is Map && progress['waiting_in_line'] == true;
}

/// An action is never inferred from a failed upload or a UI status label.
/// Only the scoped server summary may offer recovery of its existing record.
String? intakeProcessingRetryAction(ManifestEntry entry) {
  final Specimen? specimen = entry.specimen;
  if (specimen == null || specimen.disposition != null) return null;
  final Object? offered = specimen.data['available_actions'];
  if (offered is! List) return null;
  final String blocker = textOf(specimen.data['blocker'], '');
  // A start cannot move a photo forward in line; it is never offered there.
  if (intakeWaitingInLine(specimen)) return null;
  if (specimen.state == 'pending' &&
      entry.state == UploadState.processing &&
      blocker.isEmpty &&
      offered.contains('start_processing')) {
    return 'start_processing';
  }
  if (specimen.state != 'processing_blocked' ||
      entry.state != UploadState.processingBlocked ||
      blocker == 'external_outcome_unknown' ||
      blocker == 'sensitive_record_not_processed' ||
      blocker == 'collection_processing_unconfigured' ||
      blockerWords(blocker) != null) {
    return null;
  }
  return offered.contains('retry') ? 'retry' : null;
}

String intakeProcessingBlockerReason(Specimen specimen) {
  final String blocker = textOf(specimen.data['blocker'], '');
  return switch (blocker) {
    'external_outcome_unknown' =>
      'The last processing request may have run, but its result is not confirmed.',
    'sensitive_record_not_processed' =>
      'This photo is marked sensitive, so automatic processing is not allowed.',
    'collection_processing_unconfigured' =>
      'Processing is not set up for this collection.',
    'model_rate_limited' => 'The processing service is busy.',
    _ =>
      blockerWords(blocker)?.sentence ??
          'Processing stopped before this photo could reach the main Queue.',
  };
}

/// Visible next-step guidance, rather than an unexplained Needs attention chip.
String intakeProcessingRecoveryGuidance(ManifestEntry entry) {
  final String? action = intakeProcessingRetryAction(entry);
  if (action == 'start_processing') {
    return 'Your photo is saved. Retry start asks the normal pipeline to begin; it does not upload the photo again.';
  }
  if (action == 'retry') {
    return 'Your photo and completed work are saved. Retry processing continues this record; another processing attempt may incur a charge.';
  }
  final Specimen? specimen = entry.specimen;
  if (specimen == null) {
    return 'Your photo is saved. Retry controls appear after its current status and your access are confirmed.';
  }
  final String blocker = textOf(specimen.data['blocker'], '');
  if (blocker == 'external_outcome_unknown') {
    return 'Your photo and completed work are saved. An administrator must check the previous request before it can be safely repeated.';
  }
  if (specimen.state == 'paused') {
    return 'Your photo is saved. Processing was paused; an authorized operator can resume it from the record’s processing controls.';
  }
  if (specimen.state == 'cancelled') {
    return 'Your photo is saved. Processing was cancelled and will not restart automatically.';
  }
  if (specimen.state == 'completed') {
    return 'Your photo is saved. Checking for the final Queue outcome; do not upload it again.';
  }
  return 'Your photo and completed work are saved. Ask your collection administrator to review this processing hold; uploading again will not fix it.';
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
