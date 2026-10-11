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
  'history_restored_review_required': 'Restored version needs review',
  'review_restore_version': 'Restored version',
  'review_reset_initial': 'Reset to initial version',
  'initial_record': 'Initial record',
  'field_correction': 'Correct field',
  'transcription_adjudication': 'Resolve reading',
  'segmentation_correction': 'Correct label regions',
  'authority_resolution': 'Use authority match',
  'reading_metadata': 'Record declaration',
  'classification_correction': 'Correct classification',
  // Environments (section 3, "synthetic").
  'synthetic': 'Test data',
  // Field research reasons and blockers. A reason with a subject
  // (`<code>:<field>`) keeps it after a colon in the reason sheet.
  'field_research_model_error': 'No usable model answer',
  'field_research_timeout': 'Field research ran out of time',
  'field_research_price_unavailable': 'Field research model has no price',
  'field_research_unconfigured': 'Field research not set up',
  'raw_reading_grounding_unproved': 'Not traced to the label readings',
  'independent_observations_missing': 'Two independent readings needed',
  'raw_provenance_missing': 'Reading evidence file missing',
  'identified_by_irn_identity_unproved': 'Identifier not confirmed in EMu',
  'preserved_human_decision': 'Earlier review decision to confirm',
  // Run blockers: the server's reason a run stopped. Each name says what is
  // wrong, in the words the processing panel and the review list already use
  // for it. A blocker that is not named here is shown as the generic line
  // `blockerLabel` returns, never as its code.
  'external_outcome_unknown': 'Last request may have run',
  'pilot_evidence_review_required': 'Pilot evidence review needed',
  'collection_processing_unconfigured': 'Processing awaits collection setup',
  'sensitive_record_not_processed': 'Sensitive record held from processing',
  'institutional_policy_unapproved': 'Collection policy not approved',
  'institutional_policy_not_approved': 'Collection policy approval missing',
  'mandatory_semantics_unconfirmed': 'Required field rules not confirmed',
  'field_semantics_unconfirmed': 'Field rules not confirmed',
  'worker_readiness_not_verified': 'Processing not confirmed ready',
  'lookup_operational_failure': 'Approved source not reachable',
  'storage_unavailable': 'Specimen storage unavailable',
  'pilot_dispatch_reconciliation_required': 'Previous attempt needs a check',
  'evidence_integrity_failure': 'Saved evidence needs a check',
  // A run stopped by a limit or by the settings that carry one. Each code is
  // named for the limit it is: a step count, a request count, model units,
  // time and money are different limits, and only a money limit says "cost".
  // The sentences for each are in `blocker_words.dart`.
  'step_budget_exhausted': 'Step limit reached',
  'external_call_budget_exhausted': 'External request limit reached',
  'token_budget_exhausted': 'Model unit limit reached',
  'active_time_budget_exhausted': 'Active time limit reached',
  'cost_budget_exhausted': 'Cost limit reached',
  'approved_cost_budget_unavailable': 'Cost settings not available',
  'research_budget_state_unavailable': 'Saved cost totals not readable',
  'program_allowance_exhausted': 'Spending allowance reached',
  'program_allowance_ledger_unavailable': 'Allowance totals not readable',
  'program_allowance_unavailable': 'Spending allowance not set up',
  'evidence_harness_blocked:elapsed_budget_exhausted':
      'Evidence check time limit reached',
  'pilot_launch_budget_exhausted': 'Pilot cost limit reached',
  'pilot_cohort_reading_budget_insufficient': 'Reading cost limit too low',
  'pilot_run_budget_not_approved': 'Run limits do not fit the pilot',
  'pilot_stage_cost_reservations_mismatch': 'Stage cost settings differ',
  'pilot_cohort_reader_cost_unknown': 'Reading cost not set',
  // A run whose automatic retries ran out, by the cause that stopped it. The
  // name differs from the cause's own, so a menu that lists both keeps them
  // apart. A cause not named here reads `retriesStoppedLabel`.
  'retry_budget_exhausted:lookup_operational_failure':
      'Retries stopped, source not reachable',
  'retry_budget_exhausted:field_research_timeout':
      'Retries stopped, ran out of time',
  'retry_budget_exhausted:field_research_model_error':
      'Retries stopped, no usable model answer',
};

/// What a run's blocker starts with once its automatic retries have run out.
///
/// The cause that stopped the run follows the colon:
/// `retry_budget_exhausted:lookup_operational_failure`. The word "budget" in
/// the prefix says the retries ran out. It never says a cost limit stopped the
/// run, so a reader of this code looks at the cause.
const String retriesStoppedPrefix = 'retry_budget_exhausted:';

/// The cause behind a run whose automatic retries ran out, or null when
/// [value] is not such a blocker.
String? retriesStoppedCause(String value) =>
    value.startsWith(retriesStoppedPrefix)
    ? value.substring(retriesStoppedPrefix.length)
    : null;

/// The name for a run whose retries ran out for a cause this client has no
/// name for.
const String retriesStoppedLabel = 'Automatic retries stopped';

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
  // A run whose retries ran out for a cause the table does not name reads as
  // one general line, not as `retry budget exhausted:` and that cause's code.
  if (retriesStoppedCause(value) != null) return retriesStoppedLabel;
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
