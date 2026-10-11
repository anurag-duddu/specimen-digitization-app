/// A run's blocker, in words a person can act on (UX writing guidelines 4.9).
///
/// The server blocks a run with a machine code. After its automatic retries
/// run out the code is `retry_budget_exhausted:<cause>`. A code is never
/// primary text: every screen that mentions a blocker says what stopped the
/// run and what to do about it. The code stays in the technical details that
/// already carry it (the workbench's review details drawer and the history's
/// retained version data), where an administrator can read it.
///
/// Every blocker is read by its exact code, from a table. Nothing is judged by
/// a word inside the code: a step limit, a request limit, a time limit and a
/// cost limit all say "budget" on the wire and are different limits, so each
/// has its own name and sentence, and only a limit on money says "cost".
///
/// A blocker this client has no words for is described generically. Showing
/// the code, or its words with the underscores taken out, would hand a
/// reviewer an internal term to guess at.
library;

import 'vocabulary.dart';

/// What happened and what to do about it, as two sentences.
class BlockerWords {
  const BlockerWords(this.what, this.next, {this.why});

  /// What stopped the run, without its closing full stop. A list sets it
  /// above [next]; a panel reads both as one passage.
  final String what;

  /// What the reader can do now.
  final String next;

  /// A caveat the panel keeps behind a "Why" control, for a stop whose
  /// meaning depends on a cost that may not be recorded.
  final String? why;

  /// Both, as one passage of two sentences.
  String get sentence => '$what. $next';
}

const String _retryLater = 'Retry later, or ask an administrator.';
const String _reviewLimit = 'An administrator must review the approved limit.';
const String _reviewSettings =
    'An administrator must review the cost settings.';
const String _checkTotals =
    'An operator must check them before processing continues.';
const String _costNotRecorded =
    'Where a cost is not recorded, it is unknown, not zero.';

/// What stopped a run's retries, by cause. The first is the wording the
/// processing panel has used since an unreachable source was told apart from a
/// cost limit.
const Map<String, BlockerWords> _retriesStoppedBy = <String, BlockerWords>{
  'lookup_operational_failure': BlockerWords(
    'An approved source could not be reached after repeated attempts',
    _retryLater,
  ),
  'field_research_timeout': BlockerWords(
    'Field research ran out of time after repeated attempts',
    _retryLater,
  ),
  'field_research_model_error': BlockerWords(
    'The model gave no usable answer after repeated attempts',
    _retryLater,
  ),
};

/// A run whose retries ran out for a cause this client has no words for.
const BlockerWords _retriesStopped = BlockerWords(
  'Processing stopped after repeated attempts',
  _retryLater,
);

/// The sentences for a run stopped by a limit, or by the settings that carry
/// one, by the exact code the server sets. The names are in the vocabulary
/// table.
const Map<String, BlockerWords> _limitWords = <String, BlockerWords>{
  // The run's own limits (the execution policy of its profile).
  'step_budget_exhausted': BlockerWords(
    'The run reached its limit on processing steps',
    _reviewLimit,
  ),
  'external_call_budget_exhausted': BlockerWords(
    'The run reached its limit on external requests',
    _reviewLimit,
  ),
  'token_budget_exhausted': BlockerWords(
    'The run reached its limit on model units',
    _reviewLimit,
  ),
  'active_time_budget_exhausted': BlockerWords(
    'The run reached its limit on active processing time',
    _reviewLimit,
  ),
  // Limits on money.
  'cost_budget_exhausted': BlockerWords(
    'Processing stopped at a cost limit',
    'An administrator must review the approved limit or the provider '
        'configuration.',
    why: _costNotRecorded,
  ),
  'program_allowance_exhausted': BlockerWords(
    "Processing stopped at the program's spending allowance",
    'An administrator must review it.',
    why: _costNotRecorded,
  ),
  // A limit that could not be checked, because its settings or totals were
  // not available.
  'approved_cost_budget_unavailable': BlockerWords(
    'The approved cost settings for this run are not available',
    _reviewSettings,
  ),
  'research_budget_state_unavailable': BlockerWords(
    'The saved cost totals for this record could not be read',
    _checkTotals,
  ),
  'program_allowance_ledger_unavailable': BlockerWords(
    "The program's spending totals could not be read",
    _checkTotals,
  ),
  'program_allowance_unavailable': BlockerWords(
    "The program's spending allowance is not set up for this collection",
    'An administrator must review the allowance settings.',
  ),
  // The evidence check's own time limit.
  'evidence_harness_blocked:elapsed_budget_exhausted': BlockerWords(
    'An evidence check reached its time limit',
    _reviewLimit,
  ),
  // The pilot launch's limits and cost settings.
  'pilot_launch_budget_exhausted': BlockerWords(
    "The pilot's cost limit would be crossed",
    _reviewLimit,
  ),
  'pilot_cohort_reading_budget_insufficient': BlockerWords(
    'The cost limit does not cover the planned readings',
    _reviewLimit,
  ),
  'pilot_run_budget_not_approved': BlockerWords(
    "The run's approved limits do not fit the pilot launch",
    'An administrator must review them.',
  ),
  'pilot_stage_cost_reservations_mismatch': BlockerWords(
    "The run's stage cost settings differ from the pilot launch",
    'An administrator must review them.',
  ),
  'pilot_cohort_reader_cost_unknown': BlockerWords(
    'The cost of a reading step is not set',
    _reviewSettings,
  ),
};

/// A blocker this client has no words for.
const BlockerWords unnamedBlockerWords = BlockerWords(
  'Processing needs an operator check before it can continue',
  'Ask an administrator to review it.',
);

/// The short name for a blocker this client has no words for.
const String unnamedBlockerLabel = 'Needs an operator check';

/// The sentences for [blocker], or null when this client has none for it.
///
/// A run whose automatic retries ran out reads by its cause, and a cause this
/// client has no words for gets the general sentence. Any other blocker reads
/// by its exact code.
BlockerWords? blockerWords(String blocker) {
  final String? cause = retriesStoppedCause(blocker);
  if (cause != null) return _retriesStoppedBy[cause] ?? _retriesStopped;
  return _limitWords[blocker];
}

/// Whether this client has a name of its own for [blocker].
bool blockerIsNamed(String blocker) =>
    userFacingTerms.containsKey(blocker) ||
    retriesStoppedCause(blocker) != null;

/// The short name for [blocker], for a line, a list row or a menu entry.
///
/// Never the code: a blocker without a name of its own reads
/// [unnamedBlockerLabel].
String blockerLabel(String blocker) =>
    blockerIsNamed(blocker) ? vocabularyLabel(blocker) : unnamedBlockerLabel;
