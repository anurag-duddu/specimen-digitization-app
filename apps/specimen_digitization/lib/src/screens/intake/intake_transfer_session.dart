/// An intake transfer survives a change of collection route within this app
/// session. Only upload handles and checksums are saved across app restarts;
/// the operator must reselect interrupted image bytes after a restart.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/widgets.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../models.dart';
import '../../theme/motion.dart';
import '../../widgets/upload_item.dart';
import 'intake_status.dart';
import 'manifest_entry.dart';

export 'intake_status.dart' show intakeWaitingInLine;

/// The repository owns the lifetime boundary. A different signed-in user or
/// collection never sees another user's queue, even if the repository is reused.
final Expando<Map<String, IntakeTransferSession>> _sessions =
    Expando<Map<String, IntakeTransferSession>>('intake transfer sessions');

// Poll only until the server confirms hand-off to the pipeline.
const int _processingPollMilliseconds = 5000;
// Owner-approved grace period for a saved photo awaiting dispatch (INT-UX-072).
const int _automaticStartSeconds = 60;

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
    this.automaticStartDelay = const Duration(seconds: _automaticStartSeconds),
  }) : processingPollInterval =
           processingPollInterval ??
           const Duration(milliseconds: _processingPollMilliseconds);

  final SpecimenRepository repository;
  final CollectionScope scope;
  final String userId;

  /// Test seam for a slow local preference write at the sign-out boundary.
  final Future<void> Function()? beforePersist;
  final Duration processingPollInterval;
  final Duration automaticStartDelay;
  final List<ManifestEntry> entries = <ManifestEntry>[];
  final Set<VoidCallback> _completed = <VoidCallback>{};
  final Set<VoidCallback> _handedOff = <VoidCallback>{};
  final Map<ManifestEntry, Timer> _transferRetries = <ManifestEntry, Timer>{};
  final Map<ManifestEntry, int> _transferAttempts = <ManifestEntry, int>{};
  final Map<ManifestEntry, double> _transferProgressAtFailure = {};
  final Set<ManifestEntry> _retryDue = <ManifestEntry>{};
  final Map<ManifestEntry, Timer> _automaticStarts = <ManifestEntry, Timer>{};
  final Set<ManifestEntry> _startDue = <ManifestEntry>{};
  final Map<String, int> _processingRevisions = <String, int>{};
  Timer? _processingPoll;
  bool _refreshingProcessing = false;
  bool _observingAppLifecycle = false;
  bool _appInBackground = false;
  int _foregroundGeneration = 0;
  bool busy = false;
  bool stopping = false;
  bool _closed = false;
  bool _completionWhileDetached = false;
  bool _handoffWhileDetached = false;
  String? restoreError;
  bool signInRequired = false;
  bool _resumeSending = false;
  ManifestEntry? _resumeOnly;

  /// Cumulative sent count, kept under the existing name for screen callers.
  int movedToQueue = 0;
  int duplicateCount = 0;
  int get sentCount => movedToQueue;
  int get departureCount => sentCount + duplicateCount;

  String get summary =>
      intakeBatchSummary(entries, sent: sentCount, duplicates: duplicateCount);

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

  /// Registers for a photo being handed off to Specimens.
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
      !_closed && !signInRequired && entries.any(_needsProcessingRefresh);

  /// Processing checks are useful only while Intake or its camera route is
  /// observing this session. Reattaching a listener restarts a poll that was
  /// paused when the last route went away. Sign-in recovery is explicit.
  @override
  void addListener(VoidCallback listener) {
    final bool wasObserved = hasListeners;
    super.addListener(listener);
    _observeAppLifecycle();
    _scheduleProcessingPoll(immediately: !wasObserved);
    scheduleMicrotask(_resumeAutomaticWork);
  }

  @override
  void removeListener(VoidCallback listener) {
    super.removeListener(listener);
    if (_closed || hasListeners) return;
    _processingPoll?.cancel();
    _processingPoll = null;
    // Transfers still belong to the session while another route is visible.
  }

  void _observeAppLifecycle() {
    if (_observingAppLifecycle || _closed) return;
    WidgetsBinding.instance.addObserver(this);
    _observingAppLifecycle = true;
    final AppLifecycleState? state = WidgetsBinding.instance.lifecycleState;
    _appInBackground = state != null && state != AppLifecycleState.resumed;
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    final bool wasInBackground = _appInBackground;
    _appInBackground = state != AppLifecycleState.resumed;
    if (_appInBackground || wasInBackground) {
      // A pre-background offer cannot authorize work after resuming. Keep the
      // confirmed display, but require a read begun in this foreground period.
      _foregroundGeneration++;
      for (final ManifestEntry entry in entries) {
        entry.startOfferCurrent = false;
      }
      changed();
    }
    if (!_appInBackground && wasInBackground) {
      unawaited(refreshProcessingStatuses());
    }
    _scheduleProcessingPoll(immediately: !_appInBackground);
    if (!_appInBackground) _resumeAutomaticWork();
  }

  bool _needsProcessingRefresh(ManifestEntry entry) => entry.tracksProcessing;

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
          // Finished in an earlier session: Specimens owns it now, so
          // it no longer belongs in this device's Intake list.
          if (state == UploadState.inMainQueue) {
            droppedFinished = true;
            continue;
          }
          entries.add(
            ManifestEntry.tracking(
                digest: digest,
                name: 'Saved photo',
                handle: <String, dynamic>{'upload_id': value['upload_id']},
                specimenId: specimenId,
                state: state,
              )
              ..savedAt = DateTime.tryParse(textOf(value['saved_at'], ''))
              ..automaticStartAttempted =
                  value['automatic_start_attempted'] == true
              ..startDispatchStatus = value['start_dispatch_status'] as String?,
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
      restoreError = intakeRestoreError;
      changed();
    }
  }

  Future<void> persist() async {
    await _persist();
  }

  Future<bool> _persist({ManifestEntry? automaticStart}) async {
    await beforePersist?.call();
    final SharedPreferences prefs = await SharedPreferences.getInstance();
    if (_closed) {
      await prefs.remove(_storageKey);
      return false;
    }
    await prefs.reload();
    if (_closed) {
      await prefs.remove(_storageKey);
      return false;
    }
    List<Json> stored = const <Json>[];
    try {
      stored = objects(jsonDecode(prefs.getString(_storageKey) ?? '[]'));
    } catch (_) {
      // A damaged saved list must not block new uploads. This save replaces it.
    }
    for (final ManifestEntry entry in entries) {
      if (stored.any(
        (row) =>
            row['digest'] == entry.digest &&
            row['upload_id'] == entry.session?['upload_id'] &&
            row['specimen_id'] == entry.specimenId &&
            row['automatic_start_attempted'] == true,
      )) {
        entry.automaticStartAttempted = true;
      }
    }
    if (automaticStart != null) {
      // Re-read shared storage just before saving the decision and dispatching.
      // Also preserve another session's true flag on ordinary saves. This
      // narrows the multi-session race; read/modify/write is NOT atomic. Two
      // sessions that both read false before either writes can still dispatch.
      if (automaticStart.automaticStartAttempted) return false;
      automaticStart.automaticStartAttempted = true;
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
                  if (entry.savedAt != null)
                    'saved_at': entry.savedAt!.toIso8601String(),
                  'automatic_start_attempted': entry.automaticStartAttempted,
                  if (entry.startDispatchStatus != null)
                    'start_dispatch_status': entry.startDispatchStatus,
                },
              },
            )
            .toList(),
      ),
    );
    return true;
  }

  void remove(ManifestEntry entry) {
    if ((entry.removable || entry.dismissible) &&
        !entry.checking &&
        entry.state != UploadState.uploading &&
        (entry.state != UploadState.processing ||
            intakeStatus(entry).action == IntakeAction.dismiss)) {
      entries.remove(entry);
      _forgetEntry(entry);
      changed();
      unawaited(persist());
    }
  }

  /// Stops after the current transfer. Pending retries return to Ready.
  void stop() {
    stopping = true;
    _resumeSending = false;
    _resumeOnly = null;
    for (final ManifestEntry entry in entries) {
      if (entry.state == UploadState.interrupted &&
          entry.file != null &&
          intakeTransientFailure(entry.transferError)) {
        entry.state = UploadState.ready;
        entry.reason = intakeStoppedReason;
        entry.transferError = null;
      }
    }
    for (final Timer timer in _transferRetries.values) {
      timer.cancel();
    }
    _transferRetries.clear();
    _retryDue.clear();
    _transferAttempts.clear();
    _transferProgressAtFailure.clear();
    changed();
  }

  /// Starts a serial pump. Automatic retries do not retry unrelated refusals.
  Future<void> start({ManifestEntry? only}) async {
    if (_closed || busy || signInRequired) return;
    if (only != null && canRetryProcessing(only)) {
      return retryProcessing(only);
    }
    _observeAppLifecycle();
    busy = true;
    stopping = false;
    changed();
    final Set<ManifestEntry> attempted = <ManifestEntry>{};
    try {
      while (!_closed && !stopping && !signInRequired && !_appInBackground) {
        final ManifestEntry? entry =
            only ??
            entries
                .where(
                  (e) =>
                      e.sendable &&
                      e.state == UploadState.ready &&
                      !attempted.contains(e) &&
                      !_transferRetries.containsKey(e),
                )
                .firstOrNull;
        if (entry == null ||
            !entries.contains(entry) ||
            !entry.sendable ||
            attempted.contains(entry)) {
          break;
        }
        attempted.add(entry);
        _transferRetries.remove(entry)?.cancel();
        _retryDue.remove(entry);
        final bool authorized = await _sendOne(entry);
        if (!authorized) {
          _resumeSending = !stopping;
          _resumeOnly = stopping ? null : only;
          break;
        }
        if (only != null) break;
      }
      if (_appInBackground && !stopping) {
        _resumeSending = true;
        _resumeOnly = only;
      }
    } finally {
      if (!_closed && stopping) {
        for (final ManifestEntry entry in entries) {
          if (entry.sendable && entry.state == UploadState.ready) {
            entry.state = UploadState.ready;
            entry.reason = intakeStoppedReason;
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
      _resumeAutomaticWork();
    }
  }

  /// Called by the screen only after the same user's sign-in is restored.
  /// Sign-out/account changes still close the session and release its bytes.
  Future<void> resumeAfterSignIn() async {
    if (_closed) return;
    signInRequired = false;
    final bool resume = _resumeSending;
    final ManifestEntry? only = _resumeOnly;
    _resumeSending = false;
    _resumeOnly = null;
    changed();
    if (resume) await start(only: only);
    await refreshProcessingStatuses();
    _resumeAutomaticWork();
  }

  void _pauseForSignIn() {
    signInRequired = true;
    _processingPoll?.cancel();
    _processingPoll = null;
  }

  Future<bool> _sendOne(ManifestEntry entry) async {
    final IntakeFile? file = entry.file;
    if (file == null) return true;
    try {
      entry.checking = true;
      entry.reason = null;
      entry.why = null;
      entry.transferError = null;
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
      } else {
        entry.state = UploadState.uploading;
        changed();
        await repository.upload(scope, entry.session!, file, (double progress) {
          if (_closed) return;
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
        } else if (completion['specimen_id'] is String &&
            (completion['specimen_id'] as String).isNotEmpty) {
          entry.savedAt ??= DateTime.now();
          _applyProcessingSummary(entry, Specimen(completion));
        } else {
          entry.state = UploadState.accepted;
          entry.reason = intakeSavedReason;
        }
      }
      entry.progress = 1;
      entry.file = null;
      final bool handedOff = entry.state == UploadState.inMainQueue;
      _transferAttempts.remove(entry);
      _transferProgressAtFailure.remove(entry);
      _retireFinished();
      changed();
      await persist();
      if (_closed) return false;
      _scheduleProcessingPoll();
      if (handedOff) _notifyHandoff();
      if (_completed.isEmpty) _completionWhileDetached = true;
      for (final VoidCallback callback in _completed.toList()) {
        if (handedOff && _handedOff.contains(callback)) continue;
        callback();
      }
      return true;
    } catch (error) {
      if (_closed) return false;
      entry.checking = false;
      entry.transferError = error;
      entry.why = error.toString();
      final bool denied =
          error is ApiFailure && (error.status == 401 || error.status == 403);
      if (denied) {
        entry.state = UploadState.ready;
        entry.reason = stopping ? intakeStoppedReason : null;
        entry.why = null;
        _pauseForSignIn();
      } else {
        entry.state = intakeTransientFailure(error)
            ? UploadState.interrupted
            : UploadState.failed;
        entry.reason = intakeStatus(entry).reason;
        if (intakeCodecFailure(error)) {
          entry.why =
              '${error.toString()} '
              'Ask an administrator to check the codec, collection profile and runtime.';
        }
        if (intakeTransientFailure(error)) {
          if (stopping) {
            entry.state = UploadState.ready;
            entry.reason = intakeStoppedReason;
            entry.transferError = null;
          } else {
            // Offset and callback progress describe the same bytes: avoid
            // counting a later offset confirmation as a second advance.
            final Object? offset = entry.session?['offset'];
            final double progress = math.max(
              entry.progress,
              offset is num && file.bytes.isNotEmpty
                  ? offset / file.bytes.length
                  : 0,
            );
            final double previous = _transferProgressAtFailure[entry] ?? 0;
            if (progress > previous) _transferAttempts.remove(entry);
            _transferProgressAtFailure[entry] = math.max(previous, progress);
            _scheduleTransferRetry(entry);
          }
        }
      }
      changed();
      await persist();
      return !denied;
    }
  }

  /// Refreshes saved photos only until the server confirms pipeline hand-off.
  Future<void> refreshProcessingStatuses() async {
    if (_closed ||
        _appInBackground ||
        _refreshingProcessing ||
        !needsProcessingPoll) {
      return;
    }
    _processingPoll?.cancel();
    _processingPoll = null;
    _refreshingProcessing = true;
    final int generation = _foregroundGeneration;
    var changedAny = false;
    final int sentBefore = sentCount;
    try {
      for (final ManifestEntry entry
          in entries.where(_needsProcessingRefresh).toList()) {
        if (_closed || _appInBackground) return;
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
          if (!entries.contains(entry) ||
              generation != _foregroundGeneration ||
              entry.checking ||
              !identical(entry.specimen, summaryAtRead)) {
            continue;
          }
          if (specimen == null) {
            entry.startOfferCurrent = false;
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
          if (!entries.contains(entry) ||
              generation != _foregroundGeneration ||
              entry.checking ||
              !identical(entry.specimen, summaryAtRead)) {
            continue;
          }
          entry.startOfferCurrent = false;
          entry.why = error.toString();
          changedAny = true;
          if (error.status == 401 || error.status == 403) {
            _pauseForSignIn();
            break;
          }
        } catch (_) {
          if (_closed) return;
          if (!entries.contains(entry) ||
              generation != _foregroundGeneration ||
              entry.checking ||
              !identical(entry.specimen, summaryAtRead)) {
            continue;
          }
          entry.startOfferCurrent = false;
          changedAny = true;
        }
      }
      if (_retireFinished()) changedAny = true;
      if (sentCount > sentBefore) _notifyHandoff();
      if (changedAny && !_closed) {
        changed();
        await persist();
      }
    } finally {
      _refreshingProcessing = false;
      if (!_closed &&
          !_appInBackground &&
          generation != _foregroundGeneration) {
        // Resume may have happened while an older read was still in flight.
        unawaited(refreshProcessingStatuses());
      } else {
        _scheduleProcessingPoll();
        _resumeAutomaticWork();
      }
    }
  }

  /// Only a reported failed start can offer manual recovery in Intake.
  bool canRetryProcessing(ManifestEntry entry) =>
      !signInRequired &&
      repository is IntakeProcessingRepository &&
      intakeProcessingRetryAction(entry) != null;

  /// Compatibility API for the row's Start action. Pipeline retries live in Specimens.
  Future<void> retryProcessing(ManifestEntry entry) async {
    if (!canRetryProcessing(entry)) return;
    await _startProcessing(entry);
  }

  Future<void> _startProcessing(
    ManifestEntry entry, {
    bool automatic = false,
  }) async {
    if (_closed ||
        busy ||
        stopping ||
        _appInBackground ||
        signInRequired ||
        entry.checking ||
        !entries.contains(entry) ||
        !entry.startOfferCurrent ||
        !intakeStartOffered(entry.specimen) ||
        repository is! IntakeProcessingRepository) {
      return;
    }
    final Specimen current = entry.specimen!;
    final int generation = _foregroundGeneration;
    busy = true;
    entry.checking = true;
    if (!automatic) entry.automaticStartAttempted = true;
    _automaticStarts.remove(entry)?.cancel();
    _startDue.remove(entry);
    changed();
    try {
      // The consumed attempt survives a guard change during persistence. Do
      // not roll it back: another session may already have acted on the flag.
      // Even if this request never leaves, retain the same conservative rule
      // as a crash/ambiguous dispatch: read status, never auto-start again.
      if (!await _persist(automaticStart: automatic ? entry : null)) return;
      if (_closed ||
          _appInBackground ||
          signInRequired ||
          stopping ||
          generation != _foregroundGeneration ||
          !entries.contains(entry) ||
          !entry.startOfferCurrent ||
          !identical(entry.specimen, current) ||
          !intakeStartOffered(entry.specimen)) {
        return;
      }
      final Json response = await (repository as IntakeProcessingRepository)
          .startIntakeProcessing(
            scope,
            current,
            'intake-start-${entry.digest}-${current.revision}',
          );
      if (_closed) return;
      final Specimen refreshed = Specimen(response);
      if (refreshed.id != entry.specimenId) {
        throw const ApiFailure('The requested photo could not be verified.');
      }
      final Object? dispatch = response['dispatch'];
      final Object? dispatchStatus = dispatch is Map
          ? dispatch['status']
          : null;
      if (!const <String>{
        'requested',
        'failed',
        'unconfigured',
      }.contains(dispatchStatus)) {
        throw const ApiFailure('The processing start could not be confirmed.');
      }
      _applyProcessingSummary(
        entry,
        refreshed,
        startOfferCurrent:
            !_appInBackground && generation == _foregroundGeneration,
      );
      final int sentBefore = sentCount;
      _retireFinished();
      if (sentCount > sentBefore) _notifyHandoff();
      await persist();
    } catch (error) {
      if (_closed) return;
      // An ambiguous response is not a server-reported failed dispatch.
      // Read back before offering any action; never repeat the automatic start.
      entry.specimen = null;
      entry.startOfferCurrent = false;
      entry.startDispatchStatus = null;
      entry.reason = null;
      entry.why = error.toString();
      if (error is ApiFailure && (error.status == 401 || error.status == 403)) {
        _pauseForSignIn();
      }
    } finally {
      if (!_closed) {
        entry.checking = false;
        busy = false;
        changed();
        _scheduleProcessingPoll();
        _resumeAutomaticWork();
      }
    }
  }

  void _applyProcessingSummary(
    ManifestEntry entry,
    Specimen specimen, {
    bool startOfferCurrent = true,
  }) {
    final int knownRevision = _processingRevisions[specimen.id] ?? 0;
    if (specimen.revision < knownRevision) return;
    _processingRevisions[specimen.id] = specimen.revision;
    entry.specimen = specimen;
    entry.startOfferCurrent = startOfferCurrent && !_appInBackground;
    entry.specimenId = specimen.id;
    entry.why = null;
    final Object? dispatch = specimen.data['dispatch'];
    if (dispatch is Map && dispatch['status'] is String) {
      entry.startDispatchStatus = dispatch['status'] as String;
    }
    if (specimen.data['upload_state'] == 'duplicate') {
      entry.state = UploadState.duplicate;
    } else if (intakeHandedOff(specimen)) {
      entry.state = UploadState.inMainQueue;
      entry.startDispatchStatus = null;
    } else {
      entry.state = specimen.data['status'] == 'processing_blocked'
          ? UploadState.processingBlocked
          : UploadState.processing;
    }
    entry.reason = intakeStatus(entry).reason;
    if (entry.tracksProcessing && specimen.data['status'] == 'pending') {
      _scheduleAutomaticStart(entry);
    }
  }

  bool _retireFinished() {
    final List<ManifestEntry> finished = entries
        .where(
          (entry) =>
              entry.state == UploadState.inMainQueue ||
              entry.state == UploadState.duplicate,
        )
        .toList();
    for (final ManifestEntry entry in finished) {
      if (entry.state == UploadState.duplicate) {
        duplicateCount++;
      } else {
        movedToQueue++;
      }
      entries.remove(entry);
      _forgetEntry(entry);
    }
    return finished.isNotEmpty;
  }

  void _forgetEntry(ManifestEntry entry) {
    _processingRevisions.remove(entry.specimenId);
    _transferRetries.remove(entry)?.cancel();
    _transferAttempts.remove(entry);
    _transferProgressAtFailure.remove(entry);
    _retryDue.remove(entry);
    _automaticStarts.remove(entry)?.cancel();
    _startDue.remove(entry);
  }

  void _scheduleTransferRetry(ManifestEntry entry) {
    _observeAppLifecycle();
    final int attempt = _transferAttempts.update(
      entry,
      (n) => n + 1,
      ifAbsent: () => 1,
    );
    final int seconds = switch (attempt) {
      1 => 5,
      2 => 15,
      _ => 60,
    };
    _transferRetries.remove(entry)?.cancel();
    _transferRetries[entry] = Timer(Duration(seconds: seconds), () {
      _transferRetries.remove(entry);
      _retryDue.add(entry);
      _resumeAutomaticWork();
    });
  }

  void _scheduleAutomaticStart(ManifestEntry entry) {
    if (repository is! IntakeProcessingRepository ||
        entry.automaticStartAttempted ||
        _automaticStarts.containsKey(entry) ||
        _startDue.contains(entry)) {
      return;
    }
    _observeAppLifecycle();
    final Duration remaining = entry.savedAt == null
        ? automaticStartDelay
        : entry.savedAt!.add(automaticStartDelay).difference(DateTime.now());
    entry.savedAt ??= DateTime.now();
    _automaticStarts[entry] = Timer(
      remaining.isNegative ? Duration.zero : remaining,
      () {
        _automaticStarts.remove(entry);
        _startDue.add(entry);
        _resumeAutomaticWork();
      },
    );
  }

  void _resumeAutomaticWork() {
    if (_closed ||
        busy ||
        stopping ||
        signInRequired ||
        _appInBackground ||
        _refreshingProcessing) {
      return;
    }
    if (_resumeSending) {
      final ManifestEntry? only = _resumeOnly;
      _resumeSending = false;
      _resumeOnly = null;
      unawaited(start(only: only));
      return;
    }
    for (final ManifestEntry entry in _retryDue.toList()) {
      if (entries.contains(entry) && entry.sendable) {
        unawaited(start(only: entry));
        return;
      }
      _retryDue.remove(entry);
    }
    for (final ManifestEntry entry in _startDue.toList()) {
      if (entries.contains(entry) &&
          !entry.automaticStartAttempted &&
          !entry.checking &&
          entry.startOfferCurrent &&
          intakeStartOffered(entry.specimen) &&
          entry.startDispatchStatus != 'unconfigured' &&
          repository is IntakeProcessingRepository) {
        unawaited(_startProcessing(entry, automatic: true));
        return;
      }
    }
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
    for (final Timer timer in [
      ..._transferRetries.values,
      ..._automaticStarts.values,
    ]) {
      timer.cancel();
    }
    _transferRetries.clear();
    _transferAttempts.clear();
    _transferProgressAtFailure.clear();
    _retryDue.clear();
    _automaticStarts.clear();
    _startDue.clear();
    _processingRevisions.clear();
    unawaited(persist());
    dispose();
  }
}

/// Compatibility copy for callers that still draw the old stage widget.
const String intakeInLineReason = 'Sent to Specimens.';

String? intakeProcessingRetryAction(ManifestEntry entry) =>
    intakeStatus(entry).action == IntakeAction.start
    ? 'start_processing'
    : null;

String intakeProcessingBlockerReason(Specimen specimen) =>
    intakeStatus(
      ManifestEntry(
        digest: '',
        name: '',
        state: UploadState.processingBlocked,
        specimenId: specimen.id,
        specimen: specimen,
      ),
    ).reason ??
    '';

String intakeProcessingRecoveryGuidance(ManifestEntry entry) =>
    intakeStatus(entry).reason ?? '';

UploadState _restoredTrackingState(Object? value) => switch (value) {
  'inMainQueue' => UploadState.inMainQueue,
  'processingBlocked' => UploadState.processingBlocked,
  _ => UploadState.processing,
};

String intakeCompletionReason(Json completion) =>
    intakeStatus(
      ManifestEntry(
        digest: '',
        name: '',
        state: UploadState.accepted,
        specimenId: completion['specimen_id'] as String?,
        specimen: Specimen(completion),
      ),
    ).reason ??
    '';
