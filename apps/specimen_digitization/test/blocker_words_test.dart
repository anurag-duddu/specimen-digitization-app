// The words for a run's blocker (lib/src/blocker_words.dart).
//
// Every string a person can read for a blocker is checked here against the
// mechanical rules of the UX writing checklist (design/02-ux-writing-
// guidelines.md section 6: items 1, 2, 3, 4, 5 and 6), because a blocker line
// is the one a reviewer reads when work has stopped.

import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/blocker_words.dart';
import 'package:specimen_digitization/src/vocabulary.dart';

/// The blocker names this change added to the vocabulary table.
const List<String> namedBlockers = <String>[
  'external_outcome_unknown',
  'pilot_evidence_review_required',
  'collection_processing_unconfigured',
  'sensitive_record_not_processed',
  'institutional_policy_unapproved',
  'institutional_policy_not_approved',
  'mandatory_semantics_unconfirmed',
  'field_semantics_unconfirmed',
  'worker_readiness_not_verified',
  'lookup_operational_failure',
  'storage_unavailable',
  'pilot_dispatch_reconciliation_required',
  'evidence_integrity_failure',
];

const List<String> causes = <String>[
  'lookup_operational_failure',
  'field_research_timeout',
  'field_research_model_error',
  'some_future_cause',
  '',
];

/// The dashes the guidelines ban (item 1), written as code points so this
/// file carries neither.
final String emDash = String.fromCharCode(0x2014);
final String enDash = String.fromCharCode(0x2013);

/// Banned wherever a person reads (guideline 6, item 6).
final RegExp banned = RegExp(
  r'\b(invalid|illegal|failed to|an error occurred|something went wrong|oops|'
  r'please wait|simply|just|easily|unfortunately|sorry|we|our|delightful|'
  r'seamless)\b',
  caseSensitive: false,
);

/// A name for a line, a list row or a menu entry.
void expectLabelRules(String label) {
  expect(label, isNotEmpty);
  expect(label.length, lessThanOrEqualTo(40), reason: label);
  expect(label, matches(RegExp(r'^[A-Z]')), reason: label);
  expect(label, isNot(endsWith('.')), reason: label);
  expect(label, isNot(contains('_')), reason: label);
  expect(label, isNot(contains(':')), reason: label);
  expect(label, isNot(contains(';')), reason: label);
  expect(label, isNot(contains(emDash)), reason: label);
  expect(label, isNot(contains(enDash)), reason: label);
  expect(banned.hasMatch(label), isFalse, reason: label);
}

/// A sentence a person reads.
void expectSentenceRules(String sentence) {
  expect(sentence, isNot(contains('_')), reason: sentence);
  expect(sentence, isNot(contains(';')), reason: sentence);
  expect(sentence, isNot(contains(emDash)), reason: sentence);
  expect(sentence, isNot(contains(enDash)), reason: sentence);
  expect(banned.hasMatch(sentence), isFalse, reason: sentence);
  for (final String one in sentence.split(RegExp(r'(?<=\.)\s+'))) {
    expect(one, matches(RegExp(r'^[A-Z].*\.$')), reason: one);
    expect(one.split(' ').length, lessThanOrEqualTo(25), reason: one);
  }
}

void main() {
  group('retry_budget_exhausted', () {
    test('is read by its cause, never by the word "budget"', () {
      expect(
        isCostLimit('retry_budget_exhausted:lookup_operational_failure'),
        isFalse,
      );
      expect(
        isCostLimit('retry_budget_exhausted:field_research_timeout'),
        isFalse,
      );
      expect(isCostLimit('retry_budget_exhausted:adapter_failure'), isFalse);
      expect(isCostLimit('retry_budget_exhausted:cost_limit'), isTrue);
      expect(isCostLimit('cost_budget_exhausted'), isTrue);
      expect(isCostLimit(''), isFalse);
    });

    test(
      'names the cause, and a generic line for a cause it does not know',
      () {
        for (final String cause in causes) {
          final String code = 'retry_budget_exhausted:$cause';
          expect(blockerIsNamed(code), isTrue, reason: code);
          expect(
            vocabularyLabel(code),
            blockerLabel(code),
            reason: 'the table and the blocker lines must agree on $code',
          );
          expectLabelRules(blockerLabel(code));
        }
        expect(
          vocabularyLabel('retry_budget_exhausted:lookup_operational_failure'),
          'Approved source not reachable',
        );
        expect(
          vocabularyLabel('retry_budget_exhausted:something_new'),
          retriesStoppedLabel,
        );
      },
    );

    test('says what to do, for every cause', () {
      for (final String cause in causes) {
        final BlockerWords? words = retriesStoppedWords(
          'retry_budget_exhausted:$cause',
        );
        expect(words, isNotNull, reason: cause);
        expect(words!.next, 'Retry later, or ask an administrator.');
        expect(words.what, isNot(endsWith('.')), reason: cause);
        expectSentenceRules(words.sentence);
      }
    });

    test('is not a retry stop when it is not the prefix', () {
      expect(retriesStoppedWords('cost_budget_exhausted'), isNull);
      expect(retriesStoppedWords('lookup_operational_failure'), isNull);
      expect(retriesStoppedWords(''), isNull);
    });
  });

  group('every other blocker', () {
    test('has a name that passes the writing rules', () {
      for (final String code in namedBlockers) {
        expect(blockerIsNamed(code), isTrue, reason: code);
        expectLabelRules(blockerLabel(code));
        expect(blockerLabel(code), vocabularyLabel(code), reason: code);
      }
    });

    test('a code the client has no words for reads generically', () {
      for (final String code in <String>[
        'some_future_blocker',
        'provider_circuit:open',
        'evidence_harness_blocked:3d50f205-7885-5be3-9c15-6d31ac324947',
        'adapter_failure',
      ]) {
        expect(blockerIsNamed(code), isFalse, reason: code);
        expect(blockerLabel(code), unnamedBlockerLabel, reason: code);
        expect(blockerLabel(code), isNot(contains(code)), reason: code);
      }
      expectLabelRules(unnamedBlockerLabel);
      expectLabelRules(costLimitLabel);
      expectLabelRules(retriesStoppedLabel);
      expectSentenceRules(unnamedBlockerWords.sentence);
    });

    test('a cost limit reads as one', () {
      expect(blockerLabel('cost_budget_exhausted'), costLimitLabel);
      expect(blockerLabel('retry_budget_exhausted:cost_limit'), costLimitLabel);
    });
  });
}
