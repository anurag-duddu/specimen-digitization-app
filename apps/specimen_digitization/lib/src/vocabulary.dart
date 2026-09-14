/// User-facing vocabulary (UX writing guidelines, section 3).
///
/// Server payloads keep their `snake_case` enum values. Nothing here changes
/// the wire format: this file only decides how those values are spelled on
/// screen, so one concept keeps one word everywhere in the interface.
library;

/// Inline validation for every reason field (guideline 4.10).
///
/// One constant, because seven copies of a message are seven chances to
/// diverge (guideline 6, rule 18).
const String reasonRequired = 'Enter a reason for this decision.';

/// Helper text under every reason field, naming who reads it (guideline 4.5).
const String reasonHelperText =
    'Recorded in the audit history with your name and the time.';

/// Whole server enum values the vocabulary table renames outright.
///
/// The key is the value the API sends; the value is what a reviewer reads.
const Map<String, String> userFacingTerms = <String, String>{
  // Queue names (section 3, "disposition").
  'cleared': 'Cleared',
  'needs_human_review': 'Needs review',
  'human_review_required': 'Needs review',
  'deferred': 'Deferred',
  'processing_blocked': 'Blocked',
  'duplicate': 'Already in collection',
  'dead_letter': 'Stopped after repeated failures',
  // Honest absence. Never rendered as 0, a dash, or an empty slot.
  'unmeasured': 'Not measured',
  'uncalibrated': 'Not calibrated',
  // Validation finding severities. The wire words are `hard` and `warning`,
  // and both were reaching the screen unchanged: a finding row read
  // "A supported collector is required hard", which names an internal enum
  // rather than what the reviewer has to do about it (pass criteria 2.2 and
  // 9.1).
  'hard': 'Blocks clearance',
  'warning': 'Worth checking',
  // Evidence states shown in the correction dialog.
  'supported': 'Supported',
  'unknown': 'Unknown',
  'unreadable': 'Unreadable',
  'ambiguous': 'Ambiguous',
  'not_present': 'Not present',
  'not_applicable': 'Not applicable',
  'unresolved': 'Unresolved',
  // Review actions, named as the command the reviewer is giving.
  'field_correction': 'Correct field',
  'transcription_adjudication': 'Resolve reading',
  'segmentation_correction': 'Correct label regions',
  'authority_resolution': 'Use authority match',
  'reading_metadata': 'Record declaration',
  'classification_correction': 'Correct classification',
  // Environments (section 3, "synthetic").
  'synthetic': 'Test data',
};

/// Single retired words, applied to any value the table above does not name.
///
/// This keeps a value such as `segmentation_correction_pending` readable
/// without listing every combination the server can produce.
const Map<String, String> _retiredWords = <String, String>{
  'adjudicated': 'resolved',
  'adjudication': 'resolution',
  'artifact': 'evidence file',
  'candidate': 'suggested match',
  'candidates': 'suggested matches',
  'digest': 'checksum',
  'disposition': 'queue',
  'lease': 'reservation',
  'literal': 'as written',
  'normalized': 'standardized',
  'observation': 'reading',
  'observations': 'readings',
  'parsed': 'read as',
  'phase': 'step',
  'preflight': 'server check',
  'revision': 'version',
  'segmentation': 'label detection',
  'synthetic': 'test',
  'uncalibrated': 'not calibrated',
  'unmeasured': 'not measured',
};

/// The reviewer-facing spelling of one server value.
///
/// Falls back to the plain-English reading of a `snake_case` value, so a term
/// the table has not met yet still reaches the screen without underscores.
String vocabularyLabel(String value) {
  final String? named = userFacingTerms[value];
  if (named != null) return named;
  return value
      .split('_')
      .map((String word) => _retiredWords[word] ?? word)
      .join(' ');
}

/// The environment name used in the non-production banner (guideline 5.1).
///
/// Sentence case, never shouted: capitals for extended text read as
/// aggressive, and the banner is a statement of fact.
String environmentLabel(String environment) => switch (environment) {
  'synthetic' => 'Test',
  '' => 'Unnamed',
  _ => environment[0].toUpperCase() + environment.substring(1),
};
