/// A run's blocker, in words a person can act on (UX writing guidelines 4.9).
///
/// The server blocks a run with a machine code, and after its automatic
/// retries run out the code is `retry_budget_exhausted:<cause>`. A code is
/// never primary text: every screen that mentions a blocker says what stopped
/// the run and what to do about it. The code stays in the technical details
/// that already carry it (the review details drawer), where an administrator
/// can read it.
///
/// A blocker this client has no words for is described generically. Showing
/// the code, or its words with the underscores taken out, would hand a
/// reviewer an internal term to guess at.
library;

import 'vocabulary.dart';

/// What happened and what to do about it, as two sentences.
class BlockerWords {
  const BlockerWords(this.what, this.next);

  /// What stopped the run, without its closing full stop. A list sets it
  /// above [next]; a panel reads both as one passage.
  final String what;

  /// What the reader can do now.
  final String next;

  /// Both, as one passage of two sentences.
  String get sentence => '$what. $next';
}

const String _retryLater = 'Retry later, or ask an administrator.';

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

/// A blocker this client has no words for.
const BlockerWords unnamedBlockerWords = BlockerWords(
  'Processing needs an operator check before it can continue',
  'Ask an administrator to review it.',
);

/// The short name for a blocker this client has no words for.
const String unnamedBlockerLabel = 'Needs an operator check';

/// The short name for a stop at a cost limit.
const String costLimitLabel = 'Cost limit reached';

/// Whether [blocker] is a stop at a cost limit.
///
/// A run whose retries ran out is judged by its cause, never by the word
/// "budget" in `retry_budget_exhausted:`: an unreachable source is no cost
/// limit.
bool isCostLimit(String blocker) {
  final String cause = retriesStoppedCause(blocker) ?? blocker;
  return cause.contains('budget') || cause.contains('cost');
}

/// The sentences for a run whose automatic retries ran out, or null when
/// [blocker] is not such a blocker. The cause picks the sentence; a cause this
/// client has no words for gets the general one.
BlockerWords? retriesStoppedWords(String blocker) {
  final String? cause = retriesStoppedCause(blocker);
  if (cause == null) return null;
  return _retriesStoppedBy[cause] ?? _retriesStopped;
}

/// Whether this client has words of its own for [blocker].
bool blockerIsNamed(String blocker) =>
    userFacingTerms.containsKey(blocker) ||
    retriesStoppedCause(blocker) != null ||
    isCostLimit(blocker);

/// The short name for [blocker], for a line, a list row or a menu entry.
///
/// Never the code: a blocker without a name of its own reads
/// [unnamedBlockerLabel].
String blockerLabel(String blocker) {
  if (userFacingTerms.containsKey(blocker)) return vocabularyLabel(blocker);
  final String? cause = retriesStoppedCause(blocker);
  if (cause != null && userFacingTerms.containsKey(cause)) {
    return vocabularyLabel(blocker);
  }
  if (isCostLimit(blocker)) return costLimitLabel;
  if (cause != null) return retriesStoppedLabel;
  return unnamedBlockerLabel;
}
