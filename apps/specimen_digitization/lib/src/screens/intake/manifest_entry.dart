/// One row of the intake manifest, and the two sentences the manifest header
/// computes from a batch of them.
///
/// The state and the reason are separate fields (heuristics audit, H4.5). The
/// state is one of the eight `UploadState` values the shared `UploadItem`
/// draws; the reason is one plain sentence attached to the file it is about
/// (H9.4), never a progress string and never a screen-level banner.
library;

import '../../capture_quality.dart';
import '../../models.dart';
import '../../widgets/upload_item.dart';

/// One file on its way into a collection.
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
  });

  /// A restored upload handle, read back from local storage after a restart.
  /// The bytes are gone; only the server handle and the checksum survive.
  ManifestEntry.restored({required this.digest, required Json handle})
    : name = 'Interrupted upload ${digest.substring(0, 12)}',
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
    this.reason = 'Checking processing status.',
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
  ManifestEntry.skipped({required this.digest, required this.name, String? why})
    : file = null,
      session = null,
      state = UploadState.skipped,
      reason = why,
      progress = 0,
      quality = null,
      specimenId = null,
      specimen = null,
      why = null;

  /// What a restored handle can say for itself.
  static const String restoredReason =
      'Select this file again to resume it from the server offset.';

  /// The checksum, or a synthetic key for a row that never got one.
  final String digest;

  /// What the row is called when there are no bytes to name it from.
  final String name;

  /// The bytes and metadata, once this client has read them.
  IntakeFile? file;

  /// The server's upload handle, once one exists.
  Json? session;

  /// Where the file has got to. One of the eight upload states.
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
      specimenId != null && state == UploadState.processing;

  /// A finished Intake row can be removed without affecting the server.
  bool get dismissible =>
      state == UploadState.accepted ||
      state == UploadState.inMainQueue ||
      state == UploadState.processingBlocked ||
      state == UploadState.duplicate;

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

/// The manifest header's aggregate line (screen blueprints, section 5;
/// heuristics audit, H1.5 and pass criterion 1.5).
///
/// Reads "8 of 12 uploaded, 1 skipped". Counts that are zero are left out,
/// because a zero is noise in a line an operator reads at a glance.
/// True when every file in the batch reached a state the server holds.
///
/// The summary line and the one per batch haptic both key off this, so the
/// buzz and the sentence can never disagree (motion catalog, row 67).
bool batchComplete(Iterable<ManifestEntry> entries) {
  final List<ManifestEntry> all = entries.toList(growable: false);
  return all.isNotEmpty && all.every((ManifestEntry e) => e.settled);
}

/// The sentence that appears once a whole batch has landed.
String batchCompleteLine(Iterable<ManifestEntry> entries) {
  final int count = entries.length;
  return count == 1
      ? '1 photograph is in the Intake queue.'
      : '$count photographs are in the Intake queue.';
}

/// What a screen reader hears when finished photos leave Intake for the main
/// Queue. Spoken once, politely; the rows themselves leave without a sound.
String movedToQueueLine(int count) => count == 1
    ? 'Photo moved to the main Queue.'
    : '$count photos moved to the main Queue.';

/// A compact account of the new Intake queue. This deliberately stops before
/// the existing post-processing Queue's three outcomes.
String ingestionQueueLine(Iterable<ManifestEntry> entries) {
  final List<ManifestEntry> all = entries.toList(growable: false);
  if (all.isEmpty) return 'No photographs in the Intake queue';
  int count(UploadState state) =>
      all.where((ManifestEntry entry) => entry.state == state).length;
  final int ready = count(UploadState.ready);
  final int sending =
      count(UploadState.checking) + count(UploadState.uploading);
  final int uploaded = count(UploadState.accepted);
  final int processing = count(UploadState.processing);
  final int handedOff = count(UploadState.inMainQueue);
  final int attention =
      count(UploadState.processingBlocked) +
      count(UploadState.failed) +
      count(UploadState.interrupted);
  final int other = count(UploadState.duplicate) + count(UploadState.skipped);
  final List<String> parts = <String>[
    if (ready > 0) '$ready ready',
    if (sending > 0) '$sending uploading',
    if (uploaded > 0) '$uploaded uploaded',
    if (processing > 0) '$processing processing',
    if (handedOff > 0) '$handedOff in main Queue',
    if (attention > 0) '$attention need attention',
    if (other > 0) '$other not sent',
  ];
  final String noun = all.length == 1 ? 'photograph' : 'photographs';
  return '${all.length} $noun · ${parts.join(', ')}';
}

String batchProgressLine(Iterable<ManifestEntry> entries) {
  final List<ManifestEntry> all = entries.toList(growable: false);
  if (all.isEmpty) return 'No files selected yet';
  int count(UploadState state) =>
      all.where((ManifestEntry e) => e.state == state).length;
  final StringBuffer line = StringBuffer(
    '${count(UploadState.accepted)} of ${all.length} uploaded',
  );
  final int skipped = count(UploadState.skipped);
  final int duplicate = count(UploadState.duplicate);
  final int failed = count(UploadState.failed);
  final int interrupted = count(UploadState.interrupted);
  final int processing = count(UploadState.processing);
  final int handedOff = count(UploadState.inMainQueue);
  final int processingBlocked = count(UploadState.processingBlocked);
  if (skipped > 0) line.write(', $skipped skipped');
  if (duplicate > 0) line.write(', $duplicate already in collection');
  if (interrupted > 0) line.write(', $interrupted interrupted');
  if (failed > 0) line.write(', $failed failed');
  if (processing > 0) line.write(', $processing processing');
  if (handedOff > 0) line.write(', $handedOff in main Queue');
  if (processingBlocked > 0) line.write(', $processingBlocked need attention');
  return line.toString();
}
