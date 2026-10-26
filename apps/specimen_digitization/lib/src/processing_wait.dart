/// Waiting states whose saved blocker does not ask an operator to intervene.
library;

import 'models.dart';
import 'review_context.dart' show objectOf;

enum ProcessingWait {
  externalResult,
  retryScheduled,
  retryDue;

  String get summary => switch (this) {
    externalResult => 'Waiting for external result',
    retryScheduled => 'Retry scheduled',
    retryDue => 'Waiting for automatic retry',
  };

  String get detail => switch (this) {
    externalResult =>
      'This request is still reserved for processing. '
          'Its result has not been recorded yet.',
    retryScheduled =>
      'Processing will retry automatically at the scheduled time.',
    retryDue =>
      'The scheduled retry is due. Waiting for the processing service '
          'to pick it up.',
  };
}

// Workflow.step persists an external intent while retaining one of these
// stages. A real failure changes the stage to processing_blocked, even when
// it retains the same blocker and a still-active lease.
const Set<String> _externalStages = <String>{
  'classify',
  'segment',
  'transcribe',
  'first_pass',
  'parse',
  // The workflow dispatches FIELD_RESEARCH from plan without changing stage
  // before saving its external intent.
  'plan',
  'lookup',
  'authority',
  'field_research',
};

// Known retryable causes emitted by the model runtime, provider adapters and
// workflow recovery. Unknown causes, limits and credential failures retain
// their recovery guidance even if an inconsistent record says retry_scheduled.
const Set<String> _retryCauses = <String>{
  'reader_worker_failed',
  'reader_worker_process_exit',
  'reader_deadline_exceeded',
  'reader_cleanup_incomplete',
  'reader_unrecognized_answer',
  'first_pass_worker_process_exit',
  'first_pass_deadline_exceeded',
  'extract_worker_process_exit',
  'extract_deadline_exceeded',
  'reading_result_lost',
  'first_pass_result_lost',
  'extraction_result_lost',
  'model_rate_limited',
  'model_provider_error',
  'model_malformed_response',
  'provider_deadline_outcome_unknown',
  'sam3_busy',
  'sam3_timeout',
  'sam3_unavailable',
  'taxonomy_rate_limited',
  'taxonomy_timeout',
  'taxonomy_provider_error',
  'authority_rate_limited',
  'authority_timeout',
  'authority_provider_error',
  'lookup_operational_failure',
  'field_research_model_error',
  'field_research_timeout',
};

/// A presentation hint, never authority to retry or to clear a specimen.
///
/// An active lease alone proves no running request: require the server's
/// matching stage and status too. Missing or contradictory evidence keeps
/// the existing blocker presentation. A saved intent may also survive a
/// worker crash, so the copy describes a reservation, not proven execution.
ProcessingWait? processingWaitFor(Specimen specimen, {DateTime? now}) {
  final Json data = specimen.data;
  final Json run = objectOf(data['run']);
  final Object? stage = run['stage'];
  final Object? blocker = run['blocker'];
  final Object? status = data['status'];
  if (run['dead_letter'] != false ||
      specimen.disposition != null ||
      run['disposition'] != null ||
      (data['stage'] != null && data['stage'] != stage) ||
      (data['blocker'] != null && data['blocker'] != blocker) ||
      (data['operational_state'] != null &&
          data['operational_state'] != status)) {
    return null;
  }
  final DateTime at = now ?? DateTime.now();
  final DateTime? lease = DateTime.tryParse(textOf(run['lease_until'], ''));
  // A due retry clears next_retry_at before dispatch but keeps its stage
  // until the result is saved (Workflow.step). Its new intent is also waiting
  // for a result, not waiting for a scheduled or manual retry.
  final bool externalStage =
      (status == 'running' && _externalStages.contains(stage)) ||
      (status == 'retry_scheduled' && stage == 'retry_scheduled');
  if (externalStage &&
      blocker == 'external_outcome_unknown' &&
      run['next_retry_at'] == null &&
      lease != null &&
      lease.isAfter(at)) {
    return ProcessingWait.externalResult;
  }
  final DateTime? retry = DateTime.tryParse(textOf(run['next_retry_at'], ''));
  if (status == 'retry_scheduled' &&
      stage == 'retry_scheduled' &&
      _retryCauses.contains(blocker) &&
      run['lease_until'] == null &&
      retry != null) {
    return retry.isAfter(at)
        ? ProcessingWait.retryScheduled
        : ProcessingWait.retryDue;
  }
  return null;
}
