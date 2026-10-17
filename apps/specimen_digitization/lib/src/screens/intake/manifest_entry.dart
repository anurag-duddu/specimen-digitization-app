/// A photo awaiting hand-off, with the server summary and local transfer state.
/// Intake's display words and actions are defined in intake_status.dart.
library;

import '../../capture_quality.dart';
import '../../models.dart';
import '../../widgets/upload_item.dart';
import 'intake_status.dart';

/// One photo on its way into a collection.
class ManifestEntry {
  ManifestEntry({
    required this.digest,
    required this.name,
    this.file,
    this.session,
    this.state = UploadState.interrupted,
    this.reason,
    this.why,
    this.progress = 0,
    this.quality,
    this.specimenId,
    this.specimen,
    this.transferError,
    this.refusal,
  });

  /// A restored upload handle, read back from local storage after a restart.
  /// The bytes are gone; only the server handle and the checksum survive.
  ManifestEntry.restored({required this.digest, required Json handle})
    : name = 'Unfinished photo',
      file = null,
      session = handle,
      state = UploadState.interrupted,
      reason = restoredReason,
      why = null,
      progress = 0,
      quality = null,
      specimenId = null,
      specimen = null;

  /// A server-held photograph restored for processing tracking after restart.
  ManifestEntry.tracking({
    required this.digest,
    required this.name,
    required Json handle,
    required this.specimenId,
    this.state = UploadState.processing,
    this.reason,
  }) : file = null,
       session = handle,
       why = null,
       progress = 1,
       quality = null,
       specimen = null;

  /// A file this client refused before any byte reached the server.
  ///
  /// A rejection is a row with a reason, not a banner that the next rejection
  /// overwrites (heuristics audit, H1.6 and H9.4).
  ManifestEntry.skipped({
    required this.digest,
    required this.name,
    String? why,
    this.refusal,
  }) : file = null,
       session = null,
       state = UploadState.skipped,
       reason = why,
       progress = 0,
       quality = null,
       specimenId = null,
       specimen = null,
       why = null;

  /// What a restored handle can say for itself.
  static const String restoredReason = intakeUnfinishedReason;

  /// The checksum, or a synthetic key for a row that never got one.
  final String digest;

  /// What the row is called when there are no bytes to name it from.
  final String name;

  /// The bytes and metadata, once this client has read them.
  IntakeFile? file;

  /// The server's upload handle, once one exists.
  Json? session;

  /// Where the photo has got to. Shared with the Sources upload widget.
  UploadState state;

  /// One plain sentence saying why the state is what it is.
  String? reason;

  /// The expandable half of [reason], when the reason carries a caveat.
  String? why;

  /// Transfer fraction, 0 to 1. Monotonic: a resumed upload that reports a
  /// lower server offset never runs the ring backwards (motion, row 65).
  double progress;

  /// The local, uncalibrated measurement, when this device could decode the
  /// image at all.
  CaptureQuality? quality;

  /// The record created by upload completion, once the server returns it.
  String? specimenId;

  /// The most recent summary used for processing progress and retry.
  Specimen? specimen;

  /// The last transfer error, for classification and the details sheet.
  Object? transferError;

  /// Local admission failure. Older callers can keep their existing row key.
  IntakeRefusal? refusal;

  /// A server-reported start dispatch result, retained across status reads.
  String? startDispatchStatus;

  /// Persisted before dispatch so restoring a photo cannot start it twice.
  bool automaticStartAttempted = false;

  /// Completion time anchors the one automatic start even after restoration.
  DateTime? savedAt;

  /// The server's decode check, once the operator has asked for one.
  Json? preflight;

  /// Why the server check did not run.
  String? preflightError;

  /// True while a server round trip for this row is in flight.
  bool checking = false;

  /// The row name, preferring the file's own.
  String get label => file?.name ?? name;

  /// The state to draw. A round trip in progress shows as Checking without
  /// destroying the state it will return to.
  UploadState get displayState => checking ? UploadState.checking : state;

  /// True once the server holds these pixels, by either route.
  bool get settled =>
      state == UploadState.accepted ||
      state == UploadState.processing ||
      state == UploadState.inMainQueue ||
      state == UploadState.processingBlocked ||
      state == UploadState.duplicate;

  /// True while Intake should refresh the server's processing summary.
  bool get tracksProcessing =>
      specimenId != null &&
      !intakeHandedOff(specimen) &&
      (state == UploadState.processing ||
          state == UploadState.processingBlocked);

  /// A finished Intake row can be removed without affecting the server.
  bool get dismissible =>
      state == UploadState.accepted ||
      state == UploadState.inMainQueue ||
      state == UploadState.processingBlocked ||
      state == UploadState.duplicate ||
      intakeStatus(this).action == IntakeAction.dismiss;

  /// True for a row a batch should try to send.
  bool get sendable =>
      file != null &&
      !settled &&
      !checking &&
      state != UploadState.uploading &&
      state != UploadState.skipped;

  /// True while the row may still be taken out of the batch.
  bool get removable => !settled && !checking && state != UploadState.uploading;

  /// Records a transfer fraction, never below the highest already seen.
  void observeProgress(double fraction) {
    final double bounded = fraction.isNaN ? 0 : fraction.clamp(0.0, 1.0);
    if (bounded > progress) progress = bounded;
  }
}

/// True when every photo in this list is held by the server.
bool batchComplete(Iterable<ManifestEntry> entries) {
  final List<ManifestEntry> all = entries.toList(growable: false);
  return all.isNotEmpty && all.every((ManifestEntry e) => e.settled);
}

/// Compatibility entry points for the existing list and camera callers.
String batchCompleteLine(Iterable<ManifestEntry> entries) =>
    intakeBatchSummary(entries);

String movedToQueueLine(int count) => intakeDepartureLine(count);

String ingestionQueueLine(Iterable<ManifestEntry> entries) =>
    intakeBatchSummary(entries);

String batchProgressLine(Iterable<ManifestEntry> entries) =>
    intakeBatchSummary(entries);
