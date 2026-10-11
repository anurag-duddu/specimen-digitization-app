// The words for a run's blocker (lib/src/blocker_words.dart).
//
// Every string a person can read for a blocker is checked here against the
// mechanical rules of the UX writing checklist (design/02-ux-writing-
// guidelines.md section 6: items 1, 2, 3, 4, 5 and 6), because a blocker line
// is the one a reviewer reads when work has stopped. A blocker is read by its
// exact code, from a table, and the last group reads the backend's own source
// to prove the table holds every limit code the server can set.

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:specimen_digitization/src/blocker_words.dart';
import 'package:specimen_digitization/src/vocabulary.dart';

/// The blocker names the vocabulary table holds for blockers the client
/// already explained elsewhere.
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

/// The limits the server stops a run at, by family. Each has its own name and
/// sentences.
const Map<String, List<String>> limitFamilies = <String, List<String>>{
  'the run limits': <String>[
    'step_budget_exhausted',
    'external_call_budget_exhausted',
    'token_budget_exhausted',
    'active_time_budget_exhausted',
  ],
  'the evidence check time limit': <String>[
    'evidence_harness_blocked:elapsed_budget_exhausted',
  ],
  'the limits on money': <String>[
    'cost_budget_exhausted',
    'program_allowance_exhausted',
    'pilot_launch_budget_exhausted',
    'pilot_cohort_reading_budget_insufficient',
  ],
  'the limits that could not be checked': <String>[
    'approved_cost_budget_unavailable',
    'research_budget_state_unavailable',
    'program_allowance_ledger_unavailable',
    'program_allowance_unavailable',
  ],
  'the pilot cost settings': <String>[
    'pilot_run_budget_not_approved',
    'pilot_stage_cost_reservations_mismatch',
    'pilot_cohort_reader_cost_unknown',
  ],
};

/// The limits on money: the only blockers whose name or sentence may call
/// something a cost limit.
const Set<String> moneyLimits = <String>{
  'cost_budget_exhausted',
  'program_allowance_exhausted',
  'pilot_launch_budget_exhausted',
  'pilot_cohort_reading_budget_insufficient',
};

const List<String> causes = <String>[
  'lookup_operational_failure',
  'field_research_timeout',
  'field_research_model_error',
  'some_future_cause',
  '',
];

final List<String> limitCodes = <String>[
  for (final List<String> family in limitFamilies.values) ...family,
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
      for (final String cause in causes) {
        expect(
          blockerWords('retry_budget_exhausted:$cause'),
          isNotNull,
          reason: cause,
        );
      }
      expect(
        blockerWords('retry_budget_exhausted:cost_budget_exhausted')!.what,
        'Processing stopped after repeated attempts',
      );
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
          'Retries stopped, source not reachable',
        );
        expect(
          vocabularyLabel('retry_budget_exhausted:something_new'),
          retriesStoppedLabel,
        );
      },
    );

    test('keeps a retry stop apart from the cause it stopped on', () {
      for (final String cause in causes.take(3)) {
        expect(
          blockerLabel('retry_budget_exhausted:$cause'),
          isNot(blockerLabel(cause)),
          reason: cause,
        );
      }
    });

    test('says what to do, for every cause', () {
      for (final String cause in causes) {
        final BlockerWords? words = blockerWords(
          'retry_budget_exhausted:$cause',
        );
        expect(words, isNotNull, reason: cause);
        expect(words!.next, 'Retry later, or ask an administrator.');
        expect(words.what, isNot(endsWith('.')), reason: cause);
        expectSentenceRules(words.sentence);
      }
    });
  });

  group('a limit is read by its exact code', () {
    for (final MapEntry<String, List<String>> family in limitFamilies.entries) {
      test('${family.key} have their own names and sentences', () {
        for (final String code in family.value) {
          final BlockerWords? words = blockerWords(code);
          expect(words, isNotNull, reason: code);
          expect(blockerIsNamed(code), isTrue, reason: code);
          expect(blockerLabel(code), vocabularyLabel(code), reason: code);
          expect(blockerLabel(code), isNot(unnamedBlockerLabel), reason: code);
          expectLabelRules(blockerLabel(code));
          expectSentenceRules(words!.sentence);
          expect(words.what, isNot(endsWith('.')), reason: code);
          if (words.why != null) expectSentenceRules(words.why!);
        }
      });
    }

    test('no two blockers share a name', () {
      final List<String> codes = <String>[
        ...limitCodes,
        ...namedBlockers,
        for (final String cause in causes.take(3))
          'retry_budget_exhausted:$cause',
      ];
      final List<String> names = <String>[
        for (final String code in codes) blockerLabel(code),
      ];
      expect(names.toSet(), hasLength(names.length), reason: '$names');
    });

    test('only a limit on money says "cost limit" or "spending allowance"', () {
      for (final String code in limitCodes) {
        final String said =
            '${blockerLabel(code)} ${blockerWords(code)!.sentence}'
                .toLowerCase();
        final bool callsItMoney =
            said.contains('cost limit') ||
            said.contains('spending allowance reached');
        expect(
          callsItMoney,
          moneyLimits.contains(code),
          reason: '$code: $said',
        );
      }
      for (final String code in <String>[
        'step_budget_exhausted',
        'external_call_budget_exhausted',
        'token_budget_exhausted',
        'active_time_budget_exhausted',
        'evidence_harness_blocked:elapsed_budget_exhausted',
      ]) {
        final String said =
            '${blockerLabel(code)} ${blockerWords(code)!.sentence}'
                .toLowerCase();
        expect(said, isNot(contains('cost')), reason: code);
        expect(said, isNot(contains('spending')), reason: code);
      }
    });

    test('a caveat label fits the 40 character maximum', () {
      // The panel keeps `cost_budget_exhausted`'s 79 character instruction as
      // it had it before this change; every other caveat label is short.
      for (final String code in limitCodes) {
        final BlockerWords words = blockerWords(code)!;
        if (words.why == null || code == 'cost_budget_exhausted') continue;
        expect(words.next.length, lessThanOrEqualTo(40), reason: code);
      }
    });

    test('the program allowance is a spending limit', () {
      expect(
        blockerLabel('program_allowance_exhausted'),
        'Spending allowance reached',
      );
      expect(
        blockerWords('program_allowance_exhausted')!.what,
        contains('spending allowance'),
      );
    });

    test('a word inside a code decides nothing', () {
      for (final String code in <String>[
        'some_future_budget_exhausted',
        'some_future_cost_check',
        'a_new_allowance_problem',
        'time_budget_exhausted',
      ]) {
        expect(blockerWords(code), isNull, reason: code);
        expect(blockerIsNamed(code), isFalse, reason: code);
        expect(blockerLabel(code), unnamedBlockerLabel, reason: code);
      }
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
        expect(blockerWords(code), isNull, reason: code);
      }
      expectLabelRules(unnamedBlockerLabel);
      expectLabelRules(retriesStoppedLabel);
      expectSentenceRules(unnamedBlockerWords.sentence);
    });
  });

  group('the backend', () {
    String source(String path) {
      final File file = File('../../src/specimen_digitization/$path');
      expect(file.existsSync(), isTrue, reason: path);
      return file.readAsStringSync();
    }

    /// Every quoted code in [text] that [pattern] names (group 1) and that
    /// speaks of a budget, a cost or an allowance.
    ///
    /// What this sees, and what it does not: only a code written as a string
    /// literal in the three forms below, in six files, and only one with
    /// "budget", "cost" or "allowance" in it. It does not see a code built or
    /// passed on indirectly (`issue = issue or "<code>"`,
    /// `OperationalBlock(ledger["reading_time_blocker"])`), nor a pilot launch
    /// code about capacity or time (`pilot_cohort_reading_capacity_insufficient`,
    /// `pilot_cohort_reading_time_insufficient`, `pilot_complete_*_time_insufficient`,
    /// `pilot_cohort_execution_time_exhausted`). Those are not in the table
    /// and read "Needs an operator check".
    Set<String> limitCodesIn(String text, RegExp pattern) => <String>{
      for (final RegExpMatch match in pattern.allMatches(text))
        if (RegExp(r'budget|cost|allowance').hasMatch(match.group(1)!))
          match.group(1)!,
    };

    final RegExp raised = RegExp(r'OperationalBlock\(\s*"([a-z_]+)"');
    final RegExp assigned = RegExp(
      r'\b(?:issue|retained_cost_issue)\s*=\s*"([a-z_]+)"',
    );
    final RegExp constant = RegExp(
      r'^(?:EXHAUSTED|UNAVAILABLE)\s*=\s*"([a-z_]+)"',
      multiLine: true,
    );
    final RegExp refused = RegExp(r'LaneConflict\(\s*"([a-z_]+)"');

    test('every limit code the run can carry has its own words', () {
      final Set<String> sent = <String>{
        ...limitCodesIn(source('application/workflow.py'), raised),
        ...limitCodesIn(source('application/workflow.py'), assigned),
        ...limitCodesIn(source('research_harness/workflow_bridge.py'), raised),
        ...limitCodesIn(source('application/worker_launch.py'), raised),
        ...limitCodesIn(source('application/worker_launch.py'), assigned),
        ...limitCodesIn(source('application/lane_allowance.py'), constant),
        ...limitCodesIn(source('application/lane.py'), refused),
      };
      // The evidence check blocks a run as `evidence_harness_blocked:<reason>`,
      // and its time limit is the one reason that is a limit.
      expect(
        source('application/evidence_harness.py'),
        contains('"elapsed_budget_exhausted"'),
      );
      expect(
        source('application/evidence_runtime.py'),
        contains('"evidence_harness_blocked:"'),
      );
      sent.add('evidence_harness_blocked:elapsed_budget_exhausted');

      // A guard against a pattern that silently matched nothing.
      expect(sent.length, greaterThanOrEqualTo(15), reason: '$sent');
      for (final String code in sent) {
        expect(blockerWords(code), isNotNull, reason: '$code has no words');
        expect(blockerIsNamed(code), isTrue, reason: '$code has no name');
      }
      expect(sent.difference(limitCodes.toSet()), isEmpty);
    });
  });
}
