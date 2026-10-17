/// Intake's words and actions end at the hand-off to the pipeline.
library;

import 'dart:async';

import '../../models.dart';
import '../../widgets/upload_item.dart';
import 'manifest_entry.dart';

enum IntakeTone { none, neutral, processing, operational, error }

enum IntakeAction {
  menu(null),
  dismiss('Dismiss'),
  start('Start'),
  retryNow('Retry now'),
  chooseFile('Choose file'),
  retry('Retry'),
  remove('Remove');

  const IntakeAction(this.label);
  final String? label;
}

enum IntakeRefusal { empty, tooLarge, format, resolution, unreadable }

class IntakeStatus {
  const IntakeStatus(this.status, this.tone, {this.reason, this.action});

  final String status;
  final String? reason;
  final IntakeAction? action;
  final IntakeTone tone;

  bool get leavesIntake => status == 'Sent' || status == 'Duplicate';
}

const String intakeSavedReason = 'Saved. Start not confirmed.';
const String intakeStoppedReason = 'Stopped. Send to continue.';
const String intakeRetryingReason = 'Connection lost. Retrying.';
const String intakeStartFailedReason = 'Processing did not start. Photo saved.';
const String intakeUnconfiguredReason =
    'Not set up for processing. Ask an admin.';
const String intakeHeldReason = 'Sensitive. Saved, not read.';
const String intakeCodecReason = 'Format not supported yet. Photo kept.';
const String intakeRejectedReason = 'Photo could not be used. Retake it.';
const String intakeSensitivityReason =
    'Saved earlier with another setting. Photo kept.';
const String intakeUnfinishedReason = 'Choose this photo again.';
const String intakeSignedOutReason = 'Signed out. Sign in to keep sending.';
const String intakeRestoreError = 'Earlier photos could not be restored.';

/// Uses the status field, never a guessed stage, elapsed time or run identity.
bool intakeHandedOff(Specimen? summary) {
  if (summary == null) return false;
  if (summary.disposition?.isNotEmpty ?? false) return true;
  return switch (summary.data['status']) {
    'running' ||
    'retry_scheduled' ||
    'paused' ||
    'cancelled' ||
    'completed' => true,
    'pending' => intakeWaitingInLine(summary),
    'processing_blocked' => !const <String>{
      'sensitive_record_not_processed',
      'collection_processing_unconfigured',
      'program_allowance_unavailable',
    }.contains(summary.data['blocker']),
    _ => false,
  };
}

bool intakeWaitingInLine(Specimen? summary) {
  if (summary?.data['status'] != 'pending') return false;
  final Object? progress = summary!.data['intake_progress'];
  return progress is Map && progress['waiting_in_line'] == true;
}

bool intakeStartOffered(Specimen? summary) {
  if (summary?.data['status'] != 'pending' || intakeHandedOff(summary)) {
    return false;
  }
  final Object? actions = summary?.data['available_actions'];
  return actions is List && actions.contains('start_processing');
}

bool intakeTransientFailure(Object? error) {
  if (error is TimeoutException) return true;
  if (error is! ApiFailure) return false;
  if (error.status == 401 ||
      error.status == 403 ||
      intakeCodecFailure(error) ||
      error.code == 'intake_sensitivity_mismatch') {
    return false;
  }
  return error.code == 'network' ||
      error.code == 'timeout' ||
      error.status == 408 ||
      error.status == 429 ||
      (error.status != null && error.status! >= 500 && error.status! < 600);
}

bool intakeCodecFailure(Object? error) =>
    error is ApiFailure &&
    (error.code.startsWith('image_codec_') ||
        error.message.startsWith('image_codec_'));

/// The sole row mapping. Raw errors remain on the entry for a details sheet.
IntakeStatus intakeStatus(ManifestEntry entry, {Specimen? summary}) {
  summary ??= entry.specimen;
  if (entry.state == UploadState.duplicate ||
      summary?.data['upload_state'] == 'duplicate') {
    return const IntakeStatus('Duplicate', IntakeTone.none);
  }
  final bool saved =
      entry.specimenId?.isNotEmpty == true || summary?.id.isNotEmpty == true;
  if (entry.state == UploadState.inMainQueue ||
      (saved && intakeHandedOff(summary))) {
    return const IntakeStatus('Sent', IntakeTone.none);
  }
  if (entry.checking && !entry.settled) {
    return const IntakeStatus('Sending', IntakeTone.processing);
  }
  switch (entry.state) {
    case UploadState.ready:
      return IntakeStatus(
        'Ready',
        IntakeTone.neutral,
        reason: entry.reason == intakeStoppedReason
            ? intakeStoppedReason
            : null,
        action: IntakeAction.menu,
      );
    case UploadState.checking:
    case UploadState.uploading:
      return const IntakeStatus('Sending', IntakeTone.processing);
    case UploadState.accepted:
    case UploadState.processing:
    case UploadState.processingBlocked:
      if (!saved) {
        return const IntakeStatus(
          'Saved',
          IntakeTone.neutral,
          reason: intakeSavedReason,
          action: IntakeAction.dismiss,
        );
      }
      if (summary?.data['status'] == 'processing_blocked') {
        if (summary?.data['blocker'] == 'sensitive_record_not_processed') {
          return const IntakeStatus(
            'Held',
            IntakeTone.neutral,
            reason: intakeHeldReason,
            action: IntakeAction.dismiss,
          );
        }
        return const IntakeStatus(
          'Not started',
          IntakeTone.operational,
          reason: intakeUnconfiguredReason,
          action: IntakeAction.dismiss,
        );
      }
      final Object? dispatch = summary?.data['dispatch'];
      final Object? dispatchStatus = dispatch is Map
          ? dispatch['status']
          : entry.startDispatchStatus;
      if (summary?.data['status'] == 'pending') {
        if (dispatchStatus == 'unconfigured') {
          return const IntakeStatus(
            'Not started',
            IntakeTone.operational,
            reason: intakeUnconfiguredReason,
            action: IntakeAction.dismiss,
          );
        }
        if (dispatchStatus == 'failed') {
          return IntakeStatus(
            'Not started',
            IntakeTone.operational,
            reason: intakeStartFailedReason,
            action: intakeStartOffered(summary) ? IntakeAction.start : null,
          );
        }
      }
      return const IntakeStatus('Starting', IntakeTone.processing);
    case UploadState.interrupted:
    case UploadState.failed:
      final Object? error = entry.transferError;
      if (error is ApiFailure && (error.status == 401 || error.status == 403)) {
        return const IntakeStatus(
          'Ready',
          IntakeTone.neutral,
          action: IntakeAction.menu,
        );
      }
      if (error is ApiFailure && error.code == 'intake_sensitivity_mismatch') {
        return const IntakeStatus(
          'Not sent',
          IntakeTone.operational,
          reason: intakeSensitivityReason,
          action: IntakeAction.dismiss,
        );
      }
      if (entry.state == UploadState.interrupted && entry.file == null) {
        return const IntakeStatus(
          'Unfinished',
          IntakeTone.neutral,
          reason: intakeUnfinishedReason,
          action: IntakeAction.chooseFile,
        );
      }
      if (intakeTransientFailure(error)) {
        return const IntakeStatus(
          'Retrying',
          IntakeTone.operational,
          reason: intakeRetryingReason,
          action: IntakeAction.retryNow,
        );
      }
      if (intakeCodecFailure(error)) {
        return const IntakeStatus(
          'Not sent',
          IntakeTone.operational,
          reason: intakeCodecReason,
          action: IntakeAction.retry,
        );
      }
      return const IntakeStatus(
        'Not sent',
        IntakeTone.error,
        reason: intakeRejectedReason,
        action: IntakeAction.remove,
      );
    case UploadState.skipped:
      return IntakeStatus(
        'Not added',
        IntakeTone.error,
        reason: intakeRefusalReason(entry),
        action: IntakeAction.remove,
      );
    case UploadState.inMainQueue:
    case UploadState.duplicate:
      throw StateError('Departed rows were mapped above.');
  }
}

String intakeRefusalReason(ManifestEntry entry) {
  // Existing admission callers use these local keys. The typed field also lets
  // callers migrate without parsing or copying primary text.
  final IntakeRefusal refusal =
      entry.refusal ??
      switch (entry.digest.split(':').first) {
        'size' =>
          entry.digest.endsWith(':0')
              ? IntakeRefusal.empty
              : IntakeRefusal.tooLarge,
        'format' => IntakeRefusal.format,
        'resolution' => IntakeRefusal.resolution,
        _ => IntakeRefusal.unreadable,
      };
  return switch (refusal) {
    IntakeRefusal.empty => 'Empty file. Choose another.',
    IntakeRefusal.tooLarge => 'Over 25 MB. Choose a smaller photo.',
    IntakeRefusal.format => 'Use JPEG, PNG, HEIC, TIFF or DNG.',
    IntakeRefusal.resolution => 'Over 40 megapixels. Choose a smaller photo.',
    IntakeRefusal.unreadable => 'Could not read this photo. Choose it again.',
  };
}

/// Counts departed rows too, when the session supplies its cumulative totals.
String intakeBatchSummary(
  Iterable<ManifestEntry> entries, {
  int sent = 0,
  int duplicates = 0,
}) {
  var toFix = 0;
  var held = 0;
  var ready = 0;
  var sending = 0;
  for (final ManifestEntry entry in entries) {
    switch (intakeStatus(entry).status) {
      case 'Held':
        held++;
      case 'Ready':
        ready++;
      case 'Sending' || 'Starting' || 'Retrying':
        sending++;
      case 'Sent':
        sent++;
      case 'Duplicate':
        duplicates++;
      default:
        toFix++;
    }
  }
  final String line = <String>[
    if (toFix > 0) '$toFix to fix',
    if (held > 0) '$held held',
    if (ready > 0) '$ready ready',
    if (sending > 0) '$sending sending',
    if (sent > 0) '$sent sent',
    if (duplicates > 0) '$duplicates duplicate',
  ].join(' · ');
  return line.isEmpty ? 'No photos' : line;
}

/// Screens coalesce their count delta once per frame before speaking it.
String intakeDepartureLine(int sent, {int duplicates = 0}) => <String>[
  if (sent == 1) '1 photo sent' else if (sent > 1) '$sent photos sent',
  if (duplicates > 0) '$duplicates duplicate',
].join(' · ');
